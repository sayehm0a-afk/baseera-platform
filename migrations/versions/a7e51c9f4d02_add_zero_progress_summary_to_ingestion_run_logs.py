"""add zero_progress_summary to ingestion_run_logs

Revision ID: a7e51c9f4d02
Revises: d4f8c2a19e6b
Create Date: 2026-08-08 20:10:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "a7e51c9f4d02"
down_revision = "d4f8c2a19e6b"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ingestion_run_logs", sa.Column("zero_progress_summary", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("ingestion_run_logs", "zero_progress_summary")
