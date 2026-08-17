"""add_decision_v2_calibration_fields

RADAR-C Phase C: the existing confidence-calibration engine
(src/ai_evolution/confidence_calibration.py) fits Platt/isotonic
curves against real outcome history but, per its own module
docstring, was "never wired into live recommendation output" for
Decision Engine V2 / Radar V2 -- it only ever trained against the
older RecommendationSnapshot/RecommendationOutcome ledger. This
migration adds what's needed to fix that:

  * `confidence_calibration_models.training_source` -- distinguishes a
    model trained on the legacy V1 ledger from one trained on
    `decision_v2_snapshots`/`decision_v2_outcomes` (Decision V2 /
    Radar V2's own ledger), so "at most one ACTIVE row" becomes
    "at most one ACTIVE row per source" rather than the two use cases
    fighting over a single active slot. Existing rows are backfilled
    to 'legacy_v1' (their real, unchanged training source) via the
    server_default -- no behavior change for any model already fit.

  * `decision_v2_snapshots.calibrated_confidence_score` /
    `.calibration_version` -- mirrors exactly how
    `recommendation_snapshots.calibrated_confidence_score` already
    works: a disclosed, additive companion figure alongside the raw
    `confidence_score`, populated only once a real ACTIVE
    decision_v2-source calibration model exists (both columns stay
    NULL until then, the same honest "not yet calibrated" state
    `get_effective_confidence()` already returns).

Revision ID: e1a4c7f92b03
Revises: 65f8428163dd
Create Date: 2026-08-17 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "e1a4c7f92b03"
down_revision: Union[str, Sequence[str], None] = "65f8428163dd"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "confidence_calibration_models",
        sa.Column(
            "training_source", sa.String(length=32), nullable=False, server_default="legacy_v1"
        ),
    )
    op.add_column(
        "decision_v2_snapshots",
        sa.Column("calibrated_confidence_score", sa.Numeric(6, 2), nullable=True),
    )
    op.add_column(
        "decision_v2_snapshots",
        sa.Column("calibration_version", sa.String(length=64), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("decision_v2_snapshots", "calibration_version")
    op.drop_column("decision_v2_snapshots", "calibrated_confidence_score")
    op.drop_column("confidence_calibration_models", "training_source")
