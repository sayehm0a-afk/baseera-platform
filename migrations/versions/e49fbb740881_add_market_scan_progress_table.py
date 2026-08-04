"""add market_scan_progress table

Revision ID: e49fbb740881
Revises: c2d7e5a93f16
Create Date: 2026-08-02 11:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e49fbb740881'
down_revision: Union[str, Sequence[str], None] = 'c2d7e5a93f16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'market_scan_progress',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('run_id', sa.Integer(), nullable=False),
        sa.Column('workflow_run_id', sa.String(length=64), nullable=True),
        sa.Column('commit_sha', sa.String(length=64), nullable=True),
        sa.Column('branch', sa.String(length=255), nullable=True),
        sa.Column('mode', sa.String(length=32), nullable=True),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='RUNNING'),
        sa.Column('eligible_discovered', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('completed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('success_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('failed_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('skipped_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('insufficient_data_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('published_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('rejected_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('watch_only_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('not_evaluated_count', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('current_symbol', sa.String(length=32), nullable=True),
        sa.Column('current_symbol_name_en', sa.String(length=255), nullable=True),
        sa.Column('current_symbol_name_ar', sa.String(length=255), nullable=True),
        sa.Column('last_completed_symbol', sa.String(length=32), nullable=True),
        sa.Column('api_calls_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('retries_total', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('latest_error', sa.Text(), nullable=True),
        sa.Column('latest_warning', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['run_id'], ['market_scan_runs.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('run_id', name='uq_market_scan_progress_run_id'),
    )
    op.create_index(op.f('ix_market_scan_progress_run_id'), 'market_scan_progress', ['run_id'], unique=True)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_market_scan_progress_run_id'), table_name='market_scan_progress')
    op.drop_table('market_scan_progress')
