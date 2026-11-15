"""Internal deterministic approval transaction. No API or worker integration."""

import hashlib
import json
from decimal import Decimal, localcontext
from uuid import uuid4

from sqlalchemy import func, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from app.events import append_event
from app.finance_contracts import FinancialDocument, FinancialPolicy, invoice_key
from app.finance_rules import (
    Result,
    critical_check,
    evaluate,
    match_po,
    reject,
    resolve_vendor,
    review,
)
from app.financial_models import (
    ApprovalAllocation,
    ApprovalLedger,
    FinancialAssessment,
    Invoice,
    PolicyVersion,
    POLine,
    PurchaseOrder,
    Vendor,
)
from app.models import QueueItem, Run


class ApprovalConflict(ValueError):
    pass


def register_policy(engine, policy: FinancialPolicy, actor: str):
    """Insert-only; concurrent identical registration is harmless."""
    snapshot = policy.model_dump(mode="json")
    with Session(engine) as session, session.begin():
        session.execute(
            insert(PolicyVersion)
            .values(version=policy.version, config_json=snapshot, created_by=actor)
            .on_conflict_do_nothing(index_elements=["version"])
        )
        if session.get(PolicyVersion, policy.version).config_json != snapshot:
            raise ApprovalConflict("Policy version already has a different immutable configuration")


def approve(engine, run_id, document: FinancialDocument, policy_version: str):
    # Retry only PostgreSQL deadlock/serialization failures, never integrity conflicts.
    for attempt in range(3):
        try:
            with localcontext() as context:
                context.prec = 48
                document = FinancialDocument.model_validate(document.model_dump())
                return _approve(engine, run_id, document, policy_version)
        except OperationalError as error:
            if getattr(error.orig, "sqlstate", None) not in ("40001", "40P01") or attempt == 2:
                raise


def _approve(engine, run_id, document, policy_version):
    snapshot = document.model_dump(mode="json")
    fingerprint = hashlib.sha256(
        json.dumps([policy_version, snapshot], sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    with Session(engine) as session, session.begin():
        locked = session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"ps1-worker:{run_id}"},
        )
        if not locked:
            raise ApprovalConflict("Run has an active worker owner")
        run = session.scalar(select(Run).where(Run.id == run_id).with_for_update())
        if run is None or not (run.source or "").startswith("fixture:"):
            raise ApprovalConflict(
                "Direct financial service is restricted to explicit fixture runs"
            )
        existing = session.scalar(
            select(FinancialAssessment)
            .where(FinancialAssessment.run_id == run_id)
            .order_by(FinancialAssessment.revision.desc())
            .limit(1)
        )
        if existing:
            if existing.fingerprint != fingerprint:
                raise ApprovalConflict(
                    "Run already assessed with different financial evidence/policy"
                )
            return Result(existing.decision, existing.code, existing.reason)
        if run.decision is not None or run.policy_version not in ("not-configured", policy_version):
            raise ApprovalConflict("Run already has a decision or a different policy snapshot")
        if session.scalar(
            select(QueueItem.id).where(QueueItem.run_id == run_id, QueueItem.status == "LEASED")
        ):
            raise ApprovalConflict("Run has an unresolved queue lease")
        return assess_transaction(session, run, document, policy_version, fingerprint, snapshot)


def assess_transaction(
    session,
    run,
    document,
    policy_version,
    fingerprint,
    snapshot,
    revision=0,
    selected_po=None,
    forced_result=None,
    production=False,
    post=True,
):
    # Shared transaction body is not a second approval entrypoint. Production use
    # requires the physically owned, fenced context; fixtures retain their guard.
    if production:
        ownership = session.info.get("ps1_owned_claim")
        if ownership is None:
            raise ApprovalConflict("Production assessment requires a fenced worker transaction")
        worker, claim = ownership
        if session.bind is not claim.connection or claim.run_id != run.id:
            raise ApprovalConflict("Financial transaction is not bound to this run owner")
        worker._owned(session, claim)
    elif not (run.source or "").startswith("fixture:"):
        raise ApprovalConflict("Unowned assessment is restricted to explicit fixture runs")
    policy_row = session.get(PolicyVersion, policy_version)
    if policy_row is None:
        raise ApprovalConflict("Register an immutable policy version before assessment")
    policy = FinancialPolicy.model_validate(policy_row.config_json)
    result = forced_result or critical_check(document)
    allocations, vendor, po, observations = {}, None, None, None
    if result is None:
        vendors = session.scalars(select(Vendor)).all()
        orders = session.scalars(select(PurchaseOrder)).all()
        vendor, result = resolve_vendor(document, vendors, orders)
    if vendor is not None and result is None:
        vendor = session.scalar(
            select(Vendor)
            .where(Vendor.id == vendor.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        vendor, result = resolve_vendor(document, [vendor], orders)
    if vendor is not None and result is None:
        session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": f"ps1-invoice:{vendor.id}:{invoice_key(document.invoice_number)}"},
        )
        canonical = session.scalar(
            select(Invoice).where(
                Invoice.vendor_id == vendor.id,
                Invoice.normalized_invoice_number == invoice_key(document.invoice_number),
            )
        )
        prior = session.scalars(
            select(FinancialAssessment).where(
                FinancialAssessment.run_id != run.id,
                FinancialAssessment.vendor_id == vendor.id,
                FinancialAssessment.normalized_invoice_number
                == invoice_key(document.invoice_number),
            )
        ).all()
        conflict = any(
            FinancialDocument.model_validate(item.document_json).total_gross != document.total_gross
            or item.document_json["invoice_date"] != snapshot["invoice_date"]
            or item.document_json["currency"] != document.currency
            for item in prior
        )
        if conflict:
            result = review(
                "DUPLICATE_CONFLICT",
                "Invoice identity has conflicting amount, date or currency evidence.",
            )
        elif canonical:
            ledger = session.scalar(
                select(ApprovalLedger).where(ApprovalLedger.invoice_id == canonical.id)
            )
            result = (
                reject(
                    "DUPLICATE_APPROVED",
                    "Invoice identity was already approved; no second posting.",
                )
                if ledger
                else review(
                    "DUPLICATE_CONFLICT", "Canonical invoice has conflicting ledger evidence."
                )
            )
        else:
            if selected_po is None:
                po, result = match_po(document, vendor, orders)
            else:
                po = next((p for p in orders if p.id == selected_po), None)
                if po is None or po.vendor_id != vendor.id:
                    result = review(
                        "PO_VENDOR_MISMATCH", "Selected PO is not valid for this supplier."
                    )
    if po is not None and result is None:
        po = session.scalar(
            select(PurchaseOrder)
            .where(PurchaseOrder.id == po.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        if po.vendor_id != vendor.id:
            result = reject(
                "PO_VENDOR_MISMATCH", "Current purchase order belongs to another supplier."
            )
        lines = session.scalars(
            select(POLine).where(POLine.po_id == po.id).order_by(POLine.id).with_for_update()
        ).all()
        committed = session.scalar(
            select(func.coalesce(func.sum(ApprovalLedger.gross), 0)).where(
                ApprovalLedger.po_id == po.id
            )
        )
        drift = committed != po.committed_gross
        for line in lines:
            used = session.scalar(
                select(func.coalesce(func.sum(ApprovalAllocation.quantity), 0)).where(
                    ApprovalAllocation.po_line_id == line.id
                )
            )
            drift = drift or used != line.committed_quantity
        if result is None:
            if drift:
                result = review(
                    "ALLOCATION_CONFLICT",
                    "PO counters disagree with immutable ledger allocations.",
                )
            else:
                today = session.scalar(text("SELECT (clock_timestamp() AT TIME ZONE 'UTC')::date"))
                result, allocations = evaluate(document, vendor, po, lines, policy, today)
                observations = {
                    "vendor_id": str(vendor.id),
                    "po_id": str(po.id),
                    "po_number": po.po_number,
                    "currency": po.currency,
                    "cap_gross": str(po.approved_cap_gross),
                    "committed_gross": str(committed),
                    "remaining_gross": str(po.approved_cap_gross - committed),
                    "requested_gross": str(document.total_gross),
                    "excess_gross": str(
                        max(
                            Decimal("0"), document.total_gross - (po.approved_cap_gross - committed)
                        )
                    ),
                }
    if not post:
        return result
    if result.decision == "APPROVED":
        invoice = Invoice(
            id=uuid4(),
            vendor_id=vendor.id,
            invoice_number_original=document.invoice_number,
            normalized_invoice_number=invoice_key(document.invoice_number),
            invoice_date=document.invoice_date,
            currency=document.currency,
            gross=document.total_gross,
            canonical_run_id=run.id,
        )
        session.add(invoice)
        session.flush()
        ledger = ApprovalLedger(
            id=uuid4(),
            invoice_id=invoice.id,
            po_id=po.id,
            run_id=run.id,
            gross=document.total_gross,
        )
        session.add(ledger)
        session.flush()
        for line in lines:
            quantity = allocations.get(line.id, Decimal("0"))
            if quantity:
                session.add(
                    ApprovalAllocation(ledger_id=ledger.id, po_line_id=line.id, quantity=quantity)
                )
                line.committed_quantity += quantity
        po.committed_gross += document.total_gross
        po.version += 1
    session.add(
        FinancialAssessment(
            run_id=run.id,
            revision=revision,
            vendor_id=vendor.id if vendor is not None else None,
            normalized_invoice_number=invoice_key(document.invoice_number)
            if vendor is not None
            else None,
            policy_version=policy_version,
            fingerprint=fingerprint,
            document_json=snapshot,
            decision=result.decision,
            code=result.code,
            reason=result.reason,
            observations_json=observations,
        )
    )
    run.policy_version = policy_version
    # Review requires a real interrupt/request before public NEEDS_REVIEW is valid.
    run.decision = None if result.decision == "NEEDS_REVIEW" else result.decision
    run.job_state = "INTERRUPTED" if result.decision == "NEEDS_REVIEW" else "COMPLETED"
    run.reason = result.reason
    run.updated_at = func.now()
    for job in (
        [] if production else session.scalars(select(QueueItem).where(QueueItem.run_id == run.id))
    ):
        job.status, job.lease_until = "DONE", None
    append_event(
        session,
        run.id,
        f"financial-assessment:{revision}",
        "DECISION_RECORDED",
        {
            "decision": result.decision,
            "code": result.code,
            "source": "WORKFLOW" if production else "DETERMINISTIC_FIXTURE",
            "provisional": result.decision == "NEEDS_REVIEW",
        },
        stage="FINANCIAL_VALIDATION",
    )
    return result
