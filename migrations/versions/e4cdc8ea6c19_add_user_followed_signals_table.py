"""add_user_followed_signals_table

Revision ID: e4cdc8ea6c19
Revises: a3f9d1c6e8b2
Create Date: 2026-09-18 08:53:30.547442

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e4cdc8ea6c19'
down_revision: Union[str, Sequence[str], None] = 'a3f9d1c6e8b2'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        'user_followed_signals',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('decision_v2_snapshot_id', sa.Integer(), nullable=False),
        sa.Column('symbol', sa.String(length=16), nullable=False),
        sa.Column('followed_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['decision_v2_snapshot_id'], ['decision_v2_snapshots.id'], ),
        sa.ForeignKeyConstraint(['user_id'], ['users.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'decision_v2_snapshot_id', name='uq_user_followed_signal_snapshot'),
    )
    op.create_index(
        op.f('ix_user_followed_signals_decision_v2_snapshot_id'),
        'user_followed_signals', ['decision_v2_snapshot_id'], unique=False,
    )
    op.create_index(op.f('ix_user_followed_signals_symbol'), 'user_followed_signals', ['symbol'], unique=False)
    op.create_index(op.f('ix_user_followed_signals_user_id'), 'user_followed_signals', ['user_id'], unique=False)


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_user_followed_signals_user_id'), table_name='user_followed_signals')
    op.drop_index(op.f('ix_user_followed_signals_symbol'), table_name='user_followed_signals')
    op.drop_index(op.f('ix_user_followed_signals_decision_v2_snapshot_id'), table_name='user_followed_signals')
    op.drop_table('user_followed_signals')
