"""add_skipped_symbols_summary

Full-market-scan production automation follow-up: a "skipped" scan
outcome (SymbolScanOutcome.skipped_reason set, e.g.
"insufficient_data"/"stock_not_registered") was only ever tracked as an
aggregate count (MarketScanRun.symbols_skipped) -- the exact symbol/
reason pair existed in memory for the duration of one scan and was then
discarded on a successful run, since only the FAILED path ever wrote to
error_summary. Root-caused in production: a real 393-symbol scan
(run 98) skipped 2 symbols with no way to identify which ones or why
after the fact. This adds a dedicated column (distinct from
error_summary, since a skip is not an error) populated by
MarketIntelligenceEngine.execute_scan whenever symbols_skipped > 0.

Revision ID: d4f8c2a19e6b
Revises: 3c76770a2b30
Create Date: 2026-08-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4f8c2a19e6b"
down_revision: Union[str, Sequence[str], None] = "3c76770a2b30"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("market_scan_runs", sa.Column("skipped_symbols_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("market_scan_runs", "skipped_symbols_summary")
