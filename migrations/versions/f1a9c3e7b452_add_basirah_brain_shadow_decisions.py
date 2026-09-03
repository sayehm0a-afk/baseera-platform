"""add_basirah_brain_shadow_decisions

BASIRAH BRAIN STAGE 1 -- isolated, insert-only Shadow ledger for the new
AI-analyst synthesis layer (src.ai.basirah_brain). This table is never
read by any consumer-facing route and is never joined into
RadarOpportunity/ShadowLiveSignal publication; DecisionV2Snapshot and
every existing production decision path stay byte-for-byte unchanged by
this migration.

Revision ID: f1a9c3e7b452
Revises: a19f4b7d6e02
Create Date: 2026-09-03 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f1a9c3e7b452"
down_revision: Union[str, Sequence[str], None] = "a19f4b7d6e02"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "basirah_brain_shadow_decisions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column(
            "decision_v2_snapshot_id",
            sa.Integer(),
            sa.ForeignKey("decision_v2_snapshots.id"),
            nullable=True,
        ),
        sa.Column("input_schema_version", sa.String(length=16), nullable=False),
        sa.Column("output_schema_version", sa.String(length=16), nullable=True),
        sa.Column("model_provider", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=64), nullable=False),
        sa.Column("prompt_version", sa.String(length=16), nullable=False),
        sa.Column("input_hash", sa.String(length=64), nullable=False),
        sa.Column("deterministic_decision", sa.String(length=32), nullable=False),
        sa.Column("brain_decision", sa.String(length=32), nullable=True),
        sa.Column("brain_confidence_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("agreement_status", sa.String(length=24), nullable=True),
        sa.Column("reason_codes", sa.JSON(), nullable=True),
        sa.Column("raw_structured_output", sa.JSON(), nullable=True),
        sa.Column("latency_ms", sa.Numeric(10, 2), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_code", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index(
        "ix_basirah_brain_shadow_decisions_symbol", "basirah_brain_shadow_decisions", ["symbol"]
    )
    op.create_index(
        "ix_basirah_brain_shadow_decisions_stock_id", "basirah_brain_shadow_decisions", ["stock_id"]
    )
    op.create_index(
        "ix_basirah_brain_shadow_decisions_decision_v2_snapshot_id",
        "basirah_brain_shadow_decisions",
        ["decision_v2_snapshot_id"],
    )
    op.create_index(
        "ix_basirah_brain_shadow_decisions_input_hash", "basirah_brain_shadow_decisions", ["input_hash"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        "ix_basirah_brain_shadow_decisions_input_hash", table_name="basirah_brain_shadow_decisions"
    )
    op.drop_index(
        "ix_basirah_brain_shadow_decisions_decision_v2_snapshot_id",
        table_name="basirah_brain_shadow_decisions",
    )
    op.drop_index(
        "ix_basirah_brain_shadow_decisions_stock_id", table_name="basirah_brain_shadow_decisions"
    )
    op.drop_index(
        "ix_basirah_brain_shadow_decisions_symbol", table_name="basirah_brain_shadow_decisions"
    )
    op.drop_table("basirah_brain_shadow_decisions")
