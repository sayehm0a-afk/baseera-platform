"""add_user_deletion_fk_policies

Revision ID: c4d8e6f19a2b
Revises: a3f7c9e21b04
Create Date: 2026-07-27 00:00:00.000000

Phase 13 P13.6 (database & customer data protection): before this
migration, every foreign key referencing `users.id` (except
`user_sessions`/`subscriptions`, cascaded at the ORM level by
`User.sessions`/`User.subscription`) had no `ON DELETE` clause at all,
which Postgres treats as `NO ACTION` -- functionally identical to
`RESTRICT`. That is the *correct* default for financial/audit records
(`invoices.user_id`, `audit_logs.actor_user_id`, both left untouched
here), but it meant `AuthRepository.delete_user()` -- including the new
self-service `DELETE /api/v1/auth/me` -- would fail for almost any
account that had ever actually used the product (a portfolio, a
watchlist, a single notification, one AI-generated recommendation was
enough to block deletion outright).

This migration assigns a deliberate policy per data category instead
of leaving every table on the same implicit default:

- CASCADE: purely personal, no independent retention value once the
  owning user is gone -- notifications, watchlists (+ their items),
  settings, recommendation-view history, generated report requests,
  and virtual portfolios (+ their holdings/analysis snapshots/news
  alerts, cascaded a second level from the portfolio).
- SET NULL: the row has value independent of who the user was
  (aggregate AI cost/usage accounting, product feedback content, a
  support conversation's substance) -- `ai_requests.user_id`,
  `feedback.user_id`, `support_tickets.user_id` (newly made nullable
  here -- it previously required a user), and
  `support_tickets.assigned_staff_user_id` (nulls out if the *staff*
  member's own account is ever deleted, independent of this feature).
- Left as NO ACTION / RESTRICT (unchanged, no action needed):
  `invoices.user_id`, `audit_logs.actor_user_id` -- financial and
  security-audit records must never be silently discarded or
  anonymized away; deleting an account with either blocks the delete,
  exactly as already tested in
  test_admin_routes.py::test_owner_cannot_delete_a_user_with_non_cascading_related_records.

See docs/DATABASE_SECURITY_AND_RETENTION.md and
docs/ACCOUNT_DELETION_AND_EXPORT.md for the full policy writeup.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "c4d8e6f19a2b"
down_revision: Union[str, Sequence[str], None] = "a3f7c9e21b04"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, constraint_name, column, ref_table)
_CASCADE_FKS = [
    ("notifications", "notifications_user_id_fkey", "user_id", "users"),
    ("user_watchlists", "user_watchlists_user_id_fkey", "user_id", "users"),
    ("user_watchlist_items", "user_watchlist_items_watchlist_id_fkey", "watchlist_id", "user_watchlists"),
    ("user_settings", "user_settings_user_id_fkey", "user_id", "users"),
    ("recommendation_history", "recommendation_history_user_id_fkey", "user_id", "users"),
    ("reports", "reports_user_id_fkey", "user_id", "users"),
    ("portfolios", "fk_portfolios_user_id_users", "user_id", "users"),
    ("portfolio_holdings", "portfolio_holdings_portfolio_id_fkey", "portfolio_id", "portfolios"),
    ("portfolio_analysis_snapshots", "portfolio_analysis_snapshots_portfolio_id_fkey", "portfolio_id", "portfolios"),
    ("portfolio_news_alerts", "portfolio_news_alerts_portfolio_id_fkey", "portfolio_id", "portfolios"),
]

_SET_NULL_FKS = [
    ("ai_requests", "ai_requests_user_id_fkey", "user_id", "users"),
    ("feedback", "feedback_user_id_fkey", "user_id", "users"),
    ("support_tickets", "support_tickets_user_id_fkey", "user_id", "users"),
    ("support_tickets", "support_tickets_assigned_staff_user_id_fkey", "assigned_staff_user_id", "users"),
]


def _is_sqlite() -> bool:
    """Postgres auto-names an unnamed FK constraint `<table>_<column>_fkey`
    at the server level, so `drop_constraint(name)` finds it. SQLite does
    not -- a `Column(ForeignKey(...))` with no explicit name is truly
    anonymous in SQLite's own schema, so batch mode's reflection can
    never find it by the Postgres-convention name this migration uses.
    SQLite here exists only for `tests/integration/test_migrations.py`'s
    fast structural smoke test (table/column shape, chain integrity) --
    it never runs in production and that test never asserts FK ondelete
    behavior -- so on SQLite this migration adds the new, correctly
    configured constraint without first dropping the old anonymous one
    (harmless duplicate FK, SQLite-only); on Postgres (the only engine
    this behavior actually matters on) it does the full drop-and-recreate
    verified against a real Postgres 16 instance during development."""
    return op.get_bind().dialect.name == "sqlite"


def upgrade() -> None:
    """Upgrade schema."""
    # support_tickets.user_id must become nullable before it can be
    # ON DELETE SET NULL -- a NOT NULL column can never be nulled.
    with op.batch_alter_table("support_tickets") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=True, existing_nullable=False)

    sqlite = _is_sqlite()
    for table, constraint, column, ref_table in _CASCADE_FKS:
        with op.batch_alter_table(table) as batch_op:
            if not sqlite:
                batch_op.drop_constraint(constraint, type_="foreignkey")
            batch_op.create_foreign_key(constraint, ref_table, [column], ["id"], ondelete="CASCADE")

    for table, constraint, column, ref_table in _SET_NULL_FKS:
        with op.batch_alter_table(table) as batch_op:
            if not sqlite:
                batch_op.drop_constraint(constraint, type_="foreignkey")
            batch_op.create_foreign_key(constraint, ref_table, [column], ["id"], ondelete="SET NULL")


def downgrade() -> None:
    """Downgrade schema."""
    sqlite = _is_sqlite()
    for table, constraint, column, ref_table in _SET_NULL_FKS:
        with op.batch_alter_table(table) as batch_op:
            if not sqlite:
                batch_op.drop_constraint(constraint, type_="foreignkey")
                batch_op.create_foreign_key(constraint, ref_table, [column], ["id"])

    for table, constraint, column, ref_table in reversed(_CASCADE_FKS):
        with op.batch_alter_table(table) as batch_op:
            if not sqlite:
                batch_op.drop_constraint(constraint, type_="foreignkey")
                batch_op.create_foreign_key(constraint, ref_table, [column], ["id"])

    with op.batch_alter_table("support_tickets") as batch_op:
        batch_op.alter_column("user_id", existing_type=sa.Integer(), nullable=False, existing_nullable=True)
