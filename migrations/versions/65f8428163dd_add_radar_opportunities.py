"""add_radar_opportunities

Basirah Radar V2 (2026-08-16), Phase B forward-testing foundation:
`radar_opportunities`, the durable record of every candidate Radar V2's
orchestrator actually emitted -- one row per `decision_v2_snapshots`
row it was built from (unique FK), plus Stage 1's local-only ranking
evidence for that candidate (score, per-component breakdown, which
signals fired, its rank within that run's narrowed set) that Decision
V2's own schema has no concept of. Entry zone/targets/stop/reasoning/
gates/later real-market outcome are all reached via
`decision_v2_snapshot_id`, not duplicated here -- see
src/domain/models/radar_opportunity.py's module docstring for the full
design rationale.

Revision ID: 65f8428163dd
Revises: 879941a7def9
Create Date: 2026-08-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "65f8428163dd"
down_revision: Union[str, Sequence[str], None] = "879941a7def9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "radar_opportunities",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column(
            "decision_v2_snapshot_id", sa.Integer(), sa.ForeignKey("decision_v2_snapshots.id"), nullable=False
        ),
        sa.Column("scan_run_id", sa.Integer(), nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("classification_label_ar", sa.String(length=64), nullable=False),
        sa.Column("confidence_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("price_at_signal", sa.Numeric(18, 4), nullable=True),
        sa.Column("stage1_rank", sa.Integer(), nullable=True),
        sa.Column("stage1_ranking_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("stage1_component_scores", sa.JSON(), nullable=True),
        sa.Column("stage1_signals", sa.JSON(), nullable=True),
        sa.Column("stage1_risk_reward_ratio", sa.Numeric(9, 4), nullable=True),
        sa.Column("ranking_reason_ar", sa.Text(), nullable=True),
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by_id", sa.Integer(), sa.ForeignKey("radar_opportunities.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("decision_v2_snapshot_id", name="uq_radar_opportunity_snapshot"),
    )
    op.create_index("ix_radar_opportunities_symbol", "radar_opportunities", ["symbol"])
    op.create_index("ix_radar_opportunities_stock_id", "radar_opportunities", ["stock_id"])
    op.create_index("ix_radar_opportunities_scan_run_id", "radar_opportunities", ["scan_run_id"])
    op.create_index("ix_radar_opportunities_classification", "radar_opportunities", ["classification"])
    op.create_index("ix_radar_opportunities_emitted_at", "radar_opportunities", ["emitted_at"])
    op.create_index("ix_radar_opportunities_superseded_by_id", "radar_opportunities", ["superseded_by_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_radar_opportunities_superseded_by_id", table_name="radar_opportunities")
    op.drop_index("ix_radar_opportunities_emitted_at", table_name="radar_opportunities")
    op.drop_index("ix_radar_opportunities_classification", table_name="radar_opportunities")
    op.drop_index("ix_radar_opportunities_scan_run_id", table_name="radar_opportunities")
    op.drop_index("ix_radar_opportunities_stock_id", table_name="radar_opportunities")
    op.drop_index("ix_radar_opportunities_symbol", table_name="radar_opportunities")
    op.drop_table("radar_opportunities")
