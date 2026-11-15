"""Read projections; no financial mutations, model calls or checkpoint access."""

import base64
import hashlib
import json
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import String, and_, cast, func, or_, select

from app.access import submitter_reason
from app.evidence_verification import VERIFIER_VERSION, verify
from app.extraction_schema import InvoiceExtractionV1
from app.extraction_store import APIUsage
from app.financial_models import ApprovalLedger, FinancialAssessment, PurchaseOrder, Vendor
from app.models import Document, Run, RunEvent
from app.product_reads import EXPLANATIONS, processing_failure, rule_checks
from app.read_contracts import (
    DashboardSummary,
    ExtractedField,
    POView,
    RunPage,
    RunSummary,
    StageView,
    UsageView,
    VendorView,
)
from app.workflow_models import ReviewRequest, WorkflowRun

HEADERS = (
    "vendor_name",
    "vendor_tax_id",
    "invoice_number",
    "invoice_date",
    "po_reference",
    "currency",
    "subtotal_net",
    "tax_total",
    "total_gross",
    "tax_mode",
)
LINE_FIELDS = (
    "description",
    "sku",
    "po_line_no",
    "quantity",
    "unit_price",
    "price_basis",
    "tax_rate",
    "net_amount",
    "tax_amount",
    "gross_amount",
)
SAFE_EVENT_KEYS = {
    "operation",
    "attempt",
    "retry",
    "source",
    "graph_version",
    "fresh_api_call",
    "attempt_id",
    "decision",
    "code",
    "provisional",
    "review_request_id",
    "generation",
    "action",
    "actor_id",
    "financial_post_unchanged",
    "invoice_processed",
    "outcome",
    "elapsed_ms",
}


def events(session, run_id, after=0, limit=500):
    return session.scalars(
        select(RunEvent)
        .where(RunEvent.run_id == run_id, RunEvent.seq > after)
        .order_by(RunEvent.seq)
        .limit(limit)
    ).all()


def public_event(event):
    from app.contracts import RunEventResponse

    return RunEventResponse(
        run_id=event.run_id,
        seq=event.seq,
        stage=event.stage,
        type=event.type,
        occurred_at=event.occurred_at,
        payload={
            k: v
            for k, v in event.payload_json.items()
            if k in SAFE_EVENT_KEYS and isinstance(v, (str, int, bool, type(None)))
        },
    )


def mode(run, work):
    return "DEMO_REPLAY" if run.replay_mode else work.source_mode if work else "NOT_STARTED"


def processing_time(rows):
    start, total, intervals, uncertain = None, 0, 0, False
    for event in rows:
        operation = event.payload_json.get("operation")
        if operation == "WORKER_CLAIM":
            uncertain |= start is not None
            start = event.occurred_at
        elif start is not None:
            if operation in ("LEASE_EXPIRED", "RECOVER_COMMITTED_DECISION"):
                start, uncertain = None, True
            elif (
                event.type in ("REVIEW_REQUESTED", "RUN_COMPLETED", "RUN_FAILED")
                or operation in ("PROCESSOR_ERROR", "TEST_PROCESSOR_STOPPED")
                or event.event_key == "workflow-stopped"
            ):
                total += max(0, int((event.occurred_at - start).total_seconds() * 1000))
                intervals += 1
                start = None
    if uncertain or start is not None:
        return None, "incomplete"
    return (total, "measured") if intervals else (None, "pending")


def stage_views(rows):
    stages = {}
    for event in rows:
        key = event.event_key or ""
        if not key.startswith("graph:"):
            continue
        group, phase = key.rsplit(":", 1)
        if phase == "start":
            stages[group] = StageView(
                key=group,
                name=event.stage,
                operation=event.payload_json.get("operation", event.stage),
                status="running",
                started_at=event.occurred_at,
                finished_at=None,
                elapsed_ms=None,
            )
        elif group in stages and phase == "end":
            stage = stages[group]
            stage.status, stage.finished_at = "finished", event.occurred_at
            stage.elapsed_ms = max(
                0, int((event.occurred_at - stage.started_at).total_seconds() * 1000)
            )
    return list(stages.values())


def usage_view(work, usage):
    if work and work.source_mode == "MOCK_OPENAI":
        return UsageView(reserved_attempts=work.extraction_attempts, cost_status="not_applicable")
    complete_cost = bool(usage) and all(u.estimated_cost_usd is not None for u in usage)
    complete_cost &= work is not None and len(usage) == work.extraction_attempts

    def total(field):
        return (
            sum(getattr(u, field) for u in usage)
            if usage and all(getattr(u, field) is not None for u in usage)
            else None
        )

    return UsageView(
        recorded_attempts=len(usage),
        reserved_attempts=work.extraction_attempts if work else 0,
        input_tokens=total("input_tokens"),
        output_tokens=total("output_tokens"),
        estimated_cost_usd=str(sum((u.estimated_cost_usd for u in usage), Decimal("0")))
        if complete_cost
        else None,
        cost_status="estimated" if complete_cost else "unknown",
        rate_sources=sorted({u.rate_source for u in usage if u.rate_source}),
    )


def po_view(po, relationship="PRINTED_REFERENCE"):
    return (
        POView(
            po_id=po.id,
            po_number=po.po_number,
            status=po.status,
            currency=po.currency,
            cap_gross=str(po.approved_cap_gross),
            committed_gross=str(po.committed_gross),
            remaining_gross=str(po.approved_cap_gross - po.committed_gross),
            relationship=relationship,
        )
        if po
        else None
    )


def detail(session, run):
    work = session.get(WorkflowRun, run.id)
    assessment = session.scalar(
        select(FinancialAssessment)
        .where(FinancialAssessment.run_id == run.id)
        .order_by(FinancialAssessment.revision.desc())
        .limit(1)
    )
    ledger = session.scalar(select(ApprovalLedger).where(ApprovalLedger.run_id == run.id))
    request = session.scalar(
        select(ReviewRequest).where(ReviewRequest.run_id == run.id, ReviewRequest.status == "OPEN")
    )
    wire = work.extraction_json if work and work.extraction_json else {}
    checked, fields, findings = None, [], []
    if wire:
        document = session.get(Document, run.document_id)
        if (
            work.verifier_version == VERIFIER_VERSION
            and hashlib.sha256(document.content).hexdigest() == run.document_sha256
        ):
            checked = verify(InvoiceExtractionV1.model_validate(wire), document.content)
            findings = list(checked.findings)
        else:
            findings = ["VERIFICATION_VERSION_OR_DOCUMENT_MISMATCH"]
        verified = (
            {e.field: e for e in checked.document.evidence if e.verified}
            if checked and checked.document
            else {}
        )

        def field(path, value):
            evidence = verified.get(path)
            fields.append(
                ExtractedField(
                    field=path,
                    value=str(value) if value is not None else None,
                    verification="missing"
                    if value is None
                    else "verified"
                    if evidence
                    else "unverified",
                    pages=[evidence.page] if evidence else [],
                )
            )

        for key in HEADERS:
            field(key, wire.get(key))
        for index, line in enumerate(wire.get("line_items", []), 1):
            number = line.get("line_no")
            for key in LINE_FIELDS:
                path = (
                    f"lines.{number}.{key}"
                    if number is not None
                    else f"unidentified_lines.{index}.{key}"
                )
                field(path, line.get(key))
    vendor = (
        session.get(Vendor, assessment.vendor_id) if assessment and assessment.vendor_id else None
    )
    observation_keys = {
        "vendor_id",
        "po_id",
        "po_number",
        "currency",
        "cap_gross",
        "committed_gross",
        "remaining_gross",
        "requested_gross",
        "excess_gross",
    }
    observations = (
        {
            k: v
            for k, v in assessment.observations_json.items()
            if k in observation_keys and isinstance(v, str)
        }
        if assessment and assessment.observations_json
        else None
    )
    po_id = ledger.po_id if ledger else UUID(observations["po_id"]) if observations else None
    # Historical detail can identify an explicit printed PO, but never invent its old balance.
    po = (
        session.get(PurchaseOrder, po_id)
        if po_id
        else session.scalar(
            select(PurchaseOrder).where(PurchaseOrder.po_number == wire.get("po_reference"))
        )
        if wire.get("po_reference")
        else None
    )
    rows = session.scalars(
        select(RunEvent).where(RunEvent.run_id == run.id).order_by(RunEvent.seq)
    ).all()
    elapsed, time_status = processing_time(rows)
    reason_code = next(
        (e.payload_json.get("code") for e in reversed(rows) if e.type == "DECISION_RECORDED"), None
    )
    usage = session.scalars(select(APIUsage).where(APIUsage.run_id == run.id)).all()
    return dict(
        updated_at=run.updated_at.astimezone(UTC),
        source_mode=mode(run, work),
        policy_version=run.policy_version,
        model_id=run.model_id,
        reason_code=reason_code,
        error_code=run.error_code,
        invoice_number=wire.get("invoice_number"),
        invoice_currency=wire.get("currency"),
        invoice_total=wire.get("total_gross"),
        fields=fields,
        verification_findings=findings,
        vendor=VendorView(vendor_id=vendor.id, name=vendor.legal_name, status=vendor.status)
        if vendor
        else None,
        purchase_order=po_view(
            po,
            "APPROVED_ALLOCATION"
            if ledger
            else "ASSESSED_PO"
            if observations
            else "PRINTED_REFERENCE",
        ),
        decision_observations=observations,
        approved_gross=str(ledger.gross) if ledger else None,
        review_request_id=request.id if request else None,
        stages=stage_views(rows),
        processing_ms=elapsed,
        processing_time_status=time_status,
        usage=usage_view(work, usage),
        checks=rule_checks(assessment, ledger, fields),
        business_explanation=EXPLANATIONS.get(reason_code),
        processing_failure=processing_failure(run, work, usage),
    )


def history(session, state, decision, cursor, limit, q="", *, owner_id=None):
    query = select(Run)
    if owner_id is not None:
        query = query.where(Run.owner_id == owner_id)
    if state:
        query = query.where(Run.job_state == state)
    if decision:
        query = query.where(Run.decision == decision)
    if q:
        query = query.outerjoin(WorkflowRun, WorkflowRun.run_id == Run.id).where(
            or_(
                cast(Run.id, String).icontains(q, autoescape=True),
                WorkflowRun.extraction_json["invoice_number"]
                .as_string()
                .icontains(q, autoescape=True),
                WorkflowRun.extraction_json["vendor_name"]
                .as_string()
                .icontains(q, autoescape=True),
            )
        )
    count = session.scalar(select(func.count()).select_from(query.subquery()))
    if cursor:
        try:
            data = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if data["state"] != state or data["decision"] != decision or data.get("q", "") != q:
                raise ValueError()
            if data.get("owner_id") != owner_id:
                raise ValueError()
            timestamp = datetime.fromisoformat(data["created_at"])
            if timestamp.tzinfo is None:
                raise ValueError()
            ident = UUID(data["id"])
        except (ValueError, TypeError, KeyError):
            raise HTTPException(422, detail="Invalid cursor or changed history filters.") from None
        query = query.where(
            or_(Run.created_at < timestamp, and_(Run.created_at == timestamp, Run.id < ident))
        )
    rows = session.scalars(
        query.order_by(Run.created_at.desc(), Run.id.desc()).limit(limit + 1)
    ).all()
    page, next_cursor = rows[:limit], None
    if len(rows) > limit:
        last = page[-1]
        next_cursor = (
            base64.urlsafe_b64encode(
                json.dumps(
                    dict(
                        state=state,
                        decision=decision,
                        q=q,
                        owner_id=owner_id,
                        created_at=last.created_at.isoformat(),
                        id=str(last.id),
                    )
                ).encode()
            )
            .decode()
            .rstrip("=")
        )
    works = {
        w.run_id: w
        for w in session.scalars(
            select(WorkflowRun).where(WorkflowRun.run_id.in_([r.id for r in page]))
        )
    }
    items = []
    usages, assessments, latest_codes = {}, {}, {}
    for event in session.scalars(
        select(RunEvent)
        .where(RunEvent.run_id.in_([r.id for r in page]), RunEvent.type == "DECISION_RECORDED")
        .order_by(RunEvent.seq)
    ):
        code = event.payload_json.get("code")
        if isinstance(code, str):
            latest_codes[event.run_id] = code
    for usage in session.scalars(select(APIUsage).where(APIUsage.run_id.in_([r.id for r in page]))):
        usages.setdefault(usage.run_id, []).append(usage)
    for item in session.scalars(
        select(FinancialAssessment)
        .where(FinancialAssessment.run_id.in_([r.id for r in page]))
        .order_by(FinancialAssessment.revision)
    ):
        assessments[item.run_id] = item
    for run in page:
        work = works.get(run.id)
        wire = work.extraction_json or {} if work else {}
        items.append(
            RunSummary(
                run_id=run.id,
                created_at=run.created_at.astimezone(UTC),
                job_state=run.job_state,
                decision=run.decision,
                invoice_number=wire.get("invoice_number"),
                vendor_name=wire.get("vendor_name"),
                currency=wire.get("currency"),
                total_gross=wire.get("total_gross"),
                reason=submitter_reason(
                    EXPLANATIONS.get(latest_codes.get(run.id)) or run.reason,
                    latest_codes.get(run.id)
                    or (assessments[run.id].code if run.id in assessments else None),
                    run.decision,
                )
                if owner_id is not None
                else run.reason,
                source_mode=mode(run, work),
                updated_at=run.updated_at.astimezone(UTC),
                reason_code=latest_codes.get(run.id)
                or (assessments[run.id].code if run.id in assessments else None),
                estimated_api_cost_usd=usage_view(work, usages.get(run.id, [])).estimated_cost_usd,
                processing_failure=processing_failure(run, work, usages.get(run.id, [])),
            )
        )
    return RunPage(items=items, next_cursor=next_cursor, total_count=count)


def dashboard(session):
    from decimal import localcontext

    with localcontext() as context:
        context.prec = 48
        return _dashboard(session)


def _dashboard(session):
    runs = session.scalars(select(Run)).all()
    works = {w.run_id: w for w in session.scalars(select(WorkflowRun))}
    usage, event_rows, assessments = {}, {}, {}
    for u in session.scalars(select(APIUsage)):
        usage.setdefault(u.run_id, []).append(u)
    for e in session.scalars(select(RunEvent).order_by(RunEvent.run_id, RunEvent.seq)):
        event_rows.setdefault(e.run_id, []).append(e)
    for a in session.scalars(select(FinancialAssessment).order_by(FinancialAssessment.revision)):
        assessments[a.run_id] = a
    measured, costs, unknown_cost, overrun = [], [], 0, {}
    for run in runs:
        elapsed, status = processing_time(event_rows.get(run.id, []))
        if status == "measured":
            measured.append(elapsed)
        work = works.get(run.id)
        if work and work.source_mode == "LIVE_OPENAI" and work.extraction_attempts:
            cost = usage_view(work, usage.get(run.id, [])).estimated_cost_usd
            if cost is None:
                unknown_cost += 1
            else:
                costs.append(Decimal(cost))
        a = assessments.get(run.id)
        if run.job_state != "WAITING_REVIEW" or not a or a.code != "PO_CAP_EXCEEDED":
            continue
        key = (
            (a.vendor_id, a.normalized_invoice_number)
            if a.vendor_id and a.normalized_invoice_number
            else (run.id,)
        )
        try:
            facts = a.observations_json
            requested, remaining, excess = (
                Decimal(facts[k]) for k in ("requested_gross", "remaining_gross", "excess_gross")
            )
            if (
                not all(x.is_finite() for x in (requested, remaining, excess))
                or excess <= 0
                or excess != requested - remaining
            ):
                raise ValueError()
            signature = (
                a.document_json.get("invoice_date"),
                a.document_json.get("currency"),
                requested,
            )
            previous = overrun.get(key)
            overrun[key] = (
                (signature, max(excess, previous[1]))
                if previous and previous[0] == signature
                else (signature, excess)
                if key not in overrun
                else None
            )
        except (ValueError, TypeError, KeyError, InvalidOperation):
            overrun[key] = None
    known = [v[1] for v in overrun.values() if v is not None]
    reviewed_ids = set(session.scalars(select(ReviewRequest.run_id).distinct()))
    eligible = [
        r
        for r in runs
        if r.id in works
        and works[r.id].source_mode in ("MOCK_OPENAI", "LIVE_OPENAI")
        and (r.decision in ("APPROVED", "REJECTED") or r.job_state == "WAITING_REVIEW")
    ]
    straight = sum(r.decision == "APPROVED" and r.id not in reviewed_ids for r in eligible)
    return DashboardSummary(
        total_runs=len(runs),
        total_processed=sum(r.decision in ("APPROVED", "REJECTED") for r in runs),
        approved=sum(r.decision == "APPROVED" for r in runs),
        rejected=sum(r.decision == "REJECTED" for r in runs),
        awaiting_review=sum(r.job_state == "WAITING_REVIEW" for r in runs),
        active=sum(r.job_state in ("QUEUED", "RUNNING") for r in runs),
        failed=sum(r.job_state == "FAILED" for r in runs),
        average_processing_ms=sum(measured) // len(measured) if measured else None,
        processing_time_sample_count=len(measured),
        estimated_api_cost_usd=str(sum(costs, Decimal("0"))) if costs else None,
        estimated_cost_known_runs=len(costs),
        estimated_cost_unknown_runs=unknown_cost,
        potential_po_overrun_inr=str(sum(known, Decimal("0"))) if known else None,
        overrun_known_identities=len(known),
        overrun_unknown_identities=sum(v is None for v in overrun.values()),
        straight_through_approved=straight,
        automation_eligible_runs=len(eligible),
        straight_through_rate_pct=str(
            (Decimal(straight) * 100 / len(eligible)).quantize(Decimal("0.1"))
        )
        if eligible
        else None,
        mock_runs=sum(mode(r, works.get(r.id)) == "MOCK_OPENAI" for r in runs),
        live_runs=sum(mode(r, works.get(r.id)) == "LIVE_OPENAI" for r in runs),
        replay_runs=sum(r.replay_mode for r in runs),
    )
