"""Persist sanitized usage after a model call, never around a model call."""

from datetime import datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, Integer, Numeric, String, func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Mapped, Session, mapped_column

from app.db import Base


class APIUsage(Base):
    __tablename__ = "api_usage"
    __table_args__ = (CheckConstraint("latency_ms >= 0"),)
    attempt_id: Mapped[UUID] = mapped_column(primary_key=True)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), index=True)
    document_sha256: Mapped[str] = mapped_column(String(64))
    model_id: Mapped[str] = mapped_column(String(100))
    requested_model: Mapped[str] = mapped_column(String(100))
    input_tokens: Mapped[int | None] = mapped_column(Integer)
    cached_tokens: Mapped[int | None] = mapped_column(Integer)
    cache_write_tokens: Mapped[int | None] = mapped_column(Integer)
    output_tokens: Mapped[int | None] = mapped_column(Integer)
    estimated_cost_usd: Mapped[Decimal | None] = mapped_column(Numeric(20, 10))
    rate_source: Mapped[str | None] = mapped_column(String(500))
    latency_ms: Mapped[int] = mapped_column(Integer)
    prompt_version: Mapped[str] = mapped_column(String(80))
    schema_version: Mapped[str] = mapped_column(String(80))
    input_path: Mapped[str] = mapped_column(String(100))
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


def recorder(engine, run_id, document_sha256):
    def record(attempt):
        usage = attempt["usage"] if isinstance(attempt.get("usage"), dict) else {}
        details = usage.get("input_tokens_details") or {}
        if not isinstance(details, dict):
            details = {}

        def count(value):
            return value if type(value) is int and value >= 0 else None

        values = {
            key: attempt[key]
            for key in (
                "model_id",
                "requested_model",
                "latency_ms",
                "prompt_version",
                "schema_version",
                "input_path",
                "error_code",
                "rate_source",
            )
        }
        values.update(
            attempt_id=UUID(attempt["attempt_id"]),
            run_id=run_id,
            document_sha256=document_sha256,
            input_tokens=count(usage.get("input_tokens")),
            output_tokens=count(usage.get("output_tokens")),
            cached_tokens=count(details.get("cached_tokens")),
            cache_write_tokens=count(details.get("cache_write_tokens")),
            estimated_cost_usd=(
                Decimal(attempt["estimated_cost_usd"]).quantize(Decimal("0.0000000001"))
                if attempt["estimated_cost_usd"] is not None
                else None
            ),
        )
        with Session(engine) as session, session.begin():
            session.execute(
                insert(APIUsage)
                .values(**values)
                .on_conflict_do_nothing(index_elements=["attempt_id"])
            )
            existing = session.get(APIUsage, values["attempt_id"])
            if any(getattr(existing, key) != value for key, value in values.items()):
                raise ValueError("Conflicting usage attempt replay")

    return record
