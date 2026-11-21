"""next_action_done: next actions (from call summaries) the user ticked off on the Dashboard

Revision ID: 0006
Revises: 0005
"""

import sqlalchemy as sa

from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "next_action_done",
        sa.Column("call_id", sa.Uuid(), nullable=False),
        sa.Column("idx", sa.Integer(), nullable=False),
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.ForeignKeyConstraint(["uid"], ["users.uid"]),
        sa.PrimaryKeyConstraint("call_id", "idx"),
    )
    op.create_index(op.f("ix_next_action_done_uid"), "next_action_done", ["uid"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_next_action_done_uid"), table_name="next_action_done")
    op.drop_table("next_action_done")
