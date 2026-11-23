"""Read-only review context, separate from financial authorization and source trust."""

import re
from decimal import Decimal, localcontext

from sqlalchemy import func, select

from app.finance_contracts import normalized_name, tax_key
from app.finance_rules import match_lines
from app.financial_models import ApprovalLedger, POLine, Vendor
from app.read_contracts import ReviewComparison


def decimal_value(value):
    text = str(value)
    if len(text) > 40 or not re.fullmatch(r"-?[0-9]{1,24}(?:\.[0-9]{1,12})?", text):
        return None
    return Decimal(text)


def comparisons(session, fields, document, po, observations):
    rows, seen = [], set()
    by_path = {f.field: f for f in fields}

    def add(
        path,
        title,
        expected,
        label,
        explanation,
        *,
        numeric=False,
        normalize=lambda x: x,
        remaining=False,
        provenance="CURRENT_MASTER",
        context_only=False,
        currency=None,
    ):
        field = by_path.get(path)
        if field is None:
            return
        value = field.value
        difference = None
        if value is None:
            status = "missing" if field.required_for_approval else "information"
        elif expected is None:
            status = "unverified" if field.verification != "verified" else "information"
        elif numeric:
            actual, wanted = decimal_value(value), decimal_value(expected)
            if actual is None or wanted is None:
                status = "unverified"
            else:
                with localcontext() as ctx:
                    ctx.prec = 48
                    difference = str(actual - wanted)
                    same = Decimal(difference) <= 0 if remaining else Decimal(difference) == 0
                status = "matches" if same else "different"
        else:
            normalized = normalize(value)
            status = (
                "matches"
                if normalized is not None and normalized == normalize(str(expected))
                else "different"
            )
        if context_only:
            status = "information"
        elif status == "matches" and field.verification != "verified":
            status = "unverified"
        rows.append(
            ReviewComparison(
                field=path,
                title=title,
                invoice_value=value,
                expected_value=str(expected) if expected is not None else None,
                expected_label=label,
                status=status,
                source_verification=field.verification,
                pages=field.pages,
                difference=difference,
                currency=currency,
                provenance=provenance,
                description=explanation,
            )
        )
        seen.add(path)

    vendor = session.get(Vendor, po.vendor_id) if po else None
    if vendor:
        add(
            "vendor_name",
            "Supplier name",
            vendor.legal_name,
            "Vendor registered for " + po.po_number,
            "Compare the supplier, not the buyer's billing details.",
            normalize=normalized_name,
        )
        add(
            "vendor_tax_id",
            "Supplier GSTIN",
            vendor.normalized_tax_id,
            "Registered supplier GSTIN",
            "Optional when absent from the PDF. A printed supplier GSTIN must match this record.",
            normalize=tax_key,
        )
        add(
            "po_reference",
            "Purchase order",
            po.po_number,
            "Purchase order record",
            "A missing reference needs an authorized PO selection; the model cannot invent it.",
        )
        add(
            "currency",
            "Currency",
            po.currency,
            "PO currency",
            "Different or unsupported currencies require review; no conversion is performed.",
        )
        if observations and "remaining_gross" in observations:
            add(
                "total_gross",
                "Invoice amount / available funds",
                observations["remaining_gross"],
                "Available at assessment",
                "This is the recorded pre-decision allowance. "
                "A positive difference is the excess, not an amount already paid.",
                numeric=True,
                remaining=True,
                provenance="RECORDED_ASSESSMENT",
                currency=observations["currency"],
            )
        else:
            committed = session.scalar(
                select(func.coalesce(func.sum(ApprovalLedger.gross), 0)).where(
                    ApprovalLedger.po_id == po.id
                )
            )
            reconciled = committed == po.committed_gross
            add(
                "total_gross",
                "Invoice amount / available funds",
                po.approved_cap_gross - committed if reconciled else None,
                "Current remaining PO funds (context)",
                "Current PO context only; this balance was not recorded in the assessment."
                if reconciled
                else "PO counter and ledger disagree; available funds cannot be verified.",
                numeric=True,
                remaining=True,
                context_only=True,
                currency=po.currency,
            )
        if document:
            lines = session.scalars(select(POLine).where(POLine.po_id == po.id)).all()
            _, pairs, error = match_lines(document, lines)
            if error is None:
                with localcontext() as ctx:
                    ctx.prec = 48
                    for actual, expected in pairs:
                        prefix = f"lines.{actual.line_no}."
                        price = expected.unit_price
                        if actual.price_basis == "GROSS":
                            price *= 1 + expected.tax_rate / 100
                        add(
                            prefix + "unit_price",
                            f"Line {actual.line_no} unit price",
                            price,
                            f"PO line {expected.line_no} price ({actual.price_basis})",
                            "Price differences follow the recorded financial policy.",
                            numeric=True,
                            currency=po.currency,
                        )
                        add(
                            prefix + "tax_rate",
                            f"Line {actual.line_no} tax rate (%)",
                            expected.tax_rate,
                            f"PO line {expected.line_no} tax rate",
                            "Tax treatment must also reconcile with source amounts.",
                            numeric=True,
                        )
                        add(
                            prefix + "quantity",
                            f"Line {actual.line_no} quantity",
                            expected.quantity - expected.committed_quantity,
                            f"Current remaining PO line {expected.line_no} quantity (context)",
                            "Current allowance only. The checklist records whether "
                            "quantity validation executed.",
                            numeric=True,
                            remaining=True,
                            context_only=True,
                        )
    # Include every unresolved essential source field even when no master can be matched.
    for field in fields:
        if (
            field.field not in seen
            and field.required_for_approval
            and field.verification != "verified"
        ):
            title = field.field.replace("lines.", "Line ").replace("_", " ")
            add(
                field.field,
                title,
                None,
                "PDF evidence required",
                "Inspect the original PDF. Request corrected information "
                "if this value cannot be established.",
                provenance="SOURCE_ONLY",
            )
    return rows
