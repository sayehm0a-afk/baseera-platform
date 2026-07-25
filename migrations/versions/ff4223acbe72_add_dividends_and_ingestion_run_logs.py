"""add dividends and ingestion_run_logs tables

Revision ID: ff4223acbe72
Revises: a75a1f329294
Create Date: 2026-07-25 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'ff4223acbe72'
down_revision: Union[str, Sequence[str], None] = 'a75a1f329294'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('dividends',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('stock_id', sa.Integer(), nullable=False),
    sa.Column('ex_date', sa.Date(), nullable=False),
    sa.Column('payment_date', sa.Date(), nullable=True),
    sa.Column('amount_per_share', sa.Numeric(precision=12, scale=4), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('is_synthetic', sa.Boolean(), server_default='false', nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('stock_id', 'ex_date', name='uq_dividend_identity')
    )
    op.create_index(op.f('ix_dividends_ex_date'), 'dividends', ['ex_date'], unique=False)
    op.create_index(op.f('ix_dividends_stock_id'), 'dividends', ['stock_id'], unique=False)

    op.create_table('ingestion_run_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('job_name', sa.String(length=64), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Numeric(precision=10, scale=3), nullable=True),
    sa.Column('symbols_requested', sa.Integer(), server_default='0', nullable=False),
    sa.Column('symbols_succeeded', sa.Integer(), server_default='0', nullable=False),
    sa.Column('symbols_failed', sa.Integer(), server_default='0', nullable=False),
    sa.Column('rows_upserted', sa.Integer(), server_default='0', nullable=False),
    sa.Column('retry_count', sa.Integer(), server_default='0', nullable=False),
    sa.Column('status', sa.Enum('RUNNING', 'SUCCESS', 'PARTIAL', 'FAILED', name='ingestionjobstatus'), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_ingestion_run_logs_job_name'), 'ingestion_run_logs', ['job_name'], unique=False)
    op.create_index(op.f('ix_ingestion_run_logs_started_at'), 'ingestion_run_logs', ['started_at'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_ingestion_run_logs_started_at'), table_name='ingestion_run_logs')
    op.drop_index(op.f('ix_ingestion_run_logs_job_name'), table_name='ingestion_run_logs')
    op.drop_table('ingestion_run_logs')
    op.drop_index(op.f('ix_dividends_stock_id'), table_name='dividends')
    op.drop_index(op.f('ix_dividends_ex_date'), table_name='dividends')
    op.drop_table('dividends')
    # ### end Alembic commands ###
    # Not auto-generated: dropping ingestion_run_logs above removes the
    # table but its Postgres ENUM type is an independent object that
    # outlives the column -- the same defect class 0001's 'timeframe'
    # ENUM and a75a1f329294's 'periodtype' ENUM both had (M2.1, M2.3);
    # dropped explicitly here so a subsequent upgrade doesn't fail with
    # "type already exists".
    sa.Enum(name='ingestionjobstatus').drop(op.get_bind(), checkfirst=True)
