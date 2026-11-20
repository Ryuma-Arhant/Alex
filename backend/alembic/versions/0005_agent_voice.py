"""agents.voice: the voice the user chose for their agent (male | female)

Existing agents become "male", the voice every call used until now.

Revision ID: 0005
Revises: 0004
"""

import sqlalchemy as sa

from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agents", sa.Column("voice", sa.String(length=10), nullable=False, server_default="male"))


def downgrade() -> None:
    op.drop_column("agents", "voice")
