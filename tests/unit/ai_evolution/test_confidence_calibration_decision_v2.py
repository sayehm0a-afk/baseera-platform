"""RADAR-C Phase C: tests for confidence_calibration.py's decision_v2
training source -- the previously-disclosed gap ("never wired into
live recommendation output" for Decision Engine V2) closed by adding
a second, independently-scoped ledger (DecisionV2Snapshot/
DecisionV2Outcome) alongside the original legacy_v1 one
(RecommendationSnapshot/RecommendationOutcome), which
test_confidence_calibration.py already covers in full. Follows that
file's exact fixture pattern (in-memory SQLite, real sklearn fits).
"""

import random
from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.confidence_calibration import (
    TRAINING_SOURCE_DECISION_V2,
    TRAINING_SOURCE_LEGACY_V1,
    ConfidenceCalibrationEngine,
    get_effective_confidence,
)
from src.core.db.database import Base
from src.domain.models import (
    ConfidenceCalibrationMethod,
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
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


def _seed_decision_v2_outcome(session, stock, day_offset, confidence, hit_target):
    ts = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en="Stock 2222",
        decision="BUY_CANDIDATE",
        decision_label_ar="شراء",
        confidence_score=confidence,
        opportunity_quality_score=60.0,
        risk_score=50.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        market_status="OPEN",
        decision_timestamp=ts,
        analysis_version="2.0.0",
        data_source="SAHMK",
    )
    session.add(snapshot)
    session.flush()
    session.add(
        DecisionV2Outcome(
            decision_v2_snapshot_id=snapshot.id,
            symbol=stock.symbol,
            due_at=ts + timedelta(days=7),
            status=DecisionV2OutcomeStatus.TARGET_1_HIT if hit_target else DecisionV2OutcomeStatus.STOP_LOSS_HIT,
            evaluated_at=ts + timedelta(days=7),
        )
    )
    return snapshot


def _seed_decision_v2_overconfident_dataset(session, stock, n=200, seed=42):
    rng = random.Random(seed)
    for i in range(n):
        hit_target = rng.random() < 0.5
        _seed_decision_v2_outcome(session, stock, day_offset=i, confidence=85.0, hit_target=hit_target)
    session.commit()


class TestDecisionV2TrainingSource:
    def test_propose_with_decision_v2_source_reads_the_decision_v2_ledger(self, session, stock):
        _seed_decision_v2_overconfident_dataset(session, stock, n=60)

        engine = ConfidenceCalibrationEngine()
        row = engine.propose(
            session, date(2026, 1, 1), date(2026, 12, 31),
            min_sample_size=30, source=TRAINING_SOURCE_DECISION_V2,
        )

        assert row.training_source == TRAINING_SOURCE_DECISION_V2
        assert row.training_sample_size == 60
        assert row.method is ConfidenceCalibrationMethod.PLATT

    def test_default_source_is_legacy_v1_unaffected_by_decision_v2_data(self, session, stock):
        # Seeding only decision_v2 outcomes must not satisfy a
        # legacy_v1-source propose() call -- the two ledgers are
        # completely separate tables.
        _seed_decision_v2_overconfident_dataset(session, stock, n=60)

        engine = ConfidenceCalibrationEngine()
        with pytest.raises(ValueError, match="Insufficient outcome history"):
            engine.propose(session, date(2026, 1, 1), date(2026, 12, 31), min_sample_size=30)

    def test_active_models_are_scoped_independently_per_source(self, session, stock):
        _seed_decision_v2_overconfident_dataset(session, stock, n=60)
        engine = ConfidenceCalibrationEngine()
        row = engine.propose(
            session, date(2026, 1, 1), date(2026, 12, 31),
            min_sample_size=30, source=TRAINING_SOURCE_DECISION_V2,
        )
        engine.test(session, row.version)
        engine.activate(session, row.version)

        assert engine.get_active_model(session, source=TRAINING_SOURCE_DECISION_V2) is not None
        assert engine.get_active_model(session, source=TRAINING_SOURCE_LEGACY_V1) is None
        assert engine.get_active_model(session) is None  # default source is legacy_v1

    def test_get_effective_confidence_returns_none_until_a_decision_v2_model_is_active(self, session, stock):
        probability, version = get_effective_confidence(session, 80.0, source=TRAINING_SOURCE_DECISION_V2)
        assert probability is None
        assert version is None

    def test_get_effective_confidence_applies_the_active_decision_v2_model(self, session, stock):
        _seed_decision_v2_overconfident_dataset(session, stock, n=60)
        engine = ConfidenceCalibrationEngine()
        row = engine.propose(
            session, date(2026, 1, 1), date(2026, 12, 31),
            min_sample_size=30, source=TRAINING_SOURCE_DECISION_V2,
        )
        engine.test(session, row.version)
        engine.activate(session, row.version)

        probability, version = get_effective_confidence(session, 85.0, source=TRAINING_SOURCE_DECISION_V2)
        assert probability is not None
        assert 0.0 <= probability <= 1.0
        assert version == row.version

        # legacy_v1 (the default) must remain uncalibrated -- activating
        # a decision_v2 model must never leak into the other source.
        legacy_probability, legacy_version = get_effective_confidence(session, 85.0)
        assert legacy_probability is None
        assert legacy_version is None
