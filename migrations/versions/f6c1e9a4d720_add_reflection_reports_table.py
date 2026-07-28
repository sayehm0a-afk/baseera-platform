"""add_reflection_reports_table

E6 of the AI Evolution Layer: a new `reflection_reports` table, one
row per day, summarizing that day's evaluated `RecommendationOutcome`
rows.

Revision ID: f6c1e9a4d720
Revises: d3f8b21e6a45
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f6c1e9a4d720"
down_revision: Union[str, Sequence[str], None] = "d3f8b21e6a45"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "reflection_reports",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("review_date", sa.Date(), nullable=False),
        sa.Column("recommendations_reviewed", sa.Integer(), nullable=False),
        sa.Column("successful_count", sa.Integer(), nullable=False),
        sa.Column("failed_count", sa.Integer(), nullable=False),
        sa.Column("partial_count", sa.Integer(), nullable=False),
        sa.Column("expired_count", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Numeric(6, 4), nullable=True),
        sa.Column("key_findings", sa.JSON(), nullable=False),
        sa.Column("improvement_suggestions", sa.JSON(), nullable=False),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("review_date"),
    )
    op.create_index(
        op.f("ix_reflection_reports_review_date"), "reflection_reports", ["review_date"], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_reflection_reports_review_date"), table_name="reflection_reports")
    op.drop_table("reflection_reports")
