from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from decimal import Decimal
from threading import Barrier

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DBAPIError, IntegrityError
from sqlalchemy.orm import Session

from app.approval import ApprovalConflict, approve, register_policy
from app.finance_contracts import FinancialPolicy
from app.financial_models import (
    ApprovalAllocation,
    ApprovalLedger,
    FinancialAssessment,
    Invoice,
    POLine,
    PurchaseOrder,
    Vendor,
)
from app.intake import create_intake
from app.models import Run, RunEvent
from tests.financial_fixtures import POLICY, assess, changed, document, masters, run

D = Decimal


def test_h1_approval_and_identical_replay(database, pdf):
    engine = database[0]
    _, po_id, line_id = masters(engine)
    run_id = run(engine, pdf)
    doc = document()
    first = approve(engine, run_id, doc, POLICY.version)
    assert first.decision == "APPROVED"
    assert approve(engine, run_id, doc, POLICY.version) == first
    with pytest.raises(ApprovalConflict):
        approve(engine, run_id, changed(doc, invoice_number="CHANGED"), POLICY.version)
    with Session(engine) as s:
        assert s.get(PurchaseOrder, po_id).committed_gross == D("11800")
        assert s.get(POLine, line_id).committed_quantity == D("10")
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1
        assert s.scalar(select(func.count()).select_from(ApprovalAllocation)) == 1
        assert s.get(Run, run_id).decision == "APPROVED"
        assert (
            s.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id))
            == 2
        )


def test_e1_prior_partial_approval_accumulates_and_holds_excess(database, pdf):
    engine = database[0]
    _, po_id, _ = masters(engine, cap="100000", rate="0")
    assert assess(engine, pdf, document(qty="70", rate="0")).decision == "APPROVED"
    result = assess(engine, pdf, document(number="INV-002", qty="35", rate="0"))
    assert result.code == "PO_CAP_EXCEEDED" and "5000.00" in result.reason
    with Session(engine) as s:
        assert s.get(PurchaseOrder, po_id).committed_gross == D("70000")
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1


def test_e2_ambiguous_po_e3_duplicate_e4_bank_mismatch(database, pdf):
    engine = database[0]
    vendor_id, _, _ = masters(engine)
    with Session(engine) as s, s.begin():
        s.add(
            PurchaseOrder(
                po_number="PO-002",
                vendor_id=vendor_id,
                issued_at=date(2026, 10, 1),
                approved_cap_gross=D("50000"),
            )
        )
    assert assess(engine, pdf, document(po_reference=None)).code == "PO_AMBIGUOUS"
    assert assess(engine, pdf, document()).decision == "APPROVED"
    assert assess(engine, pdf, document(number="INV 001")).code == "DUPLICATE_APPROVED"
    assert (
        assess(engine, pdf, document(number="INV-003", bank_account_last4="9876")).code
        == "BANK_MISMATCH"
    )


@pytest.mark.parametrize("duplicate", [False, True])
def test_concurrent_approvals_never_double_allocate_or_overspend(database, pdf, duplicate):
    engine = database[0]
    _, po_id, _ = masters(engine, cap="15000")
    ids = [run(engine, pdf), run(engine, pdf)]
    barrier = Barrier(2)

    def execute(index):
        barrier.wait(timeout=10)
        return approve(
            engine,
            ids[index],
            document(number="INV-001" if duplicate else f"INV-{index}"),
            POLICY.version,
        )

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(execute, range(2)))
    assert sum(r.decision == "APPROVED" for r in results) == 1
    assert {r.code for r in results} == {
        "VALIDATED",
        "DUPLICATE_APPROVED" if duplicate else "PO_CAP_EXCEEDED",
    }
    with Session(engine) as s:
        assert s.get(PurchaseOrder, po_id).committed_gross == D("11800")
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 1


@pytest.mark.parametrize(
    "status,code,decision",
    [
        ("CANCELLED", "PO_CLOSED", "REJECTED"),
        ("CLOSED", "PO_CLOSED", "NEEDS_REVIEW"),
        ("EXPIRED", "PO_CLOSED", "NEEDS_REVIEW"),
    ],
)
def test_stale_po_master_is_revalidated(database, pdf, status, code, decision):
    engine = database[0]
    _, po_id, _ = masters(engine)
    doc = document()  # valid data built before PO changes
    with Session(engine) as s, s.begin():
        s.get(PurchaseOrder, po_id).status = status
    result = assess(engine, pdf, doc)
    assert (result.code, result.decision) == (code, decision)


@pytest.mark.parametrize(
    "case,code",
    [
        ("inactive", "VENDOR_INACTIVE"),
        ("unknown", "VENDOR_UNKNOWN"),
        ("name", "VENDOR_ID_MISMATCH"),
        ("currency", "UNSUPPORTED_CURRENCY"),
        ("tax", "TAX_UNCLEAR"),
        ("price", "PRICE_VARIANCE"),
        ("arithmetic", "ARITHMETIC_MISMATCH"),
        ("missing", "CRITICAL_FIELD_MISSING"),
        ("future", "FUTURE_DATE"),
        ("before", "DATE_BEFORE_PO"),
    ],
)
def test_unsafe_evidence_never_approves(database, pdf, case, code):
    engine = database[0]
    vendor_id, _, _ = masters(engine)
    updates = dict(
        unknown={"vendor_tax_id": "27XXXXX1234F1Z5"},
        name={"vendor_name": "Other supplier"},
        currency={"currency": "USD"},
        arithmetic={"total_gross": "11802.00"},
        missing={"invoice_date": None},
        future={"invoice_date": str(date.today() + timedelta(days=30))},
        before={"invoice_date": "2026-01-01"},
    )
    if case == "inactive":
        with Session(engine) as s, s.begin():
            s.get(Vendor, vendor_id).status = "INACTIVE"
    doc = document(**updates.get(case, {}))
    if case in ("tax", "price"):
        lines = [line.model_dump(mode="json") for line in doc.lines]
        lines[0]["tax_amount" if case == "tax" else "unit_price"] = (
            "1800.01" if case == "tax" else "1001"
        )
        doc = changed(doc, lines=lines)
    assert assess(engine, pdf, doc).code == code
    with Session(engine) as s:
        assert s.scalar(select(func.count()).select_from(ApprovalLedger)) == 0


def test_h2_unjustified_two_rupees_routes_to_review(database, pdf):
    engine = database[0]
    masters(engine, cap="60000", rate="0")
    with Session(engine) as s, s.begin():
        s.scalar(select(POLine)).unit_price = D("49998")
    doc = document(qty="1", price="49998", rate="0", total_gross="50000")
    assert assess(engine, pdf, doc).code == "ARITHMETIC_MISMATCH"


def test_inclusive_tax_and_quantity_accumulation(database, pdf):
    engine = database[0]
    masters(engine)
    doc = document(tax_mode="INCLUSIVE")
    lines = [line.model_dump(mode="json") for line in doc.lines]
    lines[0].update(unit_price="1180", price_basis="GROSS")
    assert assess(engine, pdf, changed(doc, lines=lines)).decision == "APPROVED"


def test_transaction_failure_rolls_back_ledger_counters_events_and_decision(database, pdf):
    engine = database[0]
    _, po_id, line_id = masters(engine)
    run_id = run(engine, pdf)
    with engine.begin() as c:
        c.execute(text("ALTER TABLE financial_assessments ADD CONSTRAINT injected CHECK (false)"))
    with pytest.raises(IntegrityError):
        approve(engine, run_id, document(), POLICY.version)
    with Session(engine) as s:
        for model in (Invoice, ApprovalLedger, ApprovalAllocation, FinancialAssessment):
            assert s.scalar(select(func.count()).select_from(model)) == 0
        assert s.get(PurchaseOrder, po_id).committed_gross == 0
        assert s.get(POLine, line_id).committed_quantity == 0
        assert s.get(Run, run_id).decision is None
        assert (
            s.scalar(select(func.count()).select_from(RunEvent).where(RunEvent.run_id == run_id))
            == 1
        )
    with engine.begin() as c:
        c.execute(text("ALTER TABLE financial_assessments DROP CONSTRAINT injected"))
    assert approve(engine, run_id, document(), POLICY.version).decision == "APPROVED"


def test_immutable_policy_and_approved_history(database, pdf):
    engine = database[0]
    masters(engine)
    register_policy(engine, POLICY, "again")
    with pytest.raises(ApprovalConflict):
        register_policy(engine, FinancialPolicy(line_rounding_abs_cap_inr=D("0.01")), "changed")
    assert assess(engine, pdf, document()).decision == "APPROVED"
    for table in (
        "policy_versions",
        "approval_ledger",
        "approval_allocations",
        "invoices",
        "financial_assessments",
    ):
        with pytest.raises(DBAPIError), engine.begin() as c:
            c.execute(text(f"DELETE FROM {table}"))


def test_drift_and_production_intake_are_not_approved(database, pdf):
    engine = database[0]
    _, po_id, _ = masters(engine)
    with Session(engine) as s, s.begin():
        s.get(PurchaseOrder, po_id).committed_gross = D("1")
    assert assess(engine, pdf, document()).code == "ALLOCATION_CONFLICT"
    ordinary = create_intake(engine, pdf, None, None).run_id
    with pytest.raises(ApprovalConflict):
        approve(engine, ordinary, document(), POLICY.version)


def test_vendor_status_enum_rejects_unknown_database_values(database):
    with pytest.raises(IntegrityError), Session(database[0]) as s, s.begin():
        s.add(Vendor(legal_name="Rejected supplier", status="REJECTED"))
