"""add_fundamental_summary

Section 12 of the Decision Intelligence Engine request: a real,
structured fundamental summary (revenue/profit growth, margins, ROE,
debt-to-equity, valuation multiples, dividend yield) computed from the
same M2.3 FundamentalAnalysisResult ratios fundamental_contributor.py
already scores with -- see src/analysis/decision_v2/fundamental_summary.py.
Never fabricated: values are None when the underlying ratio could not
be computed from real reported financials.

Revision ID: c3e6b9f27d1a
Revises: b2d5a8f14c6e
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c3e6b9f27d1a"
down_revision: Union[str, Sequence[str], None] = "b2d5a8f14c6e"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("decision_v2_snapshots", sa.Column("fundamental_summary", sa.JSON(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("fundamental_summary_ar", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("decision_v2_snapshots", "fundamental_summary_ar")
    op.drop_column("decision_v2_snapshots", "fundamental_summary")
