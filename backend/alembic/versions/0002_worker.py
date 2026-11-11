"""Worker claim indexes and event operation deduplication."""

import sqlalchemy as sa

from alembic import op

revision = "0002_worker"
down_revision = "0001_intake"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("run_events", sa.Column("event_key", sa.String(200)))
    op.create_unique_constraint("uq_event_operation", "run_events", ["run_id", "event_key"])
    op.create_index(
        "uq_run_active_lease",
        "run_queue",
        ["run_id"],
        unique=True,
        postgresql_where=sa.text("status = 'LEASED'"),
    )
    op.create_index("ix_queue_ready", "run_queue", ["status", "next_attempt_at"])


def downgrade():
    op.drop_index("ix_queue_ready", table_name="run_queue")
    op.drop_index("uq_run_active_lease", table_name="run_queue")
    op.drop_constraint("uq_event_operation", "run_events", type_="unique")
    op.drop_column("run_events", "event_key")
