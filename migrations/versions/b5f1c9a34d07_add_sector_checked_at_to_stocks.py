"""add sector_checked_at to stocks

Revision ID: b5f1c9a34d07
Revises: a7e51c9f4d02
Create Date: 2026-08-10 05:25:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "b5f1c9a34d07"
down_revision = "a7e51c9f4d02"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("stocks", sa.Column("sector_checked_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("stocks", "sector_checked_at")
