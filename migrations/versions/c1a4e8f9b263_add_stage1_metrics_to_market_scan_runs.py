"""add stage1_universe_size and stage1_candidate_count to market_scan_runs

Revision ID: c1a4e8f9b263
Revises: 5126413133b2
Create Date: 2026-08-19 00:00:00.000000

Radar V2's Stage 1 (`src.market_intelligence.stage1_local_scan`) already
computes, for every cycle, how many symbols made up the full local
universe it scanned for free and how many of those it ranked as real
candidates -- but until this migration, those two numbers only ever
existed in-memory (`RadarV2RunResult.stage1_universe_size`/
`stage1_candidate_count`), logged as text and then discarded. Consumers
had no honest way to see "how many stocks did the radar actually look
at" -- only the capped, paid-live-validation count
(`RADAR_STAGE2_CANDIDATE_CAP`, default 15) ever reached the API. This
persists both numbers onto the `MarketScanRun` row a Radar V2 cycle
already writes, so a later read-only route can report the real funnel
without spending any new SAHMK quota.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "c1a4e8f9b263"
down_revision = "5126413133b2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_scan_runs", sa.Column("stage1_universe_size", sa.Integer(), nullable=True))
    op.add_column("market_scan_runs", sa.Column("stage1_candidate_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("market_scan_runs", "stage1_candidate_count")
    op.drop_column("market_scan_runs", "stage1_universe_size")
