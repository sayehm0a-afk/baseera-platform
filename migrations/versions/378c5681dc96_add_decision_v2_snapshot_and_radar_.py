"""add_decision_v2_snapshot_and_radar_performance_indexes

2026-09-19 performance audit: two confirmed missing-index gaps.

`decision_v2_snapshots` is insert-only and unbounded-growth (the same
symbol/stock can be decided many times a day), and the dominant query
pattern across this codebase is "latest snapshot for symbol/stock_id X"
(`filter(...).order_by(decision_timestamp.desc())`), or the batched
"latest per stock_id across N rows" window-function lookup
(`stock_id.in_(...)` + `row_number() OVER (PARTITION BY ... ORDER BY
decision_timestamp DESC)`) used by `src.api.routes.portfolio`/`stocks`/
`watchlist`. The table already has separate single-column indexes on
`symbol`, `stock_id`, and `decision_timestamp`, but Postgres cannot
satisfy an equality filter *and* an ORDER BY from two separate
single-column indexes in one index scan -- both composite indexes
below match a real, confirmed hot-path filter+sort shape.

`radar_opportunities.stage1_ranking_score` is the sort key for the
live radar list (`order_by(stage1_ranking_score.desc().nullslast())`
in `src.market_intelligence.radar_v2.list_live_opportunities`) but had
no index at all.

Revision ID: 378c5681dc96
Revises: 89715dffe0b2
Create Date: 2026-09-19 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "378c5681dc96"
down_revision: Union[str, Sequence[str], None] = "89715dffe0b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_index(
        op.f("ix_decision_v2_snapshots_symbol_decision_timestamp"),
        "decision_v2_snapshots",
        ["symbol", "decision_timestamp"],
    )
    op.create_index(
        op.f("ix_decision_v2_snapshots_stock_id_decision_timestamp"),
        "decision_v2_snapshots",
        ["stock_id", "decision_timestamp"],
    )
    op.create_index(
        op.f("ix_radar_opportunities_stage1_ranking_score"),
        "radar_opportunities",
        ["stage1_ranking_score"],
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(op.f("ix_radar_opportunities_stage1_ranking_score"), table_name="radar_opportunities")
    op.drop_index(
        op.f("ix_decision_v2_snapshots_stock_id_decision_timestamp"), table_name="decision_v2_snapshots"
    )
    op.drop_index(
        op.f("ix_decision_v2_snapshots_symbol_decision_timestamp"), table_name="decision_v2_snapshots"
    )
