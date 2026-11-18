"""Persistence for deterministic financial services; no payment records."""

from datetime import date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Numeric,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Vendor(Base):
    __tablename__ = "vendors"
    __table_args__ = (
        UniqueConstraint("jurisdiction", "normalized_tax_id"),
        UniqueConstraint("jurisdiction", "name_key", name="uq_vendor_name_key"),
        CheckConstraint("status IN ('ACTIVE','INACTIVE','BLACKLISTED')", name="ck_vendor_status"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    legal_name: Mapped[str] = mapped_column(String(200))
    name_key: Mapped[str | None] = mapped_column(String(600))
    jurisdiction: Mapped[str] = mapped_column(String(2), default="IN")
    tax_id_original: Mapped[str | None] = mapped_column(String(100))
    normalized_tax_id: Mapped[str | None] = mapped_column(String(15))
    status: Mapped[str] = mapped_column(String(20), default="ACTIVE")
    bank_last4: Mapped[str | None] = mapped_column(String(4))


class VendorAction(Base):
    __tablename__ = "vendor_actions"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_vendor_action_actor_key"),
        CheckConstraint("kind IN ('CREATE','STATUS')", name="ck_vendor_action_kind"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    vendor_id: Mapped[UUID] = mapped_column(ForeignKey("vendors.id"), index=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    kind: Mapped[str] = mapped_column(String(10))
    request_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class PurchaseOrder(Base):
    __tablename__ = "purchase_orders"
    __table_args__ = (
        CheckConstraint("status IN ('OPEN','CLOSED','CANCELLED','EXPIRED')"),
        CheckConstraint("currency = 'INR'"),
        CheckConstraint("committed_gross >= 0 AND approved_cap_gross >= committed_gross"),
        CheckConstraint("expires_at IS NULL OR expires_at >= issued_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    po_number: Mapped[str] = mapped_column(String(100), unique=True)
    vendor_id: Mapped[UUID] = mapped_column(ForeignKey("vendors.id"), index=True)
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="OPEN")
    issued_at: Mapped[date] = mapped_column(Date)
    expires_at: Mapped[date | None] = mapped_column(Date)
    approved_cap_gross: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    committed_gross: Mapped[Decimal] = mapped_column(
        Numeric(18, 2), default=Decimal("0"), server_default="0"
    )
    version: Mapped[int] = mapped_column(default=1)


class POLine(Base):
    __tablename__ = "po_lines"
    __table_args__ = (
        UniqueConstraint("po_id", "line_no"),
        CheckConstraint(
            "quantity > 0 AND committed_quantity >= 0 AND committed_quantity <= quantity"
        ),
        CheckConstraint("unit_price >= 0 AND tax_rate >= 0 AND tax_rate <= 100"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    po_id: Mapped[UUID] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    line_no: Mapped[int]
    sku: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    unit_price: Mapped[Decimal] = mapped_column(Numeric(18, 4))
    tax_rate: Mapped[Decimal] = mapped_column(Numeric(9, 6))
    committed_quantity: Mapped[Decimal] = mapped_column(
        Numeric(18, 6), default=Decimal("0"), server_default="0"
    )


class PolicyVersion(Base):
    __tablename__ = "policy_versions"
    version: Mapped[str] = mapped_column(String(80), primary_key=True)
    config_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    created_by: Mapped[str] = mapped_column(String(100))


class POCreation(Base):
    __tablename__ = "purchase_order_creations"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_po_creation_actor_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    po_id: Mapped[UUID] = mapped_column(ForeignKey("purchase_orders.id"), unique=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    snapshot_json: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Invoice(Base):
    __tablename__ = "invoices"
    __table_args__ = (
        UniqueConstraint("vendor_id", "normalized_invoice_number"),
        CheckConstraint("currency = 'INR' AND gross > 0"),
        CheckConstraint("status = 'APPROVED'"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    vendor_id: Mapped[UUID] = mapped_column(ForeignKey("vendors.id"))
    invoice_number_original: Mapped[str] = mapped_column(String(200))
    normalized_invoice_number: Mapped[str] = mapped_column(String(200))
    invoice_date: Mapped[date] = mapped_column(Date)
    currency: Mapped[str] = mapped_column(String(3))
    gross: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    status: Mapped[str] = mapped_column(String(20), default="APPROVED")
    canonical_run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), unique=True)


class ApprovalLedger(Base):
    __tablename__ = "approval_ledger"
    __table_args__ = (CheckConstraint("gross > 0"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    invoice_id: Mapped[UUID] = mapped_column(ForeignKey("invoices.id"), unique=True)
    po_id: Mapped[UUID] = mapped_column(ForeignKey("purchase_orders.id"), index=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), unique=True)
    gross: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class ApprovalAllocation(Base):
    __tablename__ = "approval_allocations"
    __table_args__ = (CheckConstraint("quantity > 0"),)
    ledger_id: Mapped[UUID] = mapped_column(ForeignKey("approval_ledger.id"), primary_key=True)
    po_line_id: Mapped[UUID] = mapped_column(ForeignKey("po_lines.id"), primary_key=True)
    quantity: Mapped[Decimal] = mapped_column(Numeric(18, 6))


class FinancialAssessment(Base):
    __tablename__ = "financial_assessments"
    __table_args__ = (CheckConstraint("decision IN ('APPROVED','NEEDS_REVIEW','REJECTED')"),)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    revision: Mapped[int] = mapped_column(primary_key=True, default=0)
    vendor_id: Mapped[UUID | None] = mapped_column(ForeignKey("vendors.id"), index=True)
    normalized_invoice_number: Mapped[str | None] = mapped_column(String(200))
    policy_version: Mapped[str] = mapped_column(ForeignKey("policy_versions.version"))
    fingerprint: Mapped[str] = mapped_column(String(64))
    document_json: Mapped[dict] = mapped_column(JSON)
    decision: Mapped[str] = mapped_column(String(30))
    code: Mapped[str] = mapped_column(String(80))
    reason: Mapped[str] = mapped_column(String(1000))
    observations_json: Mapped[dict | None] = mapped_column(JSON)
