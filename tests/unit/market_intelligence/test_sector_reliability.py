"""Unit tests for src.market_intelligence.sector_reliability -- the
real, per-sector historical win-rate disclosure shown on the personal
"أفضل فرص المضاربة الآن" screen. Same in-memory-sqlite construction
pattern as test_personal_performance.py, since both modules read the
exact same RecommendationOutcome/RecommendationSnapshot/Stock tables.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import RecommendationLabel, RecommendationOutcome, RecommendationOutcomeStatus, RecommendationSnapshot, Stock
from src.market_intelligence.sector_reliability import (
    RELIABILITY_HIGH,
    RELIABILITY_INSUFFICIENT_DATA,
    RELIABILITY_LOW,
    RELIABILITY_MODERATE,
    compute_sector_reliability_by_arabic_label,
    reliability_for_sector,
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


def _make_stock(session, symbol, sector) -> Stock:
    stock = session.query(Stock).filter_by(symbol=symbol).first()
    if stock is None:
        stock = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector=sector)
        session.add(stock)
        session.commit()
    return stock


def _add_outcome(session, symbol, *, sector, status, horizon_days=3):
    stock = _make_stock(session, symbol, sector)
    snapshot = RecommendationSnapshot(
        stock_id=stock.id, symbol=symbol, evaluated_at=datetime.now(timezone.utc),
        recommendation=RecommendationLabel.BUY, total_score=70.0, confidence_score=75.0,
        engine_version="v2", source="live_scan", is_paper_trade=False,
    )
    session.add(snapshot)
    session.commit()
    session.add(
        RecommendationOutcome(
            snapshot_id=snapshot.id, symbol=symbol, evaluation_horizon_days=horizon_days,
            due_at=datetime.now(timezone.utc), status=status,
            return_pct=5.0 if status == RecommendationOutcomeStatus.SUCCESSFUL else -3.0,
            hit_target=status == RecommendationOutcomeStatus.SUCCESSFUL,
            hit_stop=status == RecommendationOutcomeStatus.FAILED,
        )
    )
    session.commit()


def _fill_sector(session, sector, symbol_prefix, wins, losses, horizon_days=3):
    for i in range(wins):
        _add_outcome(session, f"{symbol_prefix}W{i}", sector=sector, status=RecommendationOutcomeStatus.SUCCESSFUL, horizon_days=horizon_days)
    for i in range(losses):
        _add_outcome(session, f"{symbol_prefix}L{i}", sector=sector, status=RecommendationOutcomeStatus.FAILED, horizon_days=horizon_days)


def test_empty_database_returns_empty_map(session):
    result = compute_sector_reliability_by_arabic_label(session)
    assert result == {}


def test_high_reliability_sector_classified_correctly(session):
    # 9 wins / 1 loss = 90% win rate, n=10 (>= MIN_GROUP_SAMPLE_SIZE)
    _fill_sector(session, "Banks", "B", wins=9, losses=1)

    result = compute_sector_reliability_by_arabic_label(session, evaluation_horizon_days=3)

    reliability = result["البنوك"]
    assert reliability.level == RELIABILITY_HIGH
    assert reliability.win_rate_pct == 90.0
    assert reliability.sample_size == 10


def test_low_reliability_sector_classified_correctly(session):
    # 1 win / 9 losses = 10% win rate, n=10
    _fill_sector(session, "Energy", "E", wins=1, losses=9)

    result = compute_sector_reliability_by_arabic_label(session, evaluation_horizon_days=3)

    reliability = result["الطاقة"]
    assert reliability.level == RELIABILITY_LOW
    assert reliability.win_rate_pct == 10.0
    assert reliability.sample_size == 10


def test_moderate_reliability_sector_classified_correctly(session):
    # 5 wins / 5 losses = 50% win rate, n=10 -- between the two cutoffs
    _fill_sector(session, "Materials", "M", wins=5, losses=5)

    result = compute_sector_reliability_by_arabic_label(session, evaluation_horizon_days=3)

    reliability = result["المواد الأساسية"]
    assert reliability.level == RELIABILITY_MODERATE
    assert reliability.win_rate_pct == 50.0


def test_small_sample_sector_is_disclosed_as_insufficient_not_a_fabricated_rate(session):
    # Only 5 outcomes, all wins -- would look like 100% but the real
    # sample is too small to mean anything (MIN_GROUP_SAMPLE_SIZE=10).
    _fill_sector(session, "Utilities", "U", wins=5, losses=0)

    result = compute_sector_reliability_by_arabic_label(session, evaluation_horizon_days=3)

    reliability = result["المرافق العامة"]
    assert reliability.level == RELIABILITY_INSUFFICIENT_DATA
    assert reliability.win_rate_pct is None
    assert reliability.sample_size == 5


def test_wrong_evaluation_horizon_days_does_not_match(session):
    _fill_sector(session, "Banks", "B", wins=9, losses=1, horizon_days=7)

    # This module's own default horizon (3 days) does not match the
    # 7-day outcomes seeded above -- must not accidentally borrow them.
    result = compute_sector_reliability_by_arabic_label(session)

    assert result == {}


def test_reliability_for_sector_falls_back_to_insufficient_data_for_unknown_or_none_sector(session):
    _fill_sector(session, "Banks", "B", wins=9, losses=1)
    reliability_map = compute_sector_reliability_by_arabic_label(session, evaluation_horizon_days=3)

    assert reliability_for_sector(reliability_map, None).level == RELIABILITY_INSUFFICIENT_DATA
    assert reliability_for_sector(reliability_map, "قطاع غير موجود").level == RELIABILITY_INSUFFICIENT_DATA
    assert reliability_for_sector(reliability_map, "البنوك").level == RELIABILITY_HIGH


def test_paper_trades_and_backtest_snapshots_are_excluded(session):
    stock = _make_stock(session, "9999", "Banks")
    paper_trade_snapshot = RecommendationSnapshot(
        stock_id=stock.id, symbol="9999", evaluated_at=datetime.now(timezone.utc),
        recommendation=RecommendationLabel.BUY, total_score=70.0, confidence_score=80.0,
        engine_version="v2", source="live_scan", is_paper_trade=True,
    )
    session.add(paper_trade_snapshot)
    session.commit()
    session.add(
        RecommendationOutcome(
            snapshot_id=paper_trade_snapshot.id, symbol="9999", evaluation_horizon_days=3,
            due_at=datetime.now(timezone.utc), status=RecommendationOutcomeStatus.SUCCESSFUL,
            return_pct=5.0, hit_target=True, hit_stop=False,
        )
    )
    session.commit()

    result = compute_sector_reliability_by_arabic_label(session, evaluation_horizon_days=3)

    assert result == {}
