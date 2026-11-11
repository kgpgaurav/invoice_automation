"""Private workflow artifacts and closed review lifecycle; not checkpoint state."""

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db import Base


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), primary_key=True)
    policy_version: Mapped[str] = mapped_column(ForeignKey("policy_versions.version"))
    model_id: Mapped[str] = mapped_column(String(100))
    prompt_version: Mapped[str] = mapped_column(String(80))
    schema_version: Mapped[str] = mapped_column(String(80))
    route: Mapped[str] = mapped_column(String(20))
    extraction_json: Mapped[dict | None] = mapped_column(JSON)
    extraction_history: Mapped[list] = mapped_column(JSON, default=list)
    extraction_error: Mapped[str | None] = mapped_column(String(80))
    source_mode: Mapped[str] = mapped_column(String(30), default="LIVE_OPENAI")
    graph_version: Mapped[str] = mapped_column(String(80), default="invoice-graph-1")
    verifier_version: Mapped[str] = mapped_column(String(80), default="labelled-fields-3")
    extraction_attempts: Mapped[int] = mapped_column(default=0)
    review_generation: Mapped[int] = mapped_column(default=0)
    __table_args__ = (
        CheckConstraint("extraction_attempts >= 0 AND extraction_attempts <= 2"),
        CheckConstraint("review_generation >= 0"),
        CheckConstraint("source_mode IN ('LIVE_OPENAI','MOCK_OPENAI')"),
    )


class ReviewRequest(Base):
    __tablename__ = "review_requests"
    __table_args__ = (
        UniqueConstraint("run_id", "generation"),
        Index(
            "uq_review_pending",
            "run_id",
            unique=True,
            postgresql_where=text("status IN ('PREPARED','OPEN')"),
        ),
        CheckConstraint("status IN ('PREPARED','OPEN','RESOLVED')"),
        CheckConstraint("generation >= 1"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("runs.id"), index=True)
    generation: Mapped[int]
    kind: Mapped[str] = mapped_column(String(30))
    question: Mapped[str] = mapped_column(String(1000))
    options_json: Mapped[list] = mapped_column(JSON)
    status: Mapped[str] = mapped_column(String(20), default="PREPARED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class ReviewAction(Base):
    __tablename__ = "review_actions"
    __table_args__ = (
        UniqueConstraint("review_request_id", "idempotency_key"),
        CheckConstraint("action IN ('SELECT_PO','REJECT','REQUEST_INFO')"),
    )
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    review_request_id: Mapped[UUID] = mapped_column(ForeignKey("review_requests.id"), unique=True)
    actor_id: Mapped[str] = mapped_column(String(100))
    action: Mapped[str] = mapped_column(String(30))
    payload_json: Mapped[dict] = mapped_column(JSON)
    reason: Mapped[str] = mapped_column(String(500))
    idempotency_key: Mapped[str] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
