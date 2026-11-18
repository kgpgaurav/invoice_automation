"""Reviewer-authorized new purchase orders; no financial approval overrides."""

from datetime import date
from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import (
    AwareDatetime,
    BaseModel,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from app.finance_contracts import Contract, Money, Price, Quantity, Rate, VendorStatus, money
from app.po_totals import supported_amounts

Reference = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=100)]
Description = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=500)]


def decimal_string(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 64:
        raise ValueError("Enter an exact decimal string")
    return value.strip()


class POCreateLine(Contract):
    sku: Reference | None = None
    description: Description
    quantity: Quantity
    unit_price: Price
    tax_rate: Rate

    @field_validator(
        "quantity", "unit_price", "tax_rate", mode="before", json_schema_input_type=str
    )
    @classmethod
    def exact_decimal(cls, value):
        return decimal_string(value)

    @field_validator("quantity", "unit_price", "tax_rate")
    @classmethod
    def canonical_decimal(cls, value, info):
        places = {"quantity": "0.000001", "unit_price": "0.0001", "tax_rate": "0.000001"}
        return value.quantize(Decimal(places[info.field_name]))


class POCreate(Contract):
    po_number: Reference
    vendor_id: UUID
    currency: Literal["INR"]
    issued_at: date
    expires_at: date | None = None
    cap_gross: Money = Field(gt=0)
    reason: Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]
    lines: tuple[POCreateLine, ...] = Field(min_length=1, max_length=50)

    @field_validator("po_number")
    @classmethod
    def printable_reference(cls, value):
        if not value.isprintable():
            raise ValueError("PO reference must contain printable characters")
        return value

    @field_validator("cap_gross", mode="before", json_schema_input_type=str)
    @classmethod
    def exact_decimal(cls, value):
        return decimal_string(value)

    @field_validator("cap_gross")
    @classmethod
    def canonical_money(cls, value):
        return money(value)

    def line_total_gross(self):
        return supported_amounts(self.lines).total_gross

    @model_validator(mode="after")
    def consistent_order(self):
        if self.expires_at is not None and self.expires_at < self.issued_at:
            raise ValueError("Expiry cannot precede the PO issue date")
        total = self.line_total_gross()
        if self.cap_gross > total:
            raise ValueError("Gross cap cannot exceed the rounded line total including tax")
        return self


class POCreated(BaseModel):
    po_id: UUID
    po_number: str
    created_at: AwareDatetime


class VendorChoice(BaseModel):
    vendor_id: UUID
    legal_name: str
    tax_id: str | None
    status: VendorStatus


class VendorChoices(BaseModel):
    items: list[VendorChoice]
    total_count: int


class POPreview(Contract):
    lines: tuple[POCreateLine, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def supported_totals(self):
        supported_amounts(self.lines)
        return self


class POLineAmounts(BaseModel):
    net: str
    tax: str
    gross: str


class POTotals(BaseModel):
    currency: Literal["INR"] = "INR"
    subtotal_net: str
    tax_total: str
    total_gross: str
    lines: list[POLineAmounts]

    @classmethod
    def from_lines(cls, lines):
        totals = supported_amounts(lines)
        return cls(
            subtotal_net=str(totals.subtotal_net),
            tax_total=str(totals.tax_total),
            total_gross=str(totals.total_gross),
            lines=[
                POLineAmounts(net=str(line.net), tax=str(line.tax), gross=str(line.gross))
                for line in totals.lines
            ],
        )
