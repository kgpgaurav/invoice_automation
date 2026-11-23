"""Retained immutable receipts for explicitly enabled demo resets."""

import sqlalchemy as sa

from alembic import op

revision = "0011_demo_reset"
down_revision = "0010_vendor_management"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "demo_reset_receipts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("dataset", sa.String(40), nullable=False),
        sa.Column("removed_counts", sa.JSON(), nullable=False),
        sa.Column("restored_counts", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_demo_reset_actor_key"),
    )
    op.execute("""CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE
        ON demo_reset_receipts FOR EACH ROW EXECUTE FUNCTION financial_immutable()""")


def downgrade():
    op.drop_table("demo_reset_receipts")
