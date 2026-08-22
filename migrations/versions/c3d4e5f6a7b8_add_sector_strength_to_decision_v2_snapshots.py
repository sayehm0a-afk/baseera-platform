"""Phase 3 area 4: add sector-relative-strength fields to decision_v2_snapshots

Revision ID: c3d4e5f6a7b8
Revises: b2c3d4e5f6a7
Create Date: 2026-08-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "c3d4e5f6a7b8"
down_revision: Union[str, Sequence[str], None] = "b2c3d4e5f6a7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.add_column(sa.Column("sector_name", sa.String(length=64), nullable=True))
        batch_op.add_column(sa.Column("sector_strength_score", sa.Numeric(6, 2), nullable=True))
        batch_op.add_column(sa.Column("stock_vs_sector_relative_strength", sa.Numeric(6, 3), nullable=True))
        batch_op.add_column(sa.Column("sector_data_timestamp", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("sector_strength_used", sa.Boolean(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.drop_column("sector_strength_used")
        batch_op.drop_column("sector_data_timestamp")
        batch_op.drop_column("stock_vs_sector_relative_strength")
        batch_op.drop_column("sector_strength_score")
        batch_op.drop_column("sector_name")
