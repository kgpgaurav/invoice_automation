"""Reviewer PO creation with real isolated PostgreSQL and explicitly mocked extraction."""

from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from threading import Event
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, func, select, text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.orm import Session

from app.config import Settings
from app.financial_models import ApprovalLedger, POCreation, POLine, PurchaseOrder, Vendor
from app.main import create_app
from app.po_contracts import POCreate
from app.po_service import POConflict, create_purchase_order
from scripts.demo_fixtures import seed
from tests.conftest import TOKEN
from tests.extraction_helpers import case
from tests.workflow_helpers import execute, invoice_pdf, mock_processor

REVIEWER = "synthetic-po-creation-reviewer-at-least-24"


def test_creation_schema_requires_decimal_strings():
    schema = POCreate.model_json_schema()
    assert schema["properties"]["cap_gross"]["type"] == "string"
    for field in ("quantity", "unit_price", "tax_rate"):
        assert schema["$defs"]["POCreateLine"]["properties"][field]["type"] == "string"


def configured(settings, *, shared=False):
    return Settings(
        _env_file=None,
        database_url=settings.database_url,
        app_api_token=TOKEN,
        reviewer_api_token=REVIEWER,
        access_mode="shared" if shared else "roles",
    )


def auth(token=REVIEWER, key="create-order"):
    return {"Authorization": "Bearer " + token, "X-Idempotency-Key": key}


@pytest.fixture
def order_body(database):
    seed(database[0])
    with Session(database[0]) as session:
        vendor = session.scalar(select(Vendor).where(Vendor.legal_name == "Aster Office Supplies"))
        return dict(
            po_number="PO-CREATED",
            vendor_id=str(vendor.id),
            currency="INR",
            issued_at="2026-10-01",
            expires_at=None,
            cap_gross="23600.00",
            reason="Authorized synthetic office-paper purchase for creation regression.",
            lines=[
                dict(
                    sku="PAPER",
                    description="Office paper",
                    quantity="20",
                    unit_price="1000",
                    tax_rate="18",
                )
            ],
        )


@pytest.mark.parametrize("identity", ["anonymous", "submitter", "shared"])
def test_only_explicit_reviewer_can_create_or_list_vendors(
    database, settings, order_body, identity
):
    with TestClient(
        create_app(configured(settings, shared=identity == "shared"), database[0])
    ) as client:
        headers = {} if identity == "anonymous" else auth(TOKEN)
        expected = 401 if identity == "anonymous" else 403
        assert client.get("/api/v1/vendors", headers=headers).status_code == expected
        assert (
            client.post("/api/v1/purchase-orders", json=order_body, headers=headers).status_code
            == expected
        )


def test_atomic_creation_receipt_terms_replay_and_unchanged_other_orders(
    database, settings, order_body
):
    engine = database[0]
    with TestClient(create_app(configured(settings), engine)) as client:
        result = client.post("/api/v1/purchase-orders", json=order_body, headers=auth())
        assert result.status_code == 201 and result.headers["cache-control"] == "no-store"
        receipt = result.json()
        detail = client.get("/api/v1/purchase-orders/" + receipt["po_id"], headers=auth()).json()
        assert detail["status"] == "OPEN" and detail["available_gross"] == "23600.00"
        assert detail["committed_gross"] == "0.00" and detail["allocations"] == []
        assert detail["lines"][0]["quantity"] == "20.000000"
        assert detail["lines"][0]["unit_price"] == "1000.0000"
        assert detail["creation"]["actor_id"] == "reviewer"
        assert detail["creation"]["reason"] == order_body["reason"]
        with Session(engine) as session, session.begin():
            session.get(Vendor, UUID(order_body["vendor_id"])).status = "INACTIVE"
        equivalent = deepcopy(order_body)
        equivalent["lines"][0]["quantity"] = "20.000000"
        replay = client.post("/api/v1/purchase-orders", json=equivalent, headers=auth())
        assert replay.status_code == 200 and replay.json() == receipt
        changed = order_body | {"reason": "Different authorization context must not replay."}
        assert (
            client.post("/api/v1/purchase-orders", json=changed, headers=auth()).status_code == 409
        )
        assert (
            client.post(
                "/api/v1/purchase-orders", json=order_body, headers=auth(key="another-key")
            ).status_code
            == 409
        )
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(POCreation)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(POLine)
                .where(POLine.po_id == UUID(receipt["po_id"]))
            )
            == 1
        )
        original = session.scalar(select(PurchaseOrder).where(PurchaseOrder.po_number == "PO-001"))
        assert str(original.approved_cap_gross) == "50000.00" and original.committed_gross == 0


@pytest.mark.parametrize("kind", ["missing", "inactive"])
def test_vendor_is_required_and_active_at_creation(database, settings, order_body, kind):
    if kind == "missing":
        order_body["vendor_id"] = str(uuid4())
    else:
        with Session(database[0]) as session, session.begin():
            session.get(Vendor, UUID(order_body["vendor_id"])).status = "INACTIVE"
    with TestClient(create_app(configured(settings), database[0])) as client:
        result = client.post("/api/v1/purchase-orders", json=order_body, headers=auth())
        assert result.status_code == (404 if kind == "missing" else 409)


@pytest.mark.parametrize(
    "change",
    [
        {"cap_gross": 23600.0},
        {"cap_gross": "23600.001"},
        {"cap_gross": "0"},
        {"cap_gross": "24000"},
        {"currency": "USD"},
        {"status": "OPEN"},
        {"committed_gross": "0"},
        {"reason": "   "},
        {"expires_at": "2026-09-30"},
        {"lines": []},
        {"po_number": "bad\nreference"},
    ],
)
def test_invalid_order_contract_never_writes(database, settings, order_body, change):
    with TestClient(create_app(configured(settings), database[0])) as client:
        result = client.post("/api/v1/purchase-orders", json=order_body | change, headers=auth())
        assert result.status_code == 422
    with Session(database[0]) as session:
        assert session.scalar(select(func.count()).select_from(POCreation)) == 0


@pytest.mark.parametrize(
    "change",
    [
        {"quantity": "0"},
        {"quantity": "1.0000001"},
        {"quantity": 20.0},
        {"unit_price": "1000.00001"},
        {"unit_price": "NaN"},
        {"tax_rate": "101"},
        {"tax_rate": "18.0000001"},
        {"tax_rate": 18},
        {"quantity": "999999999999", "unit_price": "99999999999999"},
    ],
)
def test_invalid_line_precision_tax_and_overflow(order_body, change):
    order_body["lines"][0].update(change)
    with pytest.raises(ValueError):
        POCreate.model_validate(order_body)


@pytest.mark.parametrize("same_key", [True, False])
def test_competing_creations_never_duplicate_order_or_audit(database, order_body, same_key):
    engine, _ = database
    body = POCreate.model_validate(order_body)

    def create(index):
        try:
            return create_purchase_order(
                engine, body, "concurrent" if same_key else str(index), "reviewer"
            )
        except POConflict:
            return None

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(create, (0, 1)))
    if same_key:
        assert len({result[0].po_id for result in results}) == 1
        assert sorted(result[1] for result in results) == [False, True]
    else:
        assert sum(result is not None for result in results) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(POCreation)) == 1
        assert (
            session.scalar(
                select(func.count())
                .select_from(PurchaseOrder)
                .where(PurchaseOrder.po_number == body.po_number)
            )
            == 1
        )


def test_creation_rollback_after_injected_audit_write_failure(database, order_body):
    engine = database[0]

    def fail(_connection, _cursor, statement, _parameters, _context, _many):
        if statement.startswith("INSERT INTO purchase_order_creations"):
            raise RuntimeError("injected audit failure")

    event.listen(engine, "before_cursor_execute", fail)
    try:
        with pytest.raises(RuntimeError, match="injected audit failure"):
            create_purchase_order(
                engine, POCreate.model_validate(order_body), "rollback", "reviewer"
            )
    finally:
        event.remove(engine, "before_cursor_execute", fail)
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(POCreation)) == 0
        assert (
            session.scalar(
                select(func.count())
                .select_from(PurchaseOrder)
                .where(PurchaseOrder.po_number == "PO-CREATED")
            )
            == 0
        )
        assert session.scalar(select(func.count()).select_from(POLine)) == 4  # unchanged seed


@pytest.mark.parametrize(
    "operation",
    [
        "UPDATE purchase_order_creations SET actor_id='changed'",
        "DELETE FROM purchase_order_creations",
    ],
)
def test_creation_audit_is_immutable(database, order_body, operation):
    create_purchase_order(database[0], POCreate.model_validate(order_body), "audit", "reviewer")
    with pytest.raises(DBAPIError, match="Financial history is immutable"):
        with database[0].begin() as connection:
            connection.execute(text(operation))


def test_vendor_state_is_rechecked_after_waiting_for_its_lock(database, order_body):
    engine = database[0]
    reached = Event()

    def observe(_connection, _cursor, statement, _parameters, _context, _many):
        if "SELECT" in statement and "vendors" in statement and "FOR UPDATE" in statement:
            reached.set()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with Session(engine) as session, session.begin():
            vendor = session.scalar(
                select(Vendor).where(Vendor.id == UUID(order_body["vendor_id"])).with_for_update()
            )
            event.listen(engine, "before_cursor_execute", observe)
            future = pool.submit(
                create_purchase_order,
                engine,
                POCreate.model_validate(order_body),
                "stale-vendor",
                "reviewer",
            )
            assert reached.wait(3)
            vendor.status = "INACTIVE"
        try:
            with pytest.raises(POConflict, match="no longer active"):
                future.result(timeout=5)
        finally:
            event.remove(engine, "before_cursor_execute", observe)


def test_active_vendor_search_is_bounded_literal_and_omits_bank_data(
    database, settings, order_body
):
    with Session(database[0]) as session, session.begin():
        session.add(
            Vendor(
                legal_name="Literal_% vendor", jurisdiction="IN", status="ACTIVE", bank_last4="9876"
            )
        )
    with TestClient(create_app(configured(settings), database[0])) as client:
        result = client.get("/api/v1/vendors?q=%25&limit=1", headers=auth())
        assert result.status_code == 200
        assert result.json()["total_count"] == 1
        assert result.json()["items"][0]["legal_name"] == "Literal_% vendor"
        assert "bank" not in result.text and "9876" not in result.text
        assert client.get("/api/v1/vendors?limit=51", headers=auth()).status_code == 422


def test_new_po_accepts_a_real_pdf_through_worker_and_allocation(workflow_db, settings):
    engine = workflow_db
    seed(engine)
    with Session(engine) as session:
        vendor = session.scalar(select(Vendor).where(Vendor.legal_name == "Aster Office Supplies"))
        vendor_id = vendor.id
    body = dict(
        po_number="PO-CREATED",
        vendor_id=str(vendor_id),
        currency="INR",
        issued_at="2026-10-01",
        cap_gross="23600",
        reason="Authorized synthetic purchase for end-to-end matching.",
        lines=[
            dict(
                sku="PAPER",
                description="Office paper",
                quantity="20",
                unit_price="1000",
                tax_rate="18",
            )
        ],
    )
    with TestClient(create_app(configured(settings), engine)) as client:
        created = client.post("/api/v1/purchase-orders", json=body, headers=auth())
        assert created.status_code == 201
        po_id = created.json()["po_id"]
        _, expected = case()
        expected.update(invoice_number="CREATED-001", po_reference="PO-CREATED")
        pdf = invoice_pdf(expected)
        run = client.post(
            "/api/v1/invoices/process",
            headers=auth(TOKEN, "new-po-invoice"),
            files={"file": ("synthetic.pdf", pdf, "application/pdf")},
        )
        assert run.status_code == 202
        processor, calls = mock_processor(engine, pdf, expected)
        execute(engine, processor)
        detail = client.get("/api/v1/runs/" + run.json()["run_id"], headers=auth(TOKEN)).json()
        assert detail["decision"] == "APPROVED" and detail["source_mode"] == "MOCK_OPENAI"
        ledger = client.get("/api/v1/purchase-orders/" + po_id, headers=auth()).json()
        assert ledger["available_gross"] == "11800.00"
        assert ledger["lines"][0]["committed_quantity"] == "10.000000"
        assert ledger["allocation_count"] == 1 and len(calls) == 1
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
