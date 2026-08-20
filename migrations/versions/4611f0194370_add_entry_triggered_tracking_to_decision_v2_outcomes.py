"""add_entry_triggered_tracking_to_decision_v2_outcomes

BASIRAH LIVE VALIDATION TRACKING: the outcome evaluator previously
assumed every actionable BUY-like decision filled immediately at the
signal price, so a stop-level touch before price ever traded into the
recommended entry zone was wrongly scored as a real loss. Adds
`entry_triggered`/`entry_triggered_at` (target/stop tracking now only
starts once these are set), `invalidated`/`invalidated_at` (the
pre-entry "stop level reached before ever entering" case, distinct
from a real STOP_LOSS_HIT), and literal `highest_price_after_entry`/
`lowest_price_after_entry` price columns alongside the existing
pct-based MFE/MAE. Also widens `decisionv2outcomestatus` with two new
terminal values (`ENTRY_NEVER_TRIGGERED`, `INVALIDATED`), both added to
`NON_RESOLVING_STATUSES` so no existing win-rate/false-positive-rate
computation anywhere in the codebase needs to change to stay correct.

Revision ID: 4611f0194370
Revises: d3f7a2c891e4
Create Date: 2026-08-19 21:10:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "4611f0194370"
down_revision: Union[str, Sequence[str], None] = "d3f7a2c891e4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = sa.Enum(
    "PENDING",
    "TARGET_1_HIT",
    "TARGET_2_HIT",
    "TARGET_3_HIT",
    "STOP_LOSS_HIT",
    "PARTIAL",
    "EXPIRED",
    "CANCELLED",
    "DATA_UNAVAILABLE",
    name="decisionv2outcomestatus",
)
_NEW_ENUM = sa.Enum(
    "PENDING",
    "TARGET_1_HIT",
    "TARGET_2_HIT",
    "TARGET_3_HIT",
    "STOP_LOSS_HIT",
    "PARTIAL",
    "EXPIRED",
    "CANCELLED",
    "DATA_UNAVAILABLE",
    "ENTRY_NEVER_TRIGGERED",
    "INVALIDATED",
    name="decisionv2outcomestatus",
)


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE decisionv2outcomestatus ADD VALUE IF NOT EXISTS 'ENTRY_NEVER_TRIGGERED'")
            op.execute("ALTER TYPE decisionv2outcomestatus ADD VALUE IF NOT EXISTS 'INVALIDATED'")
    else:
        with op.batch_alter_table("decision_v2_outcomes") as batch_op:
            batch_op.alter_column("status", existing_type=_OLD_ENUM, type_=_NEW_ENUM)

    with op.batch_alter_table("decision_v2_outcomes") as batch_op:
        batch_op.add_column(
            sa.Column("entry_triggered", sa.Boolean(), nullable=False, server_default="0")
        )
        batch_op.add_column(sa.Column("entry_triggered_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("invalidated", sa.Boolean(), nullable=False, server_default="0"))
        batch_op.add_column(sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True))
        batch_op.add_column(sa.Column("highest_price_after_entry", sa.Numeric(18, 4), nullable=True))
        batch_op.add_column(sa.Column("lowest_price_after_entry", sa.Numeric(18, 4), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("decision_v2_outcomes") as batch_op:
        batch_op.drop_column("lowest_price_after_entry")
        batch_op.drop_column("highest_price_after_entry")
        batch_op.drop_column("invalidated_at")
        batch_op.drop_column("invalidated")
        batch_op.drop_column("entry_triggered_at")
        batch_op.drop_column("entry_triggered")

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        with op.batch_alter_table("decision_v2_outcomes") as batch_op:
            batch_op.alter_column("status", existing_type=_NEW_ENUM, type_=_OLD_ENUM)
    # Postgres cannot remove a value from an existing ENUM type without
    # recreating it wholesale; left as a documented, deliberate no-op on
    # downgrade there, matching c7e4a9f21d68's own precedent -- any
    # ENTRY_NEVER_TRIGGERED/INVALIDATED rows would need reassigning
    # first in a real rollback, an operational decision this migration
    # can't safely make alone.
