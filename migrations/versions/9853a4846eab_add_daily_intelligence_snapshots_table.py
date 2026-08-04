"""add_daily_intelligence_snapshots_table

E9 of the AI Evolution Layer: daily_intelligence_snapshots, one
pre-aggregated row per day so the staff-only Intelligence Dashboard
reads pre-computed rows instead of live-computing on every page load.

Revision ID: 9853a4846eab
Revises: a1c5f8e3b207
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "9853a4846eab"
down_revision: Union[str, Sequence[str], None] = "a1c5f8e3b207"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "daily_intelligence_snapshots",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("recommendations_evaluated", sa.Integer(), nullable=False),
        sa.Column("successful_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("expired_count", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("calibration_error", sa.Numeric(9, 6), nullable=True),
        sa.Column("agent_panel_snapshot_count", sa.Integer(), nullable=False),
        sa.Column("agent_debate_count", sa.Integer(), nullable=False),
        sa.Column("agent_agreement_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("best_patterns", sa.JSON(), nullable=True),
        sa.Column("worst_patterns", sa.JSON(), nullable=True),
        sa.Column("sector_breakdown", sa.JSON(), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_date", name="uq_daily_intelligence_snapshot_date"),
    )
    op.create_index(
        op.f("ix_daily_intelligence_snapshots_snapshot_date"), "daily_intelligence_snapshots", ["snapshot_date"],
        unique=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_daily_intelligence_snapshots_snapshot_date"), table_name="daily_intelligence_snapshots")
    op.drop_table("daily_intelligence_snapshots")
