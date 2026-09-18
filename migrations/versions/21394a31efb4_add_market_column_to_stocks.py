"""add_market_column_to_stocks

Revision ID: 21394a31efb4
Revises: e4cdc8ea6c19
Create Date: 2026-09-18 19:17:02.376187

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21394a31efb4'
down_revision: Union[str, Sequence[str], None] = 'e4cdc8ea6c19'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


market_enum = sa.Enum('TADAWUL', 'US', name='market')


def upgrade() -> None:
    """Upgrade schema."""
    market_enum.create(op.get_bind(), checkfirst=True)
    op.add_column(
        'stocks',
        sa.Column('market', market_enum, server_default='TADAWUL', nullable=False),
    )
    op.create_index(op.f('ix_stocks_market'), 'stocks', ['market'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_stocks_market'), table_name='stocks')
    op.drop_column('stocks', 'market')
    market_enum.drop(op.get_bind(), checkfirst=True)
