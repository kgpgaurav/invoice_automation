"""Immutable reviewer PO creation receipts; existing orders are not backfilled."""

import sqlalchemy as sa

from alembic import op

revision = "0009_po_creation"
down_revision = "0008_run_owners"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "purchase_order_creations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("po_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["po_id"], ["purchase_orders.id"]),
        sa.UniqueConstraint("po_id"),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_po_creation_actor_key"),
    )
    op.execute("""CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE
        ON purchase_order_creations FOR EACH ROW EXECUTE FUNCTION financial_immutable()""")


def downgrade():
    op.drop_table("purchase_order_creations")
