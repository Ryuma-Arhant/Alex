"""calls.dial_to: the number a phone call dials (E.164), kept only until the call ends

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("dial_to", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "dial_to")
