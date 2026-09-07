"""pr113_p1_1_concurrency_safe_episode_lock

PR113 P1-1 REMEDIATION (2026-09-07): closes the independent-signal
concurrency race identified by the independent audit of Draft PR #113.
Purely a measurement/quality-ledger integrity fix -- does not touch
any recommendation-generating table, does not change Decision V2,
Radar, or Stage 1/2 behavior in any way.

decision_v2_outcomes:
  - engine_sha, config_hash: denormalized copies of the parent
    DecisionV2Snapshot's own engine_sha/config_hash, set once at
    creation time by create_pending_decision_v2_outcome and never
    mutated afterward (exactly like `symbol`'s existing denormalization
    from the same snapshot). NULL for a legacy/unversioned snapshot,
    matching engine_sha/config_hash's own NULL semantics.
  - ux_decision_v2_outcomes_open_independent_episode: a partial unique
    index on (symbol, engine_sha, config_hash) WHERE
    is_independent_signal = true AND status = 'PENDING'. This is the
    actual concurrency guarantee: at most one row can ever hold the
    "open independent episode" position for a given symbol+cohort at
    any moment, enforced by PostgreSQL itself (not by an
    application-level check-then-insert, which the independent audit
    proved is not race-safe under real concurrent transactions). A
    NULL in either engine_sha or config_hash never collides with
    anything else under a standard btree unique index -- legacy rows
    are therefore unaffected by (and not additionally protected by)
    this constraint, matching their existing "always independent,
    never linked" policy.

Pre-migration data-conflict audit (required before adding a uniqueness
rule): confirmed zero existing rows have
`is_independent_signal = true AND status = 'PENDING'` for the same
symbol more than once -- these columns did not exist before PR #113,
so no data could have accumulated under the old, race-prone logic.

Revision ID: d4e91a6c8f37
Revises: c8f3a17d92e6
Create Date: 2026-09-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "d4e91a6c8f37"
down_revision: Union[str, Sequence[str], None] = "c8f3a17d92e6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("decision_v2_outcomes", sa.Column("engine_sha", sa.String(length=64), nullable=True))
    op.add_column("decision_v2_outcomes", sa.Column("config_hash", sa.String(length=64), nullable=True))

    op.create_index(
        "ux_decision_v2_outcomes_open_independent_episode",
        "decision_v2_outcomes",
        ["symbol", "engine_sha", "config_hash"],
        unique=True,
        postgresql_where=sa.text("is_independent_signal = true AND status = 'PENDING'"),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ux_decision_v2_outcomes_open_independent_episode", table_name="decision_v2_outcomes")
    op.drop_column("decision_v2_outcomes", "config_hash")
    op.drop_column("decision_v2_outcomes", "engine_sha")
