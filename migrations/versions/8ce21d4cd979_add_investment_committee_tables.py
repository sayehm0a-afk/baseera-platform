"""add_investment_committee_tables

AI Multi-Agent Investment Committee milestone: `committee_opinions`
(one row per agent per live Decision Engine V2 decision) and
`committee_sessions` (one consensus row per decision), both FK'd to
`decision_v2_snapshots.id` -- see src/domain/models/committee_opinion.py
and committee_session.py for the full rationale.

Revision ID: 8ce21d4cd979
Revises: d4f8c1a35e2b
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "8ce21d4cd979"
down_revision: Union[str, Sequence[str], None] = "d4f8c1a35e2b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # Reuses the `agentstance` Postgres ENUM type the a1c5f8e3b207
    # migration already created for `agent_opinions.stance` --
    # create_type=False so this migration never tries to (re)create or
    # drop a type another table still depends on. Must be the
    # dialect-specific postgresql.ENUM: the generic sa.Enum silently
    # ignores a `create_type` kwarg (it isn't a recognized argument on
    # the dialect-agnostic type) and would default to creating it.
    agent_stance = postgresql.ENUM(
        "BULLISH", "BEARISH", "NEUTRAL", "UNAVAILABLE", name="agentstance", create_type=False
    )

    op.create_table(
        "committee_opinions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_v2_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column("agent_role", sa.String(length=32), nullable=False),
        sa.Column("stance", agent_stance, nullable=False),
        sa.Column("confidence", sa.Numeric(6, 2), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=True),
        sa.Column("rejection_reasons", sa.JSON(), nullable=True),
        sa.Column("used_llm", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["decision_v2_snapshot_id"], ["decision_v2_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_committee_opinions_decision_v2_snapshot_id"),
        "committee_opinions", ["decision_v2_snapshot_id"], unique=False,
    )
    op.create_index(op.f("ix_committee_opinions_agent_name"), "committee_opinions", ["agent_name"], unique=False)
    op.create_index(op.f("ix_committee_opinions_agent_role"), "committee_opinions", ["agent_role"], unique=False)

    op.create_table(
        "committee_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("decision_v2_snapshot_id", sa.Integer(), nullable=False),
        sa.Column("final_decision", sa.String(length=16), nullable=False),
        sa.Column("final_confidence", sa.Numeric(6, 2), nullable=False),
        sa.Column("participant_count", sa.Integer(), nullable=False),
        sa.Column("directional_count", sa.Integer(), nullable=False),
        sa.Column("agreement_pct", sa.Numeric(6, 2), nullable=False),
        sa.Column("disagreement_pct", sa.Numeric(6, 2), nullable=False),
        sa.Column("disagreement_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("most_optimistic_agent", sa.String(length=64), nullable=True),
        sa.Column("most_optimistic_stance", sa.String(length=16), nullable=True),
        sa.Column("most_conservative_agent", sa.String(length=64), nullable=True),
        sa.Column("most_conservative_stance", sa.String(length=16), nullable=True),
        sa.Column("consensus_reasoning_ar", sa.Text(), nullable=False),
        sa.Column("rejected_alternatives", sa.JSON(), nullable=True),
        sa.Column("weighted_votes", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["decision_v2_snapshot_id"], ["decision_v2_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("decision_v2_snapshot_id", name="uq_committee_session_snapshot"),
    )
    op.create_index(
        op.f("ix_committee_sessions_decision_v2_snapshot_id"),
        "committee_sessions", ["decision_v2_snapshot_id"], unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_committee_sessions_decision_v2_snapshot_id"), table_name="committee_sessions")
    op.drop_table("committee_sessions")
    op.drop_index(op.f("ix_committee_opinions_agent_role"), table_name="committee_opinions")
    op.drop_index(op.f("ix_committee_opinions_agent_name"), table_name="committee_opinions")
    op.drop_index(op.f("ix_committee_opinions_decision_v2_snapshot_id"), table_name="committee_opinions")
    op.drop_table("committee_opinions")
    # `agentstance` ENUM type is intentionally not dropped here -- it is
    # still owned by `agent_opinions.stance` (a1c5f8e3b207), unaffected
    # by this migration.
