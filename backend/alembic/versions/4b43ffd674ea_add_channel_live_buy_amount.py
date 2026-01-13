"""add channel live buy amount

Revision ID: 4b43ffd674ea
Revises: c4327ce1bc72
Create Date: 2026-01-13 03:02:51.636028

"""
from alembic import op
import sqlalchemy as sa

revision = "4b43ffd674ea"
down_revision = "c4327ce1bc72"  # ✅ set to your latest migration
branch_labels = None
depends_on = None

def upgrade() -> None:
    op.add_column("channels", sa.Column("live_buy_amount_sol", sa.Float(), nullable=False, server_default="0.005"))
    # optional: if you want to remove server_default after existing rows are set:
    # op.alter_column("channels", "live_buy_amount_sol", server_default=None)

def downgrade() -> None:
    op.drop_column("channels", "live_buy_amount_sol")
