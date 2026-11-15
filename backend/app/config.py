import re
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url

from app.contracts import MAX_PDF_BYTES


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid", hide_input_in_errors=True)

    database_url: SecretStr
    app_api_token: SecretStr
    max_pdf_bytes: int = Field(default=MAX_PDF_BYTES, ge=1, le=MAX_PDF_BYTES)
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    reviewer_api_token: SecretStr | None = None
    database_schema: str | None = None
    frontend_directory: Path | None = None
    openai_credential_mode: Literal["server", "reviewer"] = "server"
    byok_encryption_key: SecretStr | None = None
    access_mode: Literal["shared", "roles"] = "shared"
    submitter_api_tokens: dict[str, SecretStr] = {}

    @model_validator(mode="after")
    def distinct_identities(self):
        credentials = [self.app_api_token.get_secret_value()]
        if self.reviewer_api_token:
            credentials.append(self.reviewer_api_token.get_secret_value())
        for ident, token in self.submitter_api_tokens.items():
            if not re.fullmatch(r"[a-z0-9_-]{1,64}", ident) or ident in ("submitter", "reviewer"):
                raise ValueError("Submitter identities must be distinct safe identifiers")
            if len(token.get_secret_value()) < 24:
                raise ValueError("Each submitter credential must have at least 24 characters")
            credentials.append(token.get_secret_value())
        if self.access_mode == "roles" and len(set(credentials)) != len(credentials):
            raise ValueError("Role credentials must be unique")
        return self

    @field_validator("database_schema")
    @classmethod
    def valid_schema(cls, value):
        if value is not None and not re.fullmatch(r"[a-z_][a-z0-9_]{0,55}", value):
            raise ValueError("DATABASE_SCHEMA must be a safe lowercase PostgreSQL identifier")
        return value

    @field_validator("reviewer_api_token")
    @classmethod
    def reviewer_length(cls, value):
        if value is not None and len(value.get_secret_value()) < 24:
            raise ValueError("REVIEWER_API_TOKEN must contain at least 24 characters")
        return value

    @field_validator("database_url")
    @classmethod
    def postgres_only(cls, value: SecretStr) -> SecretStr:
        if make_url(value.get_secret_value()).drivername != "postgresql+psycopg":
            raise ValueError("DATABASE_URL must use postgresql+psycopg")
        return value

    @field_validator("app_api_token")
    @classmethod
    def token_length(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 24:
            raise ValueError("APP_API_TOKEN must contain at least 24 characters")
        return value
