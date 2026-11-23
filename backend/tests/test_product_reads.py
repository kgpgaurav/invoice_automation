from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.financial_models import ApprovalLedger, FinancialAssessment, PurchaseOrder
from app.main import create_app
from app.models import Run
from app.product_reads import rule_checks
from app.reviews import respond
from tests.conftest import TOKEN
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.test_workflow_reviews import ambiguous, selection
from tests.workflow_helpers import execute, intake, invoice_pdf, mock_processor


@pytest.mark.parametrize(
    "assessment,ledger", [(None, None), ("VALIDATED", None), ("UNRECOGNIZED", True)]
)
def test_checklist_never_infers_passes(assessment, ledger):
    ident = uuid4()
    assessment = (
        SimpleNamespace(run_id=ident, revision=0, code=assessment, decision="APPROVED")
        if assessment
        else None
    )
    ledger = SimpleNamespace(run_id=ident) if ledger else None
    checks = rule_checks(assessment, ledger, [])
    assert not any(c.status == "passed" for c in checks)
    assert all(
        c.status == "not_evaluated" for c in checks if c.rule_id in ("PO_MATCH", "PO_BALANCE")
    )


def test_recorded_hold_does_not_imply_other_checks_passed():
    assessment = SimpleNamespace(
        run_id=uuid4(), revision=0, code="PO_CAP_EXCEEDED", decision="NEEDS_REVIEW"
    )
    checks = rule_checks(assessment, None, [])
    assert [c.rule_id for c in checks if c.status == "requires_review"] == ["PO_BALANCE"]
    assert sum(c.status == "not_evaluated" for c in checks) == 6
    rejected = SimpleNamespace(
        run_id=uuid4(), revision=0, code="DUPLICATE_APPROVED", decision="REJECTED"
    )
    assert (
        next(c for c in rule_checks(rejected, None, []) if c.rule_id == "DUPLICATE_IDENTITY").status
        == "failed"
    )


def test_po_reads_checklist_and_immutable_history(workflow_db, settings):
    engine = workflow_db
    _, po_id, _ = masters(engine)
    pdf, expected = case()
    run_id = intake(engine, pdf)
    execute(engine, mock_processor(engine, pdf, expected)[0])
    with TestClient(create_app(settings, engine)) as client:
        for path in ("/purchase-orders", f"/purchase-orders/{po_id}"):
            assert client.get("/api/v1" + path).status_code == 401
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        detail = client.get(f"/api/v1/runs/{run_id}").json()
        assert len(detail["checks"]) == 13
        assert all(c["status"] == "passed" for c in detail["checks"])
        assert all(c["provenance"] == "COMMITTED_VALIDATED_ASSESSMENT" for c in detail["checks"])
        first = client.get(f"/api/v1/purchase-orders/{po_id}").json()
        assert first["ledger_committed_gross"] == "11800.00"
        assert first["available_gross"] == "38200.00" and first["balance_reconciled"]
        assert first["allocations"][0]["run_id"] == str(run_id)
        assert client.get(f"/api/v1/purchase-orders/{po_id}").json() == first
        with Session(engine) as session, session.begin():
            po = session.get(PurchaseOrder, po_id)
            po.approved_cap_gross = 60000
            po.committed_gross = 11801  # injected drift, not a financial service mutation
        changed = client.get(f"/api/v1/purchase-orders/{po_id}").json()
        assert changed["available_gross"] is None and not changed["balance_reconciled"]
        old = client.get(f"/api/v1/runs/{run_id}").json()
        assert old["decision_observations"]["cap_gross"] == "50000.00"
        assert old["checks"] == detail["checks"]
        assert client.get(f"/api/v1/purchase-orders/{uuid4()}").status_code == 404
        assert (
            client.post(f"/api/v1/purchase-orders/{po_id}", json={"approve": True}).status_code
            == 405
        )
        text = client.get(f"/api/v1/purchase-orders/{po_id}").text
        assert "bank" not in text and "document_json" not in text
    with Session(engine) as session:
        assert len(session.scalars(select(ApprovalLedger)).all()) == 1
        assert len(session.scalars(select(FinancialAssessment)).all()) == 1


def test_directory_and_search_are_bounded_literal_filters(client, database, pdf):
    engine = database[0]
    _, po_id, _ = masters(engine)
    with Session(engine) as session, session.begin():
        original = session.get(PurchaseOrder, po_id)
        session.add(
            PurchaseOrder(
                po_number="PO-002",
                vendor_id=original.vendor_id,
                issued_at=original.issued_at,
                approved_cap_gross=1000,
            )
        )
    first = client.get("/api/v1/purchase-orders?limit=1").json()
    assert first["total_count"] == 2 and first["next_after"] == "PO-001"
    second = client.get("/api/v1/purchase-orders?limit=1&after=PO-001").json()
    assert second["items"][0]["po_number"] == "PO-002"
    assert client.get("/api/v1/purchase-orders?q=aster").json()["total_count"] == 2
    assert client.get("/api/v1/purchase-orders?q=%25").json()["total_count"] == 0
    assert client.get("/api/v1/purchase-orders?limit=101").status_code == 422
    ident = intake(engine, pdf)
    assert client.get("/api/v1/runs", params={"q": str(ident)}).json()["total_count"] == 1
    assert client.get("/api/v1/runs?q=%25").json()["total_count"] == 0
    assert client.get("/api/v1/runs?q=" + "a" * 121).status_code == 422


def test_search_cursor_is_bound_to_query(workflow_db, settings):
    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    for _ in range(2):
        intake(engine, pdf)
        execute(engine, mock_processor(engine, pdf, expected)[0])
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        first = client.get("/api/v1/runs?q=aster&limit=1").json()
        assert first["total_count"] == 2
        next_page = client.get(
            "/api/v1/runs", params={"q": "aster", "limit": 1, "cursor": first["next_cursor"]}
        ).json()
        assert next_page["items"][0]["run_id"] != first["items"][0]["run_id"]
        assert (
            client.get(
                "/api/v1/runs", params={"q": "different", "cursor": first["next_cursor"]}
            ).status_code
            == 422
        )


def test_straight_through_denominator_excludes_unknown_and_resolved_review(workflow_db, settings):
    engine = workflow_db
    held_id, po_id, request_id, processor, _ = ambiguous(engine)
    pdf, expected = case()
    expected = dict(expected, invoice_number="INV-STRAIGHT-002")
    pdf = invoice_pdf(expected)
    intake(engine, pdf)
    execute(engine, mock_processor(engine, pdf, expected)[0])
    intake(engine, pdf)  # unstarted workflow is excluded
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        before = client.get("/api/v1/dashboard/summary").json()
        assert before["straight_through_approved"] == 1
        assert (
            before["automation_eligible_runs"] == 2
            and before["straight_through_rate_pct"] == "50.0"
        )
        assert before["mock_runs"] == 2 and before["live_runs"] == 0
        # Retire the unrelated queued test upload so resume claims the intended work.
        from app.models import QueueItem

        with Session(engine) as session, session.begin():
            for queued in session.scalars(select(QueueItem).where(QueueItem.status == "READY")):
                queued.status = "DONE"
        respond(engine, request_id, selection(po_id), "product-read-select", "configured-reviewer")
        execute(engine, processor)
        after = client.get("/api/v1/dashboard/summary").json()
        assert after["approved"] == 2 and after["straight_through_approved"] == 1
        assert after["straight_through_rate_pct"] == "50.0"
        with Session(engine) as session:
            assert session.get(Run, held_id).decision == "APPROVED"


def test_empty_automation_metric_stays_unknown(client):
    data = client.get("/api/v1/dashboard/summary").json()
    assert data["straight_through_rate_pct"] is None and data["automation_eligible_runs"] == 0


def test_manual_rejection_keeps_prior_assessment_distinct(workflow_db, settings):
    from app.review_contracts import ReviewResponse
    from app.workflow_models import ReviewRequest

    engine = workflow_db
    masters(engine, cap="1000")
    pdf, expected = case()
    run_id = intake(engine, pdf)
    processor, _ = mock_processor(engine, pdf, expected)
    execute(engine, processor)
    with Session(engine) as session:
        review = session.scalar(select(ReviewRequest))
        review_id, generation = review.id, review.generation
    respond(
        engine,
        review_id,
        ReviewResponse(
            generation=generation,
            action="REJECT",
            payload={},
            reason="Supporting purchase order is not valid for this request.",
        ),
        "reject-product-read",
        "configured-reviewer",
    )
    execute(engine, processor)
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = f"Bearer {TOKEN}"
        detail = client.get(f"/api/v1/runs/{run_id}").json()
        assert detail["reason_code"] == "REVIEWER_REJECTED"
        assert "authorized reviewer rejected" in detail["business_explanation"]
        historical = next(c for c in detail["checks"] if c["rule_id"] == "PO_BALANCE")
        assert historical["finding_code"] == "PO_CAP_EXCEEDED"
        assert historical["status"] == "requires_review"
        assert client.get("/api/v1/runs").json()["items"][0]["reason_code"] == "REVIEWER_REJECTED"
        assert detail["approved_gross"] is None
