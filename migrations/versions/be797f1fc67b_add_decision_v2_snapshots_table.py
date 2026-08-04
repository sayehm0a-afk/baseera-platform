"""add decision_v2_snapshots table

Revision ID: be797f1fc67b
Revises: e49fbb740881
Create Date: 2026-08-04 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'be797f1fc67b'
down_revision: Union[str, Sequence[str], None] = 'e49fbb740881'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'decision_v2_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column('company_name_ar', sa.String(length=255), nullable=True),
        sa.Column('company_name_en', sa.String(length=255), nullable=False),
        sa.Column('sector_ar', sa.String(length=128), nullable=True),
        sa.Column('decision', sa.String(length=32), nullable=False),
        sa.Column('decision_label_ar', sa.String(length=64), nullable=False),
        sa.Column('confidence_score', sa.Numeric(6, 2), nullable=False),
        sa.Column('opportunity_quality_score', sa.Numeric(6, 2), nullable=False),
        sa.Column('risk_score', sa.Numeric(6, 2), nullable=False),
        sa.Column('data_quality_score', sa.Numeric(6, 2), nullable=False),
        sa.Column('data_freshness_status', sa.String(length=16), nullable=False),
        sa.Column('current_price', sa.Numeric(18, 4), nullable=True),
        sa.Column('entry_zone_low', sa.Numeric(18, 4), nullable=True),
        sa.Column('entry_zone_high', sa.Numeric(18, 4), nullable=True),
        sa.Column('stop_loss', sa.Numeric(18, 4), nullable=True),
        sa.Column('target_1', sa.Numeric(18, 4), nullable=True),
        sa.Column('target_2', sa.Numeric(18, 4), nullable=True),
        sa.Column('target_3', sa.Numeric(18, 4), nullable=True),
        sa.Column('expected_return_target_1', sa.Numeric(9, 4), nullable=True),
        sa.Column('expected_return_target_2', sa.Numeric(9, 4), nullable=True),
        sa.Column('downside_to_stop', sa.Numeric(9, 4), nullable=True),
        sa.Column('risk_reward_target_1', sa.Numeric(9, 4), nullable=True),
        sa.Column('risk_reward_target_2', sa.Numeric(9, 4), nullable=True),
        sa.Column('expected_holding_period_min_days', sa.Integer(), nullable=True),
        sa.Column('expected_holding_period_max_days', sa.Integer(), nullable=True),
        sa.Column('expected_holding_period_label_ar', sa.String(length=64), nullable=True),
        sa.Column('horizon_type', sa.String(length=16), nullable=True),
        sa.Column('market_status', sa.String(length=32), nullable=False),
        sa.Column('decision_timestamp', sa.DateTime(timezone=True), nullable=False),
        sa.Column('invalidation_conditions', sa.JSON(), nullable=True),
        sa.Column('positive_reasons', sa.JSON(), nullable=True),
        sa.Column('negative_reasons', sa.JSON(), nullable=True),
        sa.Column('warnings', sa.JSON(), nullable=True),
        sa.Column('recommendation_basis', sa.String(length=2000), nullable=True),
        sa.Column('sub_scores', sa.JSON(), nullable=True),
        sa.Column('gates', sa.JSON(), nullable=True),
        sa.Column('analysis_version', sa.String(length=32), nullable=False),
        sa.Column('data_source', sa.String(length=32), nullable=False),
        sa.Column('is_synthetic', sa.Boolean(), nullable=True),
        sa.Column('scan_run_id', sa.Integer(), nullable=True),
        sa.Column('requested_by_user_id', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
        sa.ForeignKeyConstraint(['requested_by_user_id'], ['users.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_decision_v2_snapshots_stock_id'), 'decision_v2_snapshots', ['stock_id'], unique=False)
    op.create_index(op.f('ix_decision_v2_snapshots_symbol'), 'decision_v2_snapshots', ['symbol'], unique=False)
    op.create_index(op.f('ix_decision_v2_snapshots_decision'), 'decision_v2_snapshots', ['decision'], unique=False)
    op.create_index(
        op.f('ix_decision_v2_snapshots_decision_timestamp'), 'decision_v2_snapshots', ['decision_timestamp'],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_decision_v2_snapshots_decision_timestamp'), table_name='decision_v2_snapshots')
    op.drop_index(op.f('ix_decision_v2_snapshots_decision'), table_name='decision_v2_snapshots')
    op.drop_index(op.f('ix_decision_v2_snapshots_symbol'), table_name='decision_v2_snapshots')
    op.drop_index(op.f('ix_decision_v2_snapshots_stock_id'), table_name='decision_v2_snapshots')
    op.drop_table('decision_v2_snapshots')
