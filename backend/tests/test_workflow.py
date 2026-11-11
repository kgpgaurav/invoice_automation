from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.checkpoints import checkpoint_store
from app.financial_models import ApprovalLedger, PurchaseOrder
from app.main import create_app
from app.models import QueueItem, Run, RunEvent
from app.worker import Worker
from tests.conftest import TOKEN
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.workflow_helpers import execute, intake, mock_processor


def test_h1_pdf_to_one_immutable_approval(workflow_db, settings):
    engine = workflow_db
    _, po_id, _ = masters(engine)
    pdf, expected = case()
    from uuid import UUID

    with TestClient(create_app(settings, engine)) as client:
        result = client.post(
            "/api/v1/invoices/process",
            files={"file": ("invoice.pdf", pdf, "application/pdf")},
            headers={"Authorization": f"Bearer {TOKEN}"},
        )
        assert result.status_code == 202
        run_id = UUID(result.json()["run_id"])
    processor, calls = mock_processor(engine, pdf, expected)
    assert Worker(engine, processor).run_once()
    with Session(engine) as s:
        run = s.get(Run, run_id)
        assert (run.job_state, run.decision) == ("COMPLETED", "APPROVED")
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert s.get(PurchaseOrder, po_id).committed_gross == Decimal("11800")
        assert s.scalar(select(QueueItem.status)) == "DONE"
        events = s.scalars(select(RunEvent).order_by(RunEvent.seq)).all()
        assert [e.seq for e in events] == list(range(1, len(events) + 1))
        assert all(e.payload_json.get("source") != "LIVE_OPENAI" for e in events)
        thread_id = str(run.thread_id)
    assert len(calls) == 1
    with checkpoint_store(engine) as saver:
        saved = saver.get({"configurable": {"thread_id": thread_id}})
        assert saved["channel_values"]["decision"] == "APPROVED"
        assert "Aster" not in str(saved)


@pytest.mark.parametrize("fixture", ["scan", "inconsistent", "missing", "unsupported"])
def test_bad_evidence_never_approves(workflow_db, fixture):
    engine = workflow_db
    masters(engine)
    pdf, expected = case(fixture)
    run_id = intake(engine, pdf)
    processor, calls = mock_processor(engine, pdf, expected)
    execute(engine, processor)
    with Session(engine) as s:
        run = s.get(Run, run_id)
        assert (run.job_state, run.decision) == ("WAITING_REVIEW", "NEEDS_REVIEW")
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    assert len(calls) == (2 if fixture in ("scan", "missing") else 1)
