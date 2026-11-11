from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.config import Settings
from app.financial_models import ApprovalLedger, POLine, PurchaseOrder
from app.main import create_app
from app.models import QueueItem, Run, RunEvent
from app.review_contracts import ReviewResponse
from app.reviews import ReviewConflict, respond
from app.workflow_models import ReviewAction, ReviewRequest
from tests.conftest import TOKEN
from tests.financial_fixtures import masters
from tests.workflow_helpers import execute, intake, missing_po, mock_processor

REVIEWER = "reviewer-only-secret-at-least-24-characters"


def ambiguous(engine):
    vendor_id, po_id, _ = masters(engine)
    with Session(engine) as s, s.begin():
        po = s.get(PurchaseOrder, po_id)
        other = PurchaseOrder(
            id=uuid4(),
            vendor_id=vendor_id,
            po_number="PO-002",
            issued_at=po.issued_at,
            approved_cap_gross=po.approved_cap_gross,
        )
        s.add(other)
        s.flush()
        s.add(
            POLine(
                po_id=other.id,
                line_no=1,
                sku="PAPER",
                description="Office paper",
                quantity=100,
                unit_price=1000,
                tax_rate=18,
            )
        )
    pdf, expected = missing_po()
    run_id = intake(engine, pdf)
    processor, calls = mock_processor(engine, pdf, expected)
    execute(engine, processor)
    with Session(engine) as s:
        request = s.scalar(select(ReviewRequest).where(ReviewRequest.status == "OPEN"))
        assert request.kind == "PO_SELECTION" and len(request.options_json) == 2
        return run_id, po_id, request.id, processor, calls


def selection(po_id, generation=1):
    return ReviewResponse(
        generation=generation,
        action="SELECT_PO",
        payload={"po_id": str(po_id)},
        reason="Selected using supporting purchase order records",
    )


def test_e2_authenticated_interrupt_resume_and_replay(workflow_db, settings):
    engine = workflow_db
    run_id, po_id, request_id, processor, calls = ambiguous(engine)
    settings = Settings(
        _env_file=None,
        database_url=settings.database_url,
        app_api_token=TOKEN,
        reviewer_api_token=REVIEWER,
    )
    with TestClient(create_app(settings, engine)) as client:
        path = f"/api/v1/reviews/{request_id}/respond"
        body = selection(po_id).model_dump(mode="json")
        assert (
            client.post(path, json=body, headers={"X-Idempotency-Key": "select"}).status_code == 403
        )
        headers = {"Authorization": f"Bearer {TOKEN}", "X-Idempotency-Key": "select"}
        assert client.get(f"/api/v1/runs/{run_id}/review", headers=headers).status_code == 200
        assert client.post(path, json=body, headers=headers).status_code == 403
        headers["Authorization"] = f"Bearer {REVIEWER}"
        assert client.post(path, json=body, headers=headers).status_code == 202
        assert client.post(path, json=body, headers=headers).status_code == 202
        assert client.post(path, json=dict(body, generation=2), headers=headers).status_code == 409
        assert (
            client.post(path, json=dict(body, action="APPROVE"), headers=headers).status_code == 422
        )
    execute(engine, processor)
    with Session(engine) as s:
        assert s.get(Run, run_id).decision == "APPROVED"
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert s.scalar(select(func.count()).select_from(ReviewAction)) == 1
        assert (
            s.scalar(
                select(func.count()).select_from(QueueItem).where(QueueItem.work_type == "RESUME")
            )
            == 1
        )
    assert len(calls) == 1
    assert respond(engine, request_id, selection(po_id), "select", "configured-reviewer")


def test_review_revalidates_changed_po_and_cannot_waive_cap(workflow_db):
    engine = workflow_db
    run_id, po_id, request_id, processor, _ = ambiguous(engine)
    with Session(engine) as s, s.begin():
        s.get(PurchaseOrder, po_id).approved_cap_gross = 100
    respond(engine, request_id, selection(po_id), "choice", "configured-reviewer")
    execute(engine, processor)
    with Session(engine) as s:
        run = s.get(Run, run_id)
        assert (run.job_state, run.decision) == ("WAITING_REVIEW", "NEEDS_REVIEW")
        current = s.scalar(select(ReviewRequest).where(ReviewRequest.status == "OPEN"))
        assert current.generation == 2 and current.kind == "EVIDENCE_OR_POLICY"
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    with pytest.raises(ReviewConflict):
        respond(engine, current.id, selection(po_id, 1), "stale", "configured-reviewer")
    stop = ReviewResponse(generation=2, action="REQUEST_INFO", payload={}, reason="Need amended PO")
    respond(engine, current.id, stop, "info", "configured-reviewer")
    execute(engine, processor)
    with Session(engine) as s:
        assert s.get(Run, run_id).job_state == "INTERRUPTED"
        assert s.get(Run, run_id).decision is None
        assert (
            s.scalar(
                select(func.count())
                .select_from(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.type == "RUN_COMPLETED")
            )
            == 0
        )


def test_concurrent_conflicting_reviews_store_one_action(workflow_db):
    engine = workflow_db
    _, po_id, request_id, _, _ = ambiguous(engine)
    body = selection(po_id)

    def submit(key):
        try:
            respond(engine, request_id, body, key, "configured-reviewer")
            return "accepted"
        except ReviewConflict:
            return "conflict"

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(submit, ["a", "b"])) == ["accepted", "conflict"]
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(ReviewAction)) == 1


def test_interrupt_checkpoint_survives_failure_before_publication(workflow_db):
    from app.worker import Worker, WorkerPolicy
    from tests.test_worker import expire
    from tests.workflow_helpers import missing_po, mock_processor

    engine = workflow_db
    masters(engine)
    pdf, expected = missing_po()
    run_id = intake(engine, pdf)

    def fail(point):
        if point == "after_interrupt_checkpoint":
            raise RuntimeError("Injected crash before review publication")

    processor, calls = mock_processor(engine, pdf, expected, crash_hook=fail)
    with pytest.raises(RuntimeError):
        execute(engine, processor)
    with Session(engine) as s:
        request = s.scalar(select(ReviewRequest))
        assert request.status == "PREPARED"
        review_id = request.id
    with pytest.raises(ReviewConflict):
        respond(engine, review_id, selection(uuid4()), "premature", "configured-reviewer")
    expire(engine)
    processor.crash_hook = lambda _: None
    assert Worker(engine, processor, WorkerPolicy(retry_seconds=0)).run_once() is False
    execute(engine, processor)
    with Session(engine) as s:
        assert s.get(ReviewRequest, review_id).status == "OPEN"
        assert s.get(Run, run_id).job_state == "WAITING_REVIEW"
        assert s.scalar(select(func.count()).select_from(ReviewRequest)) == 1
    assert len(calls) == 1
