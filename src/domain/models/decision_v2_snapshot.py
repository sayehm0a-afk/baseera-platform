"""Insert-only audit record of one Decision Engine V2 result
(`src.analysis.decision_v2.types.DecisionResult`) -- written best-effort
every time `GET /api/v1/stocks/{symbol}/decision-v2` computes a real
decision, so every Arabic-labeled action Basirah ever showed a user can
be reproduced and reviewed later.

Deliberately a new, separate table rather than an extension of
`RecommendationSnapshot`: that table's identity is defined by
`(run_id, stock_id, evaluated_at)` and is tightly coupled to
`BacktestRun` (`run_id` is a real FK, and the whole row shape --
target_price/stop_loss/single confidence score -- mirrors the older,
single-point `InvestmentDecision`, not Decision V2's entry zone/three
targets/eight sub-scores/gate list). Reusing it would mean either
bending that identity/FK relationship to fit a non-backtest,
non-single-point shape, or leaving most of its columns permanently
null for every Decision V2 row -- both worse than a purpose-built
table. Follows the same domain-layer-has-no-src.analysis-dependency
rule `recommendation_snapshot.py` documents: `decision`/
`data_freshness_status` are plain strings here, not imports of
`src.analysis.decision_v2.types.Decision`/`DataFreshnessStatus`.

No unique constraint: unlike `RecommendationSnapshot` (one row per
backtest-run/symbol/date, upserted on re-run), this table is a pure
insert-only request log -- the same symbol can legitimately be decided
many times a day as users open its analysis page, and every one of
those decisions is real evidence worth keeping, not a duplicate to
collapse. Matches the append-only policy the AI Evolution Layer
design already established for `recommendation_snapshots`/
`recommendation_outcomes`/`agent_opinions`: no UPDATE, no DELETE from
application code.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class DecisionV2Snapshot(Base):
    __tablename__ = "decision_v2_snapshots"

    id = Column(Integer, primary_key=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)
    symbol = Column(String(16), nullable=False, index=True)

    company_name_ar = Column(String(255), nullable=True)
    company_name_en = Column(String(255), nullable=False)
    sector_ar = Column(String(128), nullable=True)

    decision = Column(String(32), nullable=False, index=True)
    decision_label_ar = Column(String(64), nullable=False)

    confidence_score = Column(Numeric(6, 2), nullable=False)
    opportunity_quality_score = Column(Numeric(6, 2), nullable=False)
    risk_score = Column(Numeric(6, 2), nullable=False)
    data_quality_score = Column(Numeric(6, 2), nullable=False)
    data_freshness_status = Column(String(16), nullable=False)

    current_price = Column(Numeric(18, 4), nullable=True)
    entry_zone_low = Column(Numeric(18, 4), nullable=True)
    entry_zone_high = Column(Numeric(18, 4), nullable=True)
    stop_loss = Column(Numeric(18, 4), nullable=True)
    target_1 = Column(Numeric(18, 4), nullable=True)
    target_2 = Column(Numeric(18, 4), nullable=True)
    target_3 = Column(Numeric(18, 4), nullable=True)

    expected_return_target_1 = Column(Numeric(9, 4), nullable=True)
    expected_return_target_2 = Column(Numeric(9, 4), nullable=True)
    downside_to_stop = Column(Numeric(9, 4), nullable=True)
    risk_reward_target_1 = Column(Numeric(9, 4), nullable=True)
    risk_reward_target_2 = Column(Numeric(9, 4), nullable=True)

    expected_holding_period_min_days = Column(Integer, nullable=True)
    expected_holding_period_max_days = Column(Integer, nullable=True)
    expected_holding_period_label_ar = Column(String(64), nullable=True)
    horizon_type = Column(String(16), nullable=True)

    market_status = Column(String(32), nullable=False)
    decision_timestamp = Column(DateTime(timezone=True), nullable=False, index=True)

    invalidation_conditions = Column(JSON, nullable=True)
    positive_reasons = Column(JSON, nullable=True)
    negative_reasons = Column(JSON, nullable=True)
    warnings = Column(JSON, nullable=True)
    recommendation_basis = Column(String(2000), nullable=True)

    # Full structured evidence -- every sub-score and every gate's
    # PASS/FAIL/detail/blocking record, exactly as shown to the user.
    # The five named score columns above are a query convenience;
    # these two JSON blobs are the complete, reproducible record.
    sub_scores = Column(JSON, nullable=True)
    gates = Column(JSON, nullable=True)

    analysis_version = Column(String(32), nullable=False)
    data_source = Column(String(32), nullable=False)
    is_synthetic = Column(Boolean, nullable=True)
    scan_run_id = Column(Integer, nullable=True)

    requested_by_user_id = Column(Integer, ForeignKey("users.id"), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    stock = relationship("Stock")

    def __repr__(self) -> str:
        return (
            f"<DecisionV2Snapshot symbol={self.symbol!r} decision={self.decision!r} "
            f"decision_timestamp={self.decision_timestamp!r}>"
        )
