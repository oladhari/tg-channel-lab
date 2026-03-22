"""add high-frequency recording: t_ms/source to price_points, price_cross_events table

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-03-22 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b2c3d4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ── price_points: drop per-second unique constraint, add ms timestamp + source ──
    op.drop_constraint("uq_price_points_call_tsec", "price_points", type_="unique")
    op.add_column("price_points", sa.Column("t_ms", sa.BigInteger(), nullable=True))
    op.add_column("price_points", sa.Column("source", sa.String(20), nullable=True))
    op.create_index("ix_price_points_t_ms", "price_points", ["t_ms"])

    # ── price_cross_events: one row per first threshold crossing per call ──────────
    op.create_table(
        "price_cross_events",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "call_id",
            sa.Integer(),
            sa.ForeignKey("calls.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("t_ms", sa.BigInteger(), nullable=False),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("price_usd", sa.Float(), nullable=False),
        sa.Column("event_type", sa.String(20), nullable=False),   # TP_CROSS | SL_CROSS
        sa.Column("level_pct", sa.Float(), nullable=False),
        sa.Column("source", sa.String(20), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("price_cross_events")
    op.drop_index("ix_price_points_t_ms", table_name="price_points")
    op.drop_column("price_points", "source")
    op.drop_column("price_points", "t_ms")
    op.create_unique_constraint(
        "uq_price_points_call_tsec", "price_points", ["call_id", "t_sec"]
    )
