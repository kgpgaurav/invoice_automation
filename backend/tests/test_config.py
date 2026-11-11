import pytest
from pydantic import ValidationError

from app.config import Settings


def test_secrets_are_masked_and_openai_is_optional():
    settings = Settings(
        _env_file=None,
        database_url="postgresql+psycopg://u:secret@localhost/db",
        app_api_token="a-test-token-with-at-least-24-characters",
    )
    assert settings.openai_api_key is None
    assert settings.openai_model is None
    assert "secret" not in repr(settings)
    assert "a-test-token" not in repr(settings)


@pytest.mark.parametrize(
    "values",
    [
        {"database_url": "sqlite:///test.db", "app_api_token": "x" * 24},
        {"database_url": "postgresql+psycopg://u@localhost/db", "app_api_token": "short"},
        {"database_url": "postgresql+psycopg://u@localhost/db"},
    ],
)
def test_invalid_settings_fail_fast(values):
    with pytest.raises(ValidationError):
        Settings(_env_file=None, **values)
