from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import Settings
from app.demo_reset import ResetConflict, ResetRequest, preview_reset, reset_demo
from app.financial_models import ApprovalLedger, PurchaseOrder, Vendor
from app.main import create_app
from app.worker import Worker
from scripts.demo_fixtures import dataset, seed
from tests.conftest import TOKEN
from tests.workflow_helpers import execute, intake, mock_processor

REVIEWER = "reviewer-only-demo-reset-token-12345"


def schema_for(engine):
    with engine.connect() as connection:
        return connection.scalar(text("SELECT current_schema()"))


def body_for(engine):
    return ResetRequest(
        dataset="ps1-demo-v1",
        confirmation="RESET DEMO",
        snapshot=preview_reset(engine, schema_for(engine)).snapshot,
    )


@pytest.fixture
def reset_settings(settings, database):
    return Settings(
        _env_file=None,
        **(
            settings.model_dump()
            | {
                "access_mode": "roles",
                "reviewer_api_token": REVIEWER,
                "database_schema": schema_for(database[0]),
                "demo_reset_enabled": True,
            }
        ),
    )


def test_reset_restores_baseline_and_clears_actual_workflow_artifacts(workflow_db, reset_settings):
    from datetime import timedelta
    from uuid import uuid4

    from cryptography.fernet import Fernet

    from app.provider_models import ProviderSession

    engine = workflow_db
    seed(engine)
    for ident in ("H1", "E2"):
        _, pdf, expected = next(row for row in dataset() if row[0] == ident)
        intake(engine, pdf)
        handler, _ = mock_processor(engine, pdf, expected)
        execute(engine, handler)
    with Session(engine) as session, session.begin():
        now = session.scalar(select(func.now()))
        session.add(
            ProviderSession(
                capability_hash="a" * 64,
                ciphertext=Fernet(Fernet.generate_key()).encrypt(b"synthetic-only-key"),
                models_json=["test-model"],
                expires_at=now + timedelta(hours=1),
            )
        )
        custom_id = uuid4()
        session.add(Vendor(id=custom_id, legal_name="Custom reset test vendor", status="ACTIVE"))
    from app.po_contracts import POCreate
    from app.po_service import create_purchase_order

    create_purchase_order(
        engine,
        POCreate.model_validate(
            {
                "po_number": "CUSTOM-RESET",
                "vendor_id": str(custom_id),
                "currency": "INR",
                "issued_at": "2026-10-01",
                "cap_gross": "1000",
                "reason": "Custom reset fixture",
                "lines": [
                    {
                        "description": "Custom item",
                        "quantity": "1",
                        "unit_price": "1000",
                        "tax_rate": "0",
                    }
                ],
            }
        ),
        "custom-reset-po",
        "reviewer",
    )
    before = preview_reset(engine, schema_for(engine))
    assert before.counts["approval_ledger"] == 1 and before.counts["checkpoints"] > 0
    assert before.counts["review_requests"] == 1 and before.counts["provider_sessions"] == 1
    assert before.counts["purchase_orders"] == 5
    with TestClient(create_app(reset_settings, engine)) as client:
        client.headers["Authorization"] = "Bearer " + REVIEWER
        preview = client.get("/api/v1/demo/reset")
        assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
        result = client.post(
            "/api/v1/demo/reset",
            json={
                "dataset": "ps1-demo-v1",
                "snapshot": preview.json()["snapshot"],
                "confirmation": "RESET DEMO",
            },
            headers={"X-Idempotency-Key": "reset-case"},
        )
        assert result.status_code == 201
        assert "ciphertext" not in result.text and "synthetic-only-key" not in result.text
    after = preview_reset(engine, schema_for(engine))
    for table in (
        "runs",
        "documents",
        "run_queue",
        "intake_keys",
        "api_usage",
        "workflow_runs",
        "review_requests",
        "review_actions",
        "financial_assessments",
        "invoices",
        "approval_ledger",
        "approval_allocations",
        "provider_sessions",
        "run_provider_bindings",
        "checkpoints",
        "checkpoint_blobs",
        "checkpoint_writes",
    ):
        assert after.counts[table] == 0, table
    assert (after.counts["vendors"], after.counts["purchase_orders"]) == (3, 4)
    assert after.counts["demo_reset_receipts"] == 1
    with Session(engine) as session:
        assert {
            p.po_number: str(p.approved_cap_gross) for p in session.scalars(select(PurchaseOrder))
        } == {
            "PO-001": "50000.00",
            "PO-PARTIAL": "100000.00",
            "PO-SELECT-001": "25000.00",
            "PO-SELECT-002": "40000.00",
        }
        assert all(p.committed_gross == 0 for p in session.scalars(select(PurchaseOrder)))
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
    # Checkpoint migrations remain usable after clearing all thread data.
    _, pdf, expected = next(row for row in dataset() if row[0] == "H1")
    intake(engine, pdf)
    handler, _ = mock_processor(engine, pdf, expected)
    execute(engine, handler)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1


@pytest.mark.parametrize("credential,status", [(None, 401), (TOKEN, 403)])
def test_reset_is_not_exposed_to_anonymous_or_submitter(
    database, reset_settings, credential, status
):
    with TestClient(create_app(reset_settings, database[0])) as client:
        if credential:
            client.headers["Authorization"] = "Bearer " + credential
        assert client.get("/api/v1/demo/reset").status_code == status
        assert (
            client.post(
                "/api/v1/demo/reset",
                json=body_for(database[0]).model_dump(),
                headers={"X-Idempotency-Key": "forbidden"},
            ).status_code
            == status
        )


def test_shared_compatibility_and_disabled_profiles_cannot_reset(
    database, reset_settings, settings
):
    engine = database[0]
    with TestClient(create_app(settings, engine)) as client:
        client.headers["Authorization"] = "Bearer " + TOKEN
        assert client.get("/api/v1/demo/reset").status_code == 403
    disabled = reset_settings.model_copy(update={"demo_reset_enabled": False})
    with TestClient(create_app(disabled, engine)) as client:
        client.headers["Authorization"] = "Bearer " + REVIEWER
        assert client.get("/api/v1/demo/reset").json()["enabled"] is False
        assert (
            client.post(
                "/api/v1/demo/reset",
                json=body_for(engine).model_dump(),
                headers={"X-Idempotency-Key": "disabled"},
            ).status_code
            == 403
        )


@pytest.mark.parametrize(
    "override",
    [
        {"access_mode": "shared"},
        {"database_schema": None},
        {"database_schema": "public"},
        {"database_schema": "pg_catalog"},
        {"reviewer_api_token": None},
    ],
)
def test_destructive_reset_requires_an_explicit_dedicated_role_profile(reset_settings, override):
    with pytest.raises(ValidationError, match="Demo reset requires"):
        Settings(_env_file=None, **(reset_settings.model_dump() | override))


@pytest.mark.parametrize(
    "change",
    [
        {"confirmation": "yes"},
        {"dataset": "other"},
        {"snapshot": "not-a-fingerprint"},
        {"force": True},
    ],
)
def test_reset_requires_exact_confirmation(database, reset_settings, change):
    engine = database[0]
    with TestClient(create_app(reset_settings, engine)) as client:
        client.headers["Authorization"] = "Bearer " + REVIEWER
        assert (
            client.post(
                "/api/v1/demo/reset",
                json=body_for(engine).model_dump() | change,
                headers={"X-Idempotency-Key": "invalid"},
            ).status_code
            == 422
        )
    assert preview_reset(engine, schema_for(engine)).counts["demo_reset_receipts"] == 0


def test_stale_confirmation_cannot_clear_newer_submissions(database, pdf):
    engine = database[0]
    body = body_for(engine)
    intake(engine, pdf)
    with pytest.raises(ResetConflict, match="activity changed"):
        reset_demo(engine, schema_for(engine), body, "stale", "reviewer")
    assert preview_reset(engine, schema_for(engine)).counts["runs"] == 1


def test_replay_after_new_work_does_not_erase_it_and_changed_reuse_conflicts(database, pdf):
    engine = database[0]
    body = body_for(engine)
    first, replay = reset_demo(engine, schema_for(engine), body, "lost-response", "reviewer")
    assert not replay
    intake(engine, pdf)
    again, replay = reset_demo(engine, schema_for(engine), body, "lost-response", "reviewer")
    assert replay and again == first
    with pytest.raises(ResetConflict, match="different confirmation"):
        reset_demo(engine, schema_for(engine), body_for(engine), "lost-response", "reviewer")
    assert preview_reset(engine, schema_for(engine)).counts["runs"] == 1


@pytest.mark.parametrize("expired", [False, True])
def test_live_worker_ownership_blocks_reset_even_after_lease_expiry(database, pdf, expired):
    engine = database[0]
    intake(engine, pdf)
    worker = Worker(engine, lambda *_: None)
    claim = worker.claim()
    assert claim
    try:
        if expired:
            with engine.begin() as connection:
                connection.execute(
                    text("UPDATE run_queue SET lease_until=clock_timestamp()-interval '1 second'")
                )
        with pytest.raises(ResetConflict, match="worker is processing"):
            reset_demo(engine, schema_for(engine), body_for(engine), "owned", "reviewer")
        assert preview_reset(engine, schema_for(engine)).counts["runs"] == 1
    finally:
        claim.close()
    reset_demo(engine, schema_for(engine), body_for(engine), "after-owner", "reviewer")
    assert preview_reset(engine, schema_for(engine)).counts["runs"] == 0


@pytest.mark.parametrize("stage", ["clear", "restore"])
def test_failure_rolls_back_history_keys_checkpoints_and_seed_writes(database, pdf, stage):
    engine = database[0]
    intake(engine, pdf)
    before = preview_reset(engine, schema_for(engine))

    def fail(_):
        raise RuntimeError("injected reset failure")

    with pytest.raises(RuntimeError, match="injected"):
        reset_demo(
            engine,
            schema_for(engine),
            body_for(engine),
            "rollback",
            "reviewer",
            **{"after_" + stage: fail},
        )
    after = preview_reset(engine, schema_for(engine))
    assert after.counts == before.counts and after.snapshot == before.snapshot


def test_busy_intake_transaction_prevents_reset_then_commits_normally(database, pdf):
    engine = database[0]
    body = body_for(engine)
    with engine.begin() as connection:
        connection.execute(text("LOCK TABLE run_queue IN ROW EXCLUSIVE MODE"))
        with pytest.raises(ResetConflict, match="busy"):
            reset_demo(engine, schema_for(engine), body, "busy-intake", "reviewer")
    intake(engine, pdf)
    assert preview_reset(engine, schema_for(engine)).counts["runs"] == 1


def test_competing_resets_only_one_can_clear_a_given_preview(database):
    engine = database[0]
    body, schema, barrier = body_for(engine), schema_for(engine), Barrier(2)

    def run(index):
        barrier.wait()
        try:
            return reset_demo(engine, schema, body, f"compete-{index}", "reviewer")[0]
        except ResetConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(run, [1, 2]))
    assert sum(o is not None for o in outcomes) == 1
    assert preview_reset(engine, schema).counts["demo_reset_receipts"] == 1


@pytest.mark.parametrize(
    "statement",
    ["UPDATE demo_reset_receipts SET actor_id='changed'", "DELETE FROM demo_reset_receipts"],
)
def test_reset_receipts_cannot_be_rewritten(database, statement):
    engine = database[0]
    reset_demo(engine, schema_for(engine), body_for(engine), "immutable", "reviewer")
    with pytest.raises(DBAPIError, match="Financial history is immutable"):
        with engine.begin() as connection:
            connection.execute(text(statement))


def test_unexpected_tables_or_wrong_schema_are_not_cleared(database, pdf):
    engine = database[0]
    body, schema = body_for(engine), schema_for(engine)
    with pytest.raises(ResetConflict, match="configured dedicated"):
        reset_demo(engine, "public", body, "wrong-schema", "reviewer")
    with engine.begin() as connection:
        connection.execute(text("CREATE TABLE unrelated_notes (note text)"))
    with pytest.raises(ResetConflict, match="allowlist"):
        reset_demo(engine, schema, body, "unexpected", "reviewer")


def test_intake_waiting_on_reset_preserves_the_new_pdf_after_commit(database, pdf):
    from concurrent.futures import TimeoutError

    from app.models import Document, Run

    engine = database[0]
    body, schema = body_for(engine), schema_for(engine)
    cleared, release = Event(), Event()

    def pause(_):
        cleared.set()
        assert release.wait(10)

    with ThreadPoolExecutor(max_workers=2) as pool:
        reset = pool.submit(
            reset_demo, engine, schema, body, "intake-race", "reviewer", after_clear=pause
        )
        assert cleared.wait(10)
        arrival = pool.submit(intake, engine, pdf)
        try:
            with pytest.raises(TimeoutError):
                arrival.result(timeout=0.15)
        finally:
            release.set()
        reset.result(timeout=10)
        ident = arrival.result(timeout=10)
    with Session(engine) as session:
        assert session.get(Document, session.get(Run, ident).document_id).content == pdf
    assert preview_reset(engine, schema).counts["runs"] == 1


def test_cross_schema_references_never_trigger_cascading_deletion(database):
    engine = database[0]
    seed(engine)
    schema, body = schema_for(engine), body_for(engine)
    guard = schema + "_guard"
    with engine.begin() as connection:
        connection.execute(text(f'CREATE SCHEMA "{guard}"'))
        connection.execute(
            text(f'CREATE TABLE "{guard}".links (vendor_id uuid REFERENCES "{schema}".vendors(id))')
        )
        connection.execute(text(f'INSERT INTO "{guard}".links SELECT id FROM vendors LIMIT 1'))
    try:
        with pytest.raises(DBAPIError):
            reset_demo(engine, schema, body, "no-cascade", "reviewer")
        with engine.connect() as connection:
            assert connection.scalar(text(f'SELECT count(*) FROM "{guard}".links')) == 1
        assert preview_reset(engine, schema).snapshot == body.snapshot
    finally:
        with engine.begin() as connection:
            connection.execute(text(f'DROP TABLE "{guard}".links'))
            connection.execute(text(f'DROP SCHEMA "{guard}"'))


def test_later_reset_retains_old_receipts_and_reports_only_removed_tables(database):
    engine = database[0]
    first, _ = reset_demo(engine, schema_for(engine), body_for(engine), "first", "reviewer")
    second, _ = reset_demo(engine, schema_for(engine), body_for(engine), "second", "reviewer")
    assert first.reset_id != second.reset_id
    assert "demo_reset_receipts" not in second.removed_counts
    assert preview_reset(engine, schema_for(engine)).counts["demo_reset_receipts"] == 2
