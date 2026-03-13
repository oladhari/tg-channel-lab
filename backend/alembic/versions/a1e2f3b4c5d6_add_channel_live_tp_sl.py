"""add channel live tp sl

Revision ID: a1e2f3b4c5d6
Revises: 4b43ffd674ea
Create Date: 2026-03-13 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "a1e2f3b4c5d6"
down_revision = "4b43ffd674ea"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # nullable=True so existing rows are NULL (means "use global default")
    op.add_column("channels", sa.Column("live_tp_pct", sa.Float(), nullable=True, server_default=None))
    op.add_column("channels", sa.Column("live_sl_pct", sa.Float(), nullable=True, server_default=None))


def downgrade() -> None:
    op.drop_column("channels", "live_tp_pct")
    op.drop_column("channels", "live_sl_pct")
