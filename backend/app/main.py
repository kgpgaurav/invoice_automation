import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.contracts import (
    API_PREFIX,
    MAX_PDF_BYTES,
    Health,
    IntakeResponse,
    RunEventResponse,
    RunStatus,
)
from app.db import make_engine
from app.intake import create_intake, validate_pdf
from app.models import Run, RunEvent
from app.review_contracts import ReviewAccepted, ReviewCandidate, ReviewResponse, ReviewView
from app.reviews import ReviewConflict, respond
from app.workflow_models import ReviewRequest


def create_app(settings: Settings | None = None, engine=None) -> FastAPI:
    settings = settings or Settings()
    owns_engine = engine is None
    engine = engine if engine is not None else make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns_engine:
            engine.dispose()

    app = FastAPI(title="PS-1 Invoice-to-Decision API", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    bearer = HTTPBearer(auto_error=False)

    def require_auth(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer),
        ],
    ):
        if credentials is None or not secrets.compare_digest(
            credentials.credentials.encode(),
            settings.app_api_token.get_secret_value().encode(),
        ):
            raise HTTPException(
                401,
                detail="Valid bearer credential required.",
                headers={"WWW-Authenticate": "Bearer"},
            )

    def require_reviewer(
        credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)],
    ):
        if (
            settings.reviewer_api_token is None
            or credentials is None
            or not secrets.compare_digest(
                credentials.credentials.encode(),
                settings.reviewer_api_token.get_secret_value().encode(),
            )
        ):
            raise HTTPException(403, detail="Configured reviewer credential required.")

    @app.exception_handler(SQLAlchemyError)
    async def database_unavailable(request, error):
        return JSONResponse(
            status_code=503, content={"detail": "Database unavailable. Retry later."}
        )

    @app.get(f"{API_PREFIX}/healthz", response_model=Health)
    def healthz():
        return Health(status="ok")

    @app.get(f"{API_PREFIX}/readyz", response_model=Health, responses={503: {"model": Health}})
    def readyz():
        from pathlib import Path

        config = Config()
        config.set_main_option("script_location", str(Path(__file__).parents[1] / "alembic"))
        head = ScriptDirectory.from_config(config).get_current_head()
        try:
            with engine.connect() as connection:
                revision = connection.execute(
                    text("SELECT version_num FROM alembic_version")
                ).scalar()
                if revision != head:
                    raise ValueError("Migration mismatch")
        except (SQLAlchemyError, ValueError):
            return JSONResponse(
                status_code=503,
                content={
                    "status": "not_ready",
                    "database": "unavailable",
                },
            )
        return Health(status="ready", database="ready")

    @app.post(
        f"{API_PREFIX}/invoices/process",
        response_model=IntakeResponse,
        status_code=202,
        dependencies=[Depends(require_auth)],
    )
    def process_invoice(
        file: Annotated[UploadFile, File()],
        source: Annotated[str | None, Form(max_length=200)] = None,
        idempotency_key: Annotated[
            str | None,
            Header(
                alias="X-Idempotency-Key",
                min_length=1,
                max_length=200,
            ),
        ] = None,
    ):
        content = file.file.read(MAX_PDF_BYTES + 1)
        validate_pdf(content)
        return create_intake(engine, content, source, idempotency_key)

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}",
        response_model=RunStatus,
        dependencies=[Depends(require_auth)],
    )
    def get_run(run_id: UUID):
        with Session(engine) as session:
            run = session.scalar(select(Run).where(Run.id == run_id))
            if run is None:
                raise HTTPException(404, detail="Run not found.")
            return RunStatus(
                run_id=run.id,
                job_state=run.job_state,
                decision=run.decision,
                decision_reason=run.reason,
                thread_id=run.thread_id,
                created_at=run.created_at,
                replay_mode=run.replay_mode,
                implementation_notice=(
                    "Queued: no worker has processed this run. No financial decision was made."
                    if run.model_id == "not-configured"
                    else "Controlled processing requires explicit operator opt-in. "
                    "Approval authorizes downstream processing; no payment is executed."
                ),
            )

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}/events",
        response_model=list[RunEventResponse],
        dependencies=[Depends(require_auth)],
    )
    def get_events(
        run_id: UUID,
        after_seq: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        with Session(engine) as session:
            if session.get(Run, run_id) is None:
                raise HTTPException(404, detail="Run not found.")
            events = session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.seq > after_seq)
                .order_by(RunEvent.seq)
                .limit(limit)
            )
            return [
                RunEventResponse(
                    run_id=e.run_id,
                    seq=e.seq,
                    type=e.type,
                    stage=e.stage,
                    occurred_at=e.occurred_at,
                    payload=e.payload_json,
                )
                for e in events
            ]

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}/review",
        response_model=ReviewView,
        dependencies=[Depends(require_auth)],
    )
    def get_review(run_id: UUID):
        with Session(engine) as session:
            request = session.scalar(
                select(ReviewRequest).where(
                    ReviewRequest.run_id == run_id, ReviewRequest.status == "OPEN"
                )
            )
            if request is None:
                raise HTTPException(404, detail="No open review request.")
            from app.financial_models import PurchaseOrder

            candidates = []
            for po_id in request.options_json:
                po = session.get(PurchaseOrder, UUID(po_id))
                candidates.append(
                    ReviewCandidate(
                        po_id=po_id,
                        po_number=po.po_number if po else None,
                        currency=po.currency if po else None,
                        status=po.status if po else "UNAVAILABLE",
                        remaining_gross=str(po.approved_cap_gross - po.committed_gross)
                        if po
                        else None,
                    )
                )
            return ReviewView(
                review_request_id=request.id,
                run_id=request.run_id,
                generation=request.generation,
                kind=request.kind,
                question=request.question,
                options=candidates,
                status=request.status,
                allowed_actions=(["SELECT_PO"] if request.kind == "PO_SELECTION" else [])
                + ["REJECT", "REQUEST_INFO"],
            )

    @app.post(
        f"{API_PREFIX}/reviews/{{review_id}}/respond",
        response_model=ReviewAccepted,
        status_code=202,
        dependencies=[Depends(require_reviewer)],
    )
    def respond_review(
        review_id: UUID,
        body: ReviewResponse,
        key: Annotated[str, Header(alias="X-Idempotency-Key", min_length=1, max_length=200)],
    ):
        try:
            return respond(engine, review_id, body, key, "configured-reviewer")
        except LookupError:
            raise HTTPException(404, detail="Review request not found.") from None
        except ReviewConflict as error:
            raise HTTPException(409, detail=str(error)) from None

    return app
