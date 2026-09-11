"""add decision_v2_outcome_scheduler_run_logs table

Revision ID: e426c459c0f7
Revises: d4e91a6c8f37
Create Date: 2026-09-11 12:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e426c459c0f7'
down_revision: Union[str, Sequence[str], None] = 'd4e91a6c8f37'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('decision_v2_outcome_scheduler_run_logs',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_seconds', sa.Numeric(precision=10, scale=3), nullable=True),
    sa.Column('evaluated_terminal', sa.Integer(), server_default='0', nullable=False),
    sa.Column('data_unavailable', sa.Integer(), server_default='0', nullable=False),
    sa.Column('cancelled', sa.Integer(), server_default='0', nullable=False),
    sa.Column('still_pending', sa.Integer(), server_default='0', nullable=False),
    sa.Column('status', sa.Enum('RUNNING', 'SUCCESS', 'FAILED', name='decisionv2outcomeschedulerrunstatus'), nullable=False),
    sa.Column('error_summary', sa.Text(), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(
        op.f('ix_decision_v2_outcome_scheduler_run_logs_started_at'),
        'decision_v2_outcome_scheduler_run_logs', ['started_at'], unique=False
    )
    # ### end Alembic commands ###


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f('ix_decision_v2_outcome_scheduler_run_logs_started_at'),
        table_name='decision_v2_outcome_scheduler_run_logs'
    )
    op.drop_table('decision_v2_outcome_scheduler_run_logs')
    # ### end Alembic commands ###
    # Not auto-generated: dropping the table above removes the column
    # but its Postgres ENUM type is an independent object that outlives
    # the column -- the same defect class ff4223acbe72's
    # 'ingestionjobstatus' ENUM already had (and fixed the same way).
    # Dropped explicitly here so a subsequent upgrade doesn't fail with
    # "type already exists".
    sa.Enum(name='decisionv2outcomeschedulerrunstatus').drop(op.get_bind(), checkfirst=True)
