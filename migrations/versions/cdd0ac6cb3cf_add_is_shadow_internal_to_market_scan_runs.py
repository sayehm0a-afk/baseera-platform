"""add_is_shadow_internal_to_market_scan_runs

BASIRAH -- Market Engine Shadow contamination fix, concurrency closure
(Phase 14): PR #105's consumer-visibility exclusion identifies a
Shadow-internal `MarketScanRun` via a *separate* `RecurrentScanCycle`
row that `recurrent_live_scan.py` only inserts after the scan itself
has already finished (`finish_run()` committed `status=SUCCESS` well
before `_persist_cycle()` runs). Between those two commits, a
concurrently-running consumer/engine read of "the latest successful
run" cannot yet see any exclusion signal for that row -- a real,
reproducible race window, not a hypothetical one.

This column closes it structurally: `is_shadow_internal` is set in the
same INSERT that creates the `MarketScanRun` row (via
`create_scan_run(..., is_shadow_internal=True)`, called only by
`RecurrentLiveScanScheduler`), so the discriminator exists atomically
at creation time -- before the row can ever reach RUNNING or SUCCESS.
It is additive to (not a replacement of) the existing
`RecurrentScanCycle.scan_run_id` based exclusion, which stays in place
unchanged; every existing Shadow run and every existing consumer-
isolation test keeps working exactly as before. `nullable=False` with
a `server_default` of `false` so every pre-existing row (all of them
real, non-Shadow scans -- Shadow Mode did not exist before this
column) backfills safely with no manual data migration.

Revision ID: cdd0ac6cb3cf
Revises: b3f7a1c9d824
Create Date: 2026-08-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "cdd0ac6cb3cf"
down_revision: Union[str, Sequence[str], None] = "b3f7a1c9d824"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "market_scan_runs",
        sa.Column("is_shadow_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index(
        "ix_market_scan_runs_is_shadow_internal", "market_scan_runs", ["is_shadow_internal"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_market_scan_runs_is_shadow_internal", table_name="market_scan_runs")
    op.drop_column("market_scan_runs", "is_shadow_internal")
