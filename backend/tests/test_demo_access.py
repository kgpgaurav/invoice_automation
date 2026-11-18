"""Public assignment access is opt-in and cannot publish provider/server secrets."""

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.config import Settings
from app.main import create_app

SUBMITTER = "synthetic-public-demo-submitter-at-least-24"
REVIEWER = "synthetic-public-demo-reviewer-at-least-24"
PRIVATE_SUBMITTER = "synthetic-unpublished-submit-b-at-least-24"


def configured(**overrides):
    values = dict(
        database_url="postgresql+psycopg://unused:private-db-password@127.0.0.1:1/unused",
        app_api_token=SUBMITTER,
        reviewer_api_token=REVIEWER,
        submitter_api_tokens={"submitter-b": PRIVATE_SUBMITTER},
        access_mode="roles",
        openai_credential_mode="reviewer",
        openai_api_key=None,
        byok_encryption_key=Fernet.generate_key().decode(),
    )
    return Settings(_env_file=None, **(values | overrides))


@pytest.mark.parametrize("mode", ["server", "reviewer"])
def test_demo_credentials_are_private_by_default(mode):
    settings = configured(
        openai_credential_mode=mode,
        openai_api_key="synthetic-private-provider-key" if mode == "server" else None,
    )
    assert settings.public_demo_access is False
    with TestClient(create_app(settings)) as client:
        result = client.get("/api/v1/demo-access")
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert result.json() == {"roles": []}


def test_public_demo_returns_only_the_two_designated_app_tokens_and_enforces_roles():
    settings = configured(public_demo_access=True)
    with TestClient(create_app(settings)) as client:
        result = client.get("/api/v1/demo-access")
        assert result.status_code == 200
        assert result.headers["cache-control"] == "no-store"
        assert result.json() == {
            "roles": [
                {"role": "submitter", "token": SUBMITTER},
                {"role": "reviewer", "token": REVIEWER},
            ]
        }
        for private in (
            PRIVATE_SUBMITTER,
            "private-db-password",
            settings.byok_encryption_key.get_secret_value(),
        ):
            assert private not in result.text
        config = client.get("/api/v1/openai/config").text
        assert SUBMITTER not in config and REVIEWER not in config
        assert client.get("/api/v1/access").status_code == 401
        for role, token in (("submitter", SUBMITTER), ("reviewer", REVIEWER)):
            headers = {"Authorization": "Bearer " + token}
            profile = client.get("/api/v1/access?role=reviewer", headers=headers).json()
            assert profile["role"] == role
            assert ("upload" in profile["pages"]) is (role == "submitter")
        assert (
            client.get(
                "/api/v1/purchase-orders", headers={"Authorization": "Bearer " + SUBMITTER}
            ).status_code
            == 403
        )
        assert (
            client.post(
                "/api/v1/openai/sessions",
                headers={"Authorization": "Bearer " + REVIEWER},
                json={"api_key": "synthetic-never-sent-to-provider"},
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "overrides",
    [
        {"access_mode": "shared"},
        {"openai_credential_mode": "server"},
        {"reviewer_api_token": None},
        {"openai_api_key": "synthetic-operator-key-must-stay-private"},
    ],
)
def test_public_demo_rejects_shared_or_operator_billing_configurations(overrides):
    with pytest.raises(ValidationError, match="Public demo access requires") as error:
        configured(public_demo_access=True, **overrides)
    assert SUBMITTER not in str(error.value) and REVIEWER not in str(error.value)
