"""Unit tests for E5's pattern discovery -- real SQLAlchemy ORM
against an in-memory SQLite DB.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.pattern_discovery import discover_patterns, proportion_significance_test
from src.core.db.database import Base
from src.domain.models import (
    DiscoveredPattern,
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


@pytest.fixture
def stock(session):
    row = Stock(symbol="2222", name_en="Stock 2222", sector="Energy")
    session.add(row)
    session.commit()
    return row


def _seed(session, stock, day_offset, success, signal_names, horizon_days=7):
    evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)
    signals = [
        {"name": name, "description": name, "direction": "bullish", "source": "technical", "impact": 1.0}
        for name in signal_names
    ]
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        evaluated_at=evaluated_at,
        market_price_at_evaluation=100.0,
        recommendation=RecommendationLabel.BUY,
        total_score=60.0,
        confidence_score=70.0,
        signals=signals,
        engine_version="1.0.0",
        source="live_scan",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        RecommendationOutcome(
            snapshot_id=snapshot.id,
            symbol=stock.symbol,
            evaluation_horizon_days=horizon_days,
            due_at=evaluated_at + timedelta(days=horizon_days),
            status=RecommendationOutcomeStatus.SUCCESSFUL if success else RecommendationOutcomeStatus.FAILED,
            evaluated_at=evaluated_at + timedelta(days=horizon_days),
        )
    )


class TestProportionSignificanceTest:
    def test_none_when_sample_too_small(self):
        result = proportion_significance_test(successes=1, sample_size=1, baseline_rate=0.5)
        assert result.significant is False
        assert result.z_score is None

    def test_significant_when_far_from_baseline_with_enough_samples(self):
        # 90% success rate vs. a 50% baseline, n=100 -- an obvious, large effect.
        result = proportion_significance_test(successes=90, sample_size=100, baseline_rate=0.5, min_sample_size=30)
        assert result.significant is True
        assert result.observed_rate == pytest.approx(0.9)
        assert result.p_value < 0.05

    def test_not_significant_when_close_to_baseline(self):
        result = proportion_significance_test(successes=51, sample_size=100, baseline_rate=0.5, min_sample_size=30)
        assert result.significant is False

    def test_not_significant_below_min_sample_size_even_if_p_value_is_low(self):
        # A large observed gap but too few samples -- must not be significant.
        result = proportion_significance_test(successes=10, sample_size=10, baseline_rate=0.5, min_sample_size=30)
        assert result.significant is False


class TestDiscoverPatterns:
    def test_discovers_a_signal_with_a_significantly_higher_win_rate(self, session, stock):
        # "GoldenCross" always wins (20/20); baseline population win rate is ~50%.
        for i in range(20):
            _seed(session, stock, day_offset=i, success=True, signal_names=["GoldenCross"])
        for i in range(20, 40):
            _seed(session, stock, day_offset=i, success=False, signal_names=["Unrelated"])
        session.commit()

        patterns = discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)

        names = {p.condition_description for p in patterns}
        assert "GoldenCross" in names
        golden = next(p for p in patterns if p.condition_description == "GoldenCross")
        assert golden.condition_type == "signal_present"
        assert golden.still_valid is True
        assert float(golden.win_rate) == pytest.approx(1.0)
        assert golden.sample_size == 20

    def test_does_not_discover_a_signal_with_ordinary_win_rate(self, session, stock):
        for i in range(30):
            _seed(session, stock, day_offset=i, success=(i % 2 == 0), signal_names=["Ordinary"])
        session.commit()

        patterns = discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)
        assert "Ordinary" not in {p.condition_description for p in patterns}

    def test_signal_below_min_sample_size_is_skipped(self, session, stock):
        for i in range(5):
            _seed(session, stock, day_offset=i, success=True, signal_names=["RareSignal"])
        session.commit()

        patterns = discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)
        assert "RareSignal" not in {p.condition_description for p in patterns}

    def test_rerunning_updates_the_existing_row_instead_of_duplicating(self, session, stock):
        for i in range(20):
            _seed(session, stock, day_offset=i, success=True, signal_names=["GoldenCross"])
        for i in range(20, 40):
            _seed(session, stock, day_offset=i, success=False, signal_names=["Unrelated"])
        session.commit()

        discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)
        discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)

        rows = session.query(DiscoveredPattern).filter_by(condition_description="GoldenCross").all()
        assert len(rows) == 1

    def test_a_pattern_that_stops_being_significant_is_marked_invalid_not_deleted(self, session, stock):
        for i in range(20):
            _seed(session, stock, day_offset=i, success=True, signal_names=["GoldenCross"])
        for i in range(20, 40):
            _seed(session, stock, day_offset=i, success=False, signal_names=["Unrelated"])
        session.commit()
        discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)

        # Now flood in 200 ordinary (50/50) GoldenCross calls -- both its
        # own win rate and the population baseline converge toward 0.5,
        # and the gap between them shrinks faster than the standard error
        # does, so the pattern stops testing significant.
        for i in range(40, 240):
            _seed(session, stock, day_offset=i, success=(i % 2 == 0), signal_names=["GoldenCross"])
        session.commit()

        discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)

        rows = session.query(DiscoveredPattern).filter_by(condition_description="GoldenCross").all()
        assert len(rows) == 1  # still not deleted
        assert rows[0].still_valid is False

    def test_only_the_requested_horizon_is_considered(self, session, stock):
        for i in range(20):
            _seed(session, stock, day_offset=i, success=True, signal_names=["GoldenCross"], horizon_days=14)
        session.commit()

        patterns = discover_patterns(session, evaluation_horizon_days=7, min_sample_size=15)
        assert patterns == []

    def test_returns_empty_list_when_no_labeled_outcomes_exist(self, session, stock):
        patterns = discover_patterns(session, evaluation_horizon_days=7)
        assert patterns == []
