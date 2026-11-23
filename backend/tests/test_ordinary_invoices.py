from copy import deepcopy
from decimal import Decimal

import pytest
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.approval import approve
from app.evidence_verification import verify
from app.extraction_schema import InvoiceExtractionV1
from app.finance_rules import critical_check
from app.financial_models import ApprovalLedger, FinancialAssessment, POLine, PurchaseOrder, Vendor
from tests.financial_fixtures import POLICY, masters, run
from tests.ordinary_invoices import invoice


def ordinary_masters(engine):
    vendor_id, po_id, line_id = masters(engine, cap="25000", rate="18", qty="100")
    with Session(engine) as session, session.begin():
        vendor = session.get(Vendor, vendor_id)
        vendor.legal_name = "Northstar Components Ltd"
        vendor.normalized_tax_id = "27LMNOP1234Q1Z6"
        vendor.tax_id_original = vendor.normalized_tax_id
        po = session.get(PurchaseOrder, po_id)
        po.po_number = "PUR-6042"
        line = session.get(POLine, line_id)
        line.description = "Bearing assemblies"
        line.sku = "BEARING"
        line.unit_price = Decimal("2500")
    return vendor_id, po_id, line_id


@pytest.mark.parametrize("layout", ["stacked", "percentage", "footer"])
@pytest.mark.parametrize("numbered", [True, False])
def test_ordinary_table_does_not_require_demo_labels_or_optional_codes(layout, numbered):
    pdf, wire = invoice(layout=layout, numbered=numbered)
    original = wire.model_dump()
    checked = verify(wire, pdf)
    assert checked.findings == ()
    doc = checked.document
    assert doc and critical_check(doc) is None
    assert doc.vendor_tax_id == "27LMNOP1234Q1Z6"
    assert doc.lines[0].line_no == 1 and doc.lines[0].sku is None
    assert doc.tax_total == 1350 and doc.lines[0].net_amount == 7500
    assert doc.lines[0].price_basis == "NET" and doc.tax_mode == "EXCLUSIVE"
    assert wire.model_dump() == original and wire.tax_total is None
    assert any(e.method == "DERIVED" for e in doc.evidence)


def test_real_table_can_approve_against_arbitrary_registered_vendor_and_po(database):
    engine = database[0]
    _, po_id, _ = ordinary_masters(engine)
    pdf, wire = invoice()
    result = approve(engine, run(engine, pdf), verify(wire, pdf).document, POLICY.version)
    assert result.decision == "APPROVED"
    with Session(engine) as session:
        assert session.get(PurchaseOrder, po_id).committed_gross == 8850
        assessment = session.scalar(select(FinancialAssessment))
        checks = assessment.observations_json["rule_checks"]
        assert len(checks) == 13
        assert next(c for c in checks if c["rule_id"] == "PO_PRICE")["status"] == "passed"
        assert (
            next(c for c in checks if c["rule_id"] == "BANK_DETAILS")["status"] == "not_evaluated"
        )


@pytest.mark.parametrize(
    "field,value",
    [("vendor_tax_id", "29ZZZZZ1234Q1Z9"), ("total_gross", "1350"), ("invoice_date", "2026-11-21")],
)
def test_buyer_identity_other_amounts_and_other_dates_do_not_ground(field, value):
    pdf, wire = invoice()
    data = wire.model_dump()
    data[field] = value
    data["evidence"] = [
        dict(e, raw_text=value) if e["field"] == field else e for e in data["evidence"]
    ]
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert checked.needs_review
    assert not next(p for p in checked.provenance if p["field"] == field)["grounded"]
    if checked.document:
        assert critical_check(checked.document)


def test_missing_tax_is_not_a_zero_tax_default():
    pdf, wire = invoice(tax=False, rate="0")
    checked = verify(wire, pdf)
    assert checked.needs_review
    assert checked.document is None or checked.document.tax_total is None


def test_absent_po_goes_to_review_instead_of_inferred_approval(database):
    engine = database[0]
    ordinary_masters(engine)
    pdf, wire = invoice(po=None)
    checked = verify(wire, pdf)
    assert checked.findings == ()
    ident = run(engine, pdf)
    result = approve(engine, ident, checked.document, POLICY.version)
    assert result.code == "PO_MISSING" and result.decision == "NEEDS_REVIEW"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
        trace = session.get(FinancialAssessment, (ident, 0)).observations_json["rule_checks"]
        assert next(c for c in trace if c["rule_id"] == "PO_MATCH")["status"] == "requires_review"
        assert next(c for c in trace if c["rule_id"] == "PO_BALANCE")["status"] == "not_evaluated"


@pytest.mark.parametrize("field", ["vendor_tax_id", "po_reference"])
def test_printed_identity_or_po_cannot_be_omitted_from_a_model_response(field):
    pdf, wire = invoice()
    data = deepcopy(wire.model_dump())
    data[field] = None
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert "PRINTED_FIELD_OMITTED" in checked.findings


def test_model_value_present_in_wrong_column_is_not_evidence():
    pdf, wire = invoice()
    data = wire.model_dump()
    data["line_items"][0]["quantity"] = "2500.00"
    data["evidence"] = [
        dict(e, raw_text="2500.00") if e["field"] == "lines.1.quantity" else e
        for e in data["evidence"]
    ]
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert checked.needs_review
    assert not next(p for p in checked.provenance if p["field"] == "lines.1.quantity")["grounded"]


def test_wrong_page_cannot_be_rescued_by_derived_financial_values():
    pdf, wire = invoice()
    data = wire.model_dump()
    data["evidence"] = [dict(e, page=2) for e in data["evidence"]]
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert checked.needs_review and critical_check(checked.document)


def test_inclusive_prices_are_verified_without_double_counting_tax(database):
    engine = database[0]
    ordinary_masters(engine)
    pdf, wire = invoice(inclusive=True)
    checked = verify(wire, pdf)
    assert checked.findings == ()
    assert checked.document.lines[0].price_basis == "GROSS"
    assert checked.document.tax_mode == "INCLUSIVE"
    assert (
        approve(engine, run(engine, pdf), checked.document, POLICY.version).decision == "APPROVED"
    )


def test_unsupported_currency_is_preserved_and_cannot_authorize(database):
    engine = database[0]
    ordinary_masters(engine)
    pdf, wire = invoice(currency="USD")
    checked = verify(wire, pdf)
    assert checked.document.currency == "USD" and checked.needs_review
    assert (
        approve(engine, run(engine, pdf), checked.document, POLICY.version).decision
        == "NEEDS_REVIEW"
    )


def test_source_correct_but_wrong_supplier_gstin_compares_to_po_vendor(database):
    engine = database[0]
    ordinary_masters(engine)
    pdf, wire = invoice(gst="27AAAAA0000A1Z5")
    checked = verify(wire, pdf)
    assert checked.findings == ()
    ident = run(engine, pdf)
    result = approve(engine, ident, checked.document, POLICY.version)
    assert result.code == "VENDOR_UNKNOWN"
    assert "27AAAAA0000A1Z5" in result.reason and "27LMNOP1234Q1Z6" in result.reason
    with Session(engine) as session:
        checks = session.get(FinancialAssessment, (ident, 0)).observations_json["rule_checks"]
        assert next(c for c in checks if c["rule_id"] == "SOURCE_EVIDENCE")["status"] == "passed"
        assert (
            next(c for c in checks if c["rule_id"] == "VENDOR_IDENTITY")["status"]
            == "requires_review"
        )
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0


def test_normal_layout_partial_invoices_use_committed_po_allocations(database):
    engine = database[0]
    _, po_id, line_id = ordinary_masters(engine)
    with Session(engine) as session, session.begin():
        session.get(PurchaseOrder, po_id).approved_cap_gross = 250000
        session.get(POLine, line_id).tax_rate = 0
    for num, qty in [("NS-PART-001", "70"), ("NS-PART-002", "35")]:
        pdf, wire = invoice(number=num, qty=qty, rate="0")
        ident = run(engine, pdf)
        result = approve(engine, ident, verify(wire, pdf).document, POLICY.version)
    assert result.code == "PO_CAP_EXCEEDED" and "12500.00" in result.reason
    with Session(engine) as session:
        assert session.get(PurchaseOrder, po_id).committed_gross == 175000
        trace = session.get(FinancialAssessment, (ident, 0)).observations_json["rule_checks"]
        assert next(c for c in trace if c["rule_id"] == "PO_MATCH")["status"] == "passed"
        assert next(c for c in trace if c["rule_id"] == "PO_BALANCE")["status"] == "requires_review"
        assert next(c for c in trace if c["rule_id"] == "PO_PRICE")["status"] == "not_evaluated"


def test_printed_subtotal_omitted_by_model_is_locally_read_not_defaulted():
    pdf, wire = invoice()
    data = wire.model_dump()
    data["subtotal_net"] = None
    data["evidence"] = [e for e in data["evidence"] if e["field"] != "subtotal_net"]
    original = InvoiceExtractionV1.model_validate(data)
    checked = verify(original, pdf)
    assert checked.findings == () and checked.document.subtotal_net == 7500
    assert original.subtotal_net is None


def test_printed_but_inconsistent_total_is_not_an_approval(database):
    engine = database[0]
    ordinary_masters(engine)
    pdf, wire = invoice(total_adjust="1")
    checked = verify(wire, pdf)
    assert "ARITHMETIC_MISMATCH" in checked.findings
    assert next(p for p in checked.provenance if p["field"] == "total_gross")["grounded"]
    ident = run(engine, pdf)
    assert approve(engine, ident, checked.document, POLICY.version).decision == "NEEDS_REVIEW"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
        checks = session.get(FinancialAssessment, (ident, 0)).observations_json["rule_checks"]
        assert (
            next(c for c in checks if c["rule_id"] == "INVOICE_ARITHMETIC")["status"]
            == "requires_review"
        )
