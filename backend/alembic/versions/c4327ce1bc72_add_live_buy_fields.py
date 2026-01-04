"""add live buy fields

Revision ID: c4327ce1bc72
Revises: c8b8dca003fd
Create Date: 2026-01-04 08:36:54.732617
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "c4327ce1bc72"
down_revision = "c8b8dca003fd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add BUY fields to calls
    op.add_column("calls", sa.Column("live_buy_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.add_column("calls", sa.Column("live_buy_status", sa.String(length=32), nullable=False, server_default="NONE"))
    op.add_column("calls", sa.Column("live_buy_amount_sol", sa.Float(), nullable=True))
    op.add_column("calls", sa.Column("live_buy_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("live_buy_error", sa.String(length=300), nullable=True))

    # If you want ALL new calls to default to 0.1 SOL when live_buy_enabled=True (we’ll set in code too)
    # Keeping it nullable is fine; code can fill it. But we can also backfill null -> 0.1.
    op.execute("UPDATE calls SET live_buy_amount_sol = 0.1 WHERE live_buy_amount_sol IS NULL")


def downgrade() -> None:
    op.drop_column("calls", "live_buy_error")
    op.drop_column("calls", "live_buy_sent_at")
    op.drop_column("calls", "live_buy_amount_sol")
    op.drop_column("calls", "live_buy_status")
    op.drop_column("calls", "live_buy_enabled")
