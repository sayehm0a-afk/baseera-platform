"""add_agent_opinions_and_debate_sessions_tables

E7 of the AI Evolution Layer: agent_opinions (one row per panel
member per live recommendation) and debate_sessions (one row only
when material disagreement between agents triggered a debate).

Revision ID: a1c5f8e3b207
Revises: f6c1e9a4d720
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1c5f8e3b207"
down_revision: Union[str, Sequence[str], None] = "f6c1e9a4d720"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "agent_opinions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("agent_name", sa.String(length=64), nullable=False),
        sa.Column(
            "stance",
            sa.Enum("BULLISH", "BEARISH", "NEUTRAL", "UNAVAILABLE", name="agentstance"),
            nullable=False,
        ),
        sa.Column("confidence", sa.Numeric(6, 2), nullable=True),
        sa.Column("reasoning", sa.Text(), nullable=False),
        sa.Column("used_llm", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["recommendation_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_opinions_snapshot_id"), "agent_opinions", ["snapshot_id"], unique=False)
    op.create_index(op.f("ix_agent_opinions_agent_name"), "agent_opinions", ["agent_name"], unique=False)

    op.create_table(
        "debate_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("snapshot_id", sa.Integer(), nullable=False),
        sa.Column("participants", sa.JSON(), nullable=False),
        sa.Column("rounds", sa.Integer(), nullable=False),
        sa.Column("agreement_level", sa.Numeric(6, 4), nullable=True),
        sa.Column("final_decision", sa.String(length=16), nullable=True),
        sa.Column("judge_explanation", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["recommendation_snapshots.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("snapshot_id", name="uq_debate_session_snapshot"),
    )
    op.create_index(op.f("ix_debate_sessions_snapshot_id"), "debate_sessions", ["snapshot_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_debate_sessions_snapshot_id"), table_name="debate_sessions")
    op.drop_table("debate_sessions")
    op.drop_index(op.f("ix_agent_opinions_agent_name"), table_name="agent_opinions")
    op.drop_index(op.f("ix_agent_opinions_snapshot_id"), table_name="agent_opinions")
    op.drop_table("agent_opinions")
    sa.Enum(name="agentstance").drop(op.get_bind(), checkfirst=True)
