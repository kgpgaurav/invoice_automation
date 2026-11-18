"""Reproducible synthetic PDF inputs, never completed financial results."""

from copy import deepcopy
from datetime import date
from decimal import Decimal
from uuid import uuid4

import pymupdf
from sqlalchemy.orm import Session

from app.approval import register_policy
from app.finance_contracts import FinancialPolicy
from app.financial_models import POLine, PurchaseOrder, Vendor
from scripts.extraction_fixtures import FIELDS, expected_invoice


def rows(data):
    result = [(FIELDS[k], str(v)) for k, v in data.items() if k != "line_items" and v is not None]
    for line in data["line_items"]:
        result.append((f"Line {line['line_no']} Number", str(line["line_no"])))
        result.extend(
            (f"Line {line['line_no']} {FIELDS[k]}", str(v))
            for k, v in line.items()
            if k != "line_no" and v is not None
        )
    return result


def pdf(data, scanned=False):
    with pymupdf.open() as doc:
        page = doc.new_page(width=595, height=842)
        page.draw_rect((0, 0, 595, 80), color=None, fill=(0.08, 0.22, 0.17))
        page.insert_text((38, 44), "ASTER / TAX INVOICE", fontsize=20, color=(1, 1, 1))
        page.insert_text((38, 100), "DISPOSABLE DEMO DOCUMENT / NOT PAYABLE", fontsize=9)
        for i, (label, value) in enumerate(rows(data)):
            page.insert_text((38, 130 + i * 23), f"{label}: {value}", fontsize=10)
        page.insert_text((38, 816), "Synthetic PS-1 demonstration / Page 1", fontsize=9)
        if not scanned:
            return doc.tobytes()
        pix = page.get_pixmap(matrix=pymupdf.Matrix(2, 2))
        with pymupdf.open() as scan:
            scan.new_page(width=595, height=842).insert_image(
                (0, 0, 595, 842), stream=pix.tobytes("png")
            )
            return scan.tobytes()


def dataset():
    h1 = expected_invoice()
    e2 = dict(
        deepcopy(h1),
        vendor_name="Aster Technology Services",
        vendor_tax_id="07ABCDE1234F1Z5",
        invoice_number="REVIEW-001",
        po_reference=None,
    )
    e4 = dict(deepcopy(h1), invoice_number="BANK-001", bank_account_last4="9876")
    duplicate = dict(deepcopy(h1), invoice_number="INV 001")
    created_po = dict(deepcopy(h1), invoice_number="CREATED-001", po_reference="PO-CREATED")
    partials = []
    for number, qty in (("PART-001", "70"), ("PART-002", "35")):
        net = str(Decimal(qty) * 1000)
        data = dict(
            deepcopy(h1),
            vendor_name="Aster Industrial Supplies",
            vendor_tax_id="29ABCDE1234F1Z5",
            invoice_number=number,
            po_reference="PO-PARTIAL",
            subtotal_net=net,
            tax_total="0.00",
            total_gross=net,
        )
        data["line_items"][0].update(
            quantity=qty, tax_rate="0", net_amount=net, tax_amount="0.00", gross_amount=net
        )
        partials.append(data)
    values = [
        ("H1", h1, False),
        ("E1-prior", partials[0], False),
        ("E1", partials[1], False),
        ("E2", e2, False),
        ("E3-text", duplicate, False),
        ("E3-scan", duplicate, True),
        ("E4", e4, False),
        ("PO-created-invoice", created_po, False),
    ]
    return [(name, pdf(data, scanned), data) for name, data, scanned in values]


def seed(engine):
    register_policy(engine, FinancialPolicy(), "disposable-demo-setup")
    with Session(engine) as session, session.begin():
        for name, tax, orders in (
            ("Aster Office Supplies", "27ABCDE1234F1Z5", [("PO-001", "50000", "18")]),
            ("Aster Industrial Supplies", "29ABCDE1234F1Z5", [("PO-PARTIAL", "100000", "0")]),
            (
                "Aster Technology Services",
                "07ABCDE1234F1Z5",
                [("PO-SELECT-001", "25000", "18"), ("PO-SELECT-002", "40000", "18")],
            ),
        ):
            vendor = Vendor(
                id=uuid4(),
                legal_name=name,
                jurisdiction="IN",
                tax_id_original=tax,
                normalized_tax_id=tax,
                status="ACTIVE",
                bank_last4="1234",
            )
            session.add(vendor)
            session.flush()
            for number, cap, rate in orders:
                po = PurchaseOrder(
                    id=uuid4(),
                    po_number=number,
                    vendor_id=vendor.id,
                    issued_at=date(2026, 10, 1),
                    approved_cap_gross=Decimal(cap),
                )
                session.add(po)
                session.flush()
                session.add(
                    POLine(
                        po_id=po.id,
                        line_no=1,
                        sku="PAPER",
                        description="Office paper",
                        quantity=Decimal("100"),
                        unit_price=Decimal("1000"),
                        tax_rate=Decimal(rate),
                    )
                )
