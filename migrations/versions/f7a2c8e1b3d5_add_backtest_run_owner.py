"""add_backtest_run_owner

2026-09-16 audit finding: BacktestRun had no owner column at all, so
any active-subscription customer could view or cooperatively-cancel
any other customer's backtest run just by guessing/incrementing
run_id (src/api/routes/backtests.py). Purely additive: adds a
nullable created_by_user_id, SET NULL on user deletion (a backtest's
computed result is a durable historical record, not personal data
that should vanish with the account -- the same reasoning as
decision_v2_snapshots.requested_by_user_id). Every run created before
this migration has NULL here and becomes staff-only visible, never
silently attributed to any user.

Also re-scopes idempotency_key's uniqueness from globally-unique to
unique per (idempotency_key, created_by_user_id): under the old global
constraint, a second user submitting the identical configuration
transparently received the first user's run id, which the new
per-run ownership check would then 404 on a later GET -- inconsistent
and confusing. Existing rows keep their (now-NULL-owner) key as-is;
no two pre-migration rows can collide since idempotency_key was
already globally unique before this.

Revision ID: f7a2c8e1b3d5
Revises: 6c50a61c602f
Create Date: 2026-09-16 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "f7a2c8e1b3d5"
down_revision: Union[str, Sequence[str], None] = "6c50a61c602f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column("backtest_runs", sa.Column("created_by_user_id", sa.Integer(), nullable=True))
    op.create_index(
        "ix_backtest_runs_created_by_user_id", "backtest_runs", ["created_by_user_id"]
    )
    op.create_foreign_key(
        "fk_backtest_runs_created_by_user_id_users",
        "backtest_runs", "users",
        ["created_by_user_id"], ["id"],
        ondelete="SET NULL",
    )

    op.drop_index("ix_backtest_runs_idempotency_key", table_name="backtest_runs")
    op.create_index("ix_backtest_runs_idempotency_key", "backtest_runs", ["idempotency_key"])
    op.create_unique_constraint(
        "uq_backtest_runs_idempotency_key_created_by_user_id",
        "backtest_runs",
        ["idempotency_key", "created_by_user_id"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint(
        "uq_backtest_runs_idempotency_key_created_by_user_id", "backtest_runs", type_="unique"
    )
    op.drop_index("ix_backtest_runs_idempotency_key", table_name="backtest_runs")
    op.create_index(
        "ix_backtest_runs_idempotency_key", "backtest_runs", ["idempotency_key"], unique=True
    )

    op.drop_constraint("fk_backtest_runs_created_by_user_id_users", "backtest_runs", type_="foreignkey")
    op.drop_index("ix_backtest_runs_created_by_user_id", table_name="backtest_runs")
    op.drop_column("backtest_runs", "created_by_user_id")
