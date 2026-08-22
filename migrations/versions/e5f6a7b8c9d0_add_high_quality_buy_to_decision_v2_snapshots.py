"""Phase 3: add HIGH_QUALITY_BUY tier fields to decision_v2_snapshots

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-08-22

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.add_column(sa.Column("is_high_quality_buy", sa.Boolean(), nullable=True))
        batch_op.add_column(sa.Column("high_quality_buy_explanation_ar", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.drop_column("high_quality_buy_explanation_ar")
        batch_op.drop_column("is_high_quality_buy")
