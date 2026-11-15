"""Immutable decision-time observations for accurate read-only reporting."""

import sqlalchemy as sa

from alembic import op

revision = "0006_observations"
down_revision = "0005_workflow"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_runs_history", "runs", ["created_at", "id"])
    op.add_column("financial_assessments", sa.Column("observations_json", sa.JSON(), nullable=True))


def downgrade():
    op.drop_index("ix_runs_history", table_name="runs")
    op.drop_column("financial_assessments", "observations_json")
