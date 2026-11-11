import secrets
from contextlib import asynccontextmanager
from typing import Annotated
from uuid import UUID

from alembic.config import Config
from alembic.script import ScriptDirectory
from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select, text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings
from app.contracts import API_PREFIX, MAX_PDF_BYTES, Health, IntakeResponse, RunStatus
from app.db import make_engine
from app.intake import create_intake, validate_pdf
from app.models import Run


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
                implementation_notice="Intake skeleton: no worker or AI extraction implemented. "
                "This run remains queued; no financial decision was made.",
            )

    return app
