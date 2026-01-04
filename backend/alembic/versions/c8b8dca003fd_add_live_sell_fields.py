"""add live sell fields

Revision ID: c8b8dca003fd
Revises: 8bb2fb977ae3
Create Date: 2026-01-02 06:51:36.520562
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c8b8dca003fd"
down_revision = "8bb2fb977ae3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1) Add columns with server_default so existing rows get valid values (no NULLs)
    op.add_column(
        "calls",
        sa.Column(
            "live_sell_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
    )

    op.add_column(
        "calls",
        sa.Column(
            "live_sell_status",
            sa.String(length=32),
            nullable=False,
            server_default=sa.text("'OFF'"),
        ),
    )

    op.add_column("calls", sa.Column("live_sell_reason", sa.String(length=16), nullable=True))
    op.add_column("calls", sa.Column("live_sell_sent_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("calls", sa.Column("live_sell_error", sa.String(length=300), nullable=True))

    # 2) Optional cleanup: remove server defaults after backfill
    op.alter_column("calls", "live_sell_enabled", server_default=None)
    op.alter_column("calls", "live_sell_status", server_default=None)


def downgrade() -> None:
    op.drop_column("calls", "live_sell_error")
    op.drop_column("calls", "live_sell_sent_at")
    op.drop_column("calls", "live_sell_reason")
    op.drop_column("calls", "live_sell_status")
    op.drop_column("calls", "live_sell_enabled")
