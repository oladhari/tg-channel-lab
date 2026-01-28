"""add truth fields to strategy_results

Revision ID: 6950e2174c7e
Revises: 4b43ffd674ea
Create Date: 2026-01-28 00:57:11.821081

"""
from alembic import op
import sqlalchemy as sa



# revision identifiers, used by Alembic.
revision = '6950e2174c7e'
down_revision = '4b43ffd674ea'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("strategy_results", sa.Column("truth_outcome", sa.String(length=16), nullable=True))
    op.add_column("strategy_results", sa.Column("truth_exit_price_usd", sa.Float(), nullable=True))
    op.add_column("strategy_results", sa.Column("truth_exit_t_sec", sa.Integer(), nullable=True))
    op.add_column("strategy_results", sa.Column("truth_source", sa.String(length=32), nullable=True))
    op.add_column("strategy_results", sa.Column("truth_checked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("strategy_results", sa.Column("truth_error", sa.String(length=300), nullable=True))


def downgrade() -> None:
    op.drop_column("strategy_results", "truth_error")
    op.drop_column("strategy_results", "truth_checked_at")
    op.drop_column("strategy_results", "truth_source")
    op.drop_column("strategy_results", "truth_exit_t_sec")
    op.drop_column("strategy_results", "truth_exit_price_usd")
    op.drop_column("strategy_results", "truth_outcome")

