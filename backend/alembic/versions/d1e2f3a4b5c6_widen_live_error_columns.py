"""widen live_buy_error and live_sell_error to TEXT

Revision ID: d1e2f3a4b5c6
Revises: c3d4e5f6a7b8
Create Date: 2026-03-24
"""
from alembic import op
import sqlalchemy as sa

revision = "d1e2f3a4b5c6"
down_revision = "c3d4e5f6a7b8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("calls", "live_buy_error", type_=sa.Text(), existing_type=sa.String(300), existing_nullable=True)
    op.alter_column("calls", "live_sell_error", type_=sa.Text(), existing_type=sa.String(300), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("calls", "live_buy_error", type_=sa.String(300), existing_type=sa.Text(), existing_nullable=True)
    op.alter_column("calls", "live_sell_error", type_=sa.String(300), existing_type=sa.Text(), existing_nullable=True)
