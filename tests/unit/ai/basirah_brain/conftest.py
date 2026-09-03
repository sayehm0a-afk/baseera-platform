from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.analysis.decision_v2.types import (
    DataFreshnessStatus,
    Decision,
    DecisionResult,
    GateOutcome,
    GateStatus,
    SubScores,
)
from src.core.db.database import Base
from src.domain.models import Stock


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def session_factory(session):
    # Tests share one physical in-memory SQLite connection (StaticPool)
    # across "sessions" so a fresh Session() per service call still sees
    # the same schema/data -- matches this repo's existing unit-test
    # discipline for in-memory SQLite (see test_decision_v2_outcome.py).
    def factory():
        return sessionmaker(bind=session.get_bind())()

    return factory


@pytest.fixture
def stock(session):
    row = Stock(symbol="1213", name_en="Test Co", name_ar="شركة تجريبية", sector="Materials")
    session.add(row)
    session.commit()
    return row


_DEFAULT_SUB_SCORES = SubScores(
    trend_score=70.0,
    momentum_score=60.0,
    volume_score=55.0,
    liquidity_score=80.0,
    volatility_score=65.0,
    risk_reward_score=72.0,
    market_context_score=58.0,
    data_quality_score=90.0,
)


def make_decision_result(
    symbol: str = "1213",
    decision: Decision = Decision.BUY_CANDIDATE,
    confidence_score: float = 68.0,
    data_freshness_status: DataFreshnessStatus = DataFreshnessStatus.LIVE,
    is_real_data: bool = True,
    entry_zone_low: float = 98.0,
    entry_zone_high: float = 101.0,
    stop_loss: float = 93.0,
    target_1: float = 108.0,
    target_2: float = 115.0,
    target_3: float = 122.0,
    liquidity_quality_ar: str = "جيدة",
    gates=None,
    negative_reasons=None,
    invalidation_conditions=None,
    sub_scores: SubScores = None,
) -> DecisionResult:
    return DecisionResult(
        symbol=symbol,
        company_name_ar="شركة تجريبية",
        company_name_en="Test Co",
        sector_ar="المواد الأساسية",
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=confidence_score,
        opportunity_quality_score=66.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status=data_freshness_status,
        current_price=100.0,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        stop_loss=stop_loss,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        expected_return_target_1=8.0,
        expected_return_target_2=15.0,
        downside_to_stop=-7.0,
        risk_reward_target_1=1.6,
        risk_reward_target_2=2.5,
        expected_holding_period_min_days=10,
        expected_holding_period_max_days=30,
        expected_holding_period_label_ar="قصير إلى متوسط",
        horizon_type="SHORT_TERM",
        market_status="OPEN",
        decision_timestamp=datetime(2026, 9, 3, tzinfo=timezone.utc),
        invalidation_conditions=invalidation_conditions or [],
        positive_reasons=["اتجاه صاعد"],
        negative_reasons=negative_reasons or [],
        warnings=[],
        recommendation_basis="بناءً على المؤشرات الفنية",
        analysis_version="2.0",
        data_source="SAHMK_REAL",
        scan_run_id=None,
        sub_scores=sub_scores or _DEFAULT_SUB_SCORES,
        gates=gates or [GateOutcome(name="liquidity", status=GateStatus.PASS, detail="ok", blocking=True)],
        is_real_data=is_real_data,
        liquidity_quality_ar=liquidity_quality_ar,
    )
