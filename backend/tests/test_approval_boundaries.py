from concurrent.futures import ThreadPoolExecutor
from datetime import date
from decimal import Decimal
from threading import Event

import pytest
from sqlalchemy import event, func, select
from sqlalchemy.orm import Session

from app.approval import ApprovalConflict, approve
from app.financial_models import ApprovalLedger, POLine, PurchaseOrder, Vendor
from app.worker import Worker
from tests.financial_fixtures import POLICY, assess, changed, document, masters, run

D = Decimal


def test_exact_cap_approves_and_quantity_remaining_is_strict(database, pdf):
    engine = database[0]
    masters(engine, cap="11800", qty="10")
    assert assess(engine, pdf, document()).decision == "APPROVED"
    result = assess(engine, pdf, document(number="INV-002", qty="1"))
    assert result.code == "PO_CAP_EXCEEDED"


def test_insufficient_quantity_cannot_hide_behind_available_money(database, pdf):
    engine = database[0]
    masters(engine, qty="9")
    assert assess(engine, pdf, document()).code == "QTY_EXCEEDED"


@pytest.mark.parametrize("approved_first", [True, False])
def test_duplicate_amount_conflict_after_approved_or_held_run(database, pdf, approved_first):
    engine = database[0]
    masters(engine)
    first = document() if approved_first else document(bank_account_last4="9876")
    assess(engine, pdf, first)
    assert assess(engine, pdf, document(qty="11")).code == "DUPLICATE_CONFLICT"
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == int(approved_first)


def test_same_number_different_verified_vendor_is_not_duplicate(database, pdf):
    engine = database[0]
    masters(engine)
    assert assess(engine, pdf, document()).decision == "APPROVED"
    with Session(engine) as s, s.begin():
        vendor = Vendor(
            legal_name="Birch Supplies",
            tax_id_original="27FGHIJ1234F1Z5",
            normalized_tax_id="27FGHIJ1234F1Z5",
            bank_last4="1234",
        )
        s.add(vendor)
        s.flush()
        po = PurchaseOrder(
            po_number="B-001",
            vendor_id=vendor.id,
            issued_at=date(2026, 10, 1),
            approved_cap_gross=D("50000"),
        )
        s.add(po)
        s.flush()
        s.add(
            POLine(
                po_id=po.id,
                line_no=1,
                sku="PAPER",
                description="Office paper",
                quantity=D("100"),
                unit_price=D("1000"),
                tax_rate=D("18"),
            )
        )
    result = assess(
        engine,
        pdf,
        document(
            vendor_name="Birch Supplies", vendor_tax_id="27FGHIJ1234F1Z5", po_reference="B-001"
        ),
    )
    assert result.decision == "APPROVED"


def test_lock_wait_rereads_po_state_committed_by_another_transaction(database, pdf):
    engine = database[0]
    _, po_id, _ = masters(engine)
    run_id = run(engine, pdf)
    reached_lock = Event()

    def observing(connection, cursor, statement, parameters, context, executemany):
        if "purchase_orders" in statement and "FOR UPDATE" in statement:
            reached_lock.set()

    event.listen(engine, "before_cursor_execute", observing)
    try:
        with ThreadPoolExecutor(1) as pool:
            with Session(engine) as s, s.begin():
                po = s.scalar(
                    select(PurchaseOrder).where(PurchaseOrder.id == po_id).with_for_update()
                )
                po.status = "CLOSED"
                s.flush()
                reached_lock.clear()
                future = pool.submit(approve, engine, run_id, document(), POLICY.version)
                assert reached_lock.wait(5)
            assert future.result(timeout=10).code == "PO_CLOSED"
    finally:
        event.remove(engine, "before_cursor_execute", observing)


def test_active_worker_blocks_direct_financial_commit(database, pdf):
    engine = database[0]
    masters(engine)
    run_id = run(engine, pdf)
    owner = Worker(engine, lambda *_: None).claim()
    try:
        assert owner.run_id == run_id
        with pytest.raises(ApprovalConflict, match="active worker"):
            approve(engine, run_id, document(), POLICY.version)
    finally:
        owner.close()


def test_missing_single_po_and_legal_name_fallback_require_explicit_reference(database, pdf):
    engine = database[0]
    masters(engine)
    assert assess(engine, pdf, document(po_reference=None)).code == "PO_MISSING"
    assert assess(engine, pdf, document(vendor_tax_id=None)).decision == "APPROVED"


def test_expired_date_and_missing_tax_mode_never_approve(database, pdf):
    engine = database[0]
    _, po_id, _ = masters(engine)
    assert assess(engine, pdf, document(tax_mode="UNKNOWN")).code == "TAX_UNCLEAR"
    with Session(engine) as s, s.begin():
        s.get(PurchaseOrder, po_id).expires_at = date(2026, 10, 31)
    assert assess(engine, pdf, changed(document(), invoice_number="INV-002")).code == "PO_CLOSED"
