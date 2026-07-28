"""add_recommendation_outcomes_table

E2 of the AI Evolution Layer: a new `recommendation_outcomes` table,
one row per (RecommendationSnapshot, evaluation horizon), tracking
whether a live recommendation's target price or stop loss was reached
within a fixed number of days. Rows start PENDING (created alongside
their snapshot) and are only ever transitioned forward once real
future price data exists -- never before the horizon elapses.

Revision ID: b8f4e6c1a930
Revises: e7c1a4d92f56
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b8f4e6c1a930"
down_revision: Union[str, Sequence[str], None] = "e7c1a4d92f56"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recommendation_outcomes",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("evaluation_horizon_days", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING", "SUCCESSFUL", "FAILED", "PARTIAL", "EXPIRED", "CANCELLED",
                name="recommendationoutcomestatus",
            ),
            nullable=False,
        ),
        sa.Column("price_at_evaluation", sa.Numeric(18, 4), nullable=True),
        sa.Column("return_pct", sa.Numeric(9, 4), nullable=True),
        sa.Column("hit_target", sa.Boolean(), nullable=True),
        sa.Column("hit_stop", sa.Boolean(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["recommendation_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", "evaluation_horizon_days", name="uq_recommendation_outcome_identity"),
    )
    op.create_index(
        op.f("ix_recommendation_outcomes_snapshot_id"), "recommendation_outcomes", ["snapshot_id"], unique=False
    )
    op.create_index(
        op.f("ix_recommendation_outcomes_symbol"), "recommendation_outcomes", ["symbol"], unique=False
    )
    op.create_index(
        op.f("ix_recommendation_outcomes_due_at"), "recommendation_outcomes", ["due_at"], unique=False
    )
    op.create_index(
        op.f("ix_recommendation_outcomes_status"), "recommendation_outcomes", ["status"], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_recommendation_outcomes_status"), table_name="recommendation_outcomes")
    op.drop_index(op.f("ix_recommendation_outcomes_due_at"), table_name="recommendation_outcomes")
    op.drop_index(op.f("ix_recommendation_outcomes_symbol"), table_name="recommendation_outcomes")
    op.drop_index(op.f("ix_recommendation_outcomes_snapshot_id"), table_name="recommendation_outcomes")
    op.drop_table("recommendation_outcomes")
    sa.Enum(name="recommendationoutcomestatus").drop(op.get_bind(), checkfirst=True)
