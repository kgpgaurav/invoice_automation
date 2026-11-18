"""Internal verified-document contracts; these are not an extraction or HTTP API."""

import re
from datetime import date
from decimal import ROUND_HALF_UP, Decimal
from enum import StrEnum
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Money = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=2)]
Quantity = Annotated[Decimal, Field(gt=0, max_digits=18, decimal_places=6)]
Price = Annotated[Decimal, Field(ge=0, max_digits=18, decimal_places=4)]
Rate = Annotated[Decimal, Field(ge=0, le=100, max_digits=9, decimal_places=6)]


class VendorStatus(StrEnum):
    ACTIVE = "ACTIVE"
    INACTIVE = "INACTIVE"
    BLACKLISTED = "BLACKLISTED"


class POStatus(StrEnum):
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class Contract(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid", allow_inf_nan=False)

    @model_validator(mode="before")
    @classmethod
    def forbid_float(cls, value):
        def check(item):
            if isinstance(item, float):
                raise ValueError("Use Decimal or decimal strings, never float")
            if isinstance(item, dict):
                for child in item.values():
                    check(child)
            if isinstance(item, (list, tuple)):
                for child in item:
                    check(child)

        check(value)
        return value


class Evidence(Contract):
    field: str
    raw_text: str = Field(min_length=1)
    page: int = Field(ge=1, le=5)
    method: Literal["TEXT", "VISION"]
    verified: bool = False


class FinancialLine(Contract):
    line_no: int = Field(gt=0)
    sku: str | None = None
    po_line_no: int | None = Field(default=None, gt=0)
    description: str
    quantity: Quantity | None
    unit_price: Price | None
    price_basis: Literal["NET", "GROSS"]
    tax_rate: Rate | None
    net_amount: Money | None
    tax_amount: Money | None
    gross_amount: Money | None


class FinancialDocument(Contract):
    vendor_name: str | None
    vendor_tax_id: str | None
    invoice_number: str | None
    invoice_date: date | None
    po_reference: str | None
    currency: str | None
    subtotal_net: Money | None
    tax_total: Money | None
    total_gross: Money | None
    tax_mode: Literal["EXCLUSIVE", "INCLUSIVE", "UNKNOWN"]
    bank_account_last4: str | None = Field(default=None, pattern=r"^[0-9]{4}$")
    lines: tuple[FinancialLine, ...] = ()
    evidence: tuple[Evidence, ...] = ()


class FinancialPolicy(Contract):
    version: str = "policy-1.1-demo"
    allow_implicit_po_auto_match: Literal[False] = False
    allow_header_only_auto_approval: Literal[False] = False
    allow_price_variance_auto_approval: bool = False
    unit_price_variance_pct_cap: Rate = Decimal("0.50")
    unit_price_variance_abs_cap_inr: Money = Decimal("5.00")
    invoice_arithmetic_rounding_abs_cap_inr: Money = Decimal("2.00")
    invoice_arithmetic_rounding_pct_cap: Rate = Decimal("0.01")
    line_rounding_abs_cap_inr: Money = Decimal("0.05")
    po_overrun_auto_cap_inr: Annotated[Decimal, Field(ge=0, le=0)] = Decimal("0.00")
    review_reserves_po_funds: Literal[False] = False
    require_bank_match_when_invoice_bank_present: Literal[True] = True


def invoice_key(value: str) -> str:
    return re.sub(r"[ \t\r\n\f\v_/-]", "", value.upper())


def normalized_name(value: str) -> str:
    return " ".join(value.upper().split())


def tax_key(value: str | None) -> str | None:
    if value is None:
        return None
    key = re.sub(r"[ \t\r\n\f\v]", "", value.upper())
    return key if re.fullmatch(r"[A-Z0-9]{15}", key, flags=re.ASCII) else None


def money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def price_allowed(actual: Decimal, expected: Decimal, policy: FinancialPolicy) -> bool:
    difference = abs(actual - expected)
    return difference == 0 or (
        policy.allow_price_variance_auto_approval
        and expected > 0
        and difference <= policy.unit_price_variance_abs_cap_inr
        and difference * 100 <= expected * policy.unit_price_variance_pct_cap
    )


def rounding_within_caps(difference: Decimal, gross: Decimal, policy: FinancialPolicy) -> bool:
    """Necessary caps, not proof that the discrepancy is legitimate display rounding."""
    return (
        abs(difference) <= policy.invoice_arithmetic_rounding_abs_cap_inr
        and abs(difference) * 100 <= gross * policy.invoice_arithmetic_rounding_pct_cap
    )
