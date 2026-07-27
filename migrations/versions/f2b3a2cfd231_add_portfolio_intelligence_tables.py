"""add portfolio intelligence tables

Revision ID: f2b3a2cfd231
Revises: bc03fb48f33b
Create Date: 2026-07-25 17:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f2b3a2cfd231'
down_revision: Union[str, Sequence[str], None] = 'bc03fb48f33b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'portfolios',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('cash_balance', sa.Numeric(precision=18, scale=4), server_default='0', nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )

    op.create_table(
        'portfolio_holdings',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('stock_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column('quantity', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('average_cost', sa.Numeric(precision=18, scale=4), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ),
        sa.ForeignKeyConstraint(['stock_id'], ['stocks.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('portfolio_id', 'stock_id', name='uq_portfolio_holding_identity'),
    )
    op.create_index(op.f('ix_portfolio_holdings_portfolio_id'), 'portfolio_holdings', ['portfolio_id'], unique=False)
    op.create_index(op.f('ix_portfolio_holdings_stock_id'), 'portfolio_holdings', ['stock_id'], unique=False)
    op.create_index(op.f('ix_portfolio_holdings_symbol'), 'portfolio_holdings', ['symbol'], unique=False)

    op.create_table(
        'portfolio_analysis_snapshots',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('portfolio_id', sa.Integer(), nullable=False),
        sa.Column('total_value', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('cash', sa.Numeric(precision=18, scale=4), nullable=False),
        sa.Column('health_score', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('risk_score', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('risk_level', sa.String(length=16), nullable=False),
        sa.Column('diversification_score', sa.Numeric(precision=6, scale=2), nullable=False),
        sa.Column('expected_volatility_annualized_pct', sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column('estimated_max_drawdown_pct', sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column('portfolio_beta', sa.Numeric(precision=9, scale=4), nullable=True),
        sa.Column('analysis_json', sa.JSON(), nullable=False),
        sa.Column('engine_version', sa.String(length=32), nullable=False),
        sa.Column('generated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['portfolio_id'], ['portfolios.id'], ),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        op.f('ix_portfolio_analysis_snapshots_portfolio_id'), 'portfolio_analysis_snapshots', ['portfolio_id'], unique=False
    )
    op.create_index(
        op.f('ix_portfolio_analysis_snapshots_generated_at'), 'portfolio_analysis_snapshots', ['generated_at'], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_portfolio_analysis_snapshots_generated_at'), table_name='portfolio_analysis_snapshots')
    op.drop_index(op.f('ix_portfolio_analysis_snapshots_portfolio_id'), table_name='portfolio_analysis_snapshots')
    op.drop_table('portfolio_analysis_snapshots')

    op.drop_index(op.f('ix_portfolio_holdings_symbol'), table_name='portfolio_holdings')
    op.drop_index(op.f('ix_portfolio_holdings_stock_id'), table_name='portfolio_holdings')
    op.drop_index(op.f('ix_portfolio_holdings_portfolio_id'), table_name='portfolio_holdings')
    op.drop_table('portfolio_holdings')

    op.drop_table('portfolios')
    # ### end Alembic commands ###

    # No Enum-backed columns in this migration (risk_level is a plain
    # String, matching SymbolIntelligenceRecord's own choice) -- unlike
    # 9d260aefc6a7/bc03fb48f33b, there is no Postgres ENUM type to drop
    # here.
