"""Reset receipts survive the explicitly destructive demo operation."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, DateTime, String, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class DemoResetReceipt(Base):
    __tablename__ = "demo_reset_receipts"
    __table_args__ = (
        UniqueConstraint("actor_id", "idempotency_key", name="uq_demo_reset_actor_key"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    actor_id: Mapped[str] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(128))
    request_hash: Mapped[str] = mapped_column(String(64))
    dataset: Mapped[str] = mapped_column(String(40))
    removed_counts: Mapped[dict] = mapped_column(JSON)
    restored_counts: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
