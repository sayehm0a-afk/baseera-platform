"""make_fundamental_snapshot_fields_nullable

Phase 1 Fix #3 of the production-readiness pass: a real, live capture
of SAHMK's GET /financials/{symbol}/ response (3 symbols, workflow run
30436660246) confirmed that current_assets, current_liabilities,
shares_outstanding, and eps are never present anywhere in that
response -- not under a different name, genuinely absent from the data
source. Every real ingestion was failing
(SahmkResponseValidationError) because these columns were NOT NULL,
which meant fundamental_score was None for every live recommendation
and the Strongest Fundamental / Best Medium Term / Best Long Term
rankings had nothing to rank. FundamentalScoreContributor already
skips any None ratio and computes a partial score (see
src/analysis/recommendation/fundamental_contributor.py) -- the schema
just needs to allow the data that's genuinely missing to be missing.

Revision ID: a8e2f4c91d37
Revises: f3a9c7d21b84
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a8e2f4c91d37"
down_revision: Union[str, Sequence[str], None] = "f3a9c7d21b84"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch_alter_table (not a bare op.alter_column): SQLite has no
    # native ALTER COLUMN ... DROP NOT NULL -- raw op.alter_column
    # emits that syntax directly and fails outright against SQLite
    # (real production audit finding: this migration was silently
    # broken against SQLite the whole time; only ever exercised
    # against Postgres, where ALTER COLUMN is native, so it never
    # surfaced). batch mode transparently falls back to SQLite's
    # recreate-table approach there while still emitting a plain
    # ALTER COLUMN on Postgres -- the same convention already
    # established in c4d8e6f19a2b_add_user_deletion_fk_policies.py.
    with op.batch_alter_table("fundamental_snapshots") as batch_op:
        batch_op.alter_column("current_assets", existing_type=sa.Numeric(24, 4), nullable=True)
        batch_op.alter_column("current_liabilities", existing_type=sa.Numeric(24, 4), nullable=True)
        batch_op.alter_column("shares_outstanding", existing_type=sa.BigInteger(), nullable=True)
        batch_op.alter_column("eps", existing_type=sa.Numeric(12, 4), nullable=True)


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("fundamental_snapshots") as batch_op:
        batch_op.alter_column("eps", existing_type=sa.Numeric(12, 4), nullable=False)
        batch_op.alter_column("shares_outstanding", existing_type=sa.BigInteger(), nullable=False)
        batch_op.alter_column("current_liabilities", existing_type=sa.Numeric(24, 4), nullable=False)
        batch_op.alter_column("current_assets", existing_type=sa.Numeric(24, 4), nullable=False)
