"""Independent generic layouts and negative source associations; no private PDFs."""

from decimal import Decimal

import pymupdf
import pytest

from app.evidence_verification import verify
from app.extraction_schema import InvoiceExtractionV1
from app.finance_rules import critical_check
from app.pdf_input import inspect_pdf
from app.source_layout import Span
from app.source_layout_v6 import inspect_layout, wrapped_prices


def semantic_invoice(
    *, numbered=True, printed_gross="38.50", date="02/02/2024", total_display="47.30"
):
    with pymupdf.open() as doc:
        page = doc.new_page()

        def text(x, y, value):
            page.insert_text((x, y), str(value), fontsize=9)

        for x, y, value in [
            (40, 45, "Invoice no: GN-114"),
            (40, 65, "Date of issue:"),
            (150, 65, date),
            (40, 100, "Seller:"),
            (300, 100, "Client:"),
            (40, 120, "Harbor Tools Ltd"),
            (300, 120, "Different Buyer Ltd"),
            (40, 140, "GSTIN: 27AAAAA1111A1Z5"),
            (300, 140, "GSTIN: 29BBBBB2222B1Z6"),
            (40, 170, "PO: AUTH-7"),
            (40, 210, "ITEMS"),
            (40, 240, "No."),
            (85, 240, "Description"),
            (275, 240, "Qty"),
            (305, 240, "UM"),
            (350, 240, "Net Price"),
            (410, 240, "Net Worth"),
            (465, 240, "VAT %"),
            (535, 240, "Gross"),
            (535, 250, "Worth"),
            (85, 280, "Steel"),
            (85, 291, "fasteners"),
            (275, 280, "2.00"),
            (305, 280, "pcs"),
            (350, 280, "17.50"),
            (410, 280, "35.00"),
            (465, 280, "10%"),
            (535, 280, printed_gross),
            (85, 320, "Washers"),
            (275, 320, "1.00"),
            (305, 320, "pcs"),
            (350, 320, "8.00"),
            (410, 320, "8.00"),
            (465, 320, "10%"),
            (535, 320, "8.80"),
            (40, 365, "SUMMARY"),
            (410, 390, "Net Worth"),
            (475, 390, "VAT"),
            (520, 390, "Gross Worth"),
            (417, 410, "43.00"),
            (480, 410, "4.30"),
            (544, 410, "47.30"),
            (40, 440, "Total"),
            (400, 440, "INR 43.00"),
            (470, 440, "INR 4.30"),
            (530, 440, "INR " + total_display),
        ]:
            text(x, y, value)
        if numbered:
            text(40, 280, "1.")
            text(40, 320, "2.")
        content = doc.tobytes()
    lines = []
    for i, (description, qty, price, net, gross) in enumerate(
        [
            ("Steel fasteners", "2.00", "17.50", "35.00", "38.50"),
            ("Washers", "1.00", "8.00", "8.00", "8.80"),
        ],
        1,
    ):
        lines.append(
            dict(
                line_no=i if numbered else None,
                sku=None,
                po_line_no=None,
                description=description,
                quantity=qty,
                unit_price=price,
                price_basis="NET",
                tax_rate="10",
                net_amount=net,
                tax_amount=None,
                gross_amount=gross,
            )
        )
    fields = dict(
        vendor_name="Harbor Tools Ltd",
        vendor_tax_id="27AAAAA1111A1Z5",
        invoice_number="GN-114",
        invoice_date="2024-02-02" if date == "02/02/2024" else None,
        po_reference="AUTH-7",
        currency="INR",
        subtotal_net="43.00",
        tax_total="4.30",
        total_gross="47.30",
        tax_mode="UNKNOWN",
        bank_account_last4=None,
        line_items=lines,
    )
    quotes = {k: str(v) for k, v in fields.items() if isinstance(v, str) and v != "UNKNOWN"}
    if fields["invoice_date"]:
        quotes["invoice_date"] = date
    for i, line in enumerate(lines, 1):
        quotes.update(
            {f"lines.{i}.{k}": str(v) for k, v in line.items() if v is not None and k != "line_no"}
        )
    return content, InvoiceExtractionV1.model_validate(
        dict(
            fields,
            evidence=[
                dict(field=k, raw_text=v, page=1, method="VISION") for k, v in quotes.items()
            ],
        )
    )


@pytest.mark.parametrize("numbered", [True, False])
def test_semantic_columns_multiline_description_and_summary_are_grounded(numbered):
    pdf, wire = semantic_invoice(numbered=numbered)
    checked = verify(wire, pdf)
    assert checked.findings == () and critical_check(checked.document) is None
    assert checked.document.total_gross == Decimal("47.30")
    assert checked.document.vendor_name == "Harbor Tools Ltd"
    assert checked.document.lines[0].description == "Steel fasteners"
    assert checked.document.lines[0].tax_amount == Decimal("3.50")
    assert verify(wire, pdf, version="layout-diagnostics-5").needs_review


def test_contradictory_printed_gross_cannot_be_hidden_by_correct_calculation():
    pdf, wire = semantic_invoice(printed_gross="99.00", numbered=False)
    checked = verify(wire, pdf)
    assert checked.needs_review and critical_check(checked.document)
    gross = next(p for p in checked.provenance if p["field"] == "lines.1.gross_amount")
    assert not gross["grounded"] and gross["state"] == "AMBIGUOUS"


@pytest.mark.parametrize(
    "path,value",
    [
        ("vendor_tax_id", "29BBBBB2222B1Z6"),
        ("total_gross", "43.00"),
    ],
)
def test_buyer_identity_and_net_total_do_not_verify_as_supplier_or_gross(path, value):
    pdf, wire = semantic_invoice()
    checked = verify(wire.model_copy(update={path: value}), pdf)
    assert checked.needs_review
    assert not next(p for p in checked.provenance if p["field"] == path)["grounded"]


def test_ambiguous_numeric_issue_date_remains_ambiguous():
    pdf, wire = semantic_invoice(date="07/10/2023")
    checked = verify(wire, pdf)
    assert checked.needs_review and critical_check(checked.document)
    assert (
        next(p for p in checked.provenance if p["field"] == "invoice_date")["state"] == "AMBIGUOUS"
    )
    assert checked.document.invoice_date is None


def test_missing_gross_cell_is_not_replaced_by_a_calculated_gross():
    pdf, wire = semantic_invoice(printed_gross="not legible")
    checked = verify(wire, pdf)
    assert checked.needs_review
    assert not next(p for p in checked.provenance if p["field"] == "lines.1.gross_amount")[
        "grounded"
    ]


def test_wrong_citation_page_is_still_unverified_after_number_normalization():
    pdf, wire = semantic_invoice()
    changed = wire.model_copy(
        update={"evidence": [e.model_copy(update={"page": 2}) for e in wire.evidence]}
    )
    assert verify(changed, pdf).needs_review


def test_only_tightly_joined_decimal_fragments_in_price_cells_are_normalized():
    spans = [
        Span(1, 100, 10, 120, 20, "Qty"),
        Span(1, 150, 10, 180, 20, "Rate"),
        Span(1, 220, 10, 250, 20, "Amount"),
        Span(1, 105, 35, 120, 45, "2"),
        Span(1, 155, 35, 180, 45, "1000.0"),
        Span(1, 175, 45.5, 180, 55.5, "0"),
    ]
    joined, fragments = wrapped_prices(spans)
    assert fragments == {"1000.00": "1000.0\n0"}
    assert any(s.text == "1000.00" for s in joined)
    separate = spans[:-1] + [Span(1, 170, 45.5, 180, 55.5, "12.00")]
    assert wrapped_prices(separate)[1] == {}
    next_row = spans + [Span(1, 105, 45.5, 120, 55.5, "1")]
    assert wrapped_prices(next_row)[1] == {}


def test_quantity_cell_cannot_ground_another_columns_equal_value():
    pdf, wire = semantic_invoice()
    data = wire.model_dump()
    data["line_items"][0]["quantity"] = "17.50"
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert checked.needs_review
    layout = inspect_layout(pdf, inspect_pdf(pdf).pages)
    assert layout.amount("lines.1.quantity") == 2


def test_source_supported_percent_suffix_is_normalized_without_changing_raw_extraction():
    pdf, wire = semantic_invoice()
    data = wire.model_dump()
    for line in data["line_items"]:
        line["tax_rate"] = "10%"
    raw = InvoiceExtractionV1.model_validate(data)
    checked = verify(raw, pdf)
    assert checked.findings == ()
    assert checked.document.lines[0].tax_rate == Decimal("10")
    assert raw.line_items[0].tax_rate == "10%"
    assert (
        next(p for p in checked.provenance if p["field"] == "lines.1.tax_rate")["original_value"]
        == "10%"
    )
    assert verify(raw, pdf, version="layout-diagnostics-5").needs_review


def test_contextual_header_cell_citations_require_known_association_and_page():
    pdf, wire = semantic_invoice()
    data = wire.model_dump()
    prefixes = {
        "vendor_name": "Seller: ",
        "lines.1.quantity": "Qty ",
        "lines.1.unit_price": "Net Price ",
    }
    for evidence in data["evidence"]:
        evidence["raw_text"] = prefixes.get(evidence["field"], "") + evidence["raw_text"]
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert checked.findings == ()


def test_percentage_quantity_is_not_silently_normalized_into_units():
    pdf, wire = semantic_invoice()
    data = wire.model_dump()
    data["line_items"][0]["quantity"] = "2%"
    checked = verify(InvoiceExtractionV1.model_validate(data), pdf)
    assert checked.needs_review and checked.document is None


def test_summary_heading_total_cell_citations_are_independently_associated():
    pdf, wire = semantic_invoice()
    labels = {
        "subtotal_net": "Total Net Worth INR 43.00",
        "tax_total": "Total VAT INR 4.30",
        "total_gross": "Total Gross Worth INR 47.30",
    }
    data = wire.model_dump()
    for evidence in data["evidence"]:
        evidence["raw_text"] = labels.get(evidence["field"], evidence["raw_text"])
    assert verify(InvoiceExtractionV1.model_validate(data), pdf).findings == ()


def test_conflicting_final_total_cannot_be_discarded_for_the_summary_row():
    pdf, wire = semantic_invoice(total_display="99.00")
    checked = verify(wire, pdf)
    assert checked.needs_review and critical_check(checked.document)
    assert (
        next(p for p in checked.provenance if p["field"] == "total_gross")["state"] == "AMBIGUOUS"
    )
