"""add_confidence_calibration_models_table

E3 of the AI Evolution Layer: a new `confidence_calibration_models`
table for the confidence-calibration lifecycle (Platt scaling /
isotonic regression fitted against real `RecommendationOutcome`
history) -- distinct from the existing `calibration_configs` table
(contributor-WEIGHT calibration). Mirrors calibration_configs' exact
DRAFT -> VALIDATED -> ACTIVE lifecycle.

Revision ID: c2a97e5d4b18
Revises: b8f4e6c1a930
Create Date: 2026-07-28 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c2a97e5d4b18"
down_revision: Union[str, Sequence[str], None] = "b8f4e6c1a930"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "confidence_calibration_models",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "DRAFT", "VALIDATED", "ACTIVE", "REJECTED", "SUPERSEDED", "ROLLED_BACK",
                name="confidencecalibrationstatus",
            ),
            nullable=False,
        ),
        sa.Column("method", sa.Enum("PLATT", "ISOTONIC", name="confidencecalibrationmethod"), nullable=False),
        sa.Column("model_params", sa.JSON(), nullable=False),
        sa.Column("training_period_start", sa.Date(), nullable=True),
        sa.Column("training_period_end", sa.Date(), nullable=True),
        sa.Column("training_sample_size", sa.Integer(), nullable=False),
        sa.Column("calibration_error_before", sa.Numeric(9, 6), nullable=True),
        sa.Column("calibration_error_after", sa.Numeric(9, 6), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("deactivated_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("version"),
    )
    op.create_index(
        op.f("ix_confidence_calibration_models_version"), "confidence_calibration_models", ["version"], unique=True
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_confidence_calibration_models_version"), table_name="confidence_calibration_models")
    op.drop_table("confidence_calibration_models")
    sa.Enum(name="confidencecalibrationmethod").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="confidencecalibrationstatus").drop(op.get_bind(), checkfirst=True)
