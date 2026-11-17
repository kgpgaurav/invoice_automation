"""Public presentation metadata must not guess processing mode or start processing."""

import sys

import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import create_app
from scripts import demo
from tests.conftest import TOKEN


def configuration(credential_mode="server"):
    return Settings(
        _env_file=None,
        database_url="postgresql+psycopg://unused@127.0.0.1:1/unused",
        app_api_token=TOKEN,
        openai_credential_mode=credential_mode,
        byok_encryption_key=Fernet.generate_key().decode(),
    )


@pytest.mark.parametrize("credential_mode", ["server", "reviewer"])
def test_credential_source_does_not_imply_mock_mode(credential_mode):
    # No database or provider is contacted by this public read.
    with TestClient(create_app(configuration(credential_mode))) as client:
        response = client.get("/api/v1/openai/config")
        assert response.status_code == 200
        assert response.json()["mode"] == credential_mode
        assert response.json()["mock_mode"] is False


@pytest.mark.parametrize("mode", ["mock", "live", "reviewer"])
def test_demo_api_advertises_only_explicit_mock_metadata(monkeypatch, tmp_path, mode):
    settings = configuration("reviewer" if mode == "reviewer" else "server")
    monkeypatch.setattr(demo, "load", lambda _: (tmp_path, {"mode": mode}, settings))
    monkeypatch.setattr(sys, "argv", ["demo", "api", "--name", "presentation-test"])
    captured = []

    def inspect_app(app, **options):
        assert options == {"host": "127.0.0.1", "port": 8000}
        with TestClient(app) as client:
            captured.append(client.get("/api/v1/openai/config").json())

    monkeypatch.setattr("uvicorn.run", inspect_app)
    demo.main()
    assert len(captured) == 1
    assert captured[0]["mock_mode"] is (mode == "mock")
    assert captured[0]["mode"] == settings.openai_credential_mode
