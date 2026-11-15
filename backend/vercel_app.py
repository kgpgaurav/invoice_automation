"""Vercel ASGI entrypoint for the explicitly selected private BYOK demo profile."""

from app.config import Settings
from app.main import create_app


def build_app(settings):
    if (
        settings.access_mode != "roles"
        or settings.openai_credential_mode != "reviewer"
        or settings.reviewer_api_token is None
        or set(settings.submitter_api_tokens) != {"submitter-b", "submitter-c"}
        or settings.openai_api_key is not None
    ):
        raise ValueError(
            "Vercel demo requires roles, submitter-owned OpenAI credentials, "
            "submitter-b/submitter-c tokens, a reviewer token and no operator OpenAI key."
        )
    settings = settings.model_copy(
        update={"max_pdf_bytes": min(settings.max_pdf_bytes, 4 * 1024 * 1024)}
    )
    return create_app(settings)


app = build_app(Settings())
