"""add_ingestion_run_log_stop_reason_and_skip_counts

P0 OHLCV COVERAGE RECOVERY (2026-09-06): adds stop_reason,
symbols_skipped_budget, and symbols_skipped_fresh to
ingestion_run_logs -- these values were already computed in-memory by
IngestionResult (src.market_data.ingestion._common) but discarded
before ever reaching this table, making a background run that stopped
early on a SAHMK quota refusal (symbols_failed=0, most symbols never
attempted) indistinguishable from one that genuinely had nothing left
to do. Purely additive: no existing column, table, or read path is
touched.

Revision ID: b4d8f21a6c93
Revises: f1a9c3e7b452
Create Date: 2026-09-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b4d8f21a6c93"
down_revision: Union[str, Sequence[str], None] = "f1a9c3e7b452"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("ingestion_run_logs", sa.Column("stop_reason", sa.String(length=32), nullable=True))
    op.add_column(
        "ingestion_run_logs",
        sa.Column("symbols_skipped_budget", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ingestion_run_logs",
        sa.Column("symbols_skipped_fresh", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("ingestion_run_logs", "symbols_skipped_fresh")
    op.drop_column("ingestion_run_logs", "symbols_skipped_budget")
    op.drop_column("ingestion_run_logs", "stop_reason")
