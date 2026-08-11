"""Unit tests for src.ai_evolution.personal_performance -- CONT Phase 3's
OWNER-only performance dashboard. Constructs DecisionV2Snapshot and
RecommendationSnapshot/RecommendationOutcome rows directly (same
in-memory-sqlite pattern as test_personal_scan.py) so distribution/
hit-rate/calibration behavior can be verified precisely.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.personal_performance import compute_personal_performance_dashboard
from src.core.db.database import Base
from src.domain.models import (
    DecisionV2Snapshot,
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _make_stock(session, symbol, sector="Energy") -> Stock:
    stock = session.query(Stock).filter_by(symbol=symbol).first()
    if stock is None:
        stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
        session.add(stock)
        session.commit()
    return stock


def _add_decision_v2_snapshot(
    session, symbol, *, decision="BUY_CANDIDATE", entry_status="READY_NOW",
    market_risk_state="RISK_ON", sector_ar="الطاقة", scan_run_id=1,
):
    stock = _make_stock(session, symbol)
    session.add(
        DecisionV2Snapshot(
            stock_id=stock.id, symbol=symbol, company_name_en=f"Company {symbol}",
            decision=decision, decision_label_ar="شراء", sector_ar=sector_ar,
            confidence_score=75.0, opportunity_quality_score=70.0, risk_score=40.0,
            data_quality_score=90.0, data_freshness_status="LIVE", current_price=30.0,
            market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
            analysis_version="2.0.0", data_source="SAHMK_REAL", scan_run_id=scan_run_id,
            entry_status=entry_status, market_risk_state=market_risk_state,
        )
    )
    session.commit()


def _add_outcome(
    session, symbol, *, confidence=80.0, recommendation=RecommendationLabel.BUY,
    horizon_days=7, status=RecommendationOutcomeStatus.SUCCESSFUL, return_pct=5.0,
    hit_target=True, hit_stop=False, target_1_reached=True, target_2_reached=False,
    target_3_reached=False, mfe=6.0, mae=-1.0, sector="Energy", time_horizon="SWING",
):
    stock = _make_stock(session, symbol, sector=sector)
    snapshot = RecommendationSnapshot(
        run_id=None, stock_id=stock.id, symbol=symbol, evaluated_at=datetime.now(timezone.utc),
        recommendation=recommendation, total_score=70.0, confidence_score=confidence,
        time_horizon=time_horizon, engine_version="v2", source="live_scan", is_paper_trade=False,
    )
    session.add(snapshot)
    session.commit()

    session.add(
        RecommendationOutcome(
            snapshot_id=snapshot.id, symbol=symbol, evaluation_horizon_days=horizon_days,
            due_at=datetime.now(timezone.utc), status=status, return_pct=return_pct,
            hit_target=hit_target, hit_stop=hit_stop,
            target_1_reached=target_1_reached, target_2_reached=target_2_reached,
            target_3_reached=target_3_reached,
            max_favorable_excursion_pct=mfe, max_adverse_excursion_pct=mae,
        )
    )
    session.commit()
    return snapshot


def test_reports_insufficient_data_message_when_nothing_exists(session):
    result = compute_personal_performance_dashboard(session)

    assert result.total_decisions_issued == 0
    assert result.decision_distribution == {}
    assert result.outcome_sample_size == 0
    assert result.target_1_hit_rate is None
    assert result.insufficient_data_message_ar == "بيانات غير كافية لعرض هذا المقياس"
    assert result.strongest_groups == []
    assert result.weakest_groups == []


def test_decision_and_entry_status_distribution_from_scan_originated_snapshots_only(session):
    _add_decision_v2_snapshot(session, "1111", decision="BUY_CANDIDATE", entry_status="READY_NOW")
    _add_decision_v2_snapshot(session, "2222", decision="WATCH", entry_status="WAIT_FOR_PULLBACK")
    # scan_run_id=None: a user-triggered /decision-v2 page view, not a
    # scan -- must be excluded from the personal-product distribution.
    stock = _make_stock(session, "3333")
    session.add(
        DecisionV2Snapshot(
            stock_id=stock.id, symbol="3333", company_name_en="Company 3333", decision="HOLD",
            decision_label_ar="انتظار", confidence_score=50.0, opportunity_quality_score=50.0,
            risk_score=50.0, data_quality_score=90.0, data_freshness_status="LIVE",
            market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
            analysis_version="2.0.0", data_source="SAHMK_REAL", scan_run_id=None,
        )
    )
    session.commit()

    result = compute_personal_performance_dashboard(session)

    assert result.total_decisions_issued == 2
    assert result.decision_distribution == {"BUY_CANDIDATE": 1, "WATCH": 1}
    assert result.entry_status_distribution == {"READY_NOW": 1, "WAIT_FOR_PULLBACK": 1}


def test_target_and_stop_hit_rates_computed_from_real_outcome_flags(session):
    _add_outcome(session, "1111", target_1_reached=True, target_2_reached=True, target_3_reached=False, hit_stop=False)
    _add_outcome(session, "2222", target_1_reached=False, target_2_reached=False, target_3_reached=False, hit_stop=True)

    result = compute_personal_performance_dashboard(session, evaluation_horizon_days=7)

    assert result.outcome_sample_size == 2
    assert result.target_1_hit_rate == 50.0
    assert result.target_2_hit_rate == 50.0
    assert result.target_3_hit_rate == 0.0
    assert result.stop_loss_hit_rate == 50.0
    assert result.average_max_favorable_excursion_pct == 6.0
    assert result.average_max_adverse_excursion_pct == -1.0
    assert result.average_realized_return_pct == 5.0


def test_paper_trade_and_backtest_snapshots_are_excluded(session):
    stock = _make_stock(session, "1111")
    paper_trade_snapshot = RecommendationSnapshot(
        stock_id=stock.id, symbol="1111", evaluated_at=datetime.now(timezone.utc),
        recommendation=RecommendationLabel.BUY, total_score=70.0, confidence_score=80.0,
        engine_version="v2", source="live_scan", is_paper_trade=True,
    )
    session.add(paper_trade_snapshot)
    session.commit()
    session.add(
        RecommendationOutcome(
            snapshot_id=paper_trade_snapshot.id, symbol="1111", evaluation_horizon_days=7,
            due_at=datetime.now(timezone.utc), status=RecommendationOutcomeStatus.SUCCESSFUL,
            return_pct=5.0, hit_target=True, hit_stop=False,
        )
    )
    session.commit()

    result = compute_personal_performance_dashboard(session, evaluation_horizon_days=7)

    assert result.outcome_sample_size == 0


def test_market_risk_state_calibration_is_disclosed_as_unavailable_not_fabricated(session):
    _add_outcome(session, "1111")

    result = compute_personal_performance_dashboard(session)

    assert result.market_risk_state_calibration_unavailable_ar == (
        "بيانات غير كافية -- لا يوجد ربط بين حالة مخاطر السوق وتتبع نتائج التوصيات حالياً"
    )


def test_strongest_and_weakest_groups_require_minimum_sample_size(session):
    for i in range(15):
        _add_outcome(
            session, f"11{i:02d}", sector="Energy", return_pct=5.0, hit_target=True, hit_stop=False,
            recommendation=RecommendationLabel.BUY,
        )
    for i in range(5):
        _add_outcome(
            session, f"22{i:02d}", sector="Banking", return_pct=-5.0, hit_target=False, hit_stop=True,
            recommendation=RecommendationLabel.SELL,
        )

    result = compute_personal_performance_dashboard(session)

    # Banking has only 5 samples (< _MIN_GROUP_SAMPLE_SIZE=10) -- must
    # not appear in strongest/weakest at all, never shown as if reliable.
    groups_seen = {g.group for g in result.strongest_groups + result.weakest_groups}
    assert "Banking" not in groups_seen
    assert "Energy" in groups_seen
