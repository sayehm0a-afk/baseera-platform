"""Unit tests for E3's confidence calibration engine -- real SQLAlchemy
ORM against an in-memory SQLite DB, real sklearn fits (no mocking of
LogisticRegression/IsotonicRegression), synthetic but deterministic
training data.
"""

import random
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.confidence_calibration import (
    DEFAULT_REFERENCE_HORIZON_DAYS,
    ConfidenceCalibrationEngine,
    apply_calibration,
)
from src.core.db.database import Base
from src.domain.models import (
    ConfidenceCalibrationMethod,
    ConfidenceCalibrationStatus,
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


def _seed_outcome(session, stock, day_offset, confidence, success, horizon_days=DEFAULT_REFERENCE_HORIZON_DAYS):
    evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        evaluated_at=evaluated_at,
        market_price_at_evaluation=100.0,
        recommendation=RecommendationLabel.BUY,
        total_score=60.0,
        confidence_score=confidence,
        target_price=110.0,
        stop_loss=90.0,
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
    return snapshot


def _seed_overconfident_dataset(session, stock, n=200, seed=42):
    """A recommendation engine that is systematically overconfident:
    stated confidence is always ~85, but the true success rate is only
    ~50%. A well-fit calibration curve should pull 85 down toward 0.5,
    reducing ECE relative to the raw (badly miscalibrated) confidence."""
    rng = random.Random(seed)
    for i in range(n):
        success = rng.random() < 0.5
        _seed_outcome(session, stock, day_offset=i, confidence=85.0, success=success)
    session.commit()


class TestExpectedCalibrationError:
    def test_none_for_empty_pairs(self):
        from src.ai_evolution.confidence_calibration import expected_calibration_error

        assert expected_calibration_error([]) is None

    def test_zero_for_perfectly_calibrated_pairs(self):
        from src.ai_evolution.confidence_calibration import expected_calibration_error

        # 100% of "90-confidence" calls succeed -> mean_confidence 90%, realized 100% -- not
        # perfect, but a bucket where confidence and realized accuracy are close scores low.
        pairs = [(50.0, 1), (50.0, 0)]  # 50% confidence bucket, 50% realized accuracy -- perfect
        assert expected_calibration_error(pairs) == pytest.approx(0.0)


class TestLoadTrainingPairsAndPropose:
    def test_propose_raises_below_minimum_sample_size(self, session, stock):
        _seed_outcome(session, stock, day_offset=0, confidence=70.0, success=True)
        session.commit()

        engine = ConfidenceCalibrationEngine()
        with pytest.raises(ValueError, match="Insufficient outcome history"):
            engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)

    def test_propose_uses_platt_below_isotonic_threshold(self, session, stock):
        _seed_overconfident_dataset(session, stock, n=60)

        engine = ConfidenceCalibrationEngine()
        row = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)

        assert row.method is ConfidenceCalibrationMethod.PLATT
        assert row.status is ConfidenceCalibrationStatus.DRAFT
        assert row.training_sample_size == 60
        assert "coef" in row.model_params
        assert "intercept" in row.model_params

    def test_propose_uses_isotonic_above_threshold(self, session, stock):
        _seed_overconfident_dataset(session, stock, n=60)

        engine = ConfidenceCalibrationEngine()
        row = engine.propose(
            session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30, isotonic_threshold=50,
        )

        assert row.method is ConfidenceCalibrationMethod.ISOTONIC
        assert "x_thresholds" in row.model_params
        assert "y_thresholds" in row.model_params

    def test_propose_computes_calibration_error_before_and_after(self, session, stock):
        _seed_overconfident_dataset(session, stock, n=100)

        engine = ConfidenceCalibrationEngine()
        row = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)

        assert row.calibration_error_before is not None
        assert row.calibration_error_after is not None
        # Systematically overconfident (stated 85%, true ~50%) -- a real fit must improve ECE.
        assert float(row.calibration_error_after) < float(row.calibration_error_before)

    def test_propose_only_uses_the_reference_horizon(self, session, stock):
        # A different horizon's outcome must not leak into training.
        _seed_outcome(session, stock, day_offset=0, confidence=70.0, success=True, horizon_days=14)
        _seed_overconfident_dataset(session, stock, n=30)

        engine = ConfidenceCalibrationEngine()
        row = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)

        assert row.training_sample_size == 30  # the horizon=14 row is excluded

    def test_platt_fit_raises_on_single_class_labels(self, session, stock):
        for i in range(40):
            _seed_outcome(session, stock, day_offset=i, confidence=80.0, success=True)
        session.commit()

        engine = ConfidenceCalibrationEngine()
        with pytest.raises(ValueError, match="same outcome label"):
            engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)


class TestLifecycle:
    def _propose_and_get(self, session, stock, n=100):
        _seed_overconfident_dataset(session, stock, n=n)
        engine = ConfidenceCalibrationEngine()
        row = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)
        return engine, row

    def test_test_validates_an_improving_fit(self, session, stock):
        engine, row = self._propose_and_get(session, stock)
        result = engine.test(session, row.version)
        assert result.status is ConfidenceCalibrationStatus.VALIDATED

    def test_activate_requires_validated_status(self, session, stock):
        engine, row = self._propose_and_get(session, stock)
        with pytest.raises(ValueError, match="must be VALIDATED"):
            engine.activate(session, row.version)

    def test_activate_supersedes_the_previous_active_model(self, session, stock):
        engine, first = self._propose_and_get(session, stock)
        engine.test(session, first.version)
        engine.activate(session, first.version)
        assert engine.get_active_model(session).version == first.version

        _seed_overconfident_dataset(session, stock, n=100, seed=7)
        second = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)
        engine.test(session, second.version)
        engine.activate(session, second.version)

        assert engine.get_active_model(session).version == second.version
        session.refresh(first)
        assert first.status is ConfidenceCalibrationStatus.SUPERSEDED
        assert first.deactivated_at is not None

    def test_rollback_deactivates_active_model(self, session, stock):
        engine, row = self._propose_and_get(session, stock)
        engine.test(session, row.version)
        engine.activate(session, row.version)

        result = engine.rollback(session)
        assert result is None
        assert engine.get_active_model(session) is None
        session.refresh(row)
        assert row.status is ConfidenceCalibrationStatus.ROLLED_BACK

    def test_rollback_can_reactivate_a_specific_version(self, session, stock):
        engine, first = self._propose_and_get(session, stock)
        engine.test(session, first.version)
        engine.activate(session, first.version)
        engine.rollback(session)

        result = engine.rollback(session, to_version=first.version)
        assert result.version == first.version
        assert result.status is ConfidenceCalibrationStatus.ACTIVE


class TestApplyCalibration:
    def test_platt_output_is_a_probability(self, session, stock):
        _seed_overconfident_dataset(session, stock, n=100)
        engine = ConfidenceCalibrationEngine()
        row = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)

        calibrated = apply_calibration(row, 85.0)
        assert 0.0 <= calibrated <= 1.0
        # Overconfident dataset: raw 85% confidence should calibrate down toward the true ~50% rate.
        assert calibrated < 0.85

    def test_isotonic_output_is_a_probability(self, session, stock):
        _seed_overconfident_dataset(session, stock, n=100)
        engine = ConfidenceCalibrationEngine()
        row = engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30, isotonic_threshold=50)

        calibrated = apply_calibration(row, 85.0)
        assert 0.0 <= calibrated <= 1.0
