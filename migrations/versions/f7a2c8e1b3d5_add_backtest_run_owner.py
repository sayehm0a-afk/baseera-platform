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

batch_alter_table throughout (not plain op.add_column/op.create_
foreign_key/op.create_unique_constraint): SQLite has no ALTER TABLE
ADD CONSTRAINT, used by tests/integration/test_migrations.py's
SQLite-based full chain replay -- batch mode falls back to its
copy-and-move strategy there while emitting plain ALTER TABLE on
Postgres (the same pattern already established in
21250b80c56f_add_user_id_to_portfolios.py and
c4d8e6f21b3d_add_user_deletion_fk_policies.py).

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
    with op.batch_alter_table("backtest_runs") as batch_op:
        batch_op.add_column(sa.Column("created_by_user_id", sa.Integer(), nullable=True))
        batch_op.create_index("ix_backtest_runs_created_by_user_id", ["created_by_user_id"])
        batch_op.create_foreign_key(
            "fk_backtest_runs_created_by_user_id_users",
            "users", ["created_by_user_id"], ["id"], ondelete="SET NULL",
        )
        batch_op.drop_index("ix_backtest_runs_idempotency_key")
        batch_op.create_index("ix_backtest_runs_idempotency_key", ["idempotency_key"])
        batch_op.create_unique_constraint(
            "uq_backtest_runs_idempotency_key_created_by_user_id",
            ["idempotency_key", "created_by_user_id"],
        )


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("backtest_runs") as batch_op:
        batch_op.drop_constraint("uq_backtest_runs_idempotency_key_created_by_user_id", type_="unique")
        batch_op.drop_index("ix_backtest_runs_idempotency_key")
        batch_op.create_index("ix_backtest_runs_idempotency_key", ["idempotency_key"], unique=True)

        batch_op.drop_constraint("fk_backtest_runs_created_by_user_id_users", type_="foreignkey")
        batch_op.drop_index("ix_backtest_runs_created_by_user_id")
        batch_op.drop_column("created_by_user_id")
