"""add market intelligence tables

Revision ID: bc03fb48f33b
Revises: 9d260aefc6a7
Create Date: 2026-07-25 15:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'bc03fb48f33b'
down_revision: Union[str, Sequence[str], None] = '9d260aefc6a7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'market_scan_runs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('status', sa.Enum('PENDING', 'RUNNING', 'SUCCESS', 'FAILED', name='marketscanstatus'), nullable=False),
        sa.Column('symbols_requested', sa.Integer(), server_default='0', nullable=False),
        sa.Column('symbols_succeeded', sa.Integer(), server_default='0', nullable=False),
        sa.Column('symbols_skipped', sa.Integer(), server_default='0', nullable=False),
        sa.Column('symbols_failed', sa.Integer(), server_default='0', nullable=False),
        sa.Column('error_summary', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('duration_seconds', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'symbol_intelligence_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scan_run_id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column('sector', sa.String(length=128), nullable=True),
        sa.Column(
            'recommendation',
            sa.Enum('STRONG_BUY', 'BUY', 'HOLD', 'SELL', 'STRONG_SELL', name='recommendationlabel', create_type=False),
            nullable=False,
        ),
        sa.Column('confidence', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('final_score', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('target_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('stop_loss', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('expected_return_pct', sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column('risk_level', sa.String(length=16), nullable=True),
        sa.Column('time_horizon', sa.String(length=16), nullable=True),
        sa.Column('position_size', sa.String(length=16), nullable=True),
        sa.Column('technical_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('fundamental_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('dividend_yield', sa.Numeric(precision=9, scale=6), nullable=True),
        sa.Column('rsi', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('adx', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('latest_price', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('bollinger_upper', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('bullish_factors', sa.JSON(), nullable=True),
        sa.Column('bearish_factors', sa.JSON(), nullable=True),
        sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('engine_version', sa.String(length=32), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['scan_run_id'], ['market_scan_runs.id'], ),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scan_run_id', 'stock_id', name='uq_symbol_intelligence_record_identity'),
    )
    op.create_index(
        op.f('ix_symbol_intelligence_records_scan_run_id'), 'symbol_intelligence_records', ['scan_run_id'], unique=False
    )
    op.create_index(
        op.f('ix_symbol_intelligence_records_stock_id'), 'symbol_intelligence_records', ['stock_id'], unique=False
    )
    op.create_index(
        op.f('ix_symbol_intelligence_records_symbol'), 'symbol_intelligence_records', ['symbol'], unique=False
    )
    op.create_index(
        op.f('ix_symbol_intelligence_records_sector'), 'symbol_intelligence_records', ['sector'], unique=False
    )
    op.create_index(
        op.f('ix_symbol_intelligence_records_evaluated_at'), 'symbol_intelligence_records', ['evaluated_at'], unique=False
    )

    op.create_table(
        'sector_intelligence_summaries',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scan_run_id', sa.Integer(), nullable=False),
        sa.Column('sector', sa.String(length=128), nullable=False),
        sa.Column('symbol_count', sa.Integer(), nullable=False),
        sa.Column('average_confidence', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('average_final_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('average_expected_return_pct', sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column('average_technical_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('average_fundamental_score', sa.Numeric(precision=6, scale=2), nullable=True),
        sa.Column('buy_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('sell_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('hold_count', sa.Integer(), server_default='0', nullable=False),
        sa.Column('breadth', sa.Numeric(precision=6, scale=4), nullable=False),
        sa.Column('momentum', sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['scan_run_id'], ['market_scan_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scan_run_id', 'sector', name='uq_sector_intelligence_summary_identity'),
    )
    op.create_index(
        op.f('ix_sector_intelligence_summaries_scan_run_id'), 'sector_intelligence_summaries', ['scan_run_id'], unique=False
    )
    op.create_index(
        op.f('ix_sector_intelligence_summaries_sector'), 'sector_intelligence_summaries', ['sector'], unique=False
    )

    op.create_table(
        'market_alerts',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scan_run_id', sa.Integer(), nullable=True),
        sa.Column(
            'alert_type',
            sa.Enum(
                'NEW_STRONG_BUY', 'RECOMMENDATION_UPGRADED', 'RECOMMENDATION_DOWNGRADED',
                'CONFIDENCE_ABOVE_THRESHOLD', 'TARGET_REACHED', 'RISK_SPIKE', 'SECTOR_ROTATION',
                name='alerttype',
            ),
            nullable=False,
        ),
        sa.Column('severity', sa.Enum('INFO', 'WARNING', 'CRITICAL', name='alertseverity'), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=True),
        sa.Column('sector', sa.String(length=128), nullable=True),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['scan_run_id'], ['market_scan_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_market_alerts_scan_run_id'), 'market_alerts', ['scan_run_id'], unique=False)
    op.create_index(op.f('ix_market_alerts_alert_type'), 'market_alerts', ['alert_type'], unique=False)
    op.create_index(op.f('ix_market_alerts_symbol'), 'market_alerts', ['symbol'], unique=False)
    op.create_index(op.f('ix_market_alerts_generated_at'), 'market_alerts', ['generated_at'], unique=False)

    op.create_table(
        'market_change_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scan_run_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column(
            'change_type',
            sa.Enum(
                'RECOMMENDATION_CHANGE', 'CONFIDENCE_CHANGE', 'SCORE_CHANGE', 'TARGET_PRICE_CHANGE',
                'RISK_CHANGE', 'TECHNICAL_CHANGE', 'FUNDAMENTAL_CHANGE', name='changetype',
            ),
            nullable=False,
        ),
        sa.Column('previous_value', sa.String(length=64), nullable=True),
        sa.Column('new_value', sa.String(length=64), nullable=True),
        sa.Column('delta', sa.Numeric(precision=12, scale=4), nullable=True),
        sa.Column('detected_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['scan_run_id'], ['market_scan_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_market_change_events_scan_run_id'), 'market_change_events', ['scan_run_id'], unique=False)
    op.create_index(op.f('ix_market_change_events_symbol'), 'market_change_events', ['symbol'], unique=False)
    op.create_index(op.f('ix_market_change_events_change_type'), 'market_change_events', ['change_type'], unique=False)
    op.create_index(op.f('ix_market_change_events_detected_at'), 'market_change_events', ['detected_at'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_market_change_events_detected_at'), table_name='market_change_events')
    op.drop_index(op.f('ix_market_change_events_change_type'), table_name='market_change_events')
    op.drop_index(op.f('ix_market_change_events_symbol'), table_name='market_change_events')
    op.drop_index(op.f('ix_market_change_events_scan_run_id'), table_name='market_change_events')
    op.drop_table('market_change_events')

    op.drop_index(op.f('ix_market_alerts_generated_at'), table_name='market_alerts')
    op.drop_index(op.f('ix_market_alerts_symbol'), table_name='market_alerts')
    op.drop_index(op.f('ix_market_alerts_alert_type'), table_name='market_alerts')
    op.drop_index(op.f('ix_market_alerts_scan_run_id'), table_name='market_alerts')
    op.drop_table('market_alerts')

    op.drop_index(op.f('ix_sector_intelligence_summaries_sector'), table_name='sector_intelligence_summaries')
    op.drop_index(op.f('ix_sector_intelligence_summaries_scan_run_id'), table_name='sector_intelligence_summaries')
    op.drop_table('sector_intelligence_summaries')

    op.drop_index(op.f('ix_symbol_intelligence_records_evaluated_at'), table_name='symbol_intelligence_records')
    op.drop_index(op.f('ix_symbol_intelligence_records_sector'), table_name='symbol_intelligence_records')
    op.drop_index(op.f('ix_symbol_intelligence_records_symbol'), table_name='symbol_intelligence_records')
    op.drop_index(op.f('ix_symbol_intelligence_records_stock_id'), table_name='symbol_intelligence_records')
    op.drop_index(op.f('ix_symbol_intelligence_records_scan_run_id'), table_name='symbol_intelligence_records')
    op.drop_table('symbol_intelligence_records')

    op.drop_table('market_scan_runs')
    # ### end Alembic commands ###

    # Not auto-generated: each Enum column above created an independent
    # Postgres ENUM type that outlives dropping the column/table -- same
    # defect class every prior migration in this repo already works
    # around; dropped explicitly here so a subsequent upgrade doesn't
    # fail with "type already exists". 'recommendationlabel' is NOT
    # dropped here -- it is owned by recommendation_snapshots
    # (migration 9d260aefc6a7) and reused here with create_type=False;
    # dropping it would break that earlier table's column.
    sa.Enum(name='changetype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='alertseverity').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='alerttype').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='marketscanstatus').drop(op.get_bind(), checkfirst=True)
