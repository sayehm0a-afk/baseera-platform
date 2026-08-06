"""add_quality_gate_and_outcome_tracking_columns

Adds the columns the recommendation-engine quality-gate and outcome-
tracking hardening pass needs, all additive/nullable so every existing
row (and every row a caller that hasn't been updated yet writes) stays
valid with no backfill required.

`recommendation_snapshots` gains: `target_price_2`/`target_price_3`
(Decision Engine V2 computes up to three targets; the legacy single
`target_price` column this table already has stays the primary/first
target), `expires_at` (computed from the recommendation's time_horizon
at write time -- see MarketIntelligenceRepository.save_symbol_records),
`bars_used`/`spread_pct`/`likely_suspended` (the same real signals the
new publication gates read, persisted alongside the recommendation
they gated so a later audit can see exactly what evidence was used),
and `calibrated_confidence_score` (the output of
ConfidenceCalibrationEngine.apply_calibration when an active model
exists at write time -- null whenever none does, never a fabricated
value; `calibration_version`, already a column on this table since an
earlier migration, records which model produced it).

`recommendation_outcomes` gains: `target_1_reached`/`target_2_reached`/
`target_3_reached` (+ their `_at` timestamps) for per-target hit
tracking (the existing `hit_target`/`hit_stop` booleans only ever
tracked the single legacy target), `max_favorable_excursion_pct`/
`max_adverse_excursion_pct` (MFE/MAE, computed from the real forward
price path already loaded for outcome evaluation), and
`time_to_target_days` (days from publication to the first target
touched, if any, within the evaluation horizon).

Revision ID: f3a9d2c81b4e
Revises: be797f1fc67b
Create Date: 2026-08-06 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f3a9d2c81b4e"
down_revision: Union[str, Sequence[str], None] = "be797f1fc67b"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("recommendation_snapshots", sa.Column("target_price_2", sa.Numeric(18, 4), nullable=True))
    op.add_column("recommendation_snapshots", sa.Column("target_price_3", sa.Numeric(18, 4), nullable=True))
    op.add_column("recommendation_snapshots", sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendation_snapshots", sa.Column("bars_used", sa.Integer(), nullable=True))
    op.add_column("recommendation_snapshots", sa.Column("spread_pct", sa.Numeric(9, 4), nullable=True))
    op.add_column("recommendation_snapshots", sa.Column("likely_suspended", sa.Boolean(), nullable=True))
    op.add_column(
        "recommendation_snapshots", sa.Column("calibrated_confidence_score", sa.Numeric(6, 4), nullable=True)
    )

    op.add_column("recommendation_outcomes", sa.Column("target_1_reached", sa.Boolean(), nullable=True))
    op.add_column("recommendation_outcomes", sa.Column("target_1_reached_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendation_outcomes", sa.Column("target_2_reached", sa.Boolean(), nullable=True))
    op.add_column("recommendation_outcomes", sa.Column("target_2_reached_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("recommendation_outcomes", sa.Column("target_3_reached", sa.Boolean(), nullable=True))
    op.add_column("recommendation_outcomes", sa.Column("target_3_reached_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column(
        "recommendation_outcomes", sa.Column("max_favorable_excursion_pct", sa.Numeric(9, 4), nullable=True)
    )
    op.add_column(
        "recommendation_outcomes", sa.Column("max_adverse_excursion_pct", sa.Numeric(9, 4), nullable=True)
    )
    op.add_column("recommendation_outcomes", sa.Column("time_to_target_days", sa.Integer(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("recommendation_outcomes", "time_to_target_days")
    op.drop_column("recommendation_outcomes", "max_adverse_excursion_pct")
    op.drop_column("recommendation_outcomes", "max_favorable_excursion_pct")
    op.drop_column("recommendation_outcomes", "target_3_reached_at")
    op.drop_column("recommendation_outcomes", "target_3_reached")
    op.drop_column("recommendation_outcomes", "target_2_reached_at")
    op.drop_column("recommendation_outcomes", "target_2_reached")
    op.drop_column("recommendation_outcomes", "target_1_reached_at")
    op.drop_column("recommendation_outcomes", "target_1_reached")

    op.drop_column("recommendation_snapshots", "calibrated_confidence_score")
    op.drop_column("recommendation_snapshots", "likely_suspended")
    op.drop_column("recommendation_snapshots", "spread_pct")
    op.drop_column("recommendation_snapshots", "bars_used")
    op.drop_column("recommendation_snapshots", "expires_at")
    op.drop_column("recommendation_snapshots", "target_price_3")
    op.drop_column("recommendation_snapshots", "target_price_2")
