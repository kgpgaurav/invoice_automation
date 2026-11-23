"""Versioned fields, local evidence and conservative adjustment policy."""

import pymupdf
import pytest
from pydantic import ValidationError

from app.evidence_verification import verify
from app.extraction_schema import InvoiceExtractionV1, InvoiceExtractionV12, output_format
from app.finance_rules import critical_check
from tests.ordinary_invoices import invoice
from tests.test_semantic_layouts import semantic_invoice


def extended_invoice(*, discount=None, shipping="0.00", layout="split"):
    pdf, old = invoice(layout=layout)
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        page = doc[0]
        for x, y, text in [
            (40, 235, "42 Buyer Lane"),
            (40, 255, "India"),
            (350, 215, "Due Date: Dec 20, 2026"),
            (40, 600, "Payment Terms: Net 30 days"),
            (40, 630, "Shipping charges: " + shipping),
            (230, 280, "HSN/SAC"),
            (230, 310, "8471"),
        ]:
            page.insert_text((x, y), text, fontsize=9)
        if discount is not None:
            page.insert_text((40, 660), "Discount: " + discount, fontsize=9)
        pdf = doc.tobytes()
    wire = InvoiceExtractionV12.model_validate(old.model_dump())
    return pdf, wire


def test_new_schema_is_strict_nullable_and_old_schema_is_frozen():
    old = output_format("invoice-extract-3")["schema"]
    assert old == InvoiceExtractionV1.model_json_schema()
    new = output_format()["schema"]
    for definition in (new, *new["$defs"].values()):
        assert definition["additionalProperties"] is False
        assert set(definition["required"]) == set(definition["properties"])
    assert "buyer_name" in new["properties"] and "due_date" in new["properties"]
    pdf, wire = extended_invoice()
    with pytest.raises(ValidationError):
        InvoiceExtractionV12.model_validate(dict(wire.model_dump(), shipping_amount=1.1))


def test_buyer_due_date_hsn_and_split_gst_are_independently_read_with_raw_retained():
    pdf, wire = extended_invoice()
    checked = verify(wire, pdf)
    assert checked.findings == () and critical_check(checked.document) is None
    fields = {p["field"]: p for p in checked.provenance}
    assert fields["buyer_name"]["normalized_value"] == "Independent Buyer Ltd"
    assert fields["buyer_tax_id"]["normalized_value"] == "29ZZZZZ1234Q1Z9"
    assert fields["due_date"]["normalized_value"] == "2026-12-20"
    assert fields["payment_terms"]["normalized_value"] == "Net 30 days"
    assert fields["lines.1.hsn_sac"]["normalized_value"] == "8471"
    assert fields["cgst_amount"]["normalized_value"] == "675.00"
    assert fields["cgst_amount"]["state"] == "DERIVED"
    assert fields["sgst_amount"]["normalized_value"] == "675.00"
    assert wire.cgst_amount is None and wire.buyer_name is None


@pytest.mark.parametrize(
    "field,value", [("cgst_amount", "999.00"), ("cgst_rate", "101"), ("shipping_amount", "0.001")]
)
def test_wrong_or_overprecise_financial_detail_never_becomes_approval(field, value):
    pdf, wire = extended_invoice()
    checked = verify(wire.model_copy(update={field: value}), pdf)
    assert checked.needs_review and critical_check(checked.document)
    assert not next(p for p in checked.provenance if p["field"] == field)["grounded"]


@pytest.mark.parametrize("discount,shipping", [("10.00", "0.00"), (None, "10.00")])
def test_printed_nonzero_adjustment_cannot_be_silently_omitted(discount, shipping):
    pdf, wire = extended_invoice(discount=discount, shipping=shipping)
    checked = verify(wire, pdf)
    assert critical_check(checked.document).code == "FINANCIAL_ADJUSTMENT_REQUIRES_REVIEW"
    assert "FINANCIAL_ADJUSTMENT_REQUIRES_REVIEW" in checked.findings


def test_wrong_optional_buyer_id_is_visible_and_never_used_as_supplier_identity():
    pdf, wire = extended_invoice()
    checked = verify(wire.model_copy(update={"buyer_tax_id": wire.vendor_tax_id}), pdf)
    buyer = next(p for p in checked.provenance if p["field"] == "buyer_tax_id")
    assert buyer["state"] == "UNVERIFIED"
    assert checked.document.vendor_tax_id == "27LMNOP1234Q1Z6"


def test_wrong_page_does_not_verify_a_new_field():
    pdf, wire = extended_invoice()
    data = wire.model_dump()
    data["due_date"] = "2026-12-20"
    data["evidence"].append(
        dict(field="due_date", raw_text="Dec 20, 2026", page=2, method="VISION")
    )
    checked = verify(InvoiceExtractionV12.model_validate(data), pdf)
    assert not next(p for p in checked.provenance if p["field"] == "due_date")["grounded"]


def conflicting_gst_invoice():
    pdf, raw = invoice(layout="footer")
    with pymupdf.open(stream=pdf, filetype="pdf") as doc:
        doc[0].insert_text((40, 600), "IGST 18%: 1350.00", fontsize=9)
        doc[0].insert_text((40, 620), "IGST 18%: 999.00", fontsize=9)
        pdf = doc.tobytes()
    wire = InvoiceExtractionV12.model_validate(raw.model_dump())
    return pdf, wire


def test_conflicting_printed_gst_amounts_hold_even_when_the_model_returns_null():
    pdf, wire = conflicting_gst_invoice()
    checked = verify(wire, pdf)
    field = next(p for p in checked.provenance if p["field"] == "igst_amount")
    assert field["state"] == "AMBIGUOUS" and field["required"]
    assert wire.igst_amount is None
    assert critical_check(checked.document).code == "TAX_UNCLEAR"
    from app.extended_verification import financial_conflicts

    frozen = verify(wire, pdf, version="extended-diagnostics-7")
    assert frozen.findings == ()  # Saved verifier semantics stay frozen.
    assert financial_conflicts(frozen) == ["igst_amount"]  # Authorization still holds.


@pytest.mark.parametrize("frozen", [False, True])
def test_ambiguous_null_gst_workflow_never_posts_or_spends_a_repair_call(
    workflow_db, monkeypatch, frozen
):
    from sqlalchemy import func, select
    from sqlalchemy.orm import Session

    from app import workflow
    from app.financial_models import ApprovalLedger
    from app.models import Run
    from tests.test_ordinary_invoices import ordinary_masters
    from tests.test_ordinary_workflow import processor
    from tests.workflow_helpers import execute, intake

    ordinary_masters(workflow_db)
    pdf, wire = conflicting_gst_invoice()
    ident = intake(workflow_db, pdf)
    handler, calls = processor(workflow_db, wire)
    if frozen:
        monkeypatch.setattr(workflow, "VERIFIER_VERSION", "extended-diagnostics-7")
    execute(workflow_db, handler)
    with Session(workflow_db) as session:
        run = session.get(Run, ident)
        assert run.job_state == "WAITING_REVIEW" and run.decision == "NEEDS_REVIEW"
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    assert len(calls) == 1


@pytest.mark.parametrize(
    "quote,page,valid",
    [("2.00 pcs", 1, True), ("2.00 kg", 1, False), ("9.00 pcs", 1, False), ("2.00 pcs", 2, False)],
)
def test_quantity_quote_can_span_adjacent_unit_only_when_present_on_the_correct_page(
    quote, page, valid
):
    pdf, raw = semantic_invoice()
    data = raw.model_dump()
    data["evidence"] = [e for e in data["evidence"] if e["field"] != "lines.1.quantity"]
    data["evidence"].append(
        dict(field="lines.1.quantity", raw_text=quote, page=page, method="TEXT")
    )
    wire = InvoiceExtractionV12.model_validate(data)
    checked = verify(wire, pdf)
    assert (
        next(p for p in checked.provenance if p["field"] == "lines.1.quantity")["grounded"] is valid
    )
    assert wire.evidence[-1].raw_text == quote
    frozen = verify(InvoiceExtractionV1.model_validate(data), pdf, version="semantic-diagnostics-6")
    assert not next(p for p in frozen.provenance if p["field"] == "lines.1.quantity")["grounded"]
