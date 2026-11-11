"""Pure deterministic matching and checks, independent of SQLAlchemy and AI."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, localcontext
from typing import Any

from app.finance_contracts import (
    FinancialDocument,
    FinancialPolicy,
    invoice_key,
    money,
    normalized_name,
    price_allowed,
    tax_key,
)


@dataclass(frozen=True)
class Result:
    decision: str
    code: str
    reason: str


def review(code, reason):
    return Result("NEEDS_REVIEW", code, reason)


def reject(code, reason):
    return Result("REJECTED", code, reason)


def resolve_vendor(document, vendors, orders):
    """Duck-typed read-only master snapshots; never infer identity from PDF hash."""
    if document.vendor_tax_id is not None:
        key = tax_key(document.vendor_tax_id)
        matches = [
            v for v in vendors if key and v.normalized_tax_id == key and v.jurisdiction == "IN"
        ]
    else:
        matches = [
            v
            for v in vendors
            if document.vendor_name
            and normalized_name(v.legal_name) == normalized_name(document.vendor_name)
            and any(p.po_number == document.po_reference and p.vendor_id == v.id for p in orders)
        ]
    if len(matches) != 1:
        return None, review(
            "VENDOR_UNKNOWN", "Verify the supplier identity against the vendor master."
        )
    vendor = matches[0]
    if not document.vendor_name or normalized_name(vendor.legal_name) != normalized_name(
        document.vendor_name
    ):
        return None, review(
            "VENDOR_ID_MISMATCH", "Printed supplier name conflicts with verified identity."
        )
    return vendor, None


def match_po(document, vendor, orders):
    if not document.po_reference:
        candidates = [p for p in orders if p.vendor_id == vendor.id and p.status == "OPEN"]
        return None, review(
            "PO_AMBIGUOUS" if len(candidates) > 1 else "PO_MISSING",
            "Select and verify an explicit purchase order; inferred matches cannot approve.",
        )
    matches = [p for p in orders if p.po_number == document.po_reference]
    if len(matches) != 1:
        return None, review("PO_MISSING", "Verify the printed purchase order reference.")
    po = matches[0]
    if po.vendor_id != vendor.id:
        return None, reject(
            "PO_VENDOR_MISMATCH", "Confirmed purchase order belongs to another supplier."
        )
    return po, None


def match_lines(document, lines):
    allocations: dict[Any, Decimal] = {}
    pairs = []
    for line in document.lines:
        if line.po_line_no is not None:
            candidates = [
                p
                for p in lines
                if p.line_no == line.po_line_no and (line.sku is None or line.sku == p.sku)
            ]
        elif line.sku is not None:
            candidates = [p for p in lines if line.sku == p.sku]
        else:
            candidates = [
                p
                for p in lines
                if normalized_name(line.description) == normalized_name(p.description)
            ]
        if len(candidates) != 1:
            return (
                {},
                [],
                review("LINE_AMBIGUOUS", "Verify an unambiguous PO line for every invoice line."),
            )
        po_line = candidates[0]
        pairs.append((line, po_line))
        if line.quantity is not None:
            allocations[po_line.id] = allocations.get(po_line.id, Decimal("0")) + line.quantity
    return allocations, pairs, None


def critical_check(document: FinancialDocument):
    headers = (
        "vendor_name",
        "invoice_number",
        "invoice_date",
        "currency",
        "subtotal_net",
        "tax_total",
        "total_gross",
        "tax_mode",
    )
    if (
        any(getattr(document, field) is None for field in headers)
        or not invoice_key(document.invoice_number or "")
        or not document.lines
        or document.total_gross == 0
    ):
        return review(
            "CRITICAL_FIELD_MISSING", "Critical invoice fields or line evidence are missing."
        )
    if len({line.line_no for line in document.lines}) != len(document.lines):
        return review("LINE_AMBIGUOUS", "Invoice line numbers must be unique.")
    required = set(headers)
    for field in ("vendor_tax_id", "po_reference", "bank_account_last4"):
        if getattr(document, field) is not None:
            required.add(field)
    fields = (
        "quantity",
        "unit_price",
        "price_basis",
        "tax_rate",
        "net_amount",
        "tax_amount",
        "gross_amount",
    )
    for line in document.lines:
        if any(getattr(line, field) is None for field in fields):
            return review(
                "CRITICAL_FIELD_MISSING",
                "Quantity, prices and tax evidence are required for every line.",
            )
        required.update(f"lines.{line.line_no}.{field}" for field in fields)
        required.add(f"lines.{line.line_no}.description")
        for field in ("sku", "po_line_no"):
            if getattr(line, field) is not None:
                required.add(f"lines.{line.line_no}.{field}")
    verified = {e.field for e in document.evidence if e.verified}
    if not required <= verified:
        return review(
            "UNVERIFIED_TOTAL", "Critical header or line fields lack verified source evidence."
        )
    return None


def evaluate(document, vendor, po, lines, policy: FinancialPolicy, today: date):
    with localcontext() as context:
        context.prec = 48
        return _evaluate(document, vendor, po, lines, policy, today)


def _evaluate(document, vendor, po, lines, policy: FinancialPolicy, today: date):
    """Return a provisional verdict and aggregated quantity allocation; never mutate masters."""
    error = critical_check(document)
    if error:
        return error, {}
    if document.currency != "INR" or po.currency != document.currency:
        return review(
            "UNSUPPORTED_CURRENCY", "Only explicitly evidenced INR invoices and POs can approve."
        ), {}
    if vendor.status != "ACTIVE":
        return review(
            "VENDOR_INACTIVE", "Supplier is inactive; verify its authorization before processing."
        ), {}
    if document.bank_account_last4 and document.bank_account_last4 != vendor.bank_last4:
        return review(
            "BANK_MISMATCH", "Verify the supplier's changed bank details. No funds were posted."
        ), {}
    if po.status == "CANCELLED":
        return reject("PO_CLOSED", "The purchase order is confirmed cancelled."), {}
    if po.status != "OPEN" or (po.expires_at is not None and today > po.expires_at):
        return review(
            "PO_CLOSED", "Purchase order is closed or expired; verify an authorized amendment."
        ), {}
    if document.invoice_date > today:
        return review("FUTURE_DATE", "Verify the future invoice date."), {}
    if document.invoice_date < po.issued_at or po.issued_at > today:
        return review("DATE_BEFORE_PO", "Invoice date precedes the purchase order issue date."), {}
    remaining = po.approved_cap_gross - po.committed_gross
    if document.total_gross > remaining:
        excess = document.total_gross - remaining
        return review(
            "PO_CAP_EXCEEDED",
            f"Invoice requests INR {document.total_gross:.2f}; PO remaining "
            f"INR {remaining:.2f}; excess INR {excess:.2f}. No funds were posted.",
        ), {}
    allocations, pairs, error = match_lines(document, lines)
    if error:
        return error, {}
    if document.tax_mode == "UNKNOWN":
        return review(
            "TAX_UNCLEAR", "Verify whether the invoice tax is inclusive or exclusive."
        ), {}
    for line, p in pairs:
        if line.price_basis == "GROSS" and document.tax_mode != "INCLUSIVE":
            return review(
                "TAX_UNCLEAR", "Gross unit prices require an explicit inclusive tax convention."
            ), {}
        net_unit = (
            line.unit_price
            if line.price_basis == "NET"
            else (line.unit_price / (1 + line.tax_rate / 100))
        )
        if line.tax_rate != p.tax_rate:
            return review(
                "TAX_UNCLEAR", "Invoice tax rate conflicts with the approved PO line."
            ), {}
        if not price_allowed(net_unit, p.unit_price, policy):
            return review(
                "PRICE_VARIANCE", "Invoice net unit price differs from the approved PO line."
            ), {}
        expected_net = money(line.quantity * net_unit)
        if abs(line.net_amount - expected_net) > policy.line_rounding_abs_cap_inr:
            return review(
                "ARITHMETIC_MISMATCH",
                "Invoice line net amount does not reconcile to quantity × price.",
            ), {}
        if (
            line.tax_amount != money(line.net_amount * line.tax_rate / 100)
            or line.gross_amount != line.net_amount + line.tax_amount
        ):
            return review(
                "TAX_UNCLEAR", "Invoice line net, tax and gross amounts do not reconcile."
            ), {}
    if (
        sum((line.net_amount for line in document.lines), Decimal("0")) != document.subtotal_net
        or sum((line.tax_amount for line in document.lines), Decimal("0")) != document.tax_total
        or document.subtotal_net + document.tax_total != document.total_gross
    ):
        return review(
            "ARITHMETIC_MISMATCH", "Invoice line sums and printed header totals do not reconcile."
        ), {}
    for p in lines:
        if allocations.get(p.id, Decimal("0")) > p.quantity - p.committed_quantity:
            return review(
                "QTY_EXCEEDED", "Invoice quantity exceeds the uncommitted PO-line quantity."
            ), {}
    return Result(
        "APPROVED",
        "VALIDATED",
        f"Invoice validated for INR {document.total_gross:.2f}; "
        f"PO remaining after approval INR {remaining - document.total_gross:.2f}. "
        "Approved for downstream processing; no payment executed.",
    ), allocations
