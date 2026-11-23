"""Guarded synthetic master setup in isolated real PostgreSQL schemas."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.approval import approve
from app.financial_models import (
    POCreation,
    PolicyVersion,
    POLine,
    PurchaseOrder,
    Vendor,
    VendorAction,
)
from app.po_totals import order_amounts
from scripts.demo_fixtures import seed
from scripts.seed_demo import DATASET, SeedConflict, seed_demo
from tests.financial_fixtures import POLICY, document, masters, run


def execute(engine, **kwargs):
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    return seed_demo(engine, schema, schema, DATASET, **kwargs)


def counts(engine):
    with engine.connect() as connection:
        return {
            table: connection.scalar(text(f'SELECT count(*) FROM "{table}"'))
            for table in inspect(connection).get_table_names()
        }


def snapshot(engine):
    with Session(engine) as session:
        return (
            [
                (v.id, v.legal_name, v.name_key, v.status, v.bank_last4)
                for v in session.scalars(select(Vendor).order_by(Vendor.id))
            ],
            [
                (
                    p.id,
                    p.vendor_id,
                    p.po_number,
                    p.status,
                    p.approved_cap_gross,
                    p.committed_gross,
                    p.version,
                )
                for p in session.scalars(select(PurchaseOrder).order_by(PurchaseOrder.id))
            ],
            [
                (p.id, p.po_id, p.quantity, p.unit_price, p.tax_rate, p.committed_quantity)
                for p in session.scalars(select(POLine).order_by(POLine.id))
            ],
            counts(engine),
        )


@pytest.mark.parametrize(
    "schema,confirmation,dataset",
    [
        (None, None, DATASET),
        ("public", "public", DATASET),
        ("pg_catalog", "pg_catalog", DATASET),
        ("private_app", "different_app", DATASET),
        ("private_app", "private_app", "wrong"),
    ],
)
def test_confirmation_and_private_schema_guard_precede_connection(schema, confirmation, dataset):
    with pytest.raises(SeedConflict):
        seed_demo(None, schema, confirmation, dataset, apply=True)


def test_dry_run_performs_no_data_writes(database):
    engine = database[0]
    before = counts(engine)
    writes = []

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.lstrip().split()[0].upper() in (
            "INSERT",
            "UPDATE",
            "DELETE",
            "CREATE",
            "ALTER",
        ):
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", observe)
    try:
        report = execute(engine)
    finally:
        event.remove(engine, "before_cursor_execute", observe)
    assert report["mode"] == "DRY_RUN" and report["policy_to_create"]
    assert report["vendors_to_create"] == 3 and len(report["purchase_orders_to_create"]) == 4
    assert writes == [] and counts(engine) == before


def test_apply_adds_only_expected_masters_audits_and_policy_and_replays(database):
    engine = database[0]
    before = counts(engine)
    first = execute(engine, apply=True)
    assert first["mode"] == "APPLIED" and first["vendors_to_create"] == 3
    after = counts(engine)
    changed = {table for table in after if after[table] != before[table]}
    assert changed == {
        "vendors",
        "purchase_orders",
        "po_lines",
        "policy_versions",
        "vendor_actions",
        "purchase_order_creations",
    }
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(VendorAction)) == 3
        assert session.scalar(select(func.count()).select_from(POCreation)) == 4
        assert session.get(PolicyVersion, POLICY.version).config_json == POLICY.model_dump(
            mode="json"
        )
        po = session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-001"))
        assert po.approved_cap_gross == 50000 and po.committed_gross == 0 and po.version == 1
        assert (
            order_amounts(session.scalars(select(POLine).where(POLine.po_id == po.id))).total_gross
            == 118000
        )
        assert all(
            a.snapshot_json["seed_dataset"] == DATASET
            for a in session.scalars(select(VendorAction))
        )
        assert all(
            a.snapshot_json["seed_dataset"] == DATASET for a in session.scalars(select(POCreation))
        )
    saved = snapshot(engine)
    replay = execute(engine, apply=True)
    assert replay["vendors_to_create"] == 0 and replay["vendors_existing"] == 3
    assert (
        replay["purchase_orders_to_create"] == [] and len(replay["purchase_orders_existing"]) == 4
    )
    assert not replay["policy_to_create"] and snapshot(engine) == saved


def test_legacy_fixture_masters_are_reused_without_name_or_audit_backfill(database):
    engine = database[0]
    seed(engine)
    before = snapshot(engine)
    report = execute(engine, apply=True)
    assert report["vendors_existing"] == 3 and len(report["purchase_orders_existing"]) == 4
    assert snapshot(engine) == before


def test_populated_po_balances_and_approval_history_survive_setup_and_replay(database, pdf):
    engine = database[0]
    vendor_id, po_id, line_id = masters(engine)
    run_id = run(engine, pdf)
    result = approve(engine, run_id, document(), POLICY.version)
    assert result.decision == "APPROVED"
    before = counts(engine)
    report = execute(engine, apply=True)
    assert report["vendors_existing"] == 1 and report["vendors_to_create"] == 2
    with Session(engine) as session:
        assert session.get(Vendor, vendor_id).name_key is None
        assert session.get(PurchaseOrder, po_id).committed_gross == 11800
        assert session.get(POLine, line_id).committed_quantity == 10
        assert session.scalar(select(POCreation).where(POCreation.po_id == po_id)) is None
    for table in (
        "runs",
        "documents",
        "invoices",
        "approval_ledger",
        "approval_allocations",
        "run_events",
        "run_queue",
    ):
        assert counts(engine)[table] == before[table]
    saved = snapshot(engine)
    execute(engine, apply=True)
    assert snapshot(engine) == saved


@pytest.mark.parametrize(
    "conflict", ["BLACKLISTED", "INACTIVE", "bank", "name", "cap", "line", "closed"]
)
def test_existing_identity_state_or_terms_conflicts_never_overwrite_anything(database, conflict):
    engine = database[0]
    seed(engine)
    with Session(engine) as session, session.begin():
        vendor = session.scalar(select(Vendor).where(Vendor.legal_name == "Aster Office Supplies"))
        po = session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-001"))
        if conflict in ("BLACKLISTED", "INACTIVE"):
            vendor.status = conflict
        elif conflict == "bank":
            vendor.bank_last4 = "9876"
        elif conflict == "name":
            vendor.legal_name = "Another supplier"
        elif conflict == "cap":
            po.approved_cap_gross = 49000
        elif conflict == "closed":
            po.status = "CLOSED"
        else:
            session.scalar(select(POLine).where(POLine.po_id == po.id)).tax_rate = 5
    before = snapshot(engine)
    with pytest.raises(SeedConflict, match="conflict"):
        execute(engine, apply=True)
    assert snapshot(engine) == before


def test_policy_conflict_cannot_mutate_or_replace_immutable_policy(database):
    engine = database[0]
    with Session(engine) as session, session.begin():
        session.add(
            PolicyVersion(
                version=POLICY.version, config_json={"different": True}, created_by="fixture"
            )
        )
    before = counts(engine)
    with pytest.raises(SeedConflict, match="policy version"):
        execute(engine, apply=True)
    assert counts(engine) == before


def test_injected_audit_failure_rolls_back_the_entire_seed(database):
    engine = database[0]
    before = counts(engine)

    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO purchase_order_creations"):
            raise RuntimeError("injected seed failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected seed failure"):
            execute(engine, apply=True)
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    assert counts(engine) == before


def test_two_competing_seeders_commit_one_dataset(database):
    engine = database[0]
    barrier = Barrier(2)

    def apply(_):
        barrier.wait(timeout=5)
        return execute(engine, apply=True)

    with ThreadPoolExecutor(2) as pool:
        reports = list(pool.map(apply, range(2)))
    assert sorted(r["vendors_to_create"] for r in reports) == [0, 3]
    assert sorted(len(r["purchase_orders_to_create"]) for r in reports) == [0, 4]
    assert counts(engine)["vendor_actions"] == 3 and counts(engine)["purchase_order_creations"] == 4


def test_connected_schema_and_migration_head_are_checked(database):
    engine = database[0]
    with pytest.raises(SeedConflict, match="Connected schema"):
        seed_demo(engine, "another_schema", "another_schema", DATASET, apply=True)
    with engine.begin() as connection:
        connection.execute(text("UPDATE alembic_version SET version_num='stale'"))
    with pytest.raises(SeedConflict, match="Migrate"):
        execute(engine, apply=True)
    assert counts(engine)["vendors"] == 0


@pytest.mark.parametrize(
    "sql", ["UPDATE vendor_actions SET actor_id='changed'", "DELETE FROM purchase_order_creations"]
)
def test_hosted_creation_audits_are_immutable(database, sql):
    execute(database[0], apply=True)
    with pytest.raises(DBAPIError, match="Financial history is immutable"):
        with database[0].begin() as connection:
            connection.execute(text(sql))


def test_cli_defaults_to_preview_and_uses_only_explicit_environment(database, monkeypatch, capsys):
    import json
    import sys
    from types import SimpleNamespace

    from scripts import hosted

    engine = database[0]
    with engine.connect() as connection:
        schema = connection.scalar(text("SELECT current_schema()"))
    calls = []

    def settings(**kwargs):
        calls.append(kwargs)
        return SimpleNamespace(database_schema=schema)

    monkeypatch.setattr(hosted, "Settings", settings)
    monkeypatch.setattr(hosted, "make_engine", lambda _: engine)
    monkeypatch.setattr(
        sys, "argv", ["hosted", "seed-demo", "--confirm-demo", DATASET, "--confirm-schema", schema]
    )
    hosted.main()
    assert calls == [{"_env_file": None}]
    assert json.loads(capsys.readouterr().out)["mode"] == "DRY_RUN"
    assert counts(engine)["vendors"] == 0


def test_cli_never_exposes_a_database_error_payload(database, monkeypatch, capsys):
    import sys
    from types import SimpleNamespace

    from scripts import hosted
    from scripts import seed_demo as seeder

    engine = database[0]
    monkeypatch.setattr(
        hosted, "Settings", lambda **_: SimpleNamespace(database_schema="test_schema")
    )
    monkeypatch.setattr(hosted, "make_engine", lambda _: engine)
    monkeypatch.setattr(
        sys,
        "argv",
        ["hosted", "seed-demo", "--confirm-demo", DATASET, "--confirm-schema", "test_schema"],
    )

    def fail(*args, **kwargs):
        raise RuntimeError("synthetic-secret-do-not-print")

    monkeypatch.setattr(seeder, "seed_demo", fail)
    with pytest.raises(SystemExit) as error:
        hosted.main()
    assert "synthetic-secret" not in str(error.value)
    assert capsys.readouterr().out == ""


@pytest.mark.parametrize("stage", ["settings", "engine"])
def test_cli_redacts_initialization_failures(monkeypatch, capsys, stage):
    import sys
    from types import SimpleNamespace

    from scripts import hosted

    monkeypatch.setattr(
        sys,
        "argv",
        ["hosted", "seed-demo", "--confirm-demo", DATASET, "--confirm-schema", "private_app"],
    )
    monkeypatch.setattr(hosted, "Settings", lambda **_: SimpleNamespace())

    def fail(*args, **kwargs):
        raise ValueError("synthetic-secret-do-not-print")

    monkeypatch.setattr(hosted, "Settings" if stage == "settings" else "make_engine", fail)
    with pytest.raises(SystemExit) as error:
        hosted.main()
    assert "synthetic-secret" not in str(error.value)
    assert capsys.readouterr().out == ""
