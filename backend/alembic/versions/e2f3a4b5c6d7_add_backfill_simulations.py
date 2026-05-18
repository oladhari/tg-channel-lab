"""add backfill_simulations table

Revision ID: e2f3a4b5c6d7
Revises: d1e2f3a4b5c6
Create Date: 2026-03-25
"""
from alembic import op
import sqlalchemy as sa

revision = "e2f3a4b5c6d7"
down_revision = "d1e2f3a4b5c6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "backfill_simulations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("channel_id", sa.Integer(), nullable=False, index=True),
        sa.Column("channel_username", sa.String(120), nullable=False),
        sa.Column("mint", sa.String(64), nullable=False, index=True),
        sa.Column("detected_at", sa.DateTime(timezone=True), nullable=False, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("entry_price_usd", sa.Float(), nullable=True),
        sa.Column("entry_delay_sec", sa.Integer(), nullable=True),
        sa.Column("exit_price_usd", sa.Float(), nullable=True),
        sa.Column("exit_t_sec", sa.Integer(), nullable=True),
        sa.Column("tp_pct", sa.Float(), nullable=False, server_default="35.0"),
        sa.Column("sl_pct", sa.Float(), nullable=False, server_default="20.0"),
        sa.Column("result", sa.String(16), nullable=False, server_default="NO_DATA"),
        sa.Column("pnl_pct", sa.Float(), nullable=True),
        sa.Column("max_profit_pct", sa.Float(), nullable=True),
        sa.Column("max_drawdown_pct", sa.Float(), nullable=True),
        sa.Column("raw_message", sa.Text(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.UniqueConstraint("channel_id", "mint", "detected_at", name="uq_backfill_channel_mint_detected"),
    )


def downgrade() -> None:
    op.drop_table("backfill_simulations")
