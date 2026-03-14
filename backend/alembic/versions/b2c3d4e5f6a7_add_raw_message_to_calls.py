"""add raw_message to calls

Revision ID: b2c3d4e5f6a7
Revises: a1e2f3b4c5d6
Create Date: 2026-03-14 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "b2c3d4e5f6a7"
down_revision = "a1e2f3b4c5d6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("calls", sa.Column("raw_message", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("calls", "raw_message")
