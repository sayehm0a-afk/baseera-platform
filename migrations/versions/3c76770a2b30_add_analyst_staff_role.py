"""add_analyst_staff_role

M5 of the "close real user blockers" milestone: adds a fourth
`StaffRole` value, ANALYST, sitting outside the existing
OWNER > ADMIN > SUPPORT rank ladder entirely (src/auth/rbac.py's
`require_any_staff_role` checks exact membership, not rank) -- an
analyst account is granted access to specific read-only AI/market
intelligence audit routes and nothing else; it does not inherit
SUPPORT's calibration-activation power or ADMIN's user/billing
management power the way a rank-based insertion would.

Dialect-specific: Postgres has a real `staffrole` ENUM type that only
supports adding a new label (`ALTER TYPE ... ADD VALUE`, which cannot
run inside the transaction Alembic normally wraps a migration in --
hence the autocommit block); SQLite has no native enum, so the
"widen the CHECK constraint" approach already established in
a8e2f4c91d37/c4d8e6f19a2b (batch_alter_table's recreate-table
fallback) is used there instead.

Revision ID: 3c76770a2b30
Revises: 8ce21d4cd979
Create Date: 2026-08-08 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "3c76770a2b30"
down_revision: Union[str, Sequence[str], None] = "8ce21d4cd979"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_OLD_ENUM = sa.Enum("OWNER", "ADMIN", "SUPPORT", name="staffrole")
_NEW_ENUM = sa.Enum("OWNER", "ADMIN", "ANALYST", "SUPPORT", name="staffrole")


def upgrade() -> None:
    """Upgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        with op.get_context().autocommit_block():
            op.execute("ALTER TYPE staffrole ADD VALUE IF NOT EXISTS 'ANALYST'")
    else:
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("staff_role", existing_type=_OLD_ENUM, type_=_NEW_ENUM)


def downgrade() -> None:
    """Downgrade schema."""
    bind = op.get_bind()
    if bind.dialect.name != "postgresql":
        with op.batch_alter_table("users") as batch_op:
            batch_op.alter_column("staff_role", existing_type=_NEW_ENUM, type_=_OLD_ENUM)
    # Postgres cannot remove a value from an existing ENUM type without
    # recreating it wholesale; left as a documented, deliberate no-op on
    # downgrade there (any ANALYST rows would need reassigning first in
    # a real rollback, which is an operational decision, not one this
    # migration can safely make unilaterally).
