"""Reviewer pass is conditional same-thread revalidation, never an override."""

from concurrent.futures import ThreadPoolExecutor

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.config import Settings
from app.financial_models import ApprovalLedger, PurchaseOrder, Vendor
from app.main import create_app
from app.models import QueueItem, Run
from app.review_contracts import ReviewResponse
from app.reviews import ReviewConflict, respond
from app.workflow_models import ReviewAction, ReviewRequest, WorkflowRun
from tests.conftest import TOKEN
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.test_scan_review import raster_overlay
from tests.test_workflow_reviews import REVIEWER, ambiguous, selection
from tests.workflow_helpers import execute, intake, invoice_pdf, mock_processor


def pass_body(generation=1):
    return ReviewResponse(
        generation=generation,
        action="PASS",
        payload={},
        reason="Reviewed supporting source and procurement records; rerun all mandatory checks.",
    )


def held(engine, kind="inactive"):
    vendor_id, po_id, _ = masters(engine, cap="100" if kind == "cap" else "50000")
    _, expected = case()
    if kind == "missing":
        expected["invoice_date"] = None
    if kind == "bank":
        expected["bank_account_last4"] = "9876"
    if kind == "currency":
        expected["currency"] = "USD"
    pdf = invoice_pdf(expected)
    if kind == "scan":
        pdf = raster_overlay(pdf)
    if kind == "inactive":
        with Session(engine) as session, session.begin():
            session.get(Vendor, vendor_id).status = "INACTIVE"
    ident = intake(engine, pdf)
    handler, calls = mock_processor(engine, pdf, expected)
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).job_state == "WAITING_REVIEW"
        request = session.scalar(select(ReviewRequest).where(ReviewRequest.run_id == ident))
        return ident, request.id, handler, calls, vendor_id, po_id


def test_pass_schema_rejects_field_overrides_and_keeps_approve_unsupported():
    assert pass_body().payload.model_dump(exclude_none=True) == {}
    for change in (
        {"payload": {"po_id": None}},
        {"payload": {"verified": True}},
        {"action": "APPROVE"},
        {"reason": "  "},
    ):
        with pytest.raises(ValidationError):
            ReviewResponse.model_validate(dict(pass_body().model_dump(), **change))


def test_pass_rechecks_essential_fields_current_masters_and_posts_once(workflow_db, settings):
    engine = workflow_db
    ident, request_id, handler, calls, vendor_id, po_id = held(engine)
    with Session(engine) as session, session.begin():
        thread = session.get(Run, ident).thread_id
        original = session.get(WorkflowRun, ident).extraction_json
        session.get(Vendor, vendor_id).status = "ACTIVE"
    cfg = Settings(
        _env_file=None,
        database_url=settings.database_url,
        app_api_token=TOKEN,
        reviewer_api_token=REVIEWER,
        access_mode="roles",
    )
    with TestClient(create_app(cfg, engine)) as client:
        path = f"/api/v1/reviews/{request_id}/respond"
        body = pass_body().model_dump(mode="json", exclude_none=True)
        submitter = {"Authorization": f"Bearer {TOKEN}", "X-Idempotency-Key": "pass-once"}
        assert client.post(path, headers=submitter, json=body).status_code == 403
        headers = dict(submitter, Authorization=f"Bearer {REVIEWER}")
        review = client.get(f"/api/v1/runs/{ident}/review", headers=headers).json()
        assert "PASS" in review["allowed_actions"]
        assert client.post(path, headers=headers, json=body).status_code == 202
        assert client.post(path, headers=headers, json=body).status_code == 202
    with Session(engine) as session:
        assert session.get(Run, ident).decision is None
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    execute(engine, handler)
    assert respond(engine, request_id, pass_body(), "pass-once", "configured-reviewer")
    with Session(engine) as session:
        run = session.get(Run, ident)
        assert run.decision == "APPROVED" and run.thread_id == thread
        assert session.get(WorkflowRun, ident).extraction_json == original
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert session.get(PurchaseOrder, po_id).committed_gross == 11800
        assert session.scalar(select(func.count()).select_from(ReviewAction)) == 1
        assert session.scalar(select(ReviewAction.action)) == "PASS"
        assert (
            session.scalar(
                select(func.count()).select_from(QueueItem).where(QueueItem.work_type == "RESUME")
            )
            == 1
        )
    assert len(calls) == 1


@pytest.mark.parametrize("kind", ["missing", "cap", "bank", "currency", "scan", "inactive"])
def test_pass_cannot_waive_unresolved_source_or_financial_rules(workflow_db, kind):
    engine = workflow_db
    ident, request_id, handler, calls, _, _ = held(engine, kind)
    before = len(calls)
    respond(engine, request_id, pass_body(), "pass-still-held", "configured-reviewer")
    execute(engine, handler)
    with Session(engine) as session:
        run = session.get(Run, ident)
        assert run.decision == "NEEDS_REVIEW" and run.job_state == "WAITING_REVIEW"
        request = session.scalar(
            select(ReviewRequest).where(
                ReviewRequest.run_id == ident, ReviewRequest.status == "OPEN"
            )
        )
        assert request.generation == 2
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    assert len(calls) == before


def test_pass_rechecks_changes_made_after_the_reviewer_clicks(workflow_db):
    engine = workflow_db
    ident, request_id, handler, _, vendor_id, _ = held(engine)
    with Session(engine) as session, session.begin():
        session.get(Vendor, vendor_id).status = "ACTIVE"
    respond(engine, request_id, pass_body(), "pass-stale-master", "configured-reviewer")
    with Session(engine) as session, session.begin():
        session.get(Vendor, vendor_id).status = "BLACKLISTED"
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "NEEDS_REVIEW"
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0


def test_pass_preserves_a_previously_authorized_offered_po_choice(workflow_db):
    engine = workflow_db
    ident, po_id, request_id, handler, calls = ambiguous(engine)
    with Session(engine) as session, session.begin():
        thread = session.get(Run, ident).thread_id
        session.get(PurchaseOrder, po_id).approved_cap_gross = 100
    respond(engine, request_id, selection(po_id), "select-before-pass", "configured-reviewer")
    execute(engine, handler)
    with Session(engine) as session, session.begin():
        current = session.scalar(select(ReviewRequest).where(ReviewRequest.status == "OPEN"))
        assert current.generation == 2 and current.kind == "EVIDENCE_OR_POLICY"
        current_id = current.id
        session.get(PurchaseOrder, po_id).approved_cap_gross = 50000
    respond(engine, current_id, pass_body(2), "pass-prior-choice", "configured-reviewer")
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "APPROVED"
        assert session.get(Run, ident).thread_id == thread
        assert session.scalar(select(ApprovalLedger.po_id)) == po_id
    assert len(calls) == 1


def test_pass_without_a_missing_po_selection_cannot_guess_an_order(workflow_db):
    engine = workflow_db
    ident, _, request_id, handler, calls = ambiguous(engine)
    respond(engine, request_id, pass_body(), "pass-no-choice", "configured-reviewer")
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "NEEDS_REVIEW"
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    assert len(calls) == 1


def test_pass_cannot_duplicate_an_invoice_approved_while_it_was_held(workflow_db):
    engine = workflow_db
    ident, request_id, handler, _, _, po_id = held(engine, "cap")
    with Session(engine) as session, session.begin():
        session.get(PurchaseOrder, po_id).approved_cap_gross = 50000
    pdf, expected = case()
    other = intake(engine, pdf)
    execute(engine, mock_processor(engine, pdf, expected)[0])
    with Session(engine) as session:
        assert session.get(Run, other).decision == "APPROVED"
    respond(engine, request_id, pass_body(), "pass-duplicate", "configured-reviewer")
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "REJECTED"
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert session.get(PurchaseOrder, po_id).committed_gross == 11800


def test_pass_resumes_a_frozen_legacy_review_without_reextracting(workflow_db, monkeypatch):
    from app import workflow

    engine = workflow_db
    with monkeypatch.context() as frozen:
        frozen.setattr(workflow, "PROMPT_VERSION", "invoice-extract-2")
        frozen.setattr(workflow, "VERIFIER_VERSION", "layout-grounding-4")
        ident, request_id, handler, calls, vendor_id, _ = held(engine)
    with Session(engine) as session, session.begin():
        thread = session.get(Run, ident).thread_id
        session.get(Vendor, vendor_id).status = "ACTIVE"
    respond(engine, request_id, pass_body(), "pass-legacy", "configured-reviewer")
    execute(engine, handler)
    with Session(engine) as session:
        assert session.get(Run, ident).decision == "APPROVED"
        assert session.get(Run, ident).thread_id == thread
        work = session.get(WorkflowRun, ident)
        assert work.schema_version == "InvoiceExtractionV1.1"
        assert work.verifier_version == "layout-grounding-4"
    assert len(calls) == 1


def test_concurrent_passes_and_stale_generations_do_not_enqueue_twice(workflow_db):
    engine = workflow_db
    _, request_id, _, _, _, _ = held(engine)
    with pytest.raises(ReviewConflict):
        respond(engine, request_id, pass_body(2), "stale-pass", "configured-reviewer")

    def submit(key):
        try:
            respond(engine, request_id, pass_body(), key, "configured-reviewer")
            return "accepted"
        except ReviewConflict:
            return "conflict"

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(submit, ["pass-a", "pass-b"])) == ["accepted", "conflict"]
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ReviewAction)) == 1
        assert (
            session.scalar(
                select(func.count()).select_from(QueueItem).where(QueueItem.work_type == "RESUME")
            )
            == 1
        )


def test_pass_audit_enqueue_and_review_resolution_roll_back_together(workflow_db):
    engine = workflow_db
    _, request_id, _, _, _, _ = held(engine)
    with engine.begin() as connection:
        connection.execute(
            text(
                "ALTER TABLE run_events ADD CONSTRAINT injected_pass "
                "CHECK(type <> 'REVIEW_RESOLVED')"
            )
        )
    with pytest.raises(IntegrityError):
        respond(engine, request_id, pass_body(), "rollback-pass", "configured-reviewer")
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ReviewAction)) == 0
        assert session.get(ReviewRequest, request_id).status == "OPEN"
        assert (
            session.scalar(
                select(func.count()).select_from(QueueItem).where(QueueItem.work_type == "RESUME")
            )
            == 0
        )


def test_downgrade_refuses_to_invalidate_pass_audit(workflow_db, database):
    engine, config = database
    _, request_id, _, _, _, _ = held(engine)
    respond(engine, request_id, pass_body(), "audit-pass", "configured-reviewer")
    with pytest.raises(RuntimeError, match="immutable PASS review audit"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0012_extraction_diagnostics")
    with Session(engine) as session:
        assert session.scalar(select(ReviewAction.action)) == "PASS"
        assert session.scalar(text("SELECT version_num FROM alembic_version")) == "0013_review_pass"
