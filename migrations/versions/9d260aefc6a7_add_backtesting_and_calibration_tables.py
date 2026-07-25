"""add backtesting and calibration tables; add source/is_synthetic to price_bars

Revision ID: 9d260aefc6a7
Revises: ff4223acbe72
Create Date: 2026-07-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9d260aefc6a7'
down_revision: Union[str, Sequence[str], None] = 'ff4223acbe72'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # --- PriceBar provenance -- closes the gap flagged during the
    # Backtesting & Calibration Engine's architecture audit: both market
    # data providers already return source/is_synthetic per bar, but
    # upsert_price_bar previously discarded them. Existing rows (written
    # before this column existed) get the conservative default
    # is_synthetic=true -- unknown provenance is never silently treated
    # as verified-real data.
    op.add_column('price_bars', sa.Column('source', sa.String(length=64), server_default='unknown', nullable=False))
    op.add_column('price_bars', sa.Column('is_synthetic', sa.Boolean(), server_default='true', nullable=False))

    op.create_table(
        'backtest_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('idempotency_key', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', 'CANCELLED', name='backtestrunstatus'),
            nullable=False,
        ),
        sa.Column('symbols', sa.JSON(), nullable=False),
        sa.Column('strategy', sa.String(length=64), server_default='ai_decision_engine', nullable=False),
        sa.Column(
            'data_provenance_mode', sa.Enum('SYNTHETIC', 'LIVE', name='dataprovenancemode'), nullable=False
        ),
        sa.Column('start_date', sa.Date(), nullable=False),
        sa.Column('end_date', sa.Date(), nullable=False),
        sa.Column('evaluation_frequency_days', sa.Integer(), server_default='7', nullable=False),
        sa.Column('holding_horizon_days', sa.Integer(), server_default='20', nullable=False),
        sa.Column('target_price_horizon_days', sa.Integer(), server_default='60', nullable=False),
        sa.Column('transaction_cost_bps', sa.Numeric(precision=8, scale=2), server_default='0', nullable=False),
        sa.Column('slippage_bps', sa.Numeric(precision=8, scale=2), server_default='0', nullable=False),
        sa.Column('confidence_threshold', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('recommendation_threshold', sa.String(length=16), nullable=True),
        sa.Column('fundamental_reporting_lag_days', sa.Integer(), server_default='45', nullable=False),
        sa.Column('calibration_version', sa.String(length=64), nullable=True),
        sa.Column('random_seed', sa.Integer(), nullable=True),
        sa.Column('progress_current', sa.Integer(), server_default='0', nullable=False),
        sa.Column('progress_total', sa.Integer(), server_default='0', nullable=False),
        sa.Column('cancel_requested', sa.Boolean(), server_default='false', nullable=False),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_backtest_runs_idempotency_key'), 'backtest_runs', ['idempotency_key'], unique=True)

    op.create_table(
        'calibration_configs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('version', sa.String(length=64), nullable=False),
        sa.Column(
            'status',
            sa.Enum('DRAFT', 'VALIDATED', 'ACTIVE', 'REJECTED', 'SUPERSEDED', 'ROLLED_BACK', name='calibrationstatus'),
            nullable=False,
        ),
        sa.Column('config', sa.JSON(), nullable=False),
        sa.Column('training_period_start', sa.Date(), nullable=True),
        sa.Column('training_period_end', sa.Date(), nullable=True),
        sa.Column('validation_period_start', sa.Date(), nullable=True),
        sa.Column('validation_period_end', sa.Date(), nullable=True),
        sa.Column('training_run_id', sa.Integer(), nullable=True),
        sa.Column('validation_run_id', sa.Integer(), nullable=True),
        sa.Column('metrics', sa.JSON(), nullable=True),
        sa.Column('baseline_comparison_metrics', sa.JSON(), nullable=True),
        sa.Column('random_seed', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('deactivated_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['training_run_id'], ['backtest_runs.id'], ),
        sa.ForeignKeyConstraint(['validation_run_id'], ['backtest_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_calibration_configs_version'), 'calibration_configs', ['version'], unique=True)

    op.create_table(
        'recommendation_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=True),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('market_price_at_evaluation', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column(
            'recommendation',
            sa.Enum('STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL', name='recommendationlabel'),
            nullable=False,
        ),
        sa.Column('total_score', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('confidence_score', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('technical_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('fundamental_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('momentum_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('volume_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('risk_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('contributor_breakdown', sa.JSON(), nullable=True),
        sa.Column('signals', sa.JSON(), nullable=True),
        sa.Column('reasons', sa.JSON(), nullable=True),
        sa.Column('target_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('stop_loss', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('expected_return_pct', sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column('time_horizon', sa.String(length=16), nullable=True),
        sa.Column('risk_level', sa.String(length=16), nullable=True),
        sa.Column('position_size', sa.String(length=16), nullable=True),
        sa.Column('technical_input_as_of', sa.DateTime(timezone=True), nullable=True),
        sa.Column('fundamental_input_as_of', sa.Date(), nullable=True),
        sa.Column('price_bar_source', sa.String(length=64), nullable=True),
        sa.Column('price_bar_is_synthetic', sa.Boolean(), nullable=True),
        sa.Column('engine_version', sa.String(length=32), nullable=False),
        sa.Column('calibration_version', sa.String(length=64), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['backtest_runs.id'], ),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', 'stock_id', 'evaluated_at', name='uq_recommendation_snapshot_identity'),
    )
    op.create_index(op.f('ix_recommendation_snapshots_run_id'), 'recommendation_snapshots', ['run_id'], unique=False)
    op.create_index(op.f('ix_recommendation_snapshots_stock_id'), 'recommendation_snapshots', ['stock_id'], unique=False)
    op.create_index(op.f('ix_recommendation_snapshots_symbol'), 'recommendation_snapshots', ['symbol'], unique=False)
    op.create_index(
        op.f('ix_recommendation_snapshots_evaluated_at'), 'recommendation_snapshots', ['evaluated_at'], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_recommendation_snapshots_evaluated_at'), table_name='recommendation_snapshots')
    op.drop_index(op.f('ix_recommendation_snapshots_symbol'), table_name='recommendation_snapshots')
    op.drop_index(op.f('ix_recommendation_snapshots_stock_id'), table_name='recommendation_snapshots')
    op.drop_index(op.f('ix_recommendation_snapshots_run_id'), table_name='recommendation_snapshots')
    op.drop_table('recommendation_snapshots')

    op.drop_index(op.f('ix_calibration_configs_version'), table_name='calibration_configs')
    op.drop_table('calibration_configs')

    op.drop_index(op.f('ix_backtest_runs_idempotency_key'), table_name='backtest_runs')
    op.drop_table('backtest_runs')

    op.drop_column('price_bars', 'is_synthetic')
    op.drop_column('price_bars', 'source')
    # ### end Alembic commands ###

    # Not auto-generated: each Enum column above created an independent
    # Postgres ENUM type that outlives dropping the column/table --
    # same defect class 0001/a75a1f329294/ff4223acbe72 all had; dropped
    # explicitly here so a subsequent upgrade doesn't fail with "type
    # already exists".
    sa.Enum(name='recommendationlabel').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='calibrationstatus').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='dataprovenancemode').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='backtestrunstatus').drop(op.get_bind(), checkfirst=True)
