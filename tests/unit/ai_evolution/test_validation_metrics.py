"""M10 (Part G) unit tests: `compute_validation_session_metrics` over a
seeded set of `DecisionV2Snapshot`/`DecisionV2Outcome` rows -- win rate,
per-target hit rate, stop-loss rate, expectancy, ranking-position
performance, calibration, duplicate-signal analysis, and the
DATA_UNAVAILABLE/PARTIAL exclusion discipline.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.validation_metrics import compute_validation_session_metrics
from src.core.db.database import Base
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, Stock, ValidationSession, ValidationSessionStatus


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
def validation_session_id(session):
    record = ValidationSession(
        name="Test Session",
        status=ValidationSessionStatus.RUNNING,
        is_dry_run=False,
        started_at=datetime.now(timezone.utc),
    )
    session.add(record)
    session.commit()
    return record.id


def _make_stock(session, symbol):
    row = Stock(symbol=symbol, name_en=f"Stock {symbol}", sector="Energy")
    session.add(row)
    session.flush()
    return row


def _make_snapshot(
    session,
    stock,
    validation_session_id,
    decision="BUY_CANDIDATE",
    confidence_score=70.0,
    ranking_position=None,
):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=confidence_score,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=100.0,
        market_status="OPEN",
        decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        analysis_version="2.0.0",
        data_source="test",
        validation_session_id=validation_session_id,
        ranking_position=ranking_position,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _make_outcome(session, snapshot, validation_session_id, status, return_pct=None, time_to_target_days=None, time_to_stop_days=None):
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id,
        validation_session_id=validation_session_id,
        symbol=snapshot.symbol,
        due_at=datetime(2026, 1, 31, tzinfo=timezone.utc),
        status=status,
        entry_price=100.0,
        return_pct=return_pct,
        time_to_target_days=time_to_target_days,
        time_to_stop_days=time_to_stop_days,
    )
    session.add(outcome)
    session.flush()
    return outcome


class TestComputeValidationSessionMetrics:
    def test_empty_session_returns_none_metrics_not_zero_division(self, session, validation_session_id):
        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.total_signals_issued == 0
        assert result.actionable_signals == 0
        assert result.win_rate is None
        assert result.stop_loss_rate is None
        assert result.average_return_pct is None

    def test_win_rate_counts_targets_vs_stops_only(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        stock3 = _make_stock(session, "3333")

        s1 = _make_snapshot(session, stock1, validation_session_id, ranking_position=1)
        s2 = _make_snapshot(session, stock2, validation_session_id, ranking_position=2)
        s3 = _make_snapshot(session, stock3, validation_session_id, ranking_position=3)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=10.0, time_to_target_days=2)
        _make_outcome(session, s2, validation_session_id, DecisionV2OutcomeStatus.STOP_LOSS_HIT, return_pct=-10.0, time_to_stop_days=3)
        _make_outcome(session, s3, validation_session_id, DecisionV2OutcomeStatus.PENDING)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.total_signals_issued == 3
        assert result.actionable_signals == 3
        assert result.win_rate == pytest.approx(0.5)
        assert result.decisive_signal_count == 2
        assert result.stop_loss_rate == pytest.approx(1 / 3)
        assert result.pending_count == 1

    def test_data_unavailable_never_counted_as_win_or_loss(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        s1 = _make_snapshot(session, stock1, validation_session_id)
        s2 = _make_snapshot(session, stock2, validation_session_id)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=5.0)
        _make_outcome(session, s2, validation_session_id, DecisionV2OutcomeStatus.DATA_UNAVAILABLE)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.win_rate == pytest.approx(1.0)
        assert result.data_unavailable_count == 1
        assert result.data_unavailable_rate == pytest.approx(0.5)

    def test_partial_excluded_from_win_rate_and_returns(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        s1 = _make_snapshot(session, stock1, validation_session_id)
        s2 = _make_snapshot(session, stock2, validation_session_id)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=8.0)
        _make_outcome(session, s2, validation_session_id, DecisionV2OutcomeStatus.PARTIAL, return_pct=None)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.win_rate == pytest.approx(1.0)
        assert result.partial_count == 1
        assert result.average_return_pct == pytest.approx(8.0)

    def test_target_hit_rate_by_target(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        stock3 = _make_stock(session, "3333")
        stock4 = _make_stock(session, "4444")
        s1 = _make_snapshot(session, stock1, validation_session_id)
        s2 = _make_snapshot(session, stock2, validation_session_id)
        s3 = _make_snapshot(session, stock3, validation_session_id)
        s4 = _make_snapshot(session, stock4, validation_session_id)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=5.0)
        _make_outcome(session, s2, validation_session_id, DecisionV2OutcomeStatus.TARGET_2_HIT, return_pct=10.0)
        _make_outcome(session, s3, validation_session_id, DecisionV2OutcomeStatus.TARGET_3_HIT, return_pct=15.0)
        _make_outcome(session, s4, validation_session_id, DecisionV2OutcomeStatus.STOP_LOSS_HIT, return_pct=-5.0)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.target_hit_rate_by_target[1] == pytest.approx(0.25)
        assert result.target_hit_rate_by_target[2] == pytest.approx(0.25)
        assert result.target_hit_rate_by_target[3] == pytest.approx(0.25)
        assert result.stop_loss_rate == pytest.approx(0.25)

    def test_expectancy_and_average_return_differ_when_expired_present(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        s1 = _make_snapshot(session, stock1, validation_session_id)
        s2 = _make_snapshot(session, stock2, validation_session_id)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=10.0)
        _make_outcome(session, s2, validation_session_id, DecisionV2OutcomeStatus.EXPIRED, return_pct=-2.0)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        # expectancy_pct only spans target/stop decisive rows -- EXPIRED excluded.
        assert result.expectancy_pct == pytest.approx(10.0)
        # average_return_pct spans every return-bearing status, EXPIRED included.
        assert result.average_return_pct == pytest.approx(4.0)

    def test_ranking_position_performance_grouped_by_rank(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        s1 = _make_snapshot(session, stock1, validation_session_id, ranking_position=1)
        s2 = _make_snapshot(session, stock2, validation_session_id, ranking_position=2)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=8.0)
        _make_outcome(session, s2, validation_session_id, DecisionV2OutcomeStatus.STOP_LOSS_HIT, return_pct=-6.0)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        by_rank = {r.rank: r for r in result.ranking_position_performance}
        assert by_rank[1].win_rate == pytest.approx(1.0)
        assert by_rank[2].win_rate == pytest.approx(0.0)

    def test_duplicate_signal_detection(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        _make_snapshot(session, stock1, validation_session_id)
        _make_snapshot(session, stock1, validation_session_id)
        stock2 = _make_stock(session, "2222")
        _make_snapshot(session, stock2, validation_session_id)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert len(result.duplicate_signals) == 1
        assert result.duplicate_signals[0].symbol == "1111"
        assert result.duplicate_signals[0].signal_count == 2
        assert result.duplicate_signal_rate == pytest.approx(2 / 3)

    def test_calibration_pairs_only_from_decisive_outcomes(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        stock3 = _make_stock(session, "3333")
        s1 = _make_snapshot(session, stock1, validation_session_id, confidence_score=80.0)
        s2 = _make_snapshot(session, stock2, validation_session_id, confidence_score=40.0)
        s3 = _make_snapshot(session, stock3, validation_session_id, confidence_score=60.0)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=5.0)
        _make_outcome(session, s2, validation_session_id, DecisionV2OutcomeStatus.STOP_LOSS_HIT, return_pct=-5.0)
        _make_outcome(session, s3, validation_session_id, DecisionV2OutcomeStatus.PENDING)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.calibration_pair_count == 2

    def test_scoped_to_own_validation_session_only(self, session, validation_session_id):
        other_session = ValidationSession(
            name="Other",
            status=ValidationSessionStatus.RUNNING,
            is_dry_run=False,
            started_at=datetime.now(timezone.utc),
        )
        session.add(other_session)
        session.commit()

        stock1 = _make_stock(session, "1111")
        stock2 = _make_stock(session, "2222")
        s1 = _make_snapshot(session, stock1, validation_session_id)
        s2 = _make_snapshot(session, stock2, other_session.id)

        _make_outcome(session, s1, validation_session_id, DecisionV2OutcomeStatus.TARGET_1_HIT, return_pct=5.0)
        _make_outcome(session, s2, other_session.id, DecisionV2OutcomeStatus.STOP_LOSS_HIT, return_pct=-5.0)
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.total_signals_issued == 1
        assert result.win_rate == pytest.approx(1.0)

    def test_non_actionable_decision_excluded_from_actionable_signals(self, session, validation_session_id):
        stock1 = _make_stock(session, "1111")
        _make_snapshot(session, stock1, validation_session_id, decision="WATCH")
        session.commit()

        result = compute_validation_session_metrics(session, validation_session_id)

        assert result.total_signals_issued == 1
        assert result.actionable_signals == 0
        assert result.stop_loss_rate is None
