"""Temporary provider credentials. These records are never public run/checkpoint data."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import JSON, CheckConstraint, DateTime, ForeignKey, LargeBinary, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class ProviderSession(Base):
    __tablename__ = "provider_sessions"
    __table_args__ = (
        CheckConstraint("expires_at > created_at"),
        CheckConstraint("expires_at <= created_at + interval '24 hours'"),
        CheckConstraint("revoked_at IS NULL OR ciphertext IS NULL"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner_id: Mapped[str | None] = mapped_column(String(64))
    capability_hash: Mapped[str] = mapped_column(String(64), unique=True)
    ciphertext: Mapped[bytes | None] = mapped_column(LargeBinary)
    models_json: Mapped[list] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class RunProviderBinding(Base):
    __tablename__ = "run_provider_bindings"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    session_id: Mapped[UUID] = mapped_column(ForeignKey("provider_sessions.id"))
    model_id: Mapped[str] = mapped_column(String(100))
