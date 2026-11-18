"""Real PostgreSQL vendor commands, authorization, audit and financial races."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, inspect, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from alembic import command
from app.approval import approve
from app.financial_models import ApprovalLedger, PurchaseOrder, Vendor, VendorAction
from app.main import create_app
from app.po_contracts import POCreate
from app.po_service import POConflict, create_purchase_order
from app.vendor_contracts import VendorCreate, VendorStatusChange
from app.vendor_service import VendorConflict, record_vendor
from scripts.demo_fixtures import seed
from tests.conftest import TOKEN
from tests.financial_fixtures import POLICY, document, masters, run
from tests.test_po_creation import auth, configured


def body(**changes):
    return (
        dict(
            legal_name="New vendor & Co. – भारत",
            status="ACTIVE",
            tax_id=None,
            bank_last4=None,
            reason="Reviewed supplier registration for synthetic tests.",
        )
        | changes
    )


def po_body(vendor_id):
    return POCreate.model_validate(
        dict(
            po_number="PO-VENDOR-NEW",
            vendor_id=str(vendor_id),
            currency="INR",
            issued_at="2026-10-01",
            cap_gross="11800",
            reason="Reviewed new order authorization.",
            lines=[
                dict(description="Office paper", quantity="10", unit_price="1000", tax_rate="18")
            ],
        )
    )


@pytest.mark.parametrize("identity", ["anonymous", "submitter", "shared"])
def test_vendor_commands_and_preview_are_explicit_reviewer_only(database, settings, identity):
    with TestClient(
        create_app(configured(settings, shared=identity == "shared"), database[0])
    ) as client:
        headers = {} if identity == "anonymous" else auth(TOKEN)
        expected = 401 if identity == "anonymous" else 403
        assert client.post("/api/v1/vendors", json=body(), headers=headers).status_code == expected
        assert (
            client.patch(
                f"/api/v1/vendors/{uuid4()}/status",
                json={"status": "ACTIVE", "reason": "Verified status."},
                headers=headers,
            ).status_code
            == expected
        )
        assert (
            client.post(
                "/api/v1/purchase-orders/preview",
                json={"lines": po_body(uuid4()).model_dump(mode="json")["lines"]},
                headers=headers,
            ).status_code
            == expected
        )


@pytest.mark.parametrize("status", ["ACTIVE", "INACTIVE", "BLACKLISTED"])
def test_free_form_registration_preserves_sources_and_audits_replay(database, settings, status):
    engine = database[0]
    payload = body(status=status, tax_id="27 abcde1234f1z5", bank_last4="1234")
    with TestClient(create_app(configured(settings), engine)) as client:
        first = client.post("/api/v1/vendors", json=payload, headers=auth())
        assert first.status_code == 201 and first.headers["cache-control"] == "no-store"
        receipt = first.json()
        replay = client.post("/api/v1/vendors", json=payload, headers=auth())
        assert replay.status_code == 200 and replay.json() == receipt
        assert (
            client.post(
                "/api/v1/vendors", json=payload | {"reason": "Different context."}, headers=auth()
            ).status_code
            == 409
        )
        choices = client.get("/api/v1/vendors?include_unavailable=true", headers=auth()).json()
        assert choices["items"] == [
            dict(
                vendor_id=receipt["vendor_id"],
                legal_name=payload["legal_name"],
                tax_id=payload["tax_id"],
                status=status,
            )
        ]
        assert "bank" not in str(choices)
        assert client.get("/api/v1/vendors", headers=auth()).json()["total_count"] == (
            1 if status == "ACTIVE" else 0
        )
    with Session(engine) as session:
        vendor = session.get(Vendor, UUID(receipt["vendor_id"]))
        assert vendor.legal_name == payload["legal_name"]
        assert vendor.name_key == payload["legal_name"].upper()
        assert (
            vendor.tax_id_original == payload["tax_id"]
            and vendor.normalized_tax_id == "27ABCDE1234F1Z5"
        )
        action = session.get(VendorAction, UUID(receipt["action_id"]))
        assert action.snapshot_json["request"] == payload
        assert action.actor_id == "reviewer" and action.kind == "CREATE"
        assert session.scalar(select(func.count()).select_from(VendorAction)) == 1


@pytest.mark.parametrize(
    "changes",
    [
        {"legal_name": " "},
        {"legal_name": "a\nb"},
        {"legal_name": "x" * 201},
        {"status": "verified"},
        {"status": None},
        {"tax_id": "invalid"},
        {"bank_last4": "12ab"},
        {"reason": ""},
        {"verified": True},
    ],
)
def test_invalid_vendor_commands_never_create_partial_identity(database, settings, changes):
    with TestClient(create_app(configured(settings), database[0])) as client:
        assert (
            client.post("/api/v1/vendors", json=body(**changes), headers=auth()).status_code == 422
        )
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(Vendor)) == 0
        assert session.scalar(select(func.count()).select_from(VendorAction)) == 0


@pytest.mark.parametrize("legacy", [False, True])
def test_duplicate_normalized_name_and_tax_cannot_create_second_identity(database, legacy):
    engine = database[0]
    record_vendor(
        engine,
        VendorCreate.model_validate(body(legal_name="Straße Supplies", tax_id="27ABCDE1234F1Z5")),
        "first",
        "reviewer",
    )
    if legacy:
        with engine.begin() as connection:
            connection.execute(text("UPDATE vendors SET name_key=NULL"))
    with pytest.raises(VendorConflict, match="name already exists"):
        record_vendor(
            engine,
            VendorCreate.model_validate(body(legal_name="STRASSE   supplies")),
            "second",
            "reviewer",
        )
    with pytest.raises(VendorConflict, match="tax ID already exists"):
        record_vendor(
            engine,
            VendorCreate.model_validate(
                body(legal_name="Another identity", tax_id="27abcde1234f1z5")
            ),
            "third",
            "reviewer",
        )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Vendor)) == 1
        assert session.scalar(select(func.count()).select_from(VendorAction)) == 1


@pytest.mark.parametrize("same_key", [True, False])
def test_competing_registrations_produce_one_vendor_and_one_audit(database, same_key):
    barrier = Barrier(2)
    engine = database[0]

    def create(index):
        barrier.wait(timeout=5)
        try:
            return record_vendor(
                engine,
                VendorCreate.model_validate(body()),
                "same" if same_key else str(index),
                "reviewer",
            )
        except VendorConflict:
            return None

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(create, range(2)))
    if same_key:
        assert results[0][0] == results[1][0]
        assert sorted(value[1] for value in results) == [False, True]
    else:
        assert sum(value is not None for value in results) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Vendor)) == 1
        assert session.scalar(select(func.count()).select_from(VendorAction)) == 1


def test_status_command_replay_original_receipt_and_cross_operation_conflict(database, settings):
    engine = database[0]
    original, _ = record_vendor(engine, VendorCreate.model_validate(body()), "create", "reviewer")
    path = f"/api/v1/vendors/{original.vendor_id}/status"
    payload = {"status": "BLACKLISTED", "reason": "Supplier authorization withdrawn."}
    with TestClient(create_app(configured(settings), engine)) as client:
        first = client.patch(path, json=payload, headers=auth(key="status"))
        assert first.status_code == 200
        assert client.patch(path, json=payload, headers=auth(key="create")).status_code == 409
        assert (
            client.patch(
                path, json=payload | {"status": "INACTIVE"}, headers=auth(key="later")
            ).status_code
            == 200
        )
        assert client.patch(path, json=payload, headers=auth(key="status")).json() == first.json()
        assert (
            client.patch(
                f"/api/v1/vendors/{uuid4()}/status", json=payload, headers=auth(key="missing")
            ).status_code
            == 404
        )
    with Session(engine) as session:
        assert (
            session.get(Vendor, original.vendor_id).status == "INACTIVE"
        )  # replay does not change it
        changes = session.scalars(
            select(VendorAction)
            .where(VendorAction.kind == "STATUS")
            .order_by(VendorAction.created_at)
        ).all()
        assert [
            (r.snapshot_json["previous_status"], r.snapshot_json["status"]) for r in changes
        ] == [("ACTIVE", "BLACKLISTED"), ("BLACKLISTED", "INACTIVE")]


@pytest.mark.parametrize("operation", ["CREATE", "STATUS"])
def test_audit_failure_rolls_back_vendor_creation_or_status(database, operation):
    engine = database[0]
    original = None
    if operation == "STATUS":
        original, _ = record_vendor(
            engine, VendorCreate.model_validate(body()), "create", "reviewer"
        )

    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO vendor_actions"):
            raise RuntimeError("injected vendor audit failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected vendor audit failure"):
            record_vendor(
                engine,
                VendorStatusChange(status="BLACKLISTED", reason="Reviewed restriction.")
                if original
                else VendorCreate.model_validate(body()),
                "failed",
                "reviewer",
                vendor_id=original.vendor_id if original else None,
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(Vendor)) == (1 if original else 0)
        assert session.scalar(select(func.count()).select_from(VendorAction)) == (
            1 if original else 0
        )
        if original:
            assert session.get(Vendor, original.vendor_id).status == "ACTIVE"


@pytest.mark.parametrize(
    "sql", ["DELETE FROM vendor_actions", "UPDATE vendor_actions SET actor_id='changed'"]
)
def test_vendor_history_is_immutable(database, sql):
    record_vendor(database[0], VendorCreate.model_validate(body()), "audit", "reviewer")
    with pytest.raises(DBAPIError, match="Financial history is immutable"):
        with database[0].begin() as connection:
            connection.execute(text(sql))


def test_vendor_status_and_name_constraints_exist_at_database_boundary(database):
    engine = database[0]
    with pytest.raises(IntegrityError):
        with Session(engine) as session, session.begin():
            session.add(Vendor(legal_name="Invalid status", status="APPROVED"))
    with pytest.raises(IntegrityError):
        with Session(engine) as session, session.begin():
            session.add_all(
                [
                    Vendor(legal_name="One", name_key="SAME"),
                    Vendor(legal_name="Two", name_key="SAME"),
                ]
            )


def test_blacklist_blocks_forged_po_request_but_honors_prior_creation_replay(database, settings):
    engine = database[0]
    vendor, _ = record_vendor(engine, VendorCreate.model_validate(body()), "vendor", "reviewer")
    order = po_body(vendor.vendor_id)
    created, _ = create_purchase_order(engine, order, "original", "reviewer")
    record_vendor(
        engine,
        VendorStatusChange(status="BLACKLISTED", reason="Reviewed supplier restriction."),
        "blacklist",
        "reviewer",
        vendor_id=vendor.vendor_id,
    )
    with TestClient(create_app(configured(settings), engine)) as client:
        result = client.post(
            "/api/v1/purchase-orders",
            json=order.model_dump(mode="json") | {"po_number": "FORGED"},
            headers=auth(),
        )
        assert result.status_code == 409 and "blacklisted" in result.json()["detail"]["message"]
    replay, is_replay = create_purchase_order(engine, order, "original", "reviewer")
    assert is_replay and replay == created
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1


@pytest.mark.parametrize("operation", ["PO", "APPROVAL"])
def test_blacklist_committed_while_waiting_for_vendor_lock_is_rechecked(database, pdf, operation):
    engine = database[0]
    vendor_id, po_id, _ = masters(engine)
    run_id = run(engine, pdf)
    reached = Event()

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if "SELECT" in statement and "vendors" in statement and "FOR UPDATE" in statement:
            reached.set()

    with ThreadPoolExecutor(1) as pool:
        with Session(engine) as session, session.begin():
            vendor = session.scalar(select(Vendor).where(Vendor.id == vendor_id).with_for_update())
            event.listen(engine, "before_cursor_execute", observe)
            future = (
                pool.submit(create_purchase_order, engine, po_body(vendor_id), "racing", "reviewer")
                if operation == "PO"
                else pool.submit(approve, engine, run_id, document(), POLICY.version)
            )
            assert reached.wait(5)
            vendor.status = "BLACKLISTED"
        try:
            if operation == "PO":
                with pytest.raises(POConflict, match="blacklisted"):
                    future.result(timeout=10)
            else:
                result = future.result(timeout=10)
                assert result.decision == "NEEDS_REVIEW" and result.code == "VENDOR_BLACKLISTED"
        finally:
            event.remove(engine, "before_cursor_execute", observe)
    with Session(engine) as session:
        assert session.get(PurchaseOrder, po_id).committed_gross == 0
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 0
        assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 1


def test_blacklist_retains_historical_approval_and_replay_but_blocks_new_invoice(database, pdf):
    engine = database[0]
    vendor_id, po_id, _ = masters(engine)
    first = run(engine, pdf)
    assert approve(engine, first, document(), POLICY.version).decision == "APPROVED"
    record_vendor(
        engine,
        VendorStatusChange(status="BLACKLISTED", reason="Restriction after first approval."),
        "restrict",
        "reviewer",
        vendor_id=vendor_id,
    )
    assert approve(engine, first, document(), POLICY.version).decision == "APPROVED"
    second = approve(engine, run(engine, pdf), document(number="INV-002"), POLICY.version)
    assert second.code == "VENDOR_BLACKLISTED" and second.decision == "NEEDS_REVIEW"
    with Session(engine) as session:
        assert session.get(PurchaseOrder, po_id).committed_gross == 11800
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1


def test_migration_preserves_legacy_names_and_refuses_lossy_blacklist_downgrade(database):
    engine, config = database
    seed(engine)
    with Session(engine) as session:
        assert all(value is None for value in session.scalars(select(Vendor.name_key)))
        caps = list(
            session.execute(
                select(PurchaseOrder.id, PurchaseOrder.approved_cap_gross).order_by(
                    PurchaseOrder.id
                )
            )
        )
    vendor, _ = record_vendor(
        engine, VendorCreate.model_validate(body(status="BLACKLISTED")), "new", "reviewer"
    )
    with pytest.raises(RuntimeError, match="Cannot downgrade"):
        with engine.begin() as connection:
            config.attributes["connection"] = connection
            command.downgrade(config, "0009_po_creation")
    with engine.connect() as connection:
        assert "vendor_actions" in inspect(connection).get_table_names()
        assert "name_key" in {c["name"] for c in inspect(connection).get_columns("vendors")}
    with Session(engine) as session:
        assert session.get(Vendor, vendor.vendor_id).status == "BLACKLISTED"
        assert (
            list(
                session.execute(
                    select(PurchaseOrder.id, PurchaseOrder.approved_cap_gross).order_by(
                        PurchaseOrder.id
                    )
                )
            )
            == caps
        )
