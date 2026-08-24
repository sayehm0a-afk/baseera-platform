"""add_recurrent_live_scan_shadow_tables

BASIRAH -- PRODUCTION-GRADE RECURRENT LIVE MARKET INTELLIGENCE mandate,
Phase 5/14 (Shadow Mode): `recurrent_scan_cycles` (one row per recurrent
live-scan cycle attempt, including skipped ones) and
`shadow_live_signals` (the Shadow Mode audit ledger of every material
lifecycle change the recurrent scheduler detected, via the existing,
unmodified Decision V2 pipeline). Neither table is read by any
consumer-facing route; `radar_opportunities` and everything it feeds
stays completely untouched by this migration.

Revision ID: b3f7a1c9d824
Revises: a1b2c3d4e5f6
Create Date: 2026-08-24 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b3f7a1c9d824"
down_revision: Union[str, Sequence[str], None] = "a1b2c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "recurrent_scan_cycles",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cycle_id", sa.String(length=36), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "SUCCESS",
                "SUCCESS_NO_CHANGE",
                "SKIPPED_MARKET_CLOSED",
                "SKIPPED_QUOTA",
                "SKIPPED_LOCKED",
                "SKIPPED_NO_CANDIDATES",
                "PARTIAL_PROVIDER_FAILURE",
                "FAILED",
                name="recurrentscancyclestatus",
            ),
            nullable=False,
        ),
        sa.Column("skip_reason", sa.String(length=64), nullable=True),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("market_status", sa.String(length=32), nullable=True),
        sa.Column("active_signal_candidate_count", sa.Integer(), nullable=True),
        sa.Column("new_stage1_candidate_count", sa.Integer(), nullable=True),
        sa.Column("symbols_selected_count", sa.Integer(), nullable=True),
        sa.Column("symbols_evaluated_count", sa.Integer(), nullable=True),
        sa.Column("signals_new_opportunity_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signals_refreshed_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signals_missed_entry_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signals_chase_risk_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signals_invalidated_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("signals_unchanged_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("quota_remaining_before", sa.Integer(), nullable=True),
        sa.Column("quota_remaining_after", sa.Integer(), nullable=True),
        sa.Column("requests_used_estimate", sa.Integer(), nullable=True),
        sa.Column("scan_run_id", sa.Integer(), nullable=True),
        sa.Column("triggered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cycle_id", name="uq_recurrent_scan_cycle_cycle_id"),
    )
    op.create_index("ix_recurrent_scan_cycles_cycle_id", "recurrent_scan_cycles", ["cycle_id"])
    op.create_index("ix_recurrent_scan_cycles_status", "recurrent_scan_cycles", ["status"])
    op.create_index("ix_recurrent_scan_cycles_scan_run_id", "recurrent_scan_cycles", ["scan_run_id"])
    op.create_index("ix_recurrent_scan_cycles_triggered_at", "recurrent_scan_cycles", ["triggered_at"])

    op.create_table(
        "shadow_live_signals",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("cycle_id", sa.String(length=36), nullable=False),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("stock_id", sa.Integer(), sa.ForeignKey("stocks.id"), nullable=False),
        sa.Column(
            "decision_v2_snapshot_id", sa.Integer(), sa.ForeignKey("decision_v2_snapshots.id"), nullable=False
        ),
        sa.Column(
            "lifecycle_result",
            sa.Enum(
                "NEW_INTRADAY_OPPORTUNITY",
                "REFRESHED_SIGNAL",
                "MISSED_ENTRY",
                "CHASE_RISK",
                "INVALIDATED_SIGNAL",
                "STALE_SIGNAL",
                "UNCHANGED_SIGNAL",
                name="shadowlifecycleresult",
            ),
            nullable=False,
        ),
        sa.Column("change_reason", sa.Text(), nullable=True),
        sa.Column("selection_reason", sa.String(length=32), nullable=True),
        sa.Column("previous_classification", sa.String(length=32), nullable=True),
        sa.Column("classification", sa.String(length=32), nullable=False),
        sa.Column("previous_confidence_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("confidence_score", sa.Numeric(6, 2), nullable=False),
        sa.Column("previous_entry_status", sa.String(length=32), nullable=True),
        sa.Column("entry_status", sa.String(length=32), nullable=True),
        sa.Column("previous_stage1_ranking_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("stage1_ranking_score", sa.Numeric(6, 2), nullable=True),
        sa.Column("price_at_signal", sa.Numeric(18, 4), nullable=True),
        sa.Column("entry_zone_low", sa.Numeric(18, 4), nullable=True),
        sa.Column("entry_zone_high", sa.Numeric(18, 4), nullable=True),
        sa.Column("stop_loss", sa.Numeric(18, 4), nullable=True),
        sa.Column("target_1", sa.Numeric(18, 4), nullable=True),
        sa.Column("target_2", sa.Numeric(18, 4), nullable=True),
        sa.Column("target_3", sa.Numeric(18, 4), nullable=True),
        sa.Column("risk_reward_target_1", sa.Numeric(9, 4), nullable=True),
        sa.Column("data_freshness_status", sa.String(length=16), nullable=True),
        sa.Column("decision_timestamp", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_engine_version", sa.String(length=32), nullable=True),
        sa.Column("emitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("superseded_by_id", sa.Integer(), sa.ForeignKey("shadow_live_signals.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("decision_v2_snapshot_id", name="uq_shadow_live_signal_snapshot"),
    )
    op.create_index("ix_shadow_live_signals_cycle_id", "shadow_live_signals", ["cycle_id"])
    op.create_index("ix_shadow_live_signals_symbol", "shadow_live_signals", ["symbol"])
    op.create_index("ix_shadow_live_signals_stock_id", "shadow_live_signals", ["stock_id"])
    op.create_index("ix_shadow_live_signals_lifecycle_result", "shadow_live_signals", ["lifecycle_result"])
    op.create_index("ix_shadow_live_signals_emitted_at", "shadow_live_signals", ["emitted_at"])
    op.create_index("ix_shadow_live_signals_superseded_by_id", "shadow_live_signals", ["superseded_by_id"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_shadow_live_signals_superseded_by_id", table_name="shadow_live_signals")
    op.drop_index("ix_shadow_live_signals_emitted_at", table_name="shadow_live_signals")
    op.drop_index("ix_shadow_live_signals_lifecycle_result", table_name="shadow_live_signals")
    op.drop_index("ix_shadow_live_signals_stock_id", table_name="shadow_live_signals")
    op.drop_index("ix_shadow_live_signals_symbol", table_name="shadow_live_signals")
    op.drop_index("ix_shadow_live_signals_cycle_id", table_name="shadow_live_signals")
    op.drop_table("shadow_live_signals")

    op.drop_index("ix_recurrent_scan_cycles_triggered_at", table_name="recurrent_scan_cycles")
    op.drop_index("ix_recurrent_scan_cycles_scan_run_id", table_name="recurrent_scan_cycles")
    op.drop_index("ix_recurrent_scan_cycles_status", table_name="recurrent_scan_cycles")
    op.drop_index("ix_recurrent_scan_cycles_cycle_id", table_name="recurrent_scan_cycles")
    op.drop_table("recurrent_scan_cycles")

    sa.Enum(name="shadowlifecycleresult").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="recurrentscancyclestatus").drop(op.get_bind(), checkfirst=True)
