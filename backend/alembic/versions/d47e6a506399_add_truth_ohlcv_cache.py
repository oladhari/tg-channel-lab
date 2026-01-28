"""add truth ohlcv cache

Revision ID: d47e6a506399
Revises: 6950e2174c7e
Create Date: 2026-01-28 04:12:51.135097

"""
from alembic import op
import sqlalchemy as sa

from sqlalchemy.dialects import postgresql



# revision identifiers, used by Alembic.
revision = 'd47e6a506399'
down_revision = '6950e2174c7e'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "truth_ohlcv_cache",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("call_id", sa.Integer(), sa.ForeignKey("calls.id", ondelete="CASCADE"), nullable=False),

        sa.Column("network", sa.String(length=32), nullable=False, server_default="solana"),
        sa.Column("dex_id", sa.String(length=64), nullable=True),
        sa.Column("pool_address", sa.String(length=128), nullable=False),

        sa.Column("timeframe", sa.String(length=16), nullable=False),
        sa.Column("aggregate", sa.Integer(), nullable=False, server_default="1"),

        sa.Column("entry_unix", sa.BigInteger(), nullable=False),
        sa.Column("max_hold_sec", sa.Integer(), nullable=False),

        sa.Column("start_ts", sa.BigInteger(), nullable=True),
        sa.Column("end_ts", sa.BigInteger(), nullable=True),
        sa.Column("points", sa.Integer(), nullable=False, server_default="0"),

        sa.Column("source", sa.String(length=64), nullable=False, server_default="coingecko_onchain"),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=True),

        sa.Column("data_gz", postgresql.BYTEA(), nullable=True),
        sa.Column("error", sa.String(length=280), nullable=True),
    )

    op.create_unique_constraint(
        "uq_truth_cache_key",
        "truth_ohlcv_cache",
        ["call_id", "pool_address", "timeframe", "aggregate"],
    )

    op.create_index("ix_truth_cache_call_id", "truth_ohlcv_cache", ["call_id"])
    op.create_index("ix_truth_cache_pool", "truth_ohlcv_cache", ["pool_address"])
    op.create_index("ix_truth_cache_fetched_at", "truth_ohlcv_cache", ["fetched_at"])


def downgrade() -> None:
    op.drop_index("ix_truth_cache_fetched_at", table_name="truth_ohlcv_cache")
    op.drop_index("ix_truth_cache_pool", table_name="truth_ohlcv_cache")
    op.drop_index("ix_truth_cache_call_id", table_name="truth_ohlcv_cache")
    op.drop_constraint("uq_truth_cache_key", "truth_ohlcv_cache", type_="unique")
    op.drop_table("truth_ohlcv_cache")
