"""Durable intake only; financial and checkpoint tables come in later slices."""

import sqlalchemy as sa

from alembic import op

revision = "0001_intake"
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "documents",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=False),
        sa.CheckConstraint("octet_length(content) <= 12582912"),
    )
    op.create_table(
        "runs",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("document_id", sa.Uuid(), sa.ForeignKey("documents.id"), nullable=False),
        sa.Column("document_uri", sa.String(100), nullable=False),
        sa.Column("document_sha256", sa.String(64), nullable=False),
        sa.Column("source", sa.String(200)),
        sa.Column("job_state", sa.String(30), nullable=False),
        sa.Column("decision", sa.String(30)),
        sa.Column("reason", sa.String()),
        sa.Column("thread_id", sa.Uuid(), nullable=False, unique=True),
        sa.Column("policy_version", sa.String(80), nullable=False),
        sa.Column("prompt_version", sa.String(80), nullable=False),
        sa.Column("model_id", sa.String(100), nullable=False),
        sa.Column("replay_mode", sa.Boolean(), nullable=False),
        sa.Column("error_code", sa.String(80)),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.CheckConstraint(
            "job_state IN ('QUEUED','RUNNING','WAITING_REVIEW','COMPLETED','FAILED','INTERRUPTED')"
        ),
        sa.CheckConstraint(
            "decision IS NULL OR decision IN ('APPROVED','NEEDS_REVIEW','REJECTED')"
        ),
    )
    op.create_table(
        "run_events",
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("runs.id"), primary_key=True),
        sa.Column("seq", sa.Integer(), primary_key=True),
        sa.Column("stage", sa.String(40), nullable=False),
        sa.Column("type", sa.String(40), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column(
            "occurred_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "run_queue",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("runs.id"), nullable=False),
        sa.Column("work_type", sa.String(30), nullable=False),
        sa.Column("generation", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("lease_until", sa.DateTime(timezone=True)),
        sa.Column("claimed_by", sa.String(100)),
        sa.Column(
            "next_attempt_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint("run_id", "work_type", "generation"),
    )
    op.create_table(
        "intake_keys",
        sa.Column("key", sa.String(200), primary_key=True),
        sa.Column("fingerprint", sa.String(64), nullable=False),
        sa.Column("run_id", sa.Uuid(), sa.ForeignKey("runs.id"), nullable=False, unique=True),
    )


def downgrade():
    for name in ("intake_keys", "run_queue", "run_events", "runs", "documents"):
        op.drop_table(name)
