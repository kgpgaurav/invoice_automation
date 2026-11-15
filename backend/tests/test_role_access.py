"""Individual private-workspace identities; real PostgreSQL, no live model requests."""

from uuid import UUID, uuid4

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import Settings
from app.financial_models import ApprovalLedger
from app.intake import create_intake
from app.main import create_app
from app.models import QueueItem, Run
from app.provider_credentials import create_provider_session, load_key
from app.provider_models import ProviderSession
from tests.conftest import TOKEN
from tests.extraction_helpers import case
from tests.financial_fixtures import masters
from tests.workflow_helpers import execute, mock_processor

BOB = "synthetic-bob-submit-token-at-least-24"
CAROL = "synthetic-carol-submit-token-at-least-24"
REVIEWER = "synthetic-finance-review-token-at-least-24"
KEY = "synthetic-openai-key-not-live"


@pytest.fixture
def role_settings(settings):
    return Settings(
        _env_file=None,
        database_url=settings.database_url,
        app_api_token=TOKEN,
        reviewer_api_token=REVIEWER,
        access_mode="roles",
        submitter_api_tokens={"bob": BOB, "carol": CAROL},
    )


def auth(token):
    return {"Authorization": "Bearer " + token}


def submit(client, pdf, token=TOKEN, key="same-key"):
    return client.post(
        "/api/v1/invoices/process",
        headers=dict(auth(token), **{"X-Idempotency-Key": key}),
        files={"file": ("invoice.pdf", pdf, "application/pdf")},
        data={"owner_id": "bob"},
    )


def test_roles_come_from_credentials_not_client_claims(database, role_settings):
    with TestClient(create_app(role_settings, database[0])) as client:
        assert client.get("/api/v1/access").status_code == 401
        for token, role, actor in (
            (TOKEN, "submitter", "submitter"),
            (BOB, "submitter", "bob"),
            (CAROL, "submitter", "carol"),
            (REVIEWER, "reviewer", "reviewer"),
        ):
            result = client.get("/api/v1/access?role=reviewer", headers=auth(token)).json()
            assert (result["role"], result["actor_id"]) == (role, actor)
            assert ("upload" in result["pages"]) == (role == "submitter")
        for token in ("", "invalid-token"):
            assert client.get("/api/v1/access", headers=auth(token)).status_code == 401


@pytest.mark.parametrize(
    "path",
    [
        "/purchase-orders",
        "/purchase-orders/00000000-0000-0000-0000-000000000000",
        "/dashboard/summary",
        "/runs/00000000-0000-0000-0000-000000000000/review",
    ],
)
def test_submitter_cannot_open_finance_endpoints(database, role_settings, path):
    with TestClient(create_app(role_settings, database[0])) as client:
        assert client.get("/api/v1" + path, headers=auth(TOKEN)).status_code == 403
        assert client.get("/api/v1" + path, headers=auth(REVIEWER)).status_code in (200, 404)


def test_reviewer_cannot_upload_or_connect_provider(database, role_settings, pdf):
    values = role_settings.model_dump()
    values.update(
        openai_credential_mode="reviewer", byok_encryption_key=Fernet.generate_key().decode()
    )
    configured = Settings(_env_file=None, **values)
    with TestClient(create_app(configured, database[0])) as client:
        assert submit(client, pdf, REVIEWER).status_code == 403
        assert (
            client.post(
                "/api/v1/openai/sessions", headers=auth(REVIEWER), json={"api_key": KEY}
            ).status_code
            == 403
        )
        assert (
            client.delete(
                "/api/v1/openai/session",
                headers=dict(auth(REVIEWER), **{"X-OpenAI-Session": "opaque"}),
            ).status_code
            == 403
        )


def test_intake_ownership_and_idempotency_are_personal(database, role_settings, pdf):
    engine = database[0]
    with TestClient(create_app(role_settings, engine)) as client:
        a, b, c = submit(client, pdf), submit(client, pdf, BOB), submit(client, pdf, CAROL)
        assert a.status_code == b.status_code == c.status_code == 202
        assert len({result.json()["run_id"] for result in (a, b, c)}) == 3
        assert submit(client, pdf).json() == a.json()
        assert submit(client, pdf, BOB).json() == b.json()
        assert submit(client, pdf, CAROL).json() == c.json()
    with Session(engine) as session:
        assert session.get(Run, UUID(a.json()["run_id"])).owner_id == "submitter"
        assert session.get(Run, UUID(b.json()["run_id"])).owner_id == "bob"
        assert session.get(Run, UUID(c.json()["run_id"])).owner_id == "carol"
    # Fixed credentials retain their separate histories after API process recreation.
    with TestClient(create_app(role_settings, engine)) as restarted:
        for token, result in ((TOKEN, a), (BOB, b), (CAROL, c)):
            history = restarted.get("/api/v1/runs", headers=auth(token)).json()
            assert history["total_count"] == 1
            assert history["items"][0]["run_id"] == result.json()["run_id"]
            for other in (a, b, c):
                response = restarted.get(
                    "/api/v1/runs/" + other.json()["run_id"], headers=auth(token)
                )
                assert response.status_code == (200 if other is result else 404)
        assert restarted.get("/api/v1/runs", headers=auth(REVIEWER)).json()["total_count"] == 3


@pytest.mark.parametrize("suffix", ["", "/document", "/events", "/events/stream"])
def test_other_submitters_and_legacy_resources_are_hidden(database, role_settings, pdf, suffix):
    engine = database[0]
    legacy = create_intake(engine, pdf, None, None).run_id
    with TestClient(create_app(role_settings, engine)) as client:
        own = submit(client, pdf).json()["run_id"]
        other = submit(client, pdf, BOB).json()["run_id"]
        # Close only the synthetic transport fixture's queue so stream reads finish immediately.
        with Session(engine) as session, session.begin():
            for row in session.scalars(select(QueueItem)):
                row.status = "DONE"
        for ident in (other, str(legacy), str(uuid4())):
            assert (
                client.get(f"/api/v1/runs/{ident}{suffix}", headers=auth(TOKEN)).status_code == 404
            )
        assert client.get(f"/api/v1/runs/{own}{suffix}", headers=auth(TOKEN)).status_code == 200
        assert (
            client.get(f"/api/v1/runs/{other}{suffix}", headers=auth(REVIEWER)).status_code == 200
        )
        assert (
            client.get(f"/api/v1/runs/{legacy}{suffix}", headers=auth(REVIEWER)).status_code == 200
        )


def test_history_counts_search_and_cursors_are_owner_scoped(database, role_settings, pdf):
    with TestClient(create_app(role_settings, database[0])) as client:
        for i in range(3):
            submit(client, pdf, key=str(i))
            submit(client, pdf, BOB, key=str(i))
        create_intake(database[0], pdf, None, None)
        first = client.get("/api/v1/runs?limit=1&owner_id=bob", headers=auth(TOKEN)).json()
        assert first["total_count"] == 3
        assert client.get("/api/v1/runs", headers=auth(REVIEWER)).json()["total_count"] == 7
        assert (
            client.get(
                "/api/v1/runs", params={"cursor": first["next_cursor"]}, headers=auth(BOB)
            ).status_code
            == 422
        )
        other = client.get("/api/v1/runs", headers=auth(BOB)).json()["items"][0]["run_id"]
        assert (
            client.get("/api/v1/runs", params={"q": other}, headers=auth(TOKEN)).json()[
                "total_count"
            ]
            == 0
        )


def test_financial_details_are_not_in_submitter_response(workflow_db, role_settings):
    engine = workflow_db
    masters(engine)
    pdf, expected = case()
    with TestClient(create_app(role_settings, engine)) as client:
        a = submit(client, pdf).json()["run_id"]
        b = submit(client, pdf, BOB).json()["run_id"]
        processor, _ = mock_processor(engine, pdf, expected)
        execute(engine, processor)
        execute(engine, processor)
        own = client.get(f"/api/v1/runs/{a}", headers=auth(TOKEN)).json()
        finance = client.get(f"/api/v1/runs/{a}", headers=auth(REVIEWER)).json()
        assert own["decision"] == "APPROVED"
        for field in (
            "purchase_order",
            "vendor",
            "checks",
            "decision_observations",
            "review_request_id",
            "thread_id",
            "policy_version",
        ):
            assert field not in own
        assert finance["purchase_order"]["remaining_gross"] == "38200.00"
        assert client.get(f"/api/v1/runs/{b}", headers=auth(TOKEN)).status_code == 404
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1


def test_provider_session_belongs_to_its_submitter(database, role_settings, pdf, monkeypatch):
    values = role_settings.model_dump()
    values.update(
        openai_credential_mode="reviewer", byok_encryption_key=Fernet.generate_key().decode()
    )
    configured = Settings(_env_file=None, **values)
    from app import provider_routes

    def connected(engine, settings, key, **kwargs):
        with httpx.Client(
            transport=httpx.MockTransport(
                lambda _: httpx.Response(200, json={"data": [{"id": "gpt-6-luna"}]})
            )
        ) as mocked:
            return create_provider_session(engine, settings, key, client=mocked, **kwargs)

    monkeypatch.setattr(provider_routes, "create_provider_session", connected)
    engine = database[0]
    with TestClient(create_app(configured, engine)) as client:
        connection = client.post(
            "/api/v1/openai/sessions", headers=auth(TOKEN), json={"api_key": KEY}
        ).json()
        header = {"X-OpenAI-Session": connection["session_token"]}
        result = client.post(
            "/api/v1/invoices/process",
            headers=dict(auth(BOB), **header),
            files={"file": ("invoice.pdf", pdf)},
            data={"model_id": "gpt-6-luna"},
        )
        assert result.status_code == 400
        assert (
            client.delete("/api/v1/openai/session", headers=dict(auth(BOB), **header)).status_code
            == 204
        )
        with Session(engine) as session:
            row = session.scalar(select(ProviderSession))
            assert row.owner_id == "submitter" and row.ciphertext is not None
            ident = row.id
        assert load_key(engine, configured, ident) == KEY
        client.delete(
            "/api/v1/openai/session", headers=dict(auth(TOKEN), **header)
        ).raise_for_status()
        with Session(engine) as session:
            assert session.get(ProviderSession, ident).ciphertext is None


def test_owner_cannot_be_reassigned(database, role_settings, pdf):
    with TestClient(create_app(role_settings, database[0])) as client:
        submit(client, pdf)
    with pytest.raises(DBAPIError), database[0].begin() as connection:
        connection.execute(text("UPDATE runs SET owner_id='bob'"))


def test_role_credentials_must_be_distinct(role_settings):
    values = role_settings.model_dump()
    values["reviewer_api_token"] = TOKEN
    with pytest.raises(ValueError) as error:
        Settings(_env_file=None, **values)
    assert TOKEN not in str(error.value)
