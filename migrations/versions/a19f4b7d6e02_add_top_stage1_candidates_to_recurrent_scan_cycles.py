"""add_top_stage1_candidates_to_recurrent_scan_cycles

BASIRAH -- PR #107, Shadow discovery fairness + observability mandate:
the forensic audit that motivated this PR (MarketScanRun 134/135/136,
2026-08-30) found that Stage 1's own top-ranked candidates each cycle
were computed but never persisted anywhere -- the moment
`RecurrentLiveScanScheduler._run_one_cycle()` returned, that ranking
was permanently lost, so a future audit of "what did Stage 1 rank
highest, and did the allocation policy actually use it" required
reconstructing the answer from source code rather than reading it back
from data.

This column persists a bounded (<=10) JSON list of
`{symbol, rank, score, selected_for_stage2, selection_source}`
objects per cycle -- built entirely from Stage 1's own already-computed
`ranking_score` (see `stage1_local_scan.run_stage1_local_scan`); no new
score, rank, or threshold is computed anywhere in this migration or the
code that populates it.

Nullable, no default: every pre-existing `RecurrentScanCycle` row (and
every future row whose status never reaches Stage 1, e.g.
SKIPPED_QUOTA/SKIPPED_LOCKED) simply has NULL here -- no backfill, no
data rewrite, no production mutation.

Revision ID: a19f4b7d6e02
Revises: cdd0ac6cb3cf
Create Date: 2026-08-30 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a19f4b7d6e02"
down_revision: Union[str, Sequence[str], None] = "cdd0ac6cb3cf"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema.

    Uses `batch_alter_table` (alembic's recommended SQLite-portable
    ALTER pattern) rather than a bare `op.add_column`: on this
    project's SQLite migration-chain test (no live Postgres available
    in this environment -- see tests/integration/test_migrations.py's
    own docstring), a bare `add_column` of a `JSON`-typed column onto
    `recurrent_scan_cycles` specifically (a table created earlier in
    this same chain, not one of the schema's original base tables)
    triggered a SQLite/SQLAlchemy reflection-cache quirk
    (`NoSuchTableError` on a table that demonstrably exists, reproduced
    and root-caused: raw `sqlite_master`/`PRAGMA table_info` queries
    disagreed within the same connection immediately afterward).
    `batch_alter_table` avoids this by explicitly using SQLite's
    recreate-table strategy instead of relying on ALTER TABLE ADD
    COLUMN's reflection path. On Postgres (production), `batch_alter_
    table` compiles to the identical plain `ALTER TABLE ADD COLUMN`
    this migration always intended -- no behavior difference there."""
    with op.batch_alter_table("recurrent_scan_cycles") as batch_op:
        batch_op.add_column(sa.Column("top_stage1_candidates", sa.JSON(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("recurrent_scan_cycles") as batch_op:
        batch_op.drop_column("top_stage1_candidates")
