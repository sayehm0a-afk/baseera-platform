"""add_instrument_classification_to_stocks

Root-cause repair for "only a small number of stocks repeatedly appear":
production's ingestion scheduler was structurally capped at
DEFAULT_SYMBOL_UNIVERSE (5 hardcoded symbols) because
INGESTION_AUTO_DISCOVER_SYMBOLS defaulted to false and, even when
discovery ran, only the symbols job itself consulted it -- OHLCV/
fundamentals/dividends stayed capped at the static seed list forever,
so a discovered symbol could exist as a Stock row and never actually
get scanned (SymbolSelector requires PriceBar rows). This migration adds
the two columns universe_policy.classify_universe()'s per-symbol result
now persists to (via ingest_symbols._apply_entry), so exact ETF/REIT/
sukuk/rights/suspended counts are durable, SQL-queryable evidence, not
just an in-process diagnostic that resets on every deploy.

Revision ID: e7af5e2251dc
Revises: f3a9d2c81b4e
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7af5e2251dc"
down_revision: Union[str, Sequence[str], None] = "f3a9d2c81b4e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("stocks", sa.Column("instrument_bucket", sa.String(length=64), nullable=True))
    op.add_column("stocks", sa.Column("exclusion_reason", sa.String(length=255), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("stocks", "exclusion_reason")
    op.drop_column("stocks", "instrument_bucket")
