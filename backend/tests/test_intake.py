from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pymupdf
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.main import create_app
from app.models import Document, IntakeKey, QueueItem, Run, RunEvent


def upload(client, pdf, key="test-intake", source=None):
    return client.post(
        "/api/v1/invoices/process",
        files={"file": ("invoice.pdf", pdf)},
        data={"source": source} if source else {},
        headers={"X-Idempotency-Key": key},
    )


def test_intake_persists_atomic_records_and_survives_app_restart(client, database, settings, pdf):
    response = upload(client, pdf)
    assert response.status_code == 202
    body = response.json()
    assert body["job_state"] == "QUEUED"
    with Session(database[0]) as session:
        for model in (Document, Run, QueueItem, RunEvent, IntakeKey):
            assert session.scalar(select(func.count()).select_from(model)) == 1
        assert session.scalar(select(Document)).content == pdf
        assert session.scalar(select(RunEvent)).type == "RUN_QUEUED"
        assert session.scalar(select(QueueItem)).status == "READY"
    with TestClient(create_app(settings, database[0])) as restarted:
        status = restarted.get(body["links"]["status"], headers=dict(client.headers))
        assert status.status_code == 200
        assert status.json()["decision"] is None
        assert status.json()["replay_mode"] is False
        assert "no worker" in status.json()["implementation_notice"]
        assert status.json()["created_at"].endswith("Z")


def test_same_key_same_payload_and_changed_source(client, database, pdf):
    original = upload(client, pdf)
    assert upload(client, pdf).json() == original.json()
    assert upload(client, pdf, source="different").status_code == 409
    assert upload(client, pdf + b"\n").status_code == 409
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 1


def test_concurrent_idempotency(client, database, pdf):
    with ThreadPoolExecutor(max_workers=4) as executor:
        results = list(executor.map(lambda _: upload(client, pdf), range(4)))
    assert all(result.status_code == 202 for result in results)
    assert len({result.json()["run_id"] for result in results}) == 1
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Document)) == 1


@pytest.mark.parametrize(
    "case,expected",
    [
        ("fake", 422),
        ("empty", 422),
        ("pages", 422),
        ("encrypted", 422),
        ("owner_only", 422),
        ("large", 413),
    ],
)
def test_invalid_pdf_creates_no_records(client, database, case, expected):
    content = {"fake": b"%PDF-1.7\nnot a pdf", "empty": b"", "large": b"x" * (12582912 + 1)}
    if case in ("pages", "encrypted", "owner_only"):
        with pymupdf.open() as document:
            for _ in range(6 if case == "pages" else 1):
                document.new_page()
            content[case] = document.tobytes(
                encryption=pymupdf.PDF_ENCRYPT_AES_256 if case != "pages" else 0,
                owner_pw="owner",
                user_pw="" if case == "owner_only" else "secret",
            )
    assert upload(client, content[case]).status_code == expected
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Run)) == 0


def test_auth_and_resource_validation(client, pdf):
    client.headers.pop("Authorization")
    assert upload(client, pdf).status_code == 401
    assert client.get(f"/api/v1/runs/{uuid4()}").status_code == 401
    client.headers["Authorization"] = "Bearer invalid"
    assert upload(client, pdf).status_code == 401


def test_missing_or_invalid_run(client):
    assert client.get(f"/api/v1/runs/{uuid4()}").status_code == 404
    assert client.get("/api/v1/runs/not-a-uuid").status_code == 422


def test_transaction_failure_rolls_back_everything(client, database, pdf):
    # A real DB-side failure after the PDF/run inserts must not leave partial intake.
    with database[0].begin() as connection:
        connection.execute(text("ALTER TABLE run_queue ADD CONSTRAINT test_failure CHECK (false)"))
    response = upload(client, pdf)
    assert response.status_code == 503
    assert "Database unavailable" in response.json()["detail"]
    with Session(database[0]) as session:
        for model in (Document, Run, QueueItem, RunEvent, IntakeKey):
            assert session.scalar(select(func.count()).select_from(model)) == 0
