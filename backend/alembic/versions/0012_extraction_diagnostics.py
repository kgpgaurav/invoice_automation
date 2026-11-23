"""Private extraction/verification diagnostics; existing frozen artifacts are unchanged."""

import sqlalchemy as sa

from alembic import op

revision = "0012_extraction_diagnostics"
down_revision = "0011_demo_reset"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "workflow_runs",
        sa.Column(
            "diagnostic_history",
            sa.JSON(),
            nullable=False,
            server_default="[]",
        ),
    )


def downgrade():
    op.drop_column("workflow_runs", "diagnostic_history")
