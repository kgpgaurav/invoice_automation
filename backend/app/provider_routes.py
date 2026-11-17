"""Authenticated BYOK setup. Keys are never echoed in responses or validation errors."""

from datetime import datetime
from typing import Annotated, Literal

from fastapi import Depends, Header, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, SecretStr, ValidationError

from app.access import Principal, require_role
from app.contracts import API_PREFIX, MAX_PDF_PAGES
from app.provider_credentials import (
    SUPPORTED_MODELS,
    cipher,
    create_provider_session,
    purge_expired,
    revoke_session,
)


class ProviderConfig(BaseModel):
    mode: Literal["server", "reviewer"]
    mock_mode: bool = Field(
        default=False,
        description="Explicit mock-demo presentation flag; does not enable processing.",
    )
    supported_models: list[str]
    max_pdf_bytes: int
    max_pdf_pages: int


class ProviderInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    api_key: SecretStr = Field(min_length=1, max_length=1024)


class ProviderConnection(BaseModel):
    session_token: str
    models: list[str]
    expires_at: datetime


def add_provider_routes(app, settings, engine, require_auth, *, mock_mode=False):
    @app.get(f"{API_PREFIX}/openai/config", response_model=ProviderConfig)
    def provider_config():
        return ProviderConfig(
            mode=settings.openai_credential_mode,
            mock_mode=mock_mode,
            supported_models=list(SUPPORTED_MODELS),
            max_pdf_bytes=settings.max_pdf_bytes,
            max_pdf_pages=MAX_PDF_PAGES,
        )

    def enabled():
        if settings.openai_credential_mode != "reviewer":
            raise HTTPException(400, "Reviewer-supplied OpenAI credentials are not enabled.")
        cipher(settings)

    @app.post(
        f"{API_PREFIX}/openai/sessions",
        response_model=ProviderConnection,
        dependencies=[Depends(require_auth), Depends(enabled)],
        openapi_extra={
            "requestBody": {
                "required": True,
                "content": {"application/json": {"schema": ProviderInput.model_json_schema()}},
            }
        },
    )
    async def connect_provider(
        request: Request, response: Response, actor: Annotated[Principal, Depends(require_auth)]
    ):
        require_role(actor, "submitter")
        response.headers["Cache-Control"] = "no-store"
        # Manual parsing keeps submitted secrets out of FastAPI's input-bearing 422 errors.
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 4096:
                raise HTTPException(413, "OpenAI connection request is too large.")
        try:
            values = ProviderInput.model_validate_json(bytes(body))
        except ValidationError:
            raise HTTPException(422, "Provide one OpenAI API key in api_key.") from None
        # Run synchronous network discovery off the event loop; no DB transaction is open.
        from starlette.concurrency import run_in_threadpool

        purge_expired(engine)
        result = await run_in_threadpool(
            create_provider_session,
            engine,
            settings,
            values.api_key.get_secret_value(),
            **({"owner_id": actor.owner_id} if actor.owner_id is not None else {}),
        )
        return result

    @app.delete(
        f"{API_PREFIX}/openai/session",
        status_code=204,
        dependencies=[Depends(require_auth), Depends(enabled)],
    )
    def disconnect_provider(
        response: Response,
        actor: Annotated[Principal, Depends(require_auth)],
        provider_session: Annotated[str, Header(alias="X-OpenAI-Session", max_length=200)],
    ):
        require_role(actor, "submitter")
        response.headers["Cache-Control"] = "no-store"
        revoke_session(engine, provider_session, owner_id=actor.owner_id)
