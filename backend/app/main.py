import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, Query, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.access import (
    AccessView,
    Principal,
    access_view,
    authenticate,
    require_role,
    submitter_reason,
    visible_run,
)
from app.config import Settings
from app.contracts import (
    API_PREFIX,
    Health,
    IntakeResponse,
    RunEventResponse,
)
from app.db import make_engine
from app.demo_access import add_demo_access_route
from app.demo_reset import add_demo_reset_routes
from app.intake import create_intake, validate_pdf
from app.models import RunEvent
from app.po_routes import add_po_routes
from app.read_contracts import RunDetail, SubmitterRunDetail
from app.read_routes import add_read_routes
from app.read_service import detail, public_event
from app.review_contracts import ReviewAccepted, ReviewCandidate, ReviewResponse, ReviewView
from app.reviews import ReviewConflict, respond
from app.workflow_models import ReviewRequest


def create_app(
    settings: Settings | None = None, engine=None, *, mock_mode: bool = False
) -> FastAPI:
    settings = settings or Settings()
    if settings.openai_credential_mode == "reviewer":
        from app.provider_credentials import cipher

        cipher(settings)
    owns_engine = engine is None
    engine = engine if engine is not None else make_engine(settings)

    @asynccontextmanager
    async def lifespan(app):
        yield
        if owns_engine:
            engine.dispose()

    app = FastAPI(title="PS-1 Invoice-to-Decision API", version="0.1.0", lifespan=lifespan)
    app.state.engine = engine
    add_demo_access_route(app, settings)
    bearer = HTTPBearer(auto_error=False)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(request, error):
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {key: item[key] for key in ("type", "loc", "msg")} for item in error.errors()
                ]
            },
            headers={"Cache-Control": "no-store"},
        )

    def require_auth(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer),
        ],
    ):
        return authenticate(settings, credentials.credentials if credentials else None)

    def require_submitter(actor: Annotated[Principal, Depends(require_auth)]):
        return require_role(actor, "submitter")

    def require_finance(actor: Annotated[Principal, Depends(require_auth)]):
        return require_role(actor, "reviewer")

    add_po_routes(app, engine, require_auth)
    add_demo_reset_routes(app, settings, engine, require_auth)

    @app.get(f"{API_PREFIX}/access", response_model=AccessView)
    def get_access(actor: Annotated[Principal, Depends(require_auth)]):
        return access_view(settings, actor)

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

    from app.provider_routes import add_provider_routes

    add_provider_routes(app, settings, engine, require_auth, mock_mode=mock_mode)

    @app.get(f"{API_PREFIX}/healthz", response_model=Health)
    def healthz():
        from app.evidence_verification import VERIFIER_VERSION
        from app.extraction_schema import PROMPT_VERSION, SCHEMA_VERSION

        return Health(
            status="ok",
            extraction_schema_version=SCHEMA_VERSION,
            prompt_version=PROMPT_VERSION,
            verifier_version=VERIFIER_VERSION,
            scan_review_required=True,
        )

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
        actor: Annotated[Principal, Depends(require_submitter)],
        source: Annotated[str | None, Form(max_length=200)] = None,
        model_id: Annotated[str | None, Form(max_length=100)] = None,
        provider_session: Annotated[
            str | None, Header(alias="X-OpenAI-Session", max_length=200)
        ] = None,
        idempotency_key: Annotated[
            str | None,
            Header(
                alias="X-Idempotency-Key",
                min_length=1,
                max_length=200,
            ),
        ] = None,
    ):
        content = file.file.read(settings.max_pdf_bytes + 1)
        validate_pdf(content, max_bytes=settings.max_pdf_bytes)
        if settings.openai_credential_mode == "reviewer":
            from app.provider_credentials import purge_expired

            purge_expired(engine)
            if not provider_session or not model_id:
                raise HTTPException(
                    400, "Connect your OpenAI key and select a model before upload."
                )
        elif provider_session or model_id:
            raise HTTPException(400, "This workspace uses its configured server model.")
        return create_intake(
            engine,
            content,
            source,
            idempotency_key,
            provider_token=provider_session,
            model_id=model_id,
            owner_id=actor.owner_id,
        )

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}",
        response_model=RunDetail | SubmitterRunDetail,
        dependencies=[Depends(require_auth)],
    )
    def get_run(run_id: UUID, actor: Annotated[Principal, Depends(require_auth)]):
        with Session(engine) as session:
            run = visible_run(session, run_id, actor)
            if actor.role == "submitter":
                info = detail(session, run)
                return SubmitterRunDetail(
                    run_id=run.id,
                    job_state=run.job_state,
                    decision=run.decision,
                    decision_reason=submitter_reason(
                        info["business_explanation"] or run.reason,
                        info["reason_code"],
                        run.decision,
                    ),
                    created_at=run.created_at,
                    **{
                        k: info[k]
                        for k in (
                            "updated_at",
                            "source_mode",
                            "model_id",
                            "invoice_number",
                            "invoice_currency",
                            "invoice_total",
                            "fields",
                            "stages",
                            "processing_ms",
                            "usage",
                            "processing_failure",
                        )
                    },
                )
            return RunDetail(
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
                **detail(session, run),
            )

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}/events",
        response_model=list[RunEventResponse],
        dependencies=[Depends(require_auth)],
    )
    def get_events(
        run_id: UUID,
        actor: Annotated[Principal, Depends(require_auth)],
        after_seq: Annotated[int, Query(ge=0)] = 0,
        limit: Annotated[int, Query(ge=1, le=500)] = 100,
    ):
        with Session(engine) as session:
            visible_run(session, run_id, actor)
            events = session.scalars(
                select(RunEvent)
                .where(RunEvent.run_id == run_id, RunEvent.seq > after_seq)
                .order_by(RunEvent.seq)
                .limit(limit)
            )
            return [public_event(e) for e in events]

    @app.get(
        f"{API_PREFIX}/runs/{{run_id}}/review",
        response_model=ReviewView,
        dependencies=[Depends(require_finance)],
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

    add_read_routes(app, engine, require_auth, require_finance)
    if settings.frontend_directory is not None:
        from fastapi.responses import FileResponse
        from fastapi.staticfiles import StaticFiles

        directory = settings.frontend_directory.resolve(strict=True)
        app.mount("/assets", StaticFiles(directory=directory / "assets"), name="ui-assets")

        @app.get("/", include_in_schema=False)
        def frontend():
            return FileResponse(directory / "index.html", headers={"Cache-Control": "no-cache"})

    return app
