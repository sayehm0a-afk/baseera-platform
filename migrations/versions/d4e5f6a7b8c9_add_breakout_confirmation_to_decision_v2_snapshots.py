"""Phase 3 area 5: add breakout confirmation fields to decision_v2_snapshots

Revision ID: d4e5f6a7b8c9
Revises: c3d4e5f6a7b8
Create Date: 2026-08-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c3d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.add_column(sa.Column("breakout_status", sa.String(length=32), nullable=True))
        batch_op.add_column(sa.Column("breakout_hold_days", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("breakout_volume_confirmed", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("breakout_follow_through_pct", sa.Numeric(9, 2), nullable=True))
        batch_op.add_column(sa.Column("breakout_explanation_ar", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.drop_column("breakout_explanation_ar")
        batch_op.drop_column("breakout_follow_through_pct")
        batch_op.drop_column("breakout_volume_confirmed")
        batch_op.drop_column("breakout_hold_days")
        batch_op.drop_column("breakout_status")
