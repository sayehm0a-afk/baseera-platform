"""add_m10_validation_session_and_decision_v2_outcome

M10 (Real Saudi Market Signal Validation): a proper, immutable
validation ledger. Adds `validation_sessions` (the explicit, bounded
grouping for one deliberate live-validation run, distinct from routine
scheduled scans -- with a hard `is_dry_run` flag so dry-run rows can
never be mistaken for real evidence) and `decision_v2_outcomes` (the
outcome tracker correctly linked to `decision_v2_snapshots` -- the
richer, user-facing decision shape -- rather than the older
`recommendation_snapshots`/`recommendation_outcomes` pair, which stays
untouched and continues to serve backtesting/paper-trading). Also adds
`validation_session_id` and `ranking_position` to `decision_v2_snapshots`
so a snapshot issued during a session can be grouped and its rank at
publication time reproduced later.

Revision ID: 879941a7def9
Revises: c7e4a9f21d68
Create Date: 2026-08-12 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "879941a7def9"
down_revision: Union[str, Sequence[str], None] = "c7e4a9f21d68"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "validation_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column(
            "status",
            sa.Enum("RUNNING", "CLOSED", "ABORTED", name="validationsessionstatus"),
            nullable=False,
            server_default="RUNNING",
        ),
        sa.Column("is_dry_run", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source_production_commit", sa.String(length=64), nullable=True),
        sa.Column("config_fingerprint", sa.JSON(), nullable=True),
        sa.Column("market_regime_at_start", sa.JSON(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_by_user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_validation_sessions_status", "validation_sessions", ["status"])
    op.create_index("ix_validation_sessions_is_dry_run", "validation_sessions", ["is_dry_run"])
    op.create_index("ix_validation_sessions_started_at", "validation_sessions", ["started_at"])

    # batch_alter_table: SQLite (used by tests/integration/test_migrations.py's
    # SQLite-based chain replay) has no ALTER TABLE ADD CONSTRAINT -- batch
    # mode falls back to its copy-and-move strategy there while emitting
    # plain ALTER TABLE on Postgres.
    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.add_column(sa.Column("validation_session_id", sa.Integer(), nullable=True))
        batch_op.add_column(sa.Column("ranking_position", sa.Integer(), nullable=True))
        batch_op.create_index(
            "ix_decision_v2_snapshots_validation_session_id", ["validation_session_id"], unique=False
        )
        batch_op.create_foreign_key(
            "fk_decision_v2_snapshots_validation_session_id",
            "validation_sessions",
            ["validation_session_id"],
            ["id"],
        )

    op.create_table(
        "decision_v2_outcomes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "decision_v2_snapshot_id", sa.Integer(), sa.ForeignKey("decision_v2_snapshots.id"), nullable=False
        ),
        sa.Column("validation_session_id", sa.Integer(), sa.ForeignKey("validation_sessions.id"), nullable=True),
        sa.Column("symbol", sa.String(length=16), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "status",
            sa.Enum(
                "PENDING",
                "TARGET_1_HIT",
                "TARGET_2_HIT",
                "TARGET_3_HIT",
                "STOP_LOSS_HIT",
                "PARTIAL",
                "EXPIRED",
                "CANCELLED",
                "DATA_UNAVAILABLE",
                name="decisionv2outcomestatus",
            ),
            nullable=False,
            server_default="PENDING",
        ),
        sa.Column("entry_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("first_price_after_signal", sa.Numeric(18, 4), nullable=True),
        sa.Column("first_price_after_signal_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_1_hit", sa.Boolean(), nullable=True),
        sa.Column("target_1_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_2_hit", sa.Boolean(), nullable=True),
        sa.Column("target_2_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("target_3_hit", sa.Boolean(), nullable=True),
        sa.Column("target_3_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("stop_loss_hit", sa.Boolean(), nullable=True),
        sa.Column("stop_loss_hit_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("first_event", sa.String(length=8), nullable=True),
        sa.Column("max_favorable_excursion_pct", sa.Numeric(9, 4), nullable=True),
        sa.Column("max_adverse_excursion_pct", sa.Numeric(9, 4), nullable=True),
        sa.Column("end_of_session_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("next_session_price", sa.Numeric(18, 4), nullable=True),
        sa.Column("price_at_expected_duration", sa.Numeric(18, 4), nullable=True),
        sa.Column("return_pct_at_expected_duration", sa.Numeric(9, 4), nullable=True),
        sa.Column("return_pct", sa.Numeric(9, 4), nullable=True),
        sa.Column("time_to_target_days", sa.Integer(), nullable=True),
        sa.Column("time_to_stop_days", sa.Integer(), nullable=True),
        sa.Column("evaluated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("decision_v2_snapshot_id", name="uq_decision_v2_outcome_snapshot"),
    )
    op.create_index(
        "ix_decision_v2_outcomes_decision_v2_snapshot_id", "decision_v2_outcomes", ["decision_v2_snapshot_id"]
    )
    op.create_index(
        "ix_decision_v2_outcomes_validation_session_id", "decision_v2_outcomes", ["validation_session_id"]
    )
    op.create_index("ix_decision_v2_outcomes_symbol", "decision_v2_outcomes", ["symbol"])
    op.create_index("ix_decision_v2_outcomes_due_at", "decision_v2_outcomes", ["due_at"])
    op.create_index("ix_decision_v2_outcomes_status", "decision_v2_outcomes", ["status"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_decision_v2_outcomes_status", table_name="decision_v2_outcomes")
    op.drop_index("ix_decision_v2_outcomes_due_at", table_name="decision_v2_outcomes")
    op.drop_index("ix_decision_v2_outcomes_symbol", table_name="decision_v2_outcomes")
    op.drop_index("ix_decision_v2_outcomes_validation_session_id", table_name="decision_v2_outcomes")
    op.drop_index("ix_decision_v2_outcomes_decision_v2_snapshot_id", table_name="decision_v2_outcomes")
    op.drop_table("decision_v2_outcomes")

    with op.batch_alter_table("decision_v2_snapshots") as batch_op:
        batch_op.drop_constraint(
            "fk_decision_v2_snapshots_validation_session_id", type_="foreignkey"
        )
        batch_op.drop_index("ix_decision_v2_snapshots_validation_session_id")
        batch_op.drop_column("ranking_position")
        batch_op.drop_column("validation_session_id")

    op.drop_index("ix_validation_sessions_started_at", table_name="validation_sessions")
    op.drop_index("ix_validation_sessions_is_dry_run", table_name="validation_sessions")
    op.drop_index("ix_validation_sessions_status", table_name="validation_sessions")
    op.drop_table("validation_sessions")

    sa.Enum(name="decisionv2outcomestatus").drop(op.get_bind(), checkfirst=True)
    sa.Enum(name="validationsessionstatus").drop(op.get_bind(), checkfirst=True)
