"""Authenticated actor is supplied by the server, never by the review body."""

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.events import append_event
from app.models import QueueItem, Run
from app.review_contracts import ReviewAccepted, allowed_review_actions
from app.workflow_models import ReviewAction, ReviewRequest, WorkflowRun


class ReviewConflict(ValueError):
    pass


def respond(engine, review_id, body, key, actor):
    with Session(engine) as session, session.begin():
        request = session.get(ReviewRequest, review_id)
        if request is None:
            raise LookupError("Review request not found")
        if not session.scalar(
            text("SELECT pg_try_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": f"ps1-worker:{request.run_id}"},
        ):
            raise ReviewConflict("Run is busy; retry the same request")
        request = session.scalar(
            select(ReviewRequest)
            .where(ReviewRequest.id == review_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
        existing = session.scalar(
            select(ReviewAction).where(ReviewAction.review_request_id == review_id)
        )
        payload = body.payload.model_dump(mode="json", exclude_none=True)
        if existing:
            if (
                existing.idempotency_key,
                existing.action,
                existing.payload_json,
                existing.reason,
                existing.actor_id,
                request.generation,
            ) != (key, body.action, payload, body.reason, actor, body.generation):
                raise ReviewConflict("Conflicting repeated review submission")
            return ReviewAccepted(run_id=request.run_id, review_request_id=request.id)
        work = session.get(WorkflowRun, request.run_id)
        if (
            request.status != "OPEN"
            or body.generation != request.generation
            or work.review_generation != body.generation
        ):
            raise ReviewConflict("Review is not open or its generation is stale")
        if body.action == "SELECT_PO" and (
            request.kind != "PO_SELECTION" or str(body.payload.po_id) not in request.options_json
        ):
            raise ReviewConflict("PO was not offered for this review")
        if body.action not in allowed_review_actions(request.kind):
            raise ReviewConflict("Action is not offered for this review")
        run = session.scalar(select(Run).where(Run.id == request.run_id).with_for_update())
        if run.job_state != "WAITING_REVIEW" or run.decision != "NEEDS_REVIEW":
            raise ReviewConflict("Run is not awaiting this review")
        session.add(
            ReviewAction(
                review_request_id=request.id,
                actor_id=actor,
                action=body.action,
                payload_json=payload,
                reason=body.reason,
                idempotency_key=key,
            )
        )
        request.status, request.resolved_at = "RESOLVED", func.now()
        session.add(QueueItem(run_id=run.id, work_type="RESUME", generation=request.generation))
        run.job_state, run.decision = "QUEUED", None
        append_event(
            session,
            run.id,
            f"review-resolved:{request.id}",
            "REVIEW_RESOLVED",
            {
                "review_request_id": str(request.id),
                "generation": request.generation,
                "action": body.action,
                "actor_id": actor,
            },
            stage="HUMAN_REVIEW",
        )
        return ReviewAccepted(run_id=run.id, review_request_id=request.id)
