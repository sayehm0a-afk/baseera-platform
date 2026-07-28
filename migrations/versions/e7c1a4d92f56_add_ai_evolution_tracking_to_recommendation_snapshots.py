"""add_ai_evolution_tracking_to_recommendation_snapshots

Adds the columns the AI Evolution Layer's live recommendation tracking
needs on the existing `recommendation_snapshots` table: `source`
(distinguishes a live scan write from a backtest write without relying
on `run_id is None` as an implicit proxy), `variant` (champion/
challenger tagging for paper-trading comparisons), `is_paper_trade`,
`news_summary`, `market_regime`, and `agent_debate_summary`. All six
are nullable -- every row written before this migration, and every
ordinary backtest row going forward, legitimately has none of them.

Revision ID: e7c1a4d92f56
Revises: c4d8e6f19a2b
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e7c1a4d92f56"
down_revision: Union[str, Sequence[str], None] = "c4d8e6f19a2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "recommendation_snapshots",
        sa.Column("source", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "recommendation_snapshots",
        sa.Column("variant", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "recommendation_snapshots",
        sa.Column("is_paper_trade", sa.Boolean(), nullable=True),
    )
    op.add_column(
        "recommendation_snapshots",
        sa.Column("news_summary", sa.String(length=2000), nullable=True),
    )
    op.add_column(
        "recommendation_snapshots",
        sa.Column("market_regime", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "recommendation_snapshots",
        sa.Column("agent_debate_summary", sa.JSON(), nullable=True),
    )
    op.create_index(
        op.f("ix_recommendation_snapshots_source"),
        "recommendation_snapshots",
        ["source"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_recommendation_snapshots_source"), table_name="recommendation_snapshots")
    op.drop_column("recommendation_snapshots", "agent_debate_summary")
    op.drop_column("recommendation_snapshots", "market_regime")
    op.drop_column("recommendation_snapshots", "news_summary")
    op.drop_column("recommendation_snapshots", "is_paper_trade")
    op.drop_column("recommendation_snapshots", "variant")
    op.drop_column("recommendation_snapshots", "source")
