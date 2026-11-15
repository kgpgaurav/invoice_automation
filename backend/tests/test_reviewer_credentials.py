"""Real database + mocked OpenAI; no operator or reviewer live key is used."""

import json
import os
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from threading import Barrier

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import Settings
from app.extraction_client import ExtractionError
from app.financial_models import ApprovalLedger
from app.intake import create_intake
from app.main import create_app
from app.models import Document, Run
from app.provider_credentials import (
    ReviewerWorkflowProcessor,
    SessionExtractor,
    create_provider_session,
    discover_models,
    load_key,
    purge_expired,
    revoke_session,
)
from app.provider_models import ProviderSession, RunProviderBinding
from app.worker import Worker, WorkerPolicy
from tests.extraction_helpers import case, response, untrusted_extraction
from tests.financial_fixtures import POLICY, masters

KEY_A = "synthetic-reviewer-key-A-never-live"
KEY_B = "synthetic-reviewer-key-B-never-live"


@pytest.fixture
def reviewer_settings(settings):
    return Settings(
        _env_file=None,
        database_url=settings.database_url,
        app_api_token=settings.app_api_token,
        openai_api_key="synthetic-owner-key-must-never-be-used",
        openai_model="gpt-6-luna",
        openai_credential_mode="reviewer",
        byok_encryption_key=Fernet.generate_key().decode(),
    )


def catalog(status=200, data=None):
    return httpx.Client(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(
                status,
                json=data
                if data is not None
                else {
                    "data": [
                        {"id": "gpt-6-luna"},
                        {"id": "gpt-6.1-terra"},
                        {"id": "embedding-model"},
                    ]
                },
            )
        )
    )


def connect(engine, settings, key=KEY_A):
    with catalog() as client:
        return create_provider_session(engine, settings, key, client=client)


def session_id(engine, token):
    from app.provider_credentials import capability_hash

    with Session(engine) as s:
        return s.scalar(
            select(ProviderSession.id).where(
                ProviderSession.capability_hash == capability_hash(token)
            )
        )


def test_key_encrypted_restart_and_ciphertext_substitution(database, reviewer_settings):
    engine = database[0]
    a, b = connect(engine, reviewer_settings), connect(engine, reviewer_settings, KEY_B)
    aid, bid = session_id(engine, a["session_token"]), session_id(engine, b["session_token"])
    with Session(engine) as s:
        row = s.get(ProviderSession, aid)
        assert KEY_A.encode() not in row.ciphertext
        assert a["session_token"] != row.capability_hash
        assert row.expires_at - row.created_at == timedelta(hours=24)
        encrypted_b = s.get(ProviderSession, bid).ciphertext
    restarted = Settings(**reviewer_settings.model_dump(), _env_file=None)
    assert load_key(engine, restarted, aid) == KEY_A
    assert load_key(engine, restarted, bid) == KEY_B
    with Session(engine) as s, s.begin():
        s.get(ProviderSession, aid).ciphertext = encrypted_b
    with pytest.raises(ExtractionError, match="BYOK_CREDENTIALS_UNAVAILABLE"):
        load_key(engine, restarted, aid)


def test_expiry_purge_and_revocation(database, reviewer_settings):
    engine = database[0]
    a, b = connect(engine, reviewer_settings), connect(engine, reviewer_settings, KEY_B)
    aid, bid = session_id(engine, a["session_token"]), session_id(engine, b["session_token"])
    with Session(engine) as s, s.begin():
        row = s.get(ProviderSession, aid)
        now = s.scalar(select(func.now()))
        row.created_at, row.expires_at = now - timedelta(days=2), now - timedelta(days=1)
    with pytest.raises(ExtractionError, match="BYOK_CREDENTIALS_UNAVAILABLE"):
        load_key(engine, reviewer_settings, aid)
    revoke_session(engine, b["session_token"])
    revoke_session(engine, b["session_token"])
    purge_expired(engine)
    with Session(engine) as s:
        assert s.get(ProviderSession, aid).ciphertext is None
        assert s.get(ProviderSession, bid).ciphertext is None
    with pytest.raises(ExtractionError):
        load_key(engine, reviewer_settings, bid)


@pytest.mark.parametrize(
    "status,body",
    [
        (401, {}),
        (403, {}),
        (429, {}),
        (500, {}),
        (200, {}),
        (200, {"data": [{"id": "embedding-model"}]}),
        (200, {"data": [None]}),
    ],
)
def test_bad_catalog_is_sanitized(status, body):
    with catalog(status, body) as client, pytest.raises(HTTPException) as error:
        discover_models(KEY_A, client)
    assert KEY_A not in str(error.value)


def test_provider_api_and_validation_redaction(database, reviewer_settings, monkeypatch, pdf):
    engine = database[0]
    from app import provider_routes

    monkeypatch.setattr(
        provider_routes, "create_provider_session", lambda e, cfg, key: connect(e, cfg, key)
    )
    with TestClient(create_app(reviewer_settings, engine)) as client:
        assert client.post("/api/v1/openai/sessions", json={"api_key": KEY_A}).status_code == 401
        client.headers["Authorization"] = (
            "Bearer " + reviewer_settings.app_api_token.get_secret_value()
        )
        assert client.get("/api/v1/openai/config").json()["mode"] == "reviewer"
        for body in ({"api_key": KEY_A, "unexpected": KEY_A}, {"api_key": KEY_A * 80}, {}):
            result = client.post("/api/v1/openai/sessions", json=body)
            assert result.status_code in (413, 422)
            assert KEY_A not in result.text
        result = client.post("/api/v1/openai/sessions", json={"api_key": KEY_A})
        assert result.status_code == 200 and KEY_A not in result.text
        connection = result.json()
        assert connection["models"] == ["gpt-6-luna", "gpt-6.1-terra"]
        files = {"file": ("H1.pdf", pdf, "application/pdf")}
        assert client.post("/api/v1/invoices/process", files=files).status_code == 400
        headers = {"X-OpenAI-Session": connection["session_token"], "X-Idempotency-Key": "byok-1"}
        body = {"model_id": "gpt-6-luna"}
        result = client.post("/api/v1/invoices/process", files=files, data=body, headers=headers)
        assert result.status_code == 202
        assert (
            client.post("/api/v1/invoices/process", files=files, data=body, headers=headers).json()
            == result.json()
        )
        assert (
            client.post(
                "/api/v1/invoices/process",
                files=files,
                data={"model_id": "gpt-6.1-terra"},
                headers=headers,
            ).status_code
            == 409
        )
        client.delete("/api/v1/openai/session", headers=headers).raise_for_status()
        assert (
            client.post(
                "/api/v1/invoices/process",
                files=files,
                data=body,
                headers={"X-OpenAI-Session": connection["session_token"]},
            ).status_code
            == 400
        )
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(Run)) == 1
        binding = s.scalar(select(RunProviderBinding))
        assert binding.model_id == "gpt-6-luna"
        assert s.get(ProviderSession, binding.session_id).ciphertext is None


def test_binding_rollback_and_immutability(database, reviewer_settings, pdf):
    engine = database[0]
    connection = connect(engine, reviewer_settings)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE run_queue ADD CONSTRAINT injected_failure CHECK(false)"))
    with pytest.raises(DBAPIError):
        create_intake(
            engine,
            pdf,
            None,
            "rollback-byok",
            provider_token=connection["session_token"],
            model_id="gpt-6-luna",
        )
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(RunProviderBinding)) == 0
        assert s.scalar(select(func.count()).select_from(Document)) == 0
    with engine.begin() as c:
        c.execute(text("ALTER TABLE run_queue DROP CONSTRAINT injected_failure"))
    create_intake(
        engine, pdf, None, None, provider_token=connection["session_token"], model_id="gpt-6-luna"
    )
    with pytest.raises(DBAPIError), engine.begin() as c:
        c.execute(text("UPDATE run_provider_bindings SET model_id='gpt-6.1-terra'"))


def test_two_reviewers_restart_and_no_owner_key_fallback(workflow_db, reviewer_settings):
    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    calls = []

    def factory(key, model):
        def handle(request):
            calls.append((key, json.loads(request.content)["model"]))
            return response(untrusted_extraction(pdf, expected))

        return httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        )

    for key, model in ((KEY_A, "gpt-6-luna"), (KEY_B, "gpt-6.1-terra")):
        connection = connect(engine, reviewer_settings, key)
        create_intake(
            engine, pdf, None, None, provider_token=connection["session_token"], model_id=model
        )
        # Recreate the processor using only the durable binding and encryption key.
        processor = ReviewerWorkflowProcessor(
            engine, reviewer_settings, POLICY.version, client_factory=factory
        )
        processor.check_ready()
        assert Worker(engine, processor).run_once()
    assert calls == [(KEY_A, "gpt-6-luna"), (KEY_B, "gpt-6.1-terra")]
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert sorted(s.scalars(select(Run.decision)).all()) == ["APPROVED", "REJECTED"]


def test_revoked_queued_run_never_calls_model(workflow_db, reviewer_settings):
    engine = workflow_db
    masters(engine)
    pdf, _ = case()
    connection = connect(engine, reviewer_settings)
    ident = create_intake(
        engine, pdf, None, None, provider_token=connection["session_token"], model_id="gpt-6-luna"
    ).run_id
    revoke_session(engine, connection["session_token"])

    def forbidden(*_):
        pytest.fail("A revoked session must never create a provider client")

    processor = ReviewerWorkflowProcessor(
        engine, reviewer_settings, POLICY.version, client_factory=forbidden
    )
    assert Worker(engine, processor, WorkerPolicy(max_attempts=1)).run_once()
    with Session(engine) as s:
        assert s.get(Run, ident).job_state == "FAILED"
        assert s.get(Document, s.get(Run, ident).document_id).content == pdf
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0


def test_disconnect_before_transport_retry_blocks_second_attempt(database, reviewer_settings):
    engine = database[0]
    connection = connect(engine, reviewer_settings)
    ident = session_id(engine, connection["session_token"])
    calls, reservations = [], []

    def factory(key, model):
        def handle(request):
            calls.append(request)
            revoke_session(engine, connection["session_token"])
            return httpx.Response(429, json={})

        return httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        )

    extractor = SessionExtractor(
        engine, reviewer_settings, ident, "gpt-6-luna", client_factory=factory
    )
    pdf, _ = case()
    with pytest.raises(ExtractionError, match="BYOK_CREDENTIALS_UNAVAILABLE"):
        extractor.extract(pdf, before_attempt=reservations.append)
    assert len(calls) == len(reservations) == 1


def test_concurrent_workers_keep_credentials_separate(workflow_db, reviewer_settings):
    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    barrier, calls = Barrier(2), []

    def factory(key, model):
        def handle(request):
            calls.append((key, json.loads(request.content)["model"]))
            barrier.wait(timeout=15)
            return response(untrusted_extraction(pdf, expected))

        return httpx.Client(
            base_url="https://api.openai.com/v1", transport=httpx.MockTransport(handle)
        )

    for key, model in ((KEY_A, "gpt-6-luna"), (KEY_B, "gpt-6.1-terra")):
        connection = connect(engine, reviewer_settings, key)
        create_intake(
            engine, pdf, None, None, provider_token=connection["session_token"], model_id=model
        )
    processor = ReviewerWorkflowProcessor(
        engine, reviewer_settings, POLICY.version, client_factory=factory
    )
    with ThreadPoolExecutor(max_workers=2) as executor:
        assert all(executor.map(lambda _: Worker(engine, processor).run_once(), range(2)))
    assert set(calls) == {(KEY_A, "gpt-6-luna"), (KEY_B, "gpt-6.1-terra")}
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1


def test_disconnect_between_key_read_and_reservation_is_fenced(
    workflow_db, reviewer_settings, monkeypatch
):
    from app import provider_credentials
    from app.workflow_models import WorkflowRun

    engine = workflow_db
    masters(engine)
    pdf, _ = case()
    connection = connect(engine, reviewer_settings)
    ident = create_intake(
        engine, pdf, None, None, provider_token=connection["session_token"], model_id="gpt-6-luna"
    ).run_id
    original = provider_credentials.load_key
    reads = []

    def racing_read(*args):
        key = original(*args)
        reads.append(1)
        if len(reads) == 2:
            revoke_session(engine, connection["session_token"])
        return key

    monkeypatch.setattr(provider_credentials, "load_key", racing_read)

    def factory(*_):
        return httpx.Client(
            base_url="https://api.openai.com/v1",
            transport=httpx.MockTransport(
                lambda _: pytest.fail("Revocation before reservation must prevent HTTP")
            ),
        )

    processor = ReviewerWorkflowProcessor(
        engine, reviewer_settings, POLICY.version, client_factory=factory
    )
    assert Worker(engine, processor, WorkerPolicy(max_attempts=1)).run_once()
    with Session(engine) as session:
        assert session.get(Run, ident).job_state == "FAILED"
        assert session.get(WorkflowRun, ident).extraction_attempts == 0


@pytest.mark.parametrize("point", ["before_financial_commit", "after_financial_commit"])
def test_process_restart_reuses_extraction_after_key_revocation(
    workflow_db, reviewer_settings, point
):
    engine = workflow_db
    masters(engine)
    pdf, _ = case()
    connection = connect(engine, reviewer_settings)
    run_id = create_intake(
        engine, pdf, None, None, provider_token=connection["session_token"], model_id="gpt-6-luna"
    ).run_id
    with engine.connect() as c:
        schema = c.scalar(text("SELECT current_schema()"))

    def child(mode):
        return subprocess.run(
            [
                sys.executable,
                "-m",
                "tests.reviewer_harness",
                engine.url.render_as_string(hide_password=False),
                schema,
                mode,
            ],
            env=dict(
                os.environ,
                PS1_TEST_BYOK_CIPHER=reviewer_settings.byok_encryption_key.get_secret_value(),
            ),
            capture_output=True,
            text=True,
            timeout=40,
            creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
        )

    assert child(point).returncode == 73
    revoke_session(engine, connection["session_token"])
    with engine.begin() as c:
        c.execute(text("UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second'"))
    processor = ReviewerWorkflowProcessor(engine, reviewer_settings, POLICY.version)
    assert Worker(engine, processor, WorkerPolicy(retry_seconds=0)).run_once() is False
    assert child("complete").returncode == 0
    with Session(engine) as session:
        assert session.get(Run, run_id).decision == "APPROVED"
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
