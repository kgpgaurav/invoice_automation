from decimal import Decimal
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.finance_contracts import (
    FinancialPolicy,
    invoice_key,
    price_allowed,
    rounding_within_caps,
    tax_key,
)
from app.finance_rules import critical_check, evaluate, match_lines, resolve_vendor
from tests.financial_fixtures import POLICY, changed, document

D = Decimal


def test_invoice_normalization_preserves_original_identity():
    assert invoice_key("inv-001") == invoice_key("INV 001") == "INV001"
    assert invoice_key("INV_001/02") == "INV00102"
    assert invoice_key("INV-001") != invoice_key("INV-01")
    assert tax_key("27 abcde1234f1z5") == "27ABCDE1234F1Z5"
    assert tax_key("27ABCDE1234F1Z!") is None


@pytest.mark.parametrize("value", [1.1, "NaN", "Infinity", "-1", "1.001"])
def test_invalid_money_is_never_coerced(value):
    with pytest.raises(ValidationError):
        document(total_gross=value)


@pytest.mark.parametrize(
    "gross,difference,expected",
    [
        ("50000", "2", True),
        ("50000", "2.01", False),
        ("10000", "1", True),
        ("10000", "1.01", False),
        ("10000", "2", False),
    ],
)
def test_rounding_both_caps_are_necessary_not_evidence(gross, difference, expected):
    assert rounding_within_caps(D(difference), D(gross), POLICY) is expected


@pytest.mark.parametrize(
    "expected,actual,allowed",
    [
        ("1000", "1005", True),
        ("1000", "1005.01", False),
        ("100", "100.50", True),
        ("100", "100.51", False),
        ("0", "0.01", False),
    ],
)
def test_unit_price_variance_requires_both_caps_and_opt_in(expected, actual, allowed):
    assert not price_allowed(D(actual), D(expected), POLICY)
    enabled = FinancialPolicy(version="price-test", allow_price_variance_auto_approval=True)
    assert price_allowed(D(actual), D(expected), enabled) is allowed


def test_verified_evidence_required_for_every_critical_line_value():
    doc = document()
    assert critical_check(doc) is None
    data = doc.model_dump(mode="json")
    data["evidence"] = [e for e in data["evidence"] if e["field"] != "lines.1.tax_rate"]
    assert critical_check(type(doc).model_validate(data)).decision == "NEEDS_REVIEW"


def test_identity_and_lines_do_not_fuzzily_auto_match():
    vendor = SimpleNamespace(
        id=1,
        legal_name="Aster Office Supplies",
        jurisdiction="IN",
        normalized_tax_id="27ABCDE1234F1Z5",
    )
    assert resolve_vendor(document(vendor_tax_id=None, po_reference=None), [vendor], [])[0] is None
    line = SimpleNamespace(id=1, line_no=1, sku="OTHER", description="Office paper")
    assert match_lines(document(), [line])[2].code == "LINE_AMBIGUOUS"


def test_multiple_lines_aggregate_quantity_before_rule_check():
    doc = document()
    first = doc.lines[0].model_dump(mode="json")
    second = dict(first, line_no=2)
    doc = changed(
        doc, lines=[first, second], subtotal_net="20000", tax_total="3600", total_gross="23600"
    )
    line = SimpleNamespace(
        id=1,
        line_no=1,
        sku="PAPER",
        description="Office paper",
        unit_price=D("1000"),
        tax_rate=D("18"),
        quantity=D("15"),
        committed_quantity=D("0"),
    )
    vendor = SimpleNamespace(status="ACTIVE", bank_last4="1234")
    po = SimpleNamespace(
        currency="INR",
        status="OPEN",
        expires_at=None,
        issued_at=doc.invoice_date,
        approved_cap_gross=D("50000"),
        committed_gross=D("0"),
    )
    result, allocations = evaluate(doc, vendor, po, [line], POLICY, doc.invoice_date)
    assert result.code == "QTY_EXCEEDED" and not allocations
