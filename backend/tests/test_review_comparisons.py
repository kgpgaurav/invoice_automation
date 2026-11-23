from decimal import Decimal

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import Settings
from app.extraction_schema import InvoiceExtractionV1
from app.financial_models import PurchaseOrder
from app.intake import create_intake
from app.main import create_app
from tests.conftest import TOKEN
from tests.ordinary_invoices import invoice
from tests.test_ordinary_invoices import ordinary_masters
from tests.test_ordinary_workflow import processor
from tests.workflow_helpers import execute


def process(engine, pdf, wire):
    ident = create_intake(engine, pdf, None, None, owner_id="submitter").run_id
    handler, _ = processor(engine, wire)
    execute(engine, handler)
    return ident


def read(settings, engine, ident):
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        response = client.get(f"/api/v1/runs/{ident}")
        assert response.status_code == 200
        return response.json()


def test_grounded_gstin_can_differ_from_po_vendor_and_is_not_an_override(workflow_db, settings):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice(gst="27AAAAA0000A1Z5")
    ident = process(engine, pdf, wire)
    detail = read(settings, engine, ident)
    row = next(r for r in detail["comparisons"] if r["field"] == "vendor_tax_id")
    assert row["invoice_value"] == "27AAAAA0000A1Z5"
    assert row["expected_value"] == "27LMNOP1234Q1Z6"
    assert row["status"] == "different" and row["source_verification"] == "verified"
    assert row["provenance"] == "CURRENT_MASTER" and row["pages"] == [1]
    assert detail["decision"] == "NEEDS_REVIEW" and "tax ID" in detail["decision_reason"]
    balance = next(r for r in detail["comparisons"] if r["field"] == "total_gross")
    assert balance["status"] == "information" and balance["provenance"] == "CURRENT_MASTER"


def test_unverified_model_claim_cannot_become_trusted_through_comparison(workflow_db, settings):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice()
    value = wire.model_dump()
    value["evidence"] = [dict(e, page=2) for e in value["evidence"]]
    ident = process(engine, pdf, InvoiceExtractionV1.model_validate(value))
    detail = read(settings, engine, ident)
    row = next(r for r in detail["comparisons"] if r["field"] == "vendor_tax_id")
    assert row["invoice_value"] == row["expected_value"]
    assert row["status"] == "unverified" and row["source_verification"] == "unverified"
    assert detail["decision"] == "NEEDS_REVIEW" and detail["approved_gross"] is None


def test_recorded_excess_is_not_recomputed_from_changed_current_cap(workflow_db, settings):
    engine = workflow_db
    _, po_id, _ = ordinary_masters(engine)
    with Session(engine) as session, session.begin():
        session.get(PurchaseOrder, po_id).approved_cap_gross = 8000
    pdf, wire = invoice()
    ident = process(engine, pdf, wire)
    with Session(engine) as session, session.begin():
        session.get(PurchaseOrder, po_id).approved_cap_gross = 24000
    detail = read(settings, engine, ident)
    row = next(r for r in detail["comparisons"] if r["field"] == "total_gross")
    assert Decimal(row["invoice_value"]) == Decimal("8850.00")
    assert row["expected_value"] == "8000.00"
    assert row["difference"] == "850.00" and row["status"] == "different"
    assert row["provenance"] == "RECORDED_ASSESSMENT"
    assert detail["purchase_order"]["remaining_gross"] == "24000.00"


@pytest.mark.parametrize("invalid", ["not money", "1e999999999", "NaN", "-Infinity"])
def test_malformed_amount_still_has_a_readable_review_page(workflow_db, settings, invalid):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice()
    value = wire.model_dump()
    value["total_gross"] = invalid
    ident = process(engine, pdf, InvoiceExtractionV1.model_validate(value))
    detail = read(settings, engine, ident)
    assert detail["decision"] == "NEEDS_REVIEW"
    assert detail["approved_gross"] is None
    assert any(r["source_verification"] == "unverified" for r in detail["comparisons"])


def test_missing_source_fields_are_actionable_without_a_master_match(workflow_db, settings):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice(po=None, tax=False, rate="0")
    ident = process(engine, pdf, wire)
    detail = read(settings, engine, ident)
    missing = {r["field"] for r in detail["comparisons"] if r["status"] == "missing"}
    assert {"po_reference", "tax_total", "lines.1.tax_rate"} <= missing
    assert all(r["expected_value"] is None for r in detail["comparisons"])


def test_submitter_never_receives_master_comparisons_or_po_amounts(workflow_db, settings):
    engine = workflow_db
    ordinary_masters(engine)
    pdf, wire = invoice(gst="27AAAAA0000A1Z5")
    ident = process(engine, pdf, wire)
    roles = Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {"access_mode": "roles", "reviewer_api_token": "reviewer-comparison-test-token-12345"}
        ),
    )
    detail = read(roles, engine, ident)
    assert detail["decision"] == "NEEDS_REVIEW"
    assert "comparisons" not in detail and "purchase_order" not in detail
    assert "27LMNOP1234Q1Z6" not in str(detail) and "25000.00" not in str(detail)
