"""add stage1_evaluated_count to market_scan_runs

Revision ID: d3f7a2c891e4
Revises: c1a4e8f9b263
Create Date: 2026-08-19 00:00:00.000000

BASIRAH Radar Upgrade mandate Phase 2: the "Saudi Market Universe"
funnel must report real, dynamic numbers at every stage (total
available -> analyzable now -> passed initial filter -> passed
advanced analysis -> final opportunities), never a static count.
Stage 1 (`stage1_local_scan.run_stage1_local_scan`) already computes
`evaluated_count` (universe symbols that actually had enough price
history to be scored -- the "analyzable now" stage) but, like
`universe_size`/`candidate_count` before the prior migration, it only
ever existed in-memory and was discarded. This persists it alongside
the other two so the consumer-facing funnel can report it honestly.
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d3f7a2c891e4"
down_revision = "c1a4e8f9b263"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("market_scan_runs", sa.Column("stage1_evaluated_count", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("market_scan_runs", "stage1_evaluated_count")
