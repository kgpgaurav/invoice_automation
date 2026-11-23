"""Independent ordinary-table PDFs and model claims; no production fixture adapter."""

from decimal import Decimal

import pymupdf

from app.extraction_schema import InvoiceExtractionV1


def invoice(
    *,
    po="PUR-6042",
    number="NS-2026-001",
    qty="3",
    rate="18",
    layout="stacked",
    tax=True,
    numbered=True,
    currency="INR",
    gst="27LMNOP1234Q1Z6",
    inclusive=False,
    total_adjust="0",
):
    net = Decimal(qty) * Decimal("2500")
    tax_amount = net * Decimal(rate) / 100
    gross = net + tax_amount + Decimal(total_adjust)
    vendor = "Northstar Components Ltd"
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)

        def text(x, y, value, size=10):
            page.insert_text((x, y), str(value), fontsize=size)

        text(40, 50, vendor, 13)
        text(40, 70, "17 Supply Road")
        text(40, 90, "India")
        text(40, 110, "GSTIN " + gst)
        text(390, 50, "TAX INVOICE", 16)
        text(390, 75, "Invoice# " + number)
        text(40, 155, "Bill To:")
        text(40, 175, "Independent Buyer Ltd")
        text(40, 195, "GSTIN 29ZZZZZ1234Q1Z9")
        if po:
            text(40, 215, "PO: " + po)
        text(355, 155, "Invoice Date:")
        text(445, 155, "Nov 20, 2026")
        text(355, 180, "Currency: " + currency)
        headers = [(40, "#"), (70, "Item Description"), (295, "Qty"), (350, "Rate")]
        if tax and layout != "footer":
            headers += [(425, "IGST" if layout == "stacked" else "Tax (%)")]
        headers += [(520, "Amount")]
        for x, label in headers:
            text(x, 280, label)
        if numbered:
            text(40, 310, "1")
        text(70, 310, "Bearing assemblies")
        text(295, 310, qty)
        display_price = (
            Decimal("2500") * (1 + Decimal(rate) / 100) if inclusive else Decimal("2500")
        )
        text(350, 310, f"{display_price:.2f}")
        if tax and layout != "footer":
            text(425, 310, tax_amount if layout == "stacked" else rate + "%")
            if layout == "stacked":
                text(425, 326, rate)
        text(520, 310, f"{gross if inclusive else net:.2f}")
        text(405, 390, "Sub Total")
        text(510, 390, f"{net:.2f}")
        text(405, 425, "TOTAL")
        text(500, 425, f"{currency} {gross:.2f}")
        if tax and layout == "footer":
            text(405, 408, "GST (" + rate + "%)")
            text(510, 408, f"{tax_amount:.2f}")
        text(40, 500, "Synthetic test document - not payable")
        pdf = doc.tobytes()
    fields = dict(
        vendor_name=vendor,
        vendor_tax_id=gst,
        invoice_number=number,
        invoice_date="2026-11-20",
        po_reference=po,
        currency=currency,
        subtotal_net=str(net),
        tax_total=None,
        total_gross=str(gross),
        tax_mode="UNKNOWN",
        bank_account_last4=None,
        line_items=[
            dict(
                line_no=1 if numbered else None,
                sku=None,
                po_line_no=None,
                description="Bearing assemblies",
                quantity=qty,
                unit_price=f"{display_price:.2f}",
                price_basis=None,
                tax_rate=None,
                net_amount=None,
                tax_amount=None,
                gross_amount=None,
            )
        ],
    )
    snippets = {
        key: str(value)
        for key, value in fields.items()
        if key != "line_items" and value is not None and key != "tax_mode"
    }
    snippets["invoice_date"] = "Nov 20, 2026"
    snippets.update(
        {
            "lines.1.description": "Bearing assemblies",
            "lines.1.quantity": qty,
            "lines.1.unit_price": f"{display_price:.2f}",
        }
    )
    evidence = [
        dict(field=key, raw_text=value, page=1, method="VISION") for key, value in snippets.items()
    ]
    fields["evidence"] = evidence
    return pdf, InvoiceExtractionV1.model_validate(fields)
