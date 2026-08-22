"""add_arabic_presentation_fields_notifications_alerts

Pre-launch product safety fixes (Priority 2, Arabic-Only UX, 2026-08-22):
adds nullable Arabic presentation companions to already-persisted English
text -- `notifications.title_ar`/`body_ar`, `portfolio_news_alerts.
message_ar`, `watchlist_news_alerts.message_ar`. Every column is nullable
so existing rows written before this migration still read back cleanly
(the frontend falls back to the English field when the Arabic one is
NULL). No decision/classification logic changes; this is presentation
data only.

Revision ID: a1b2c3d4e5f6
Revises: 4611f0194370
Create Date: 2026-08-22 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "4611f0194370"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    with op.batch_alter_table("notifications") as batch_op:
        batch_op.add_column(sa.Column("title_ar", sa.String(length=255), nullable=True))
        batch_op.add_column(sa.Column("body_ar", sa.Text(), nullable=True))

    with op.batch_alter_table("portfolio_news_alerts") as batch_op:
        batch_op.add_column(sa.Column("message_ar", sa.Text(), nullable=True))

    with op.batch_alter_table("watchlist_news_alerts") as batch_op:
        batch_op.add_column(sa.Column("message_ar", sa.Text(), nullable=True))


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("watchlist_news_alerts") as batch_op:
        batch_op.drop_column("message_ar")

    with op.batch_alter_table("portfolio_news_alerts") as batch_op:
        batch_op.drop_column("message_ar")

    with op.batch_alter_table("notifications") as batch_op:
        batch_op.drop_column("body_ar")
        batch_op.drop_column("title_ar")
