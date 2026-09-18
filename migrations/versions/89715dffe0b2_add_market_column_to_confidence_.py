"""add_market_column_to_confidence_calibration_models

Revision ID: 89715dffe0b2
Revises: 21394a31efb4
Create Date: 2026-09-18 20:26:54.596233

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '89715dffe0b2'
down_revision: Union[str, Sequence[str], None] = '21394a31efb4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


market_enum = sa.Enum('TADAWUL', 'US', name='market')


def upgrade() -> None:
    """Upgrade schema."""
    # The 'market' Postgres enum type already exists (created by
    # 21394a31efb4 for stocks.market) -- checkfirst=True reuses it
    # rather than trying to recreate it.
    market_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'confidence_calibration_models',
        sa.Column('market', market_enum, server_default='TADAWUL', nullable=False),
    )
    op.create_index(
        op.f('ix_confidence_calibration_models_market'), 'confidence_calibration_models', ['market'], unique=False
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_confidence_calibration_models_market'), table_name='confidence_calibration_models')
    op.drop_column('confidence_calibration_models', 'market')
    # Never drop the 'market' enum type here -- stocks.market
    # (21394a31efb4) still depends on it.
