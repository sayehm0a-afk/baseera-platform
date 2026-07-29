"""add_missing_fk_indexes

Phase 3 of the production-readiness pass: a structural database audit
found 4 foreign-key columns with no supporting index -- a real,
confirmed gap (checked directly against pg_index), not a guess.
Unindexed FKs mean any join/filter on these columns, and any
ON DELETE CASCADE/SET NULL fired from the referenced table, does a
sequential scan instead of an index lookup. All four are additive,
zero-risk, standard B-tree indexes.

Revision ID: c2d7e5a93f16
Revises: a8e2f4c91d37
Create Date: 2026-07-29 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "c2d7e5a93f16"
down_revision: Union[str, Sequence[str], None] = "a8e2f4c91d37"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        op.f("ix_announcements_created_by_user_id"), "announcements", ["created_by_user_id"]
    )
    op.create_index(
        op.f("ix_support_tickets_assigned_staff_user_id"), "support_tickets", ["assigned_staff_user_id"]
    )
    op.create_index(
        op.f("ix_calibration_configs_training_run_id"), "calibration_configs", ["training_run_id"]
    )
    op.create_index(
        op.f("ix_calibration_configs_validation_run_id"), "calibration_configs", ["validation_run_id"]
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_calibration_configs_validation_run_id"), table_name="calibration_configs")
    op.drop_index(op.f("ix_calibration_configs_training_run_id"), table_name="calibration_configs")
    op.drop_index(op.f("ix_support_tickets_assigned_staff_user_id"), table_name="support_tickets")
    op.drop_index(op.f("ix_announcements_created_by_user_id"), table_name="announcements")
