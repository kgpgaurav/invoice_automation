from decimal import Decimal

import httpx
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.extraction_client import OpenAIExtractor
from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger, FinancialAssessment, PurchaseOrder
from app.models import QueueItem, Run
from app.worker import Worker, WorkerPolicy
from app.workflow import WorkflowProcessor
from app.workflow_models import ReviewAction
from scripts.extraction_fixtures import expected_invoice
from tests.financial_fixtures import POLICY, masters
from tests.test_workflow_reviews import ambiguous, selection
from tests.workflow_helpers import execute, intake, invoice_pdf, mock_processor


def test_e1_partial_invoices_cannot_consume_more_than_remaining(workflow_db):
    engine = workflow_db
    _, po_id, _ = masters(engine, cap="100000", rate="0", qty="100")
    for number, qty in (("PART-1", "70"), ("PART-2", "35")):
        expected = expected_invoice(number)
        net = str(Decimal(qty) * 1000)
        expected.update(subtotal_net=net, tax_total="0", total_gross=net)
        line = expected["line_items"][0]
        line.update(quantity=qty, tax_rate="0", net_amount=net, tax_amount="0", gross_amount=net)
        pdf = invoice_pdf(expected)
        run_id = intake(engine, pdf)
        processor, _ = mock_processor(engine, pdf, expected)
        execute(engine, processor)
    with Session(engine) as s:
        assert s.get(Run, run_id).decision == "NEEDS_REVIEW"
        assert s.get(PurchaseOrder, po_id).committed_gross == 70000
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        held = s.get(FinancialAssessment, (run_id, 0))
        assert held.code == "PO_CAP_EXCEEDED" and "5000.00" in held.reason


def test_financial_event_failure_rolls_back_then_replays_checkpoint(workflow_db):
    engine = workflow_db
    _, po_id, _ = masters(engine)
    expected = expected_invoice()
    pdf = invoice_pdf(expected)
    run_id = intake(engine, pdf)
    processor, calls = mock_processor(engine, pdf, expected)
    with engine.begin() as c:
        c.execute(
            text(
                "ALTER TABLE run_events ADD CONSTRAINT injected CHECK (type <> 'DECISION_RECORDED')"
            )
        )
    with pytest.raises(IntegrityError):
        execute(engine, processor)
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
        assert s.get(PurchaseOrder, po_id).committed_gross == 0
        assert s.get(Run, run_id).decision is None
    with engine.begin() as c:
        c.execute(text("ALTER TABLE run_events DROP CONSTRAINT injected"))
        c.execute(text("UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second'"))
    worker = Worker(engine, processor, WorkerPolicy(retry_seconds=0))
    assert worker.run_once() is False
    execute(engine, processor)
    with Session(engine) as s:
        assert s.get(Run, run_id).decision == "APPROVED"
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
    assert len(calls) == 1


def test_technical_openai_errors_exhaust_without_financial_verdict(workflow_db):
    engine = workflow_db
    masters(engine)
    expected = expected_invoice()
    run_id = intake(engine, invoice_pdf(expected))
    client = httpx.Client(
        base_url="https://api.openai.com/v1",
        transport=httpx.MockTransport(lambda _: httpx.Response(503)),
    )
    extractor = OpenAIExtractor("mock", "test-model", client=client, sleep=lambda _: None)
    processor = WorkflowProcessor(engine, extractor, POLICY.version, source_mode="MOCK_OPENAI")
    worker = Worker(engine, processor, WorkerPolicy(retry_seconds=0))
    for _ in range(3):
        assert worker.run_once()
    with Session(engine) as s:
        run = s.get(Run, run_id)
        assert run.job_state == "FAILED" and run.decision is None
        assert s.scalar(select(func.count()).select_from(APIUsage)) == 2
        assert s.scalar(select(QueueItem.status)) == "FAILED"


def test_review_action_and_resume_enqueue_roll_back_together(workflow_db):
    from app.reviews import respond

    engine = workflow_db
    _, po_id, review_id, _, _ = ambiguous(engine)
    with engine.begin() as c:
        c.execute(
            text("ALTER TABLE run_events ADD CONSTRAINT injected CHECK (type <> 'REVIEW_RESOLVED')")
        )
    with pytest.raises(IntegrityError):
        respond(engine, review_id, selection(po_id), "select", "configured-reviewer")
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(ReviewAction)) == 0
        assert (
            s.scalar(
                select(func.count()).select_from(QueueItem).where(QueueItem.work_type == "RESUME")
            )
            == 0
        )
