"""bulk_jobs / bulk_job_items: bulk calling runs (one call at a time) and each borrower's result

Revision ID: 0008
Revises: 0007
"""

import sqlalchemy as sa

from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "bulk_jobs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("uid", sa.Uuid(), nullable=False),
        sa.Column("agent_aid", sa.Uuid(), nullable=False),
        sa.Column("file_name", sa.String(length=200), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["uid"], ["users.uid"]),
        sa.ForeignKeyConstraint(["agent_aid"], ["agents.aid"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bulk_jobs_uid"), "bulk_jobs", ["uid"], unique=False)
    op.create_table(
        "bulk_job_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("job_id", sa.Uuid(), nullable=False),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("line", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("phone", sa.String(length=20), nullable=True),
        sa.Column("phone_last4", sa.String(length=4), nullable=False),
        sa.Column("amount", sa.String(length=20), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("deadline", sa.Date(), nullable=True),
        sa.Column("lender", sa.String(length=80), nullable=False),
        sa.Column("loan_reference", sa.String(length=40), nullable=False),
        sa.Column("notes", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False),
        sa.Column("result", sa.String(length=30), nullable=True),
        sa.Column("call_id", sa.Uuid(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["bulk_jobs.id"]),
        sa.ForeignKeyConstraint(["call_id"], ["calls.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_bulk_job_items_job_id"), "bulk_job_items", ["job_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_bulk_job_items_job_id"), table_name="bulk_job_items")
    op.drop_table("bulk_job_items")
    op.drop_index(op.f("ix_bulk_jobs_uid"), table_name="bulk_jobs")
    op.drop_table("bulk_jobs")
