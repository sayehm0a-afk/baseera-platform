"""add_user_id_to_portfolios

Revision ID: 21250b80c56f
Revises: 11c293dc10f5
Create Date: 2026-07-25 19:38:11.762696

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "21250b80c56f"
down_revision: Union[str, Sequence[str], None] = "11c293dc10f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    # batch_alter_table: SQLite has no ALTER TABLE ADD CONSTRAINT (used
    # by tests/integration/test_migrations.py's SQLite-based chain
    # replay) -- batch mode falls back to its copy-and-move strategy
    # there while emitting plain ALTER TABLE on Postgres.
    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.add_column(sa.Column("user_id", sa.Integer(), nullable=True))
        batch_op.create_index(op.f("ix_portfolios_user_id"), ["user_id"], unique=False)
        batch_op.create_foreign_key("fk_portfolios_user_id_users", "users", ["user_id"], ["id"])


def downgrade() -> None:
    """Downgrade schema."""
    with op.batch_alter_table("portfolios") as batch_op:
        batch_op.drop_constraint("fk_portfolios_user_id_users", type_="foreignkey")
        batch_op.drop_index(op.f("ix_portfolios_user_id"))
        batch_op.drop_column("user_id")
