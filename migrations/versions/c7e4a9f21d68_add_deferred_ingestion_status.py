"""add deferred ingestion status and next_retry_at

Root-cause fix: the four scheduled ingestion jobs (symbols,
historical_ohlcv, fundamentals, dividends) were recorded as FAILED
whenever SahmkRateLimiter correctly refused a background-priority
request to protect quota reserved for live-market-critical operations
-- a working safety feature, not a genuine ingestion defect, but
indistinguishable from one in IngestionRunLog. Adds a DEFERRED status
(Postgres: new ENUM label; SQLite: no native enum, so the CHECK
constraint is widened the same way 3c76770a2b30 widened staffrole) and
a next_retry_at column so the scheduler can persist exactly when it
will retry (the SAHMK background-quota reset time) instead of losing
that state on a restart.

Revision ID: c7e4a9f21d68
Revises: b5f1c9a34d07
Create Date: 2026-08-12 07:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c7e4a9f21d68"
down_revision: Union[str, Sequence[str], None] = "b5f1c9a34d07"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = sa.Enum("RUNNING", "SUCCESS", "PARTIAL", "FAILED", name="ingestionjobstatus")
_NEW_ENUM = sa.Enum("RUNNING", "SUCCESS", "PARTIAL", "FAILED", "DEFERRED", name="ingestionjobstatus")


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE ingestionjobstatus ADD VALUE IF NOT EXISTS 'DEFERRED'")
    else:
        with op.batch_alter_table("ingestion_run_logs") as batch_op:
            batch_op.alter_column("status", existing_type=_OLD_ENUM, type_=_NEW_ENUM)

    op.add_column(
        "ingestion_run_logs",
        sa.Column("next_retry_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("ingestion_run_logs", "next_retry_at")

    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        with op.batch_alter_table("ingestion_run_logs") as batch_op:
            batch_op.alter_column("status", existing_type=_NEW_ENUM, type_=_OLD_ENUM)
    # Postgres cannot remove a value from an existing ENUM type without
    # recreating it wholesale; left as a documented, deliberate no-op on
    # downgrade there, matching 3c76770a2b30's own precedent -- any
    # DEFERRED rows would need reassigning first in a real rollback,
    # an operational decision this migration can't safely make alone.
