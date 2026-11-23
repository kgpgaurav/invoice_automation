"""Conditional reviewer pass/recheck; retain immutable existing review audit."""

import sqlalchemy as sa

from alembic import op

revision = "0013_review_pass"
down_revision = "0012_extraction_diagnostics"
branch_labels = None
depends_on = None


def upgrade():
    constraints = [
        item
        for item in sa.inspect(op.get_bind()).get_check_constraints("review_actions")
        if "SELECT_PO" in item["sqltext"] and "REQUEST_INFO" in item["sqltext"]
    ]
    if len(constraints) != 1 or not constraints[0]["name"]:
        raise RuntimeError("Expected the existing closed review action constraint")
    op.drop_constraint(constraints[0]["name"], "review_actions", type_="check")
    op.create_check_constraint(
        "ck_review_actions_action",
        "review_actions",
        "action IN ('SELECT_PO','PASS','REJECT','REQUEST_INFO')",
    )


def downgrade():
    if op.get_bind().scalar(
        sa.text("SELECT EXISTS (SELECT 1 FROM review_actions WHERE action='PASS')")
    ):
        raise RuntimeError("Cannot downgrade while immutable PASS review audit exists")
    op.drop_constraint("ck_review_actions_action", "review_actions", type_="check")
    op.create_check_constraint(
        "review_actions_action_check",
        "review_actions",
        "action IN ('SELECT_PO','REJECT','REQUEST_INFO')",
    )
