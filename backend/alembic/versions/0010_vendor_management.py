"""Audited vendor registration/status; preserve legacy identities and PO budgets."""

import sqlalchemy as sa

from alembic import op

revision = "0010_vendor_management"
down_revision = "0009_po_creation"
branch_labels = None
depends_on = None


def upgrade():
    # 0003 used an unnamed check; PostgreSQL assigned its name. Discover rather
    # than assume the name in a schema installed by an earlier migration.
    checks = sa.inspect(op.get_bind()).get_check_constraints("vendors")
    for check in checks:
        if "status" in check["sqltext"]:
            op.drop_constraint(check["name"], "vendors", type_="check")
    op.create_check_constraint(
        "ck_vendor_status", "vendors", "status IN ('ACTIVE','INACTIVE','BLACKLISTED')"
    )
    op.add_column("vendors", sa.Column("name_key", sa.String(600), nullable=True))
    op.create_unique_constraint("uq_vendor_name_key", "vendors", ["jurisdiction", "name_key"])
    op.create_table(
        "vendor_actions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("vendor_id", sa.Uuid(), nullable=False),
        sa.Column("actor_id", sa.String(100), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.ForeignKeyConstraint(["vendor_id"], ["vendors.id"]),
        sa.UniqueConstraint("actor_id", "idempotency_key", name="uq_vendor_action_actor_key"),
        sa.CheckConstraint("kind IN ('CREATE','STATUS')", name="ck_vendor_action_kind"),
    )
    op.create_index("ix_vendor_actions_vendor_id", "vendor_actions", ["vendor_id"])
    op.execute("""CREATE TRIGGER immutable_history BEFORE UPDATE OR DELETE
        ON vendor_actions FOR EACH ROW EXECUTE FUNCTION financial_immutable()""")


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM vendors WHERE status = 'BLACKLISTED')")
    ):
        raise RuntimeError(
            "Cannot downgrade while BLACKLISTED vendors exist; preserve their status."
        )
    op.drop_table("vendor_actions")
    op.drop_constraint("uq_vendor_name_key", "vendors", type_="unique")
    op.drop_column("vendors", "name_key")
    op.drop_constraint("ck_vendor_status", "vendors", type_="check")
    op.create_check_constraint("vendors_status_check", "vendors", "status IN ('ACTIVE','INACTIVE')")
