"""Presentation of recorded financial results, never a second authorization engine."""

from datetime import UTC
from decimal import Decimal, localcontext

from fastapi import HTTPException
from sqlalchemy import func, or_, select

from app.financial_models import ApprovalLedger, Invoice, POCreation, POLine, PurchaseOrder, Vendor
from app.po_totals import order_amounts
from app.read_contracts import (
    LedgerEntryView,
    POCreationView,
    PODirectoryEntry,
    POLedgerView,
    POLineView,
    POPage,
    ProcessingFailureView,
    RuleCheckView,
)


def processing_failure(run, work, usage):
    """Explain known mock errors without classifying a document or rewriting history."""
    if (
        run.job_state == "FAILED"
        and work
        and work.source_mode == "LIVE_OPENAI"
        and work.extraction_error == "BYOK_CREDENTIALS_UNAVAILABLE"
    ):
        return ProcessingFailureView(
            code="BYOK_CREDENTIALS_UNAVAILABLE",
            message="Your OpenAI connection expired, was disconnected, or is unavailable.",
            next_action="Reconnect your key and submit a new run. The original PDF remains stored.",
            provenance="PERSISTED_EXTRACTION_ERROR",
        )
    if run.job_state != "FAILED" or not work or work.source_mode != "MOCK_OPENAI":
        return None
    if work.extraction_error == "MOCK_FIXTURE_NOT_FOUND":
        provenance = "PERSISTED_EXTRACTION_ERROR"
    elif (
        work.model_id == "fixture-extraction"
        and work.extraction_error in (None, "OPENAI_HTTP_422")
        and usage
        and all(
            u.error_code == "OPENAI_HTTP_422" and u.requested_model == "fixture-extraction"
            for u in usage
        )
    ):
        # This exact older adapter returned 422 only for an unregistered fixture hash.
        provenance = "RECORDED_MOCK_HTTP_422"
    else:
        return None
    return ProcessingFailureView(
        code="MOCK_FIXTURE_NOT_FOUND",
        message=(
            "This PDF does not match a prepared mock-demo invoice. "
            "Its contents were not analyzed by an external model."
        ),
        next_action=(
            "Upload a generated scenario PDF from this demo, or explicitly set up a separate "
            "live workspace for real OpenAI extraction."
        ),
        provenance=provenance,
    )


CHECKS = (
    ("VENDOR_IDENTITY", "Vendor identity verified"),
    ("PO_MATCH", "Purchase order matched"),
    ("DUPLICATE_IDENTITY", "No approved duplicate found"),
    ("INVOICE_ARITHMETIC", "Invoice arithmetic reconciles"),
    ("TAX_RECONCILIATION", "Tax amounts reconcile"),
    ("PO_QUANTITY", "Quantity within PO allowance"),
    ("PO_BALANCE", "Invoice within remaining PO balance"),
)
CODE_CHECK = {
    "VENDOR_UNKNOWN": "VENDOR_IDENTITY",
    "VENDOR_INACTIVE": "VENDOR_IDENTITY",
    "VENDOR_BLACKLISTED": "VENDOR_IDENTITY",
    "VENDOR_ID_MISMATCH": "VENDOR_IDENTITY",
    "PO_VENDOR_MISMATCH": "PO_MATCH",
    "PO_MISSING": "PO_MATCH",
    "PO_AMBIGUOUS": "PO_MATCH",
    "PO_CLOSED": "PO_MATCH",
    "FUTURE_DATE": "PO_MATCH",
    "DATE_BEFORE_PO": "PO_MATCH",
    "DUPLICATE_APPROVED": "DUPLICATE_IDENTITY",
    "DUPLICATE_CONFLICT": "DUPLICATE_IDENTITY",
    "ARITHMETIC_MISMATCH": "INVOICE_ARITHMETIC",
    "TAX_UNCLEAR": "TAX_RECONCILIATION",
    "QTY_EXCEEDED": "PO_QUANTITY",
    "LINE_AMBIGUOUS": "PO_QUANTITY",
    "PRICE_VARIANCE": "PO_QUANTITY",
    "PO_CAP_EXCEEDED": "PO_BALANCE",
    "ALLOCATION_CONFLICT": "PO_BALANCE",
}
EXPLANATIONS = {
    "REVIEWER_REJECTED": "An authorized reviewer rejected this invoice. No new funds were posted.",
    "VALIDATED": "The recorded financial assessment passed and this invoice was allocated once.",
    "PO_CAP_EXCEEDED": (
        "This invoice exceeds the PO balance available at assessment. No funds were posted."
    ),
    "PO_AMBIGUOUS": (
        "A PO was not established. Choose one of the offered supporting purchase orders."
    ),
    "PO_MISSING": "A supporting PO could not be established. Procurement information is needed.",
    "DUPLICATE_APPROVED": (
        "This supplier invoice was already approved. A second allocation was prevented."
    ),
    "DUPLICATE_CONFLICT": (
        "This invoice identity has conflicting records. Check its amount, date and currency."
    ),
    "BANK_MISMATCH": "Bank details differ from the vendor record. Independently verify the change.",
    "VENDOR_UNKNOWN": "The supplier could not be matched reliably to the vendor master.",
    "VENDOR_INACTIVE": "The supplier is inactive. Its authorization requires review.",
    "VENDOR_BLACKLISTED": (
        "The supplier is blacklisted. New purchase orders and invoice approvals are blocked."
    ),
    "VENDOR_ID_MISMATCH": "The printed supplier name conflicts with the matched vendor identity.",
    "PO_VENDOR_MISMATCH": "The purchase order does not belong to this supplier.",
    "PO_CLOSED": "The purchase order is closed, cancelled or expired. Check the supporting record.",
    "FUTURE_DATE": "The invoice date is in the future and needs confirmation.",
    "DATE_BEFORE_PO": "The invoice date precedes the purchase order's issue date.",
    "ARITHMETIC_MISMATCH": (
        "Printed invoice amounts do not reconcile. Corrected source information is needed."
    ),
    "TAX_UNCLEAR": (
        "The tax basis, rate or amounts could not be reconciled with the supporting records."
    ),
    "QTY_EXCEEDED": "The invoice quantity exceeds the remaining PO-line allowance.",
    "LINE_AMBIGUOUS": "One or more invoice lines could not be matched unambiguously to a PO line.",
    "PRICE_VARIANCE": "An invoice unit price differs from its approved PO line.",
    "ALLOCATION_CONFLICT": (
        "PO counters and recorded allocations disagree. Financial posting was stopped."
    ),
    "UNSUPPORTED_CURRENCY": (
        "The printed currency is preserved, but only INR is supported for approval."
    ),
    "UNVERIFIED_TOTAL": (
        "Critical source evidence is unresolved. Review the document before proceeding."
    ),
    "SCANNED_DOCUMENT_REQUIRES_REVIEW": (
        "Scanned or mixed documents require human review even when all fields verify."
    ),
    "FINANCIAL_ADJUSTMENT_REQUIRES_REVIEW": (
        "Discounts, shipping, other charges or rounding adjustments require finance review."
    ),
    "CRITICAL_FIELD_MISSING": (
        "Critical invoice information is missing. A corrected document is needed."
    ),
    "REQUEST_INFO": "Source information was requested. Processing stopped without an approval.",
}


def rule_checks(assessment, ledger, fields):
    """An explicit VALIDATED certificate + committed ledger supports passes, never code absence.

    Held assessments short-circuit. Do not reconstruct unrecorded earlier/later checks from
    their ordering or today's masters. This projection does not call evaluate().
    """
    recorded = (getattr(assessment, "observations_json", None) or {}).get("rule_checks")
    if recorded:
        return [
            RuleCheckView(
                **row,
                provenance="COMMITTED_VALIDATED_ASSESSMENT"
                if ledger and assessment.decision == "APPROVED"
                else "RECORDED_ASSESSMENT",
                assessment_revision=assessment.revision,
                pages=sorted({p for f in fields if f.verification == "verified" for p in f.pages})
                if row["status"] == "passed"
                else [],
            )
            for row in recorded
        ]
    certified = bool(
        assessment
        and ledger
        and ledger.run_id == assessment.run_id
        and assessment.code == "VALIDATED"
        and assessment.decision == "APPROVED"
    )
    revision = assessment.revision if assessment else None
    result = []
    for ident, title in CHECKS:
        recorded = assessment and CODE_CHECK.get(assessment.code) == ident
        result.append(
            RuleCheckView(
                rule_id=ident,
                title=title,
                status="passed"
                if certified
                else ("failed" if assessment.decision == "REJECTED" else "requires_review")
                if recorded
                else "not_evaluated",
                description="Certified by the committed VALIDATED assessment and approval ledger."
                if certified
                else EXPLANATIONS.get(assessment.code, "See the recorded assessment.")
                if recorded
                else "No individual result was recorded. This is not a pass.",
                provenance="COMMITTED_VALIDATED_ASSESSMENT"
                if certified
                else "RECORDED_ASSESSMENT"
                if recorded
                else "NOT_RECORDED",
                assessment_revision=revision,
                finding_code=assessment.code if recorded or certified else None,
                pages=sorted({p for f in fields if f.verification == "verified" for p in f.pages})
                if certified
                else [],
            )
        )
    if assessment and assessment.code not in CODE_CHECK and not certified:
        result.insert(
            0,
            RuleCheckView(
                rule_id=assessment.code,
                title="Bank information requires independent verification"
                if assessment.code == "BANK_MISMATCH"
                else "Recorded assessment finding",
                status="failed" if assessment.decision == "REJECTED" else "requires_review",
                description=EXPLANATIONS.get(assessment.code, "Review the recorded finding."),
                provenance="RECORDED_ASSESSMENT",
                assessment_revision=revision,
                finding_code=assessment.code,
            ),
        )
    if assessment is None and fields:
        missing = [
            f.field.replace("lines.", "line ").replace("_", " ")
            for f in fields
            if f.required_for_approval and f.value in (None, "", "UNKNOWN")
        ]
        if not any(f.field.startswith(("lines.", "unidentified_lines.")) for f in fields):
            missing.append("at least one invoice line")
        unverified = [
            f.field.replace("lines.", "line ").replace("_", " ")
            for f in fields
            if f.required_for_approval and f.value is not None and f.verification != "verified"
        ]
        result[:0] = [
            RuleCheckView(
                rule_id="REQUIRED_FIELDS",
                title="Essential invoice fields",
                status="requires_review" if missing else "passed",
                description="Missing or unknown: " + ", ".join(missing)
                if missing
                else "Required values are present; source and financial checks are separate.",
                provenance="LOCAL_SOURCE_INSPECTION",
            ),
            RuleCheckView(
                rule_id="SOURCE_EVIDENCE",
                title="Fields supported by the PDF",
                status="requires_review" if unverified or missing else "passed",
                description="PDF evidence needs verification: " + ", ".join(unverified)
                if unverified
                else "Resolve missing information before financial validation."
                if missing
                else "Required field values match local PDF evidence.",
                provenance="LOCAL_SOURCE_INSPECTION",
            ),
        ]
    return result


def directory_entry(po, vendor):
    return PODirectoryEntry(
        po_id=po.id,
        po_number=po.po_number,
        vendor_name=vendor.legal_name,
        status=po.status,
        currency=po.currency,
        cap_gross=str(po.approved_cap_gross),
        committed_gross=str(po.committed_gross),
    )


def purchase_orders(session, query, after, limit):
    statement = select(PurchaseOrder, Vendor).join(Vendor, PurchaseOrder.vendor_id == Vendor.id)
    if query:
        statement = statement.where(
            or_(
                PurchaseOrder.po_number.icontains(query, autoescape=True),
                Vendor.legal_name.icontains(query, autoescape=True),
            )
        )
    count = session.scalar(select(func.count()).select_from(statement.subquery()))
    if after:
        statement = statement.where(PurchaseOrder.po_number > after)
    rows = session.execute(statement.order_by(PurchaseOrder.po_number).limit(limit + 1)).all()
    return POPage(
        items=[directory_entry(po, vendor) for po, vendor in rows[:limit]],
        next_after=rows[limit - 1][0].po_number if len(rows) > limit else None,
        total_count=count,
    )


def purchase_order_detail(session, po_id):
    row = session.execute(
        select(PurchaseOrder, Vendor)
        .join(Vendor, PurchaseOrder.vendor_id == Vendor.id)
        .where(PurchaseOrder.id == po_id)
    ).first()
    if row is None:
        raise HTTPException(404, detail="Purchase order not found.")
    po, vendor = row
    creation = session.scalar(select(POCreation).where(POCreation.po_id == po.id))
    lines = session.scalars(
        select(POLine).where(POLine.po_id == po.id).order_by(POLine.line_no)
    ).all()
    totals = order_amounts(lines)
    statement = select(ApprovalLedger, Invoice).join(Invoice).where(ApprovalLedger.po_id == po.id)
    entries = session.execute(
        statement.order_by(ApprovalLedger.created_at, ApprovalLedger.id).limit(100)
    ).all()
    count = session.scalar(select(func.count()).select_from(statement.subquery()))
    committed = session.scalar(
        select(func.coalesce(func.sum(ApprovalLedger.gross), 0)).where(
            ApprovalLedger.po_id == po.id
        )
    )
    reconciled = committed == po.committed_gross
    with localcontext() as context:
        context.prec = 48
        available = po.approved_cap_gross - Decimal(committed) if reconciled else None
    return POLedgerView(
        **directory_entry(po, vendor).model_dump(),
        issued_at=po.issued_at.isoformat(),
        expires_at=po.expires_at.isoformat() if po.expires_at else None,
        ledger_committed_gross=str(committed),
        available_gross=str(available) if available is not None else None,
        balance_reconciled=reconciled,
        allocation_count=count,
        allocations_truncated=count > len(entries),
        vendor_status=vendor.status,
        subtotal_net=str(totals.subtotal_net),
        tax_total=str(totals.tax_total),
        total_gross=str(totals.total_gross),
        lines=[
            POLineView(
                line_no=line.line_no,
                sku=line.sku,
                description=line.description,
                quantity=str(line.quantity),
                unit_price=str(line.unit_price),
                tax_rate=str(line.tax_rate),
                committed_quantity=str(line.committed_quantity),
                net_amount=str(amount.net),
                tax_amount=str(amount.tax),
                gross_amount=str(amount.gross),
            )
            for line, amount in zip(lines, totals.lines, strict=True)
        ],
        creation=POCreationView(
            actor_id=creation.actor_id,
            created_at=creation.created_at,
            reason=creation.snapshot_json["reason"],
        )
        if creation
        else None,
        allocations=[
            LedgerEntryView(
                ledger_id=ledger.id,
                run_id=ledger.run_id,
                invoice_number=invoice.invoice_number_original,
                invoice_date=invoice.invoice_date.isoformat(),
                gross=str(ledger.gross),
                approved_at=ledger.created_at.astimezone(UTC),
            )
            for ledger, invoice in entries
        ],
    )
