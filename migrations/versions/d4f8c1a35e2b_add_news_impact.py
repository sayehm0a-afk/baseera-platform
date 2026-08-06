"""add_news_impact

Section 11 of the Decision Intelligence Engine request: a per-decision
news-impact classification (POSITIVE/NEGATIVE/NEUTRAL/NO_RELEVANT_NEWS)
computed from the existing News Intelligence system's real, DB-only
aggregate sentiment for the symbol -- see
src/analysis/decision_v2/news_impact.py. Never fabricated:
NO_RELEVANT_NEWS is the honest default when no analyzed news exists.

Revision ID: d4f8c1a35e2b
Revises: c3e6b9f27d1a
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4f8c1a35e2b"
down_revision: Union[str, Sequence[str], None] = "c3e6b9f27d1a"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("decision_v2_snapshots", sa.Column("news_impact", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("news_impact_summary_ar", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("decision_v2_snapshots", "news_impact_summary_ar")
    op.drop_column("decision_v2_snapshots", "news_impact")
