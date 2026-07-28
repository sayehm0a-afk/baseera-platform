"""Unit tests for E8's champion/challenger paper trading -- real
SQLAlchemy ORM against an in-memory SQLite DB (same technique
tests/unit/ai_evolution/agents/test_orchestrator.py already uses), a
real `AnalysisContext`/`AIDecisionEngine`, no network/LLM calls
anywhere in this module.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.paper_trading import (
    CHALLENGER_VARIANT,
    CHAMPION_VARIANT,
    compare_champion_vs_challenger,
    generate_challenger_snapshot,
    get_latest_challenger_config,
    two_sample_significance_test,
)
from src.analysis.recommendation.types import AnalysisContext
from src.core.db.database import Base
from src.domain.models import (
    CalibrationConfig,
    CalibrationStatus,
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


def _champion_snapshot(session, stock, variant=None):
    row = RecommendationSnapshot(
        stock_id=stock.id, symbol=stock.symbol, evaluated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        market_price_at_evaluation=100.0, recommendation=RecommendationLabel.BUY, total_score=60.0,
        confidence_score=70.0, engine_version="1.0.0", source="live_scan", is_paper_trade=False, variant=variant,
    )
    session.add(row)
    session.flush()
    return row


def _calibration_config(session, config, status=CalibrationStatus.VALIDATED, version="v1", created_at=None):
    row = CalibrationConfig(version=version, status=status, config=config)
    session.add(row)
    session.flush()
    if created_at is not None:
        row.created_at = created_at
    session.commit()
    return row


def _outcome(session, snapshot, horizon_days, status, evaluated_at=None):
    row = RecommendationOutcome(
        snapshot_id=snapshot.id, symbol=snapshot.symbol, evaluation_horizon_days=horizon_days,
        due_at=datetime(2026, 1, 8, tzinfo=timezone.utc), status=status,
        evaluated_at=evaluated_at or datetime(2026, 1, 9, tzinfo=timezone.utc),
    )
    session.add(row)
    session.commit()
    return row


class TestTwoSampleSignificanceTest:
    def test_insufficient_sample_size_returns_no_result(self):
        result = two_sample_significance_test(
            champion_successes=1, champion_sample_size=1, challenger_successes=1, challenger_sample_size=1,
        )
        assert result.z_score is None
        assert result.p_value is None
        assert result.significant is False

    def test_clearly_better_challenger_is_significant_with_enough_samples(self):
        result = two_sample_significance_test(
            champion_successes=30, champion_sample_size=100,
            challenger_successes=60, challenger_sample_size=100,
            min_sample_size=30,
        )
        assert result.champion_win_rate == pytest.approx(0.30)
        assert result.challenger_win_rate == pytest.approx(0.60)
        assert result.p_value < 0.05
        assert result.significant is True

    def test_challenger_with_lower_rate_is_never_significant(self):
        result = two_sample_significance_test(
            champion_successes=60, champion_sample_size=100,
            challenger_successes=30, challenger_sample_size=100,
            min_sample_size=30,
        )
        assert result.challenger_win_rate < result.champion_win_rate
        assert result.significant is False

    def test_below_min_sample_size_is_never_significant_even_with_a_tiny_p_value(self):
        result = two_sample_significance_test(
            champion_successes=1, champion_sample_size=10,
            challenger_successes=9, challenger_sample_size=10,
            min_sample_size=30,
        )
        assert result.p_value < 0.05
        assert result.significant is False

    def test_equal_rates_yield_a_p_value_near_one_half(self):
        result = two_sample_significance_test(
            champion_successes=50, champion_sample_size=100,
            challenger_successes=50, challenger_sample_size=100,
        )
        assert result.z_score == pytest.approx(0.0)
        assert result.p_value == pytest.approx(0.5)
        assert result.significant is False


class TestGetLatestChallengerConfig:
    def test_none_when_no_validated_config_exists(self, session):
        _calibration_config(session, {}, status=CalibrationStatus.DRAFT, version="draft-1")
        _calibration_config(session, {}, status=CalibrationStatus.ACTIVE, version="active-1")
        assert get_latest_challenger_config(session) is None

    def test_returns_the_most_recently_created_validated_config(self, session):
        older = _calibration_config(session, {}, version="v1")
        older.created_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        newer = _calibration_config(session, {}, version="v2")
        newer.created_at = datetime(2026, 1, 2, tzinfo=timezone.utc)
        session.commit()

        result = get_latest_challenger_config(session)
        assert result.version == "v2"

    def test_ignores_rejected_and_superseded_configs(self, session):
        _calibration_config(session, {}, status=CalibrationStatus.REJECTED, version="rejected")
        _calibration_config(session, {}, status=CalibrationStatus.SUPERSEDED, version="superseded")
        assert get_latest_challenger_config(session) is None


class TestGenerateChallengerSnapshot:
    def test_persists_a_challenger_snapshot_and_labels_the_champion(self, session, stock):
        champion = _champion_snapshot(session, stock)
        config = _calibration_config(session, {})
        context = AnalysisContext(symbol="2222")

        challenger = generate_challenger_snapshot(session, champion, context, config)
        session.commit()

        assert challenger is not None
        assert challenger.variant == CHALLENGER_VARIANT
        assert challenger.is_paper_trade is True
        assert challenger.calibration_version == config.version
        assert challenger.symbol == champion.symbol
        assert challenger.evaluated_at == champion.evaluated_at
        session.refresh(champion)
        assert champion.variant == CHAMPION_VARIANT

    def test_creates_pending_outcome_rows_for_the_challenger(self, session, stock):
        champion = _champion_snapshot(session, stock)
        config = _calibration_config(session, {})
        context = AnalysisContext(symbol="2222")

        challenger = generate_challenger_snapshot(session, champion, context, config)
        session.commit()

        outcomes = session.query(RecommendationOutcome).filter_by(snapshot_id=challenger.id).all()
        assert len(outcomes) == 7  # EVALUATION_HORIZON_DAYS has 7 entries
        assert all(row.status == RecommendationOutcomeStatus.PENDING for row in outcomes)

    def test_never_raises_on_a_malformed_calibration_config(self, session, stock):
        champion = _champion_snapshot(session, stock)
        config = _calibration_config(session, {"contributor_weights": {"not_a_real_contributor": 0.5}})
        context = AnalysisContext(symbol="2222")

        result = generate_challenger_snapshot(session, champion, context, config)

        assert result is None
        assert session.query(RecommendationSnapshot).filter_by(variant=CHALLENGER_VARIANT).count() == 0


class TestCompareChampionVsChallenger:
    def test_no_data_yields_no_result(self, session):
        result = compare_champion_vs_challenger(session)
        assert result.champion_sample_size == 0
        assert result.significant is False

    def test_computes_win_rates_from_terminal_outcomes_only(self, session, stock):
        for status in [RecommendationOutcomeStatus.SUCCESSFUL] * 2 + [RecommendationOutcomeStatus.FAILED] * 8:
            snapshot = _champion_snapshot(session, stock, variant=CHAMPION_VARIANT)
            _outcome(session, snapshot, horizon_days=7, status=status)

        for status in [RecommendationOutcomeStatus.SUCCESSFUL] * 8 + [RecommendationOutcomeStatus.FAILED] * 2:
            snapshot = _champion_snapshot(session, stock, variant=CHALLENGER_VARIANT)
            _outcome(session, snapshot, horizon_days=7, status=status)

        # PENDING rows at the same horizon must not count toward either sample.
        pending_snapshot = _champion_snapshot(session, stock, variant=CHAMPION_VARIANT)
        _outcome(session, pending_snapshot, horizon_days=7, status=RecommendationOutcomeStatus.PENDING)

        result = compare_champion_vs_challenger(session, evaluation_horizon_days=7, min_sample_size=2)

        assert result.champion_sample_size == 10
        assert result.champion_win_rate == pytest.approx(0.2)
        assert result.challenger_sample_size == 10
        assert result.challenger_win_rate == pytest.approx(0.8)
        assert result.significant is True

    def test_a_different_horizon_is_not_mixed_in(self, session, stock):
        champion_7d = _champion_snapshot(session, stock, variant=CHAMPION_VARIANT)
        _outcome(session, champion_7d, horizon_days=7, status=RecommendationOutcomeStatus.SUCCESSFUL)
        champion_30d = _champion_snapshot(session, stock, variant=CHAMPION_VARIANT)
        _outcome(session, champion_30d, horizon_days=30, status=RecommendationOutcomeStatus.FAILED)

        result = compare_champion_vs_challenger(session, evaluation_horizon_days=7, min_sample_size=1)
        assert result.champion_sample_size == 1
