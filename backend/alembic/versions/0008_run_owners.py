"""Immutable run/provider ownership. No legacy ownership is guessed or backfilled."""

import sqlalchemy as sa

from alembic import op

revision = "0008_run_owners"
down_revision = "0007_provider_sessions"
branch_labels = None
depends_on = None


def upgrade():
    for table in ("runs", "provider_sessions"):
        op.add_column(table, sa.Column("owner_id", sa.String(64), nullable=True))
    op.create_index("ix_runs_owner_history", "runs", ["owner_id", "created_at", "id"])
    op.execute("""
        CREATE FUNCTION immutable_resource_owner() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF OLD.owner_id IS DISTINCT FROM NEW.owner_id THEN
            RAISE EXCEPTION 'Resource owner is immutable';
          END IF;
          RETURN NEW;
        END $$
    """)
    for table in ("runs", "provider_sessions"):
        op.execute(f"""CREATE TRIGGER immutable_resource_owner BEFORE UPDATE OF owner_id
            ON {table} FOR EACH ROW EXECUTE FUNCTION immutable_resource_owner()""")
    op.execute("""
        CREATE FUNCTION provider_binding_owner() RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          IF (SELECT owner_id FROM runs WHERE id=NEW.run_id) IS DISTINCT FROM
             (SELECT owner_id FROM provider_sessions WHERE id=NEW.session_id) THEN
            RAISE EXCEPTION 'Provider session owner mismatch';
          END IF;
          RETURN NEW;
        END $$
    """)
    op.execute("""CREATE TRIGGER provider_binding_owner BEFORE INSERT ON run_provider_bindings
        FOR EACH ROW EXECUTE FUNCTION provider_binding_owner()""")


def downgrade():
    op.execute("DROP TRIGGER provider_binding_owner ON run_provider_bindings")
    op.execute("DROP FUNCTION provider_binding_owner()")
    for table in ("runs", "provider_sessions"):
        op.execute(f"DROP TRIGGER immutable_resource_owner ON {table}")
    op.execute("DROP FUNCTION immutable_resource_owner()")
    op.drop_index("ix_runs_owner_history", table_name="runs")
    for table in ("runs", "provider_sessions"):
        op.drop_column(table, "owner_id")
