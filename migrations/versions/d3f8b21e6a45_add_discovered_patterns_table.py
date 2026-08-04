"""add_discovered_patterns_table

E5 of the AI Evolution Layer: a new `discovered_patterns` table for
signal conditions found to be statistically associated with a
significantly different win rate than the population baseline.

Revision ID: d3f8b21e6a45
Revises: c2a97e5d4b18
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d3f8b21e6a45"
down_revision: Union[str, Sequence[str], None] = "c2a97e5d4b18"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "discovered_patterns",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("condition_type", sa.String(length=32), nullable=False),
        sa.Column("condition_description", sa.String(length=255), nullable=False),
        sa.Column("evaluation_horizon_days", sa.Integer(), nullable=False),
        sa.Column("sample_size", sa.Integer(), nullable=False),
        sa.Column("win_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("baseline_win_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("z_score", sa.Numeric(9, 4), nullable=True),
        sa.Column("p_value", sa.Numeric(9, 6), nullable=True),
        sa.Column("still_valid", sa.Boolean(), nullable=False),
        sa.Column("discovered_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "condition_type", "condition_description", "evaluation_horizon_days",
            name="uq_discovered_pattern_identity",
        ),
    )
    op.create_index(
        op.f("ix_discovered_patterns_condition_type"), "discovered_patterns", ["condition_type"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_discovered_patterns_condition_type"), table_name="discovered_patterns")
    op.drop_table("discovered_patterns")
