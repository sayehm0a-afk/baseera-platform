"""persist_decision_v2_extended_fields

Root-cause fix for a real audit-trail gap: DecisionEngineV2's Phase 2A/2C
extension fields (trade classification, entry-status, support/resistance,
liquidity/accumulation, technical_evidence, decision narrative, market
risk state) were computed and returned by GET /decision-v2 on every
request, but never persisted to decision_v2_snapshots -- so a stored
snapshot could not fully reproduce what the user actually saw. This
migration adds nullable columns for every one of those fields; both
write sites (src/api/routes/stocks.py's /decision-v2 route and
src/market_intelligence/repositories/market_intelligence_repository.py's
scheduled-scan pipeline) are updated in the same change to populate them.

Revision ID: a1c4f7e92b3d
Revises: e7af5e2251dc
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1c4f7e92b3d"
down_revision: Union[str, Sequence[str], None] = "e7af5e2251dc"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("decision_v2_snapshots", sa.Column("is_real_data", sa.Boolean(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("quote_timestamp", sa.DateTime(timezone=True), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("technical_confidence", sa.Numeric(6, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("momentum_confidence", sa.Numeric(6, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("liquidity_confidence", sa.Numeric(6, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_context_confidence", sa.Numeric(6, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("data_quality_confidence", sa.Numeric(6, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("trade_type", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("trade_type_label_ar", sa.String(length=64), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("time_horizon_rationale_ar", sa.Text(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("best_entry_price", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("accumulation_zone_low", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("accumulation_zone_high", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("entry_quality", sa.String(length=16), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("entry_quality_label_ar", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("entry_status", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("entry_status_label_ar", sa.String(length=64), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("invalidation_price", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("risk_level", sa.String(length=16), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("risk_level_label_ar", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("estimated_days_target_1", sa.Integer(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("estimated_days_target_2", sa.Integer(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("estimated_days_target_3", sa.Integer(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("nearest_support", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("major_support", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("nearest_resistance", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("major_resistance", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("breakout_level", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("breakdown_level", sa.Numeric(18, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("support_resistance_evidence_ar", sa.Text(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("current_volume", sa.Numeric(20, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("average_volume", sa.Numeric(20, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("relative_volume", sa.Numeric(9, 4), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("liquidity_quality_ar", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("accumulation_score", sa.Numeric(6, 2), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("accumulation_assessment_ar", sa.Text(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("volume_confirms_decision", sa.Boolean(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("abnormal_volume", sa.Boolean(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("technical_evidence", sa.JSON(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("trend_direction_ar", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("trend_strength_label_ar", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("decision_summary_ar", sa.Text(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("why_now_ar", sa.Text(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("why_not_stronger_ar", sa.Text(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("entry_confirmation_conditions_ar", sa.JSON(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("watch_next_session_ar", sa.JSON(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_risk_state", sa.String(length=32), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_risk_label_ar", sa.String(length=64), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_risk_basis_ar", sa.Text(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_risk_entry_permitted", sa.Boolean(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_risk_is_live", sa.Boolean(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_breadth_buy_count", sa.Integer(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_breadth_sell_count", sa.Integer(), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("market_breadth_symbols_scanned", sa.Integer(), nullable=True))
    op.add_column(
        "decision_v2_snapshots", sa.Column("market_breadth_average_confidence", sa.Numeric(6, 2), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    for column in (
        "market_breadth_average_confidence",
        "market_breadth_symbols_scanned",
        "market_breadth_sell_count",
        "market_breadth_buy_count",
        "market_risk_is_live",
        "market_risk_entry_permitted",
        "market_risk_basis_ar",
        "market_risk_label_ar",
        "market_risk_state",
        "watch_next_session_ar",
        "entry_confirmation_conditions_ar",
        "why_not_stronger_ar",
        "why_now_ar",
        "decision_summary_ar",
        "trend_strength_label_ar",
        "trend_direction_ar",
        "technical_evidence",
        "abnormal_volume",
        "volume_confirms_decision",
        "accumulation_assessment_ar",
        "accumulation_score",
        "liquidity_quality_ar",
        "relative_volume",
        "average_volume",
        "current_volume",
        "support_resistance_evidence_ar",
        "breakdown_level",
        "breakout_level",
        "major_resistance",
        "nearest_resistance",
        "major_support",
        "nearest_support",
        "estimated_days_target_3",
        "estimated_days_target_2",
        "estimated_days_target_1",
        "risk_level_label_ar",
        "risk_level",
        "invalidation_price",
        "entry_status_label_ar",
        "entry_status",
        "entry_quality_label_ar",
        "entry_quality",
        "accumulation_zone_high",
        "accumulation_zone_low",
        "best_entry_price",
        "time_horizon_rationale_ar",
        "trade_type_label_ar",
        "trade_type",
        "data_quality_confidence",
        "market_context_confidence",
        "liquidity_confidence",
        "momentum_confidence",
        "technical_confidence",
        "quote_timestamp",
        "is_real_data",
    ):
        op.drop_column("decision_v2_snapshots", column)
