from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    LargeBinary,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (CheckConstraint("octet_length(content) <= 12582912"),)
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    content: Mapped[bytes] = mapped_column(LargeBinary)
    sha256: Mapped[str] = mapped_column(String(64))


class Run(Base):
    __tablename__ = "runs"
    __table_args__ = (
        CheckConstraint(
            "job_state IN ('QUEUED','RUNNING','WAITING_REVIEW','COMPLETED','FAILED','INTERRUPTED')"
        ),
        CheckConstraint("decision IS NULL OR decision IN ('APPROVED','NEEDS_REVIEW','REJECTED')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    document_id: Mapped[UUID] = mapped_column(ForeignKey("documents.id"))
    document_uri: Mapped[str] = mapped_column(String(100))
    document_sha256: Mapped[str] = mapped_column(String(64))
    source: Mapped[str | None] = mapped_column(String(200))
    job_state: Mapped[str] = mapped_column(String(30), default="QUEUED")
    decision: Mapped[str | None] = mapped_column(String(30))
    reason: Mapped[str | None] = mapped_column(String)
    thread_id: Mapped[UUID] = mapped_column(unique=True, default=uuid4)
    policy_version: Mapped[str] = mapped_column(String(80), default="not-configured")
    prompt_version: Mapped[str] = mapped_column(String(80), default="not-configured")
    model_id: Mapped[str] = mapped_column(String(100), default="not-configured")
    replay_mode: Mapped[bool] = mapped_column(default=False)
    error_code: Mapped[str | None] = mapped_column(String(80))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class RunEvent(Base):
    __tablename__ = "run_events"
    __table_args__ = (UniqueConstraint("run_id", "event_key"),)
    event_key: Mapped[str | None] = mapped_column(String(200))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    seq: Mapped[int] = mapped_column(primary_key=True)
    stage: Mapped[str] = mapped_column(String(40))
    type: Mapped[str] = mapped_column(String(40))
    payload_json: Mapped[dict] = mapped_column(JSON)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class QueueItem(Base):
    __tablename__ = "run_queue"
    __table_args__ = (
        UniqueConstraint("run_id", "work_type", "generation"),
        Index(
            "uq_run_active_lease", "run_id", unique=True, postgresql_where=text("status = 'LEASED'")
        ),
        Index("ix_queue_ready", "status", "next_attempt_at"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"))
    work_type: Mapped[str] = mapped_column(String(30), default="PROCESS")
    generation: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(30), default="READY")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    lease_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    claimed_by: Mapped[str | None] = mapped_column(String(100))
    next_attempt_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class IntakeKey(Base):
    __tablename__ = "intake_keys"
    key: Mapped[str] = mapped_column(String(200), primary_key=True)
    fingerprint: Mapped[str] = mapped_column(String(64))
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), unique=True)
