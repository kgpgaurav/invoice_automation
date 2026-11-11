from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import make_url


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="forbid")

    database_url: SecretStr
    app_api_token: SecretStr
    openai_api_key: SecretStr | None = None
    openai_model: str | None = None
    reviewer_api_token: SecretStr | None = None

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
