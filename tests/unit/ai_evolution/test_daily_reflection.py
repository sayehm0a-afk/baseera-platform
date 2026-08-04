"""Unit tests for E6's generate_daily_reflection() -- real SQLAlchemy
ORM against an in-memory SQLite DB.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.daily_reflection import generate_daily_reflection
from src.core.db.database import Base
from src.domain.models import (
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    ReflectionReport,
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


def _seed(session, stock, status, confidence, signal_names=None, evaluated_on=date(2026, 1, 15)):
    evaluated_at_snapshot = datetime(2026, 1, 14, tzinfo=timezone.utc)
    signals = [
        {"name": name, "description": name, "direction": "bullish", "source": "technical", "impact": 1.0}
        for name in (signal_names or [])
    ]
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        evaluated_at=evaluated_at_snapshot,
        market_price_at_evaluation=100.0,
        recommendation=RecommendationLabel.BUY,
        total_score=60.0,
        confidence_score=confidence,
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
            evaluation_horizon_days=1,
            due_at=datetime(evaluated_on.year, evaluated_on.month, evaluated_on.day, tzinfo=timezone.utc),
            status=status,
            evaluated_at=datetime(evaluated_on.year, evaluated_on.month, evaluated_on.day, 12, tzinfo=timezone.utc),
        )
    )


class TestGenerateDailyReflection:
    def test_defaults_to_yesterday_utc(self, session, stock, monkeypatch):
        class _FixedDatetime(datetime):
            @classmethod
            def now(cls, tz=None):
                return datetime(2026, 1, 16, 10, 0, tzinfo=timezone.utc)

        import src.ai_evolution.daily_reflection as module

        monkeypatch.setattr(module, "datetime", _FixedDatetime)
        _seed(session, stock, RecommendationOutcomeStatus.SUCCESSFUL, confidence=80.0, evaluated_on=date(2026, 1, 15))
        session.commit()

        report = generate_daily_reflection(session)
        assert report.review_date == date(2026, 1, 15)

    def test_counts_by_status(self, session, stock):
        _seed(session, stock, RecommendationOutcomeStatus.SUCCESSFUL, confidence=80.0)
        _seed(session, stock, RecommendationOutcomeStatus.SUCCESSFUL, confidence=75.0)
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0)
        _seed(session, stock, RecommendationOutcomeStatus.PARTIAL, confidence=60.0)
        _seed(session, stock, RecommendationOutcomeStatus.EXPIRED, confidence=50.0)
        session.commit()

        report = generate_daily_reflection(session, review_date=date(2026, 1, 15))

        assert report.recommendations_reviewed == 5
        assert report.successful_count == 2
        assert report.failed_count == 1
        assert report.partial_count == 1
        assert report.expired_count == 1
        assert float(report.win_rate) == pytest.approx(2 / 3, abs=1e-3)

    def test_no_recommendations_reviewed_is_not_an_error(self, session, stock):
        report = generate_daily_reflection(session, review_date=date(2026, 1, 15))
        assert report.recommendations_reviewed == 0
        assert report.win_rate is None
        assert "No recommendations were evaluated" in report.key_findings[0]

    def test_dominant_failed_signal_is_flagged(self, session, stock):
        for _ in range(3):
            _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0, signal_names=["OverboughtRSI"])
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0, signal_names=["Other"])
        session.commit()

        report = generate_daily_reflection(session, review_date=date(2026, 1, 15))

        assert any("OverboughtRSI" in finding for finding in report.key_findings)
        assert any("OverboughtRSI" in s for s in report.improvement_suggestions)

    def test_no_suggestion_when_no_dominant_failed_signal(self, session, stock):
        # Three different signals, one each out of three failures --
        # no single signal reaches the "majority" (>=50%) threshold.
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0, signal_names=["A"])
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0, signal_names=["B"])
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0, signal_names=["C"])
        session.commit()

        report = generate_daily_reflection(session, review_date=date(2026, 1, 15))
        assert report.improvement_suggestions == []

    def test_confidence_separation_finding_and_suggestion(self, session, stock):
        _seed(session, stock, RecommendationOutcomeStatus.SUCCESSFUL, confidence=72.0)
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0)
        session.commit()

        report = generate_daily_reflection(session, review_date=date(2026, 1, 15))

        assert any("Average confidence" in f for f in report.key_findings)
        assert any("Confidence did not clearly separate" in s for s in report.improvement_suggestions)

    def test_confidence_clearly_separated_produces_no_suggestion(self, session, stock):
        _seed(session, stock, RecommendationOutcomeStatus.SUCCESSFUL, confidence=95.0)
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=40.0)
        session.commit()

        report = generate_daily_reflection(session, review_date=date(2026, 1, 15))
        assert not any("Confidence did not clearly separate" in s for s in report.improvement_suggestions)

    def test_rerunning_updates_the_existing_row_instead_of_duplicating(self, session, stock):
        _seed(session, stock, RecommendationOutcomeStatus.SUCCESSFUL, confidence=80.0)
        session.commit()

        generate_daily_reflection(session, review_date=date(2026, 1, 15))
        generate_daily_reflection(session, review_date=date(2026, 1, 15))

        rows = session.query(ReflectionReport).filter_by(review_date=date(2026, 1, 15)).all()
        assert len(rows) == 1

    def test_only_the_requested_date_is_considered(self, session, stock):
        _seed(session, stock, RecommendationOutcomeStatus.SUCCESSFUL, confidence=80.0, evaluated_on=date(2026, 1, 15))
        _seed(session, stock, RecommendationOutcomeStatus.FAILED, confidence=70.0, evaluated_on=date(2026, 1, 16))
        session.commit()

        report = generate_daily_reflection(session, review_date=date(2026, 1, 15))
        assert report.recommendations_reviewed == 1
        assert report.successful_count == 1
