"""add_industry_exchange_to_stocks

Phase 1 Fix #2 of the production-readiness pass: SAHMK's company
profile (GET /company/{symbol}/) is the source of a stock's real
display name and sector, but the adapter never called it, so every
Stock row kept its placeholder name forever (Known Gap #7 in
docs/SAHMK_INTEGRATION.md). Wiring that call also surfaces two more
reference-data fields the platform's recommendation output needs to
display (industry, exchange) that had no column to land in.

Revision ID: f3a9c7d21b84
Revises: 9853a4846eab
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f3a9c7d21b84"
down_revision: Union[str, Sequence[str], None] = "9853a4846eab"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stocks", sa.Column("industry", sa.String(length=128), nullable=True))
    op.add_column("stocks", sa.Column("exchange", sa.String(length=32), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stocks", "exchange")
    op.drop_column("stocks", "industry")
