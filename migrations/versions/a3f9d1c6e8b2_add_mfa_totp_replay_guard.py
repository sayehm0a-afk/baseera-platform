"""add_mfa_totp_replay_guard

2026-09-16 audit finding: verify_totp_code's valid_window=1 accepts a
code for ~90s (the current 30s step plus one on either side), but
nothing recorded "this account already used this step" -- a code
captured in transit, shoulder-surfed, or read off a compromised
authenticator-app screenshot could be replayed more than once within
that window even though only one login/enrollment should ever be able
to consume it. Adds a nullable mfa_last_used_totp_step so
src.auth.mfa_service can reject a code whose matched step is <= the
last one already accepted, closing the replay window without changing
any other TOTP behavior (still 30s/6-digit/SHA1, still +/-1 step of
drift tolerance for the *first* use of any given step).

Plain nullable column add, no constraint -- SQLite supports this
without batch_alter_table (unlike f7a2c8e1b3d5's constraint changes).

Revision ID: a3f9d1c6e8b2
Revises: f7a2c8e1b3d5
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a3f9d1c6e8b2"
down_revision: Union[str, Sequence[str], None] = "f7a2c8e1b3d5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("users", sa.Column("mfa_last_used_totp_step", sa.BigInteger(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("users", "mfa_last_used_totp_step")
