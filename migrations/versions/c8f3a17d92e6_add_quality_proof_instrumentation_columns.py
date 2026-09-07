"""add_quality_proof_instrumentation_columns

QUALITY PROOF INSTRUMENTATION HARDENING (2026-09-06): purely additive
measurement-layer columns closing three blockers found by the
forward-test readiness audit -- none of this changes Decision V2's
recommendation behavior, scoring, gates, or any consumer-facing field.

decision_v2_snapshots:
  - engine_sha, config_hash: immutable per-signal experiment-version
    provenance (src.analysis.decision_v2.versioning). NULL for every
    row written before this migration -- those must be treated as
    LEGACY_UNVERSIONED by any consumer, never silently backfilled with
    today's engine/config identity.

decision_v2_outcomes:
  - max_favorable_excursion_r, max_adverse_excursion_r: the existing
    pct-based MFE/MAE, expressed as an R-multiple of the entry-to-stop
    risk distance (comparable across signals with different stop
    distances).
  - independent_signal_key, is_independent_signal: analysis-only
    duplicate-signal grouping (see decision_v2_outcome_evaluation.
    create_pending_decision_v2_outcome) -- never read by any
    recommendation-facing code path.

Revision ID: c8f3a17d92e6
Revises: b4d8f21a6c93
Create Date: 2026-09-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c8f3a17d92e6"
down_revision: Union[str, Sequence[str], None] = "b4d8f21a6c93"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("decision_v2_snapshots", sa.Column("engine_sha", sa.String(length=64), nullable=True))
    op.add_column("decision_v2_snapshots", sa.Column("config_hash", sa.String(length=64), nullable=True))

    op.add_column(
        "decision_v2_outcomes", sa.Column("max_favorable_excursion_r", sa.Numeric(9, 4), nullable=True)
    )
    op.add_column(
        "decision_v2_outcomes", sa.Column("max_adverse_excursion_r", sa.Numeric(9, 4), nullable=True)
    )
    op.add_column(
        "decision_v2_outcomes", sa.Column("independent_signal_key", sa.String(length=36), nullable=True)
    )
    op.create_index(
        "ix_decision_v2_outcomes_independent_signal_key",
        "decision_v2_outcomes",
        ["independent_signal_key"],
    )
    op.add_column(
        "decision_v2_outcomes", sa.Column("is_independent_signal", sa.Boolean(), nullable=True)
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("decision_v2_outcomes", "is_independent_signal")
    op.drop_index(
        "ix_decision_v2_outcomes_independent_signal_key", table_name="decision_v2_outcomes"
    )
    op.drop_column("decision_v2_outcomes", "independent_signal_key")
    op.drop_column("decision_v2_outcomes", "max_adverse_excursion_r")
    op.drop_column("decision_v2_outcomes", "max_favorable_excursion_r")

    op.drop_column("decision_v2_snapshots", "config_hash")
    op.drop_column("decision_v2_snapshots", "engine_sha")
