"""Expiring encrypted reviewer credentials and immutable per-run provider binding."""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0007_provider_sessions"
down_revision = "0006_observations"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "provider_sessions",
        sa.Column("id", postgresql.UUID(), primary_key=True),
        sa.Column("capability_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("ciphertext", sa.LargeBinary(), nullable=True),
        sa.Column("models_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("expires_at > created_at"),
        sa.CheckConstraint("expires_at <= created_at + interval '24 hours'"),
        sa.CheckConstraint("revoked_at IS NULL OR ciphertext IS NULL"),
    )
    op.create_index("ix_provider_sessions_expires_at", "provider_sessions", ["expires_at"])
    op.create_table(
        "run_provider_bindings",
        sa.Column("run_id", postgresql.UUID(), sa.ForeignKey("runs.id"), primary_key=True),
        sa.Column(
            "session_id", postgresql.UUID(), sa.ForeignKey("provider_sessions.id"), nullable=False
        ),
        sa.Column("model_id", sa.String(100), nullable=False),
    )
    op.execute("""
        CREATE FUNCTION immutable_provider_binding() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN RAISE EXCEPTION 'Provider binding is immutable'; END $$
    """)
    op.execute("""
        CREATE TRIGGER immutable_provider_binding BEFORE UPDATE OR DELETE
        ON run_provider_bindings FOR EACH ROW EXECUTE FUNCTION immutable_provider_binding()
    """)


def downgrade():
    op.drop_table("run_provider_bindings")
    op.execute("DROP FUNCTION immutable_provider_binding()")
    op.drop_index("ix_provider_sessions_expires_at", table_name="provider_sessions")
    op.drop_table("provider_sessions")
