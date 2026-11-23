"""Worker-owned assessment reconstructs evidence; it never trusts a supplied document."""

import hashlib
import json
from decimal import localcontext
from uuid import UUID

from sqlalchemy import select

from app.approval import ApprovalConflict, assess_transaction
from app.evidence_verification import LEGACY_VERIFIER_VERSION, verify
from app.extraction_schema import parse_extraction
from app.finance_rules import Result, reject, review
from app.financial_models import ApprovalLedger, FinancialAssessment
from app.models import Document, Run
from app.ownership import owned_session
from app.workflow_models import ReviewAction, ReviewRequest, WorkflowRun


def prior_selected_po(session, run_id, generation):
    """Reuse only an earlier immutable, authorized choice for this same document."""
    choice = session.execute(
        select(ReviewRequest, ReviewAction)
        .join(ReviewAction, ReviewAction.review_request_id == ReviewRequest.id)
        .where(
            ReviewRequest.run_id == run_id,
            ReviewRequest.generation < generation,
            ReviewRequest.status == "RESOLVED",
            ReviewAction.action == "SELECT_PO",
        )
        .order_by(ReviewRequest.generation.desc())
        .limit(1)
    ).first()
    if choice is None:
        return None
    request, action = choice
    if (
        request.kind != "PO_SELECTION"
        or set(action.payload_json) != {"po_id"}
        or action.payload_json["po_id"] not in request.options_json
    ):
        raise ApprovalConflict("Earlier PO selection was not a stored candidate")
    return UUID(action.payload_json["po_id"])


def finalize_owned(worker, claim, *, post=True):
    with owned_session(worker, claim) as session, localcontext() as context:
        context.prec = 48
        run = session.scalar(select(Run).where(Run.id == claim.run_id).with_for_update())
        work = session.get(WorkflowRun, run.id)
        if work is None:
            raise ApprovalConflict("Workflow configuration missing")
        ledger = session.scalar(select(ApprovalLedger).where(ApprovalLedger.run_id == run.id))
        if ledger:
            prior = session.scalar(
                select(FinancialAssessment).where(
                    FinancialAssessment.run_id == run.id, FinancialAssessment.decision == "APPROVED"
                )
            )
            if prior is None or run.decision != "APPROVED":
                raise ApprovalConflict("Financial commit requires reconciliation")
            return Result(prior.decision, prior.code, prior.reason)
        action = None
        if work.review_generation:
            request = session.scalar(
                select(ReviewRequest).where(
                    ReviewRequest.run_id == run.id,
                    ReviewRequest.generation == work.review_generation,
                )
            )
            action = (
                session.scalar(
                    select(ReviewAction).where(ReviewAction.review_request_id == request.id)
                )
                if request
                else None
            )
            if request is None or request.status != "RESOLVED" or action is None:
                raise ApprovalConflict("No resolved authorized action for this generation")
            if action.action in ("REJECT", "REQUEST_INFO"):
                result = (
                    reject(
                        "REVIEWER_REJECTED",
                        "Authorized reviewer rejected the invoice; no funds posted.",
                    )
                    if action.action == "REJECT"
                    else Result(
                        "STOPPED",
                        "REQUEST_INFO",
                        "Additional source information requested. No funds posted.",
                    )
                )
                if post:
                    from app.events import append_event

                    run.decision = "REJECTED" if action.action == "REJECT" else None
                    run.job_state = "COMPLETED" if action.action == "REJECT" else "INTERRUPTED"
                    run.reason = result.reason
                    append_event(
                        session,
                        run.id,
                        f"review-stop:{request.id}",
                        "DECISION_RECORDED",
                        {"code": result.code, "decision": run.decision},
                        stage="HUMAN_REVIEW",
                    )
                return result
        if work.extraction_json is None:
            return review(
                "CRITICAL_FIELD_MISSING", "Extraction is unavailable; request source evidence."
            )
        document_row = session.get(Document, run.document_id)
        if hashlib.sha256(document_row.content).hexdigest() != run.document_sha256:
            raise ApprovalConflict("Stored document hash mismatch")
        # The new mandatory scan gate also protects unposted legacy/review runs.
        # Approved ledgers returned above remain immutable; old extraction and
        # financial assessments are never rewritten merely to apply this gate.
        from app.document_classification import scan_pages

        if scan_pages(document_row.content):
            result = review(
                "SCANNED_DOCUMENT_REQUIRES_REVIEW",
                "Scanned document requires human review, even when all fields verify.",
            )
            if post:
                from app.events import append_event

                run.reason = result.reason
                append_event(
                    session,
                    run.id,
                    f"scan-policy:{work.review_generation}",
                    "DECISION_RECORDED",
                    {"code": result.code, "decision": "NEEDS_REVIEW", "provisional": True},
                    stage="EVIDENCE_VERIFICATION",
                )
            return result
        checked = verify(
            parse_extraction(work.extraction_json, work.schema_version),
            document_row.content,
            version=work.verifier_version,
        )
        from app.extended_verification import financial_conflicts

        if financial_conflicts(checked):
            return review(
                "TAX_UNCLEAR", "Printed financial component values conflict; verify the source."
            )
        selected_po, forced = None, None
        if work.review_generation:
            request = session.scalar(
                select(ReviewRequest).where(
                    ReviewRequest.run_id == run.id,
                    ReviewRequest.generation == work.review_generation,
                )
            )
            action = (
                session.scalar(
                    select(ReviewAction).where(ReviewAction.review_request_id == request.id)
                )
                if request
                else None
            )
            if request is None or request.status != "RESOLVED" or action is None:
                raise ApprovalConflict("No resolved authorized action for this generation")
            if action.action == "SELECT_PO":
                if (
                    request.kind != "PO_SELECTION"
                    or checked.document is None
                    or checked.document.po_reference is not None
                ):
                    raise ApprovalConflict("PO selection cannot override printed evidence")
                selected_po = UUID(action.payload_json["po_id"])
                if str(selected_po) not in request.options_json:
                    raise ApprovalConflict("PO selection was not a stored candidate")
            elif action.action == "PASS":
                if (
                    request.kind not in ("PO_SELECTION", "EVIDENCE_OR_POLICY")
                    or action.payload_json
                ):
                    raise ApprovalConflict("Invalid conditional pass action")
                if checked.document and checked.document.po_reference is None:
                    selected_po = prior_selected_po(session, run.id, request.generation)
            elif action.action == "REJECT":
                forced = reject(
                    "REVIEWER_REJECTED",
                    "Authorized reviewer rejected the invoice; no funds posted.",
                )
            elif action.action == "REQUEST_INFO":
                return Result(
                    "STOPPED",
                    "REQUEST_INFO",
                    "Additional source information requested. No funds posted.",
                )
        if checked.document is None:
            if "SCANNED_DOCUMENT_REQUIRES_REVIEW" in checked.findings:
                return forced or review(
                    "SCANNED_DOCUMENT_REQUIRES_REVIEW",
                    "Scanned document requires human review; no funds posted.",
                )
            return forced or review(
                "UNVERIFIED_TOTAL", "Critical source fields cannot be verified."
            )
        document = checked.document
        document_snapshot = document.model_dump(mode="json")
        if work.schema_version == "InvoiceExtractionV1.2":
            document_snapshot["extraction_schema_version"] = work.schema_version
            document_snapshot["expanded_fields"] = {
                p["field"]: {
                    k: p.get(k)
                    for k in (
                        "original_value",
                        "normalized_value",
                        "state",
                        "reason_code",
                        "page",
                        "calculation",
                    )
                }
                for p in checked.provenance
                if p["field"] not in {e.field for e in document.evidence}
            }
        if work.verifier_version == LEGACY_VERIFIER_VERSION:
            document_snapshot.pop("verification_findings", None)
        fingerprint = hashlib.sha256(
            json.dumps(
                [
                    work.policy_version,
                    document_snapshot,
                    str(selected_po) if selected_po else None,
                    forced.code if forced else None,
                ],
                sort_keys=True,
                separators=(",", ":"),
            ).encode()
        ).hexdigest()
        existing = session.get(FinancialAssessment, (run.id, work.review_generation))
        if existing:
            if existing.fingerprint != fingerprint:
                raise ApprovalConflict("Conflicting financial revision replay")
            return Result(existing.decision, existing.code, existing.reason)
        return assess_transaction(
            session,
            run,
            document,
            work.policy_version,
            fingerprint,
            document_snapshot,
            revision=work.review_generation,
            selected_po=selected_po,
            forced_result=forced,
            production=True,
            post=post,
        )
