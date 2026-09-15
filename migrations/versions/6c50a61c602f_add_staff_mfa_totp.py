"""add staff mfa totp columns and backup codes table

Revision ID: 6c50a61c602f
Revises: e426c459c0f7
Create Date: 2026-09-15 18:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6c50a61c602f'
down_revision: Union[str, Sequence[str], None] = 'e426c459c0f7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('users', sa.Column('mfa_enabled', sa.Boolean(), server_default='false', nullable=False))
    op.add_column('users', sa.Column('mfa_secret_encrypted', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('mfa_pending_secret_encrypted', sa.String(length=255), nullable=True))
    op.add_column('users', sa.Column('mfa_enabled_at', sa.DateTime(timezone=True), nullable=True))

    op.create_table('mfa_backup_codes',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('user_id', sa.Integer(), nullable=False),
    sa.Column('code_hash', sa.String(length=64), nullable=False),
    sa.Column('used_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('user_id', 'code_hash', name='uq_mfa_backup_code_user_hash')
    )
    op.create_index(op.f('ix_mfa_backup_codes_user_id'), 'mfa_backup_codes', ['user_id'], unique=False)
    op.create_index(op.f('ix_mfa_backup_codes_code_hash'), 'mfa_backup_codes', ['code_hash'], unique=False)
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f('ix_mfa_backup_codes_code_hash'), table_name='mfa_backup_codes')
    op.drop_index(op.f('ix_mfa_backup_codes_user_id'), table_name='mfa_backup_codes')
    op.drop_table('mfa_backup_codes')

    op.drop_column('users', 'mfa_enabled_at')
    op.drop_column('users', 'mfa_pending_secret_encrypted')
    op.drop_column('users', 'mfa_secret_encrypted')
    op.drop_column('users', 'mfa_enabled')
    # ### end Alembic commands ###
