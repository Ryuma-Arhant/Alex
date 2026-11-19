"""one Loan-Recovery agent per user; the Manager and the simulated payment step are removed

- call_links.manager_mid, managers and agent_payments are dropped (the Manager and the payment step no longer exist).
  Calls that were manager calls stay in `calls` / `call_links`, owned by the same user.
- agents.lifecycle is now ACTIVE | DELETED. Never-paid PENDING agents become DELETED, and when a user had several
  ACTIVE agents only the most recently created stays ACTIVE (the rest become DELETED, so their call history is kept).
- A partial unique index enforces at most one ACTIVE agent per user.

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa

from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_index(op.f("ix_call_links_manager_mid"), table_name="call_links")
    op.drop_column("call_links", "manager_mid")  # also drops its foreign key to managers
    op.drop_table("managers")
    op.drop_index(op.f("ix_agent_payments_uid"), table_name="agent_payments")
    op.drop_index(op.f("ix_agent_payments_aid"), table_name="agent_payments")
    op.drop_table("agent_payments")

    op.execute("UPDATE agents SET lifecycle = 'DELETED' WHERE lifecycle <> 'ACTIVE'")
    op.execute(
        """
        UPDATE agents SET lifecycle = 'DELETED'
        WHERE lifecycle = 'ACTIVE' AND aid NOT IN (
            SELECT DISTINCT ON (uid) aid FROM agents WHERE lifecycle = 'ACTIVE' ORDER BY uid, created_at DESC
        )
        """
    )
    op.create_index(
        "uq_agents_one_active_per_user",
        "agents",
        ["uid"],
        unique=True,
        postgresql_where=sa.text("lifecycle = 'ACTIVE'"),
    )


def downgrade() -> None:
    op.drop_index("uq_agents_one_active_per_user", table_name="agents")
    op.create_table(
        "managers",
        sa.Column("mid", sa.Uuid(), nullable=False),
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("profile_id", sa.Uuid(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid"], ["users.uid"]),
        sa.ForeignKeyConstraint(["profile_id"], ["agent_profiles.id"]),
        sa.PrimaryKeyConstraint("mid"),
        sa.UniqueConstraint("uid"),
    )
    op.add_column("call_links", sa.Column("manager_mid", sa.Uuid(), nullable=True))
    op.create_foreign_key(None, "call_links", "managers", ["manager_mid"], ["mid"])
    op.create_index(op.f("ix_call_links_manager_mid"), "call_links", ["manager_mid"], unique=False)
    op.create_table(
        "agent_payments",
        sa.Column("aid", sa.Uuid(), nullable=False),
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["aid"], ["agents.aid"]),
        sa.ForeignKeyConstraint(["uid"], ["users.uid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_payments_aid"), "agent_payments", ["aid"], unique=False)
    op.create_index(op.f("ix_agent_payments_uid"), "agent_payments", ["uid"], unique=False)
