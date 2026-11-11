"""Reproducible synthetic PDF evaluation set. No production invoices or model answers."""

import json
from pathlib import Path

import pymupdf

FIELDS = {
    "vendor_name": "Vendor Name",
    "vendor_tax_id": "Vendor Tax ID",
    "invoice_number": "Invoice Number",
    "invoice_date": "Invoice Date",
    "po_reference": "PO Reference",
    "currency": "Currency",
    "subtotal_net": "Subtotal Net",
    "tax_total": "Tax Total",
    "total_gross": "Total Gross",
    "tax_mode": "Tax Mode",
    "bank_account_last4": "Bank Account Last4",
    "sku": "SKU",
    "po_line_no": "PO Line No",
    "description": "Description",
    "quantity": "Quantity",
    "unit_price": "Unit Price",
    "price_basis": "Price Basis",
    "tax_rate": "Tax Rate",
    "net_amount": "Net Amount",
    "tax_amount": "Tax Amount",
    "gross_amount": "Gross Amount",
}


def expected_invoice(number="INV-001"):
    return dict(
        vendor_name="Aster Office Supplies",
        vendor_tax_id="27ABCDE1234F1Z5",
        invoice_number=number,
        invoice_date="2026-11-01",
        po_reference="PO-001",
        currency="INR",
        subtotal_net="10000.00",
        tax_total="1800.00",
        total_gross="11800.00",
        tax_mode="EXCLUSIVE",
        bank_account_last4="1234",
        line_items=[
            dict(
                line_no=1,
                sku="PAPER",
                po_line_no=1,
                description="Office paper",
                quantity="10",
                unit_price="1000.0000",
                price_basis="NET",
                tax_rate="18",
                net_amount="10000.00",
                tax_amount="1800.00",
                gross_amount="11800.00",
            )
        ],
    )


def fixture_set():
    result = []
    for name in ("clean", "alternate", "missing", "scan", "inconsistent", "unsupported"):
        data = expected_invoice()
        if name == "missing":
            data["invoice_date"] = None
            data["po_reference"] = None
        if name == "inconsistent":
            data["total_gross"] = "12000.00"
        if name == "unsupported":
            data["currency"] = "USD"
        rows = [
            (FIELDS[key], value)
            for key, value in data.items()
            if key != "line_items" and value is not None
        ]
        for line in data["line_items"]:
            rows.append((f"Line {line['line_no']} Number", str(line["line_no"])))
            rows.extend(
                (f"Line {line['line_no']} {FIELDS[key]}", value)
                for key, value in line.items()
                if key != "line_no" and value is not None
            )
        with pymupdf.open() as doc:
            page = doc.new_page(width=595, height=842)
            page.draw_rect((0, 0, 595, 72), color=None, fill=(0.06, 0.20, 0.19))
            page.insert_text((40, 44), "ASTER / INVOICE", fontsize=20, color=(1, 1, 1))
            page.insert_text((40, 99), "Synthetic evaluation document - not payable", fontsize=10)
            for i, (label, value) in enumerate(rows):
                if name == "alternate":
                    page.insert_text(
                        (40 + (i % 2) * 277, 130 + (i // 2) * 30), f"{label}: {value}", fontsize=8
                    )
                else:
                    page.insert_text((40, 128 + i * 22), f"{label}: {value}", fontsize=10)
            page.insert_text((40, 812), "Evaluation fixture / Page 1", fontsize=9)
            if name == "scan":
                pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
                with pymupdf.open() as scan:
                    scan.new_page(width=595, height=842).insert_image(
                        (0, 0, 595, 842), stream=pix.tobytes("png")
                    )
                    pdf = scan.tobytes()
            else:
                pdf = doc.tobytes()
        result.append((name, pdf, data))
    return result


def write_fixtures(folder):
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    manifest = []
    for name, pdf, expected in fixture_set():
        (folder / f"{name}.pdf").write_bytes(pdf)
        manifest.append({"id": name, "pdf": name + ".pdf", "expected": expected})
        with pymupdf.open(stream=pdf, filetype="pdf") as doc:
            doc[0].get_pixmap().save(folder / f"{name}.png")
    (folder / "expected.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


if __name__ == "__main__":
    write_fixtures(Path(__file__).resolve().parents[2] / ".local" / "extraction-fixtures")
