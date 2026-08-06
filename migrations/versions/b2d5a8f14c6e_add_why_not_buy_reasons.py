"""add_why_not_buy_reasons

A dedicated, structured "why isn't this a buy" field on
decision_v2_snapshots -- distinct from why_not_stronger_ar (which only
explains why STRONG_BUY specifically wasn't reached, and only for an
already-buy-side decision). Sourced from real failed blocking gates and
negative_reasons (see reasoning.build_why_not_buy_reasons), never
fabricated, and empty for a genuine buy-side decision.

Revision ID: b2d5a8f14c6e
Revises: a1c4f7e92b3d
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "b2d5a8f14c6e"
down_revision: Union[str, Sequence[str], None] = "a1c4f7e92b3d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("decision_v2_snapshots", sa.Column("why_not_buy_reasons", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("decision_v2_snapshots", "why_not_buy_reasons")
