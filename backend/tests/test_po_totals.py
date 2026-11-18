"""Exact after-tax totals shared by previews, persisted terms and cap checks."""

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.financial_models import POCreation, PurchaseOrder
from app.main import create_app
from app.po_contracts import POCreateLine, POPreview, POTotals
from scripts.demo_fixtures import seed
from tests.test_po_creation import auth, configured


def line(**changes):
    return (
        dict(description="Fractional materials", quantity="1.005", unit_price="1", tax_rate="18")
        | changes
    )


@pytest.mark.parametrize(
    "lines,net,tax,gross",
    [
        ([line()], "1.01", "0.18", "1.19"),
        ([line(quantity="1", unit_price="0.05", tax_rate="10")], "0.05", "0.01", "0.06"),
        (
            [line(quantity="0.123456", unit_price="123.4567", tax_rate="18.123456")],
            "15.24",
            "2.76",
            "18.00",
        ),
        ([line(quantity="1", unit_price="0.05", tax_rate="10")] * 2, "0.10", "0.02", "0.12"),
        (
            [line(quantity="20", unit_price="1000", tax_rate="18")],
            "20000.00",
            "3600.00",
            "23600.00",
        ),
    ],
)
def test_line_rounding_and_fractional_terms_have_exact_totals(lines, net, tax, gross):
    body = POPreview.model_validate({"lines": lines})
    result = POTotals.from_lines(body.lines)
    assert (result.subtotal_net, result.tax_total, result.total_gross) == (net, tax, gross)
    assert result.currency == "INR"


@pytest.mark.parametrize(
    "changes",
    [
        {"quantity": 1},
        {"unit_price": 1.0},
        {"tax_rate": "NaN"},
        {"quantity": "0"},
        {"quantity": "1.0000001"},
        {"unit_price": "-1"},
        {"tax_rate": "100.000001"},
        {"quantity": "999999999999.999999", "unit_price": "99999999999999.9999"},
    ],
)
def test_preview_rejects_precision_coercion_and_overflow(changes):
    with pytest.raises(ValidationError):
        POPreview.model_validate({"lines": [line(**changes)]})


def test_preview_and_saved_totals_keep_cap_separate_and_write_nothing(database, settings):
    engine = database[0]
    seed(engine)
    with TestClient(create_app(configured(settings), engine)) as client:
        preview = client.post(
            "/api/v1/purchase-orders/preview",
            json={"lines": [line(quantity="100", unit_price="1000", tax_rate="18")]},
            headers=auth(),
        )
        assert preview.status_code == 200 and preview.headers["cache-control"] == "no-store"
        assert preview.json()["total_gross"] == "118000.00"
        orders = client.get("/api/v1/purchase-orders", headers=auth()).json()["items"]
        po = next(p for p in orders if p["po_number"] == "PO-001")
        detail = client.get("/api/v1/purchase-orders/" + po["po_id"], headers=auth()).json()
        assert detail["cap_gross"] == "50000.00" and detail["available_gross"] == "50000.00"
        assert (detail["subtotal_net"], detail["tax_total"], detail["total_gross"]) == (
            "100000.00",
            "18000.00",
            "118000.00",
        )
        assert detail["lines"][0]["gross_amount"] == "118000.00"
        assert detail["vendor_status"] == "ACTIVE"
    with Session(engine) as session:
        assert session.scalar(select(func.count()).select_from(PurchaseOrder)) == 4
        assert session.scalar(select(func.count()).select_from(POCreation)) == 0


def test_preview_schema_strings_and_bounded_lines():
    schema = POCreateLine.model_json_schema()
    assert all(
        schema["properties"][f]["type"] == "string" for f in ("quantity", "unit_price", "tax_rate")
    )
    for lines in ([], [line()] * 51):
        with pytest.raises(ValidationError):
            POPreview.model_validate({"lines": lines})
