"""Check published manual-entry data through real rules/review using explicit mock transport."""

import json
from decimal import Decimal
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.financial_models import ApprovalLedger, PurchaseOrder
from app.models import Run
from app.review_contracts import ReviewResponse
from app.reviews import respond
from app.workflow_models import ReviewRequest
from scripts.demo_fixtures import master_records, pdf, seed
from tests.workflow_helpers import execute, intake, mock_processor


def test_manual_invoice_packet_matches_seeded_pos_and_real_financial_outcomes(workflow_db):
    plan = json.loads(
        (Path(__file__).resolve().parents[2] / "docs/fixtures/manual-invoices-v1.json").read_text()
    )
    assert plan["kind"] == "SYNTHETIC_MANUAL_INVOICE_PLAN"
    expected_orders = {
        (name, tax, number, Decimal(cap), Decimal(rate))
        for name, tax, orders in master_records()
        for number, cap, rate in orders
    }
    assert {
        (
            row["vendor_name"],
            row["vendor_tax_id"],
            row["po_number"],
            Decimal(row["cap_gross"]),
            Decimal(row["line"]["tax_rate"]),
        )
        for row in plan["purchase_orders"]
    } == expected_orders
    seed(workflow_db)
    completed = set()
    for case in plan["cases"]:
        assert set(case["depends_on"]) <= completed
        data = case["invoice"]
        line = data["line_items"][0]
        assert Decimal(data["subtotal_net"]) == Decimal(line["quantity"]) * Decimal(
            line["unit_price"]
        )
        assert (
            Decimal(data["tax_total"])
            == Decimal(data["subtotal_net"]) * Decimal(line["tax_rate"]) / 100
        )
        assert Decimal(data["total_gross"]) == Decimal(data["subtotal_net"]) + Decimal(
            data["tax_total"]
        )
        content = pdf(data)
        ident = intake(workflow_db, content)
        processor, calls = mock_processor(workflow_db, content, data)
        execute(workflow_db, processor)
        with Session(workflow_db) as session:
            run = session.get(Run, ident)
            assert run.decision == case["expected_initial"]["decision"], case["id"]
            from app.financial_models import FinancialAssessment

            assessment = session.get(FinancialAssessment, (ident, 0))
            assert assessment.code == case["expected_initial"]["code"], case["id"]
            if case.get("review"):
                thread_id = run.thread_id
                request = session.scalar(select(ReviewRequest).where(ReviewRequest.run_id == ident))
                po_id = session.scalar(
                    select(PurchaseOrder.id).where(
                        PurchaseOrder.po_number == case["review"]["select_po"]
                    )
                )
                request_id, generation = request.id, request.generation
        if case.get("review"):
            respond(
                workflow_db,
                request_id,
                ReviewResponse(
                    generation=generation,
                    action="SELECT_PO",
                    payload={"po_id": str(po_id)},
                    reason=case["review"]["reason"],
                ),
                "manual-review-" + case["id"],
                "configured-reviewer",
            )
            execute(workflow_db, processor)
            with Session(workflow_db) as session:
                run = session.get(Run, ident)
                assert run.decision == "APPROVED" and run.thread_id == thread_id
        assert len(calls) == 1, case["id"]
        completed.add(case["id"])
    with Session(workflow_db) as session:
        assert session.scalar(select(func.count()).select_from(ApprovalLedger)) == 3
        assert session.scalar(select(func.sum(ApprovalLedger.gross))) == Decimal("93600.00")
        assert {
            po.po_number: po.approved_cap_gross - po.committed_gross
            for po in session.scalars(select(PurchaseOrder))
        } == {
            "PO-001": Decimal("38200.00"),
            "PO-PARTIAL": Decimal("30000.00"),
            "PO-SELECT-001": Decimal("13200.00"),
            "PO-SELECT-002": Decimal("40000.00"),
        }
