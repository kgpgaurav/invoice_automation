"""Reviewer-authored vendor identity/status commands; no extracted assertions."""

from typing import Annotated
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, StringConstraints, field_validator

from app.finance_contracts import Contract, VendorStatus, tax_key

Rationale = Annotated[str, StringConstraints(strip_whitespace=True, min_length=5, max_length=500)]


class VendorCreate(Contract):
    legal_name: Annotated[
        str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)
    ]
    status: VendorStatus
    tax_id: Annotated[str, StringConstraints(max_length=100)] | None = None
    bank_last4: Annotated[str, StringConstraints(pattern=r"^[0-9]{4}$")] | None = None
    reason: Rationale

    @field_validator("legal_name")
    @classmethod
    def printable_name(cls, value):
        if not value.isprintable():
            raise ValueError("Vendor name must contain printable characters")
        return value

    @field_validator("tax_id", "bank_last4", mode="before")
    @classmethod
    def optional_text(cls, value):
        return (value.strip() or None) if isinstance(value, str) else value

    @field_validator("tax_id")
    @classmethod
    def valid_tax_id(cls, value):
        if value is not None and tax_key(value) is None:
            raise ValueError("Enter a 15-character Indian tax ID, or leave it blank")
        return value


class VendorStatusChange(Contract):
    status: VendorStatus
    reason: Rationale


class VendorRecorded(BaseModel):
    vendor_id: UUID
    action_id: UUID
    recorded_at: AwareDatetime
