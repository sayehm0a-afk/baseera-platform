"""Unit tests for E4's by_llm_reasoning_involvement() -- real
SQLAlchemy ORM against an in-memory SQLite DB.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.accuracy_metrics import by_llm_reasoning_involvement
from src.core.db.database import Base
from src.domain.models import (
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


def _seed(session, stock, day_offset, confidence, success, agent_debate_summary=None, return_pct=None, horizon_days=7):
    evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc) + timedelta(days=day_offset)
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        evaluated_at=evaluated_at,
        market_price_at_evaluation=100.0,
        recommendation=RecommendationLabel.BUY,
        total_score=60.0,
        confidence_score=confidence,
        engine_version="1.0.0",
        source="live_scan",
        agent_debate_summary=agent_debate_summary,
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
            return_pct=return_pct,
        )
    )


class TestByLlmReasoningInvolvement:
    def test_splits_into_llm_assisted_and_technical_only_groups(self, session, stock):
        _seed(session, stock, day_offset=0, confidence=80.0, success=True, agent_debate_summary={"rounds": 1})
        _seed(session, stock, day_offset=1, confidence=60.0, success=False, agent_debate_summary=None)
        _seed(session, stock, day_offset=2, confidence=70.0, success=True, agent_debate_summary=None)
        session.commit()

        result = by_llm_reasoning_involvement(session, evaluation_horizon_days=7)

        assert result["llm_assisted"]["count"] == 1
        assert result["llm_assisted"]["win_rate"] == pytest.approx(1.0)
        assert result["technical_only"]["count"] == 2
        assert result["technical_only"]["win_rate"] == pytest.approx(0.5)

    def test_empty_group_reports_none_metrics_not_an_error(self, session, stock):
        _seed(session, stock, day_offset=0, confidence=80.0, success=True, agent_debate_summary=None)
        session.commit()

        result = by_llm_reasoning_involvement(session, evaluation_horizon_days=7)

        assert result["llm_assisted"]["count"] == 0
        assert result["llm_assisted"]["win_rate"] is None

    def test_only_the_requested_horizon_is_considered(self, session, stock):
        _seed(session, stock, day_offset=0, confidence=80.0, success=True, horizon_days=14)
        session.commit()

        result = by_llm_reasoning_involvement(session, evaluation_horizon_days=7)
        assert result["technical_only"]["count"] == 0

    def test_pending_and_partial_outcomes_are_excluded(self, session, stock):
        _seed(session, stock, day_offset=0, confidence=80.0, success=True)
        evaluated_at = datetime(2026, 1, 5, tzinfo=timezone.utc)
        partial_snapshot = RecommendationSnapshot(
            stock_id=stock.id, symbol=stock.symbol, evaluated_at=evaluated_at,
            market_price_at_evaluation=100.0, recommendation=RecommendationLabel.BUY,
            total_score=60.0, confidence_score=75.0, engine_version="1.0.0", source="live_scan",
        )
        session.add(partial_snapshot)
        session.flush()
        session.add(
            RecommendationOutcome(
                snapshot_id=partial_snapshot.id, symbol=stock.symbol, evaluation_horizon_days=7,
                due_at=evaluated_at + timedelta(days=7), status=RecommendationOutcomeStatus.PARTIAL,
                evaluated_at=evaluated_at + timedelta(days=7),
            )
        )
        session.commit()

        result = by_llm_reasoning_involvement(session, evaluation_horizon_days=7)
        assert result["technical_only"]["count"] == 1  # the PARTIAL row is excluded

    def test_period_filters_are_applied(self, session, stock):
        _seed(session, stock, day_offset=0, confidence=80.0, success=True)
        _seed(session, stock, day_offset=100, confidence=80.0, success=True)
        session.commit()

        result = by_llm_reasoning_involvement(
            session, evaluation_horizon_days=7, period_start=date(2026, 1, 1), period_end=date(2026, 1, 10),
        )
        assert result["technical_only"]["count"] == 1

    def test_average_return_pct_computed_from_known_returns(self, session, stock):
        _seed(session, stock, day_offset=0, confidence=80.0, success=True, return_pct=10.0)
        _seed(session, stock, day_offset=1, confidence=60.0, success=False, return_pct=-4.0)
        session.commit()

        result = by_llm_reasoning_involvement(session, evaluation_horizon_days=7)
        assert result["technical_only"]["average_return_pct"] == pytest.approx(3.0)
