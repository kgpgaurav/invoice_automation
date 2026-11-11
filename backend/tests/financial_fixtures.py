"""Synthetic verified data, not extracted invoices or a production evidence verifier."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

from sqlalchemy.orm import Session

from app.approval import approve, register_policy
from app.finance_contracts import FinancialDocument, FinancialPolicy, money
from app.financial_models import POLine, PurchaseOrder, Vendor
from app.intake import create_intake

D = Decimal
POLICY = FinancialPolicy()


def document(number="INV-001", qty="10", price="1000", rate="18", **updates):
    net = money(D(qty) * D(price))
    tax = money(net * D(rate) / 100)
    data = dict(
        vendor_name="Aster Office Supplies",
        vendor_tax_id="27ABCDE1234F1Z5",
        invoice_number=number,
        invoice_date="2026-11-01",
        po_reference="PO-001",
        currency="INR",
        subtotal_net=str(net),
        tax_total=str(tax),
        total_gross=str(net + tax),
        tax_mode="EXCLUSIVE",
        bank_account_last4="1234",
        lines=[
            dict(
                line_no=1,
                sku="PAPER",
                description="Office paper",
                quantity=qty,
                unit_price=price,
                price_basis="NET",
                tax_rate=rate,
                net_amount=str(net),
                tax_amount=str(tax),
                gross_amount=str(net + tax),
            )
        ],
    )
    data.update(updates)
    return evidenced(data)


def evidenced(data):
    data = dict(data)
    fields = {
        key: value
        for key, value in data.items()
        if key not in ("lines", "evidence") and value is not None
    }
    for line in data.get("lines", []):
        fields.update(
            {
                f"lines.{line['line_no']}.{key}": value
                for key, value in line.items()
                if value is not None and key != "line_no"
            }
        )
    data["evidence"] = [
        dict(field=key, raw_text=str(value), page=1, method="TEXT", verified=True)
        for key, value in fields.items()
    ]
    return FinancialDocument.model_validate(data)


def changed(doc, **updates):
    data = doc.model_dump(mode="json")
    data.update(updates)
    return evidenced(data)


def masters(engine, cap="50000", rate="18", qty="100"):
    register_policy(engine, POLICY, "fixture-seed")
    with Session(engine) as s, s.begin():
        vendor = Vendor(
            id=uuid4(),
            legal_name="Aster Office Supplies",
            jurisdiction="IN",
            tax_id_original="27ABCDE1234F1Z5",
            normalized_tax_id="27ABCDE1234F1Z5",
            bank_last4="1234",
        )
        s.add(vendor)
        s.flush()
        po = PurchaseOrder(
            id=uuid4(),
            po_number="PO-001",
            vendor_id=vendor.id,
            issued_at=date(2026, 10, 1),
            approved_cap_gross=D(cap),
        )
        s.add(po)
        s.flush()
        line = POLine(
            id=uuid4(),
            po_id=po.id,
            line_no=1,
            sku="PAPER",
            description="Office paper",
            quantity=D(qty),
            unit_price=D("1000"),
            tax_rate=D(rate),
        )
        s.add(line)
        return vendor.id, po.id, line.id


def run(engine, pdf):
    return create_intake(engine, pdf, "fixture:financial-domain", str(uuid4())).run_id


def assess(engine, pdf, doc):
    return approve(engine, run(engine, pdf), doc, POLICY.version)
