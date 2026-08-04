"""Unit tests for E9's `aggregate_daily_intelligence` -- real
SQLAlchemy ORM against an in-memory SQLite DB, no mocking of the
persistence layer.
"""

from datetime import date, datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.daily_intelligence_aggregation import aggregate_daily_intelligence
from src.core.db.database import Base
from src.domain.models import (
    AgentOpinion,
    AgentStance,
    DailyIntelligenceSnapshot,
    DebateSession,
    DiscoveredPattern,
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
)

_SNAPSHOT_DATE = date(2026, 1, 15)
_EVALUATED_AT = datetime(2026, 1, 15, 12, 0, tzinfo=timezone.utc)


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


def _snapshot(session, stock, confidence=70.0, sector_stock=None):
    row = RecommendationSnapshot(
        stock_id=(sector_stock or stock).id, symbol=(sector_stock or stock).symbol, evaluated_at=_EVALUATED_AT,
        market_price_at_evaluation=100.0, recommendation=RecommendationLabel.BUY, total_score=60.0,
        confidence_score=confidence, engine_version="1.0.0", source="live_scan",
    )
    session.add(row)
    session.flush()
    return row


def _outcome(session, snapshot, status, horizon_days=7):
    row = RecommendationOutcome(
        snapshot_id=snapshot.id, symbol=snapshot.symbol, evaluation_horizon_days=horizon_days,
        due_at=_EVALUATED_AT, status=status, evaluated_at=_EVALUATED_AT,
    )
    session.add(row)
    session.commit()
    return row


class TestAggregateDailyIntelligence:
    def test_no_data_yields_an_empty_but_valid_snapshot(self, session):
        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)

        assert result.recommendations_evaluated == 0
        assert result.successful_count == 0
        assert result.failed_count == 0
        assert result.win_rate is None
        assert result.calibration_error is None
        assert result.sector_breakdown is None
        assert result.best_patterns is None
        assert result.worst_patterns is None
        assert result.agent_panel_snapshot_count == 0
        assert result.agent_agreement_rate is None

    def test_counts_every_terminal_and_non_terminal_status(self, session, stock):
        s1 = _snapshot(session, stock)
        _outcome(session, s1, RecommendationOutcomeStatus.SUCCESSFUL)
        s2 = _snapshot(session, stock)
        _outcome(session, s2, RecommendationOutcomeStatus.SUCCESSFUL)
        s3 = _snapshot(session, stock)
        _outcome(session, s3, RecommendationOutcomeStatus.FAILED)
        s4 = _snapshot(session, stock)
        _outcome(session, s4, RecommendationOutcomeStatus.PARTIAL)
        s5 = _snapshot(session, stock)
        _outcome(session, s5, RecommendationOutcomeStatus.EXPIRED)

        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)

        assert result.recommendations_evaluated == 5
        assert result.successful_count == 2
        assert result.failed_count == 1
        assert result.partial_count == 1
        assert result.expired_count == 1
        assert float(result.win_rate) == pytest.approx(2 / 3, abs=1e-3)

    def test_failed_count_is_never_zero_when_failures_exist_no_hide_flag_exists(self, session, stock):
        """Non-negotiable per Part 14 of the design: nothing here can
        suppress failed_count -- this function accepts no such
        parameter at all."""
        import inspect

        s1 = _snapshot(session, stock)
        _outcome(session, s1, RecommendationOutcomeStatus.FAILED)

        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)
        assert result.failed_count == 1
        assert "hide_failures" not in inspect.signature(aggregate_daily_intelligence).parameters
        assert "exclude_failures" not in inspect.signature(aggregate_daily_intelligence).parameters

    def test_sector_breakdown_groups_by_stock_sector(self, session):
        energy = Stock(symbol="2222", name_en="Energy Co", sector="Energy")
        banking = Stock(symbol="1111", name_en="Bank Co", sector="Banking")
        session.add_all([energy, banking])
        session.commit()

        s1 = _snapshot(session, energy)
        _outcome(session, s1, RecommendationOutcomeStatus.SUCCESSFUL)
        s2 = _snapshot(session, energy)
        _outcome(session, s2, RecommendationOutcomeStatus.FAILED)
        s3 = _snapshot(session, banking)
        _outcome(session, s3, RecommendationOutcomeStatus.SUCCESSFUL)

        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)

        assert result.sector_breakdown["Energy"] == {"count": 2, "win_rate": 0.5}
        assert result.sector_breakdown["Banking"] == {"count": 1, "win_rate": 1.0}

    def test_best_and_worst_patterns_are_disjoint_and_ordered(self, session):
        for i, win_rate in enumerate([0.9, 0.8, 0.7, 0.3, 0.2, 0.1]):
            session.add(
                DiscoveredPattern(
                    condition_type="signal_present", condition_description=f"pattern-{i}",
                    evaluation_horizon_days=7, sample_size=40, win_rate=win_rate, baseline_win_rate=0.5,
                    still_valid=True, last_validated_at=datetime.now(timezone.utc),
                )
            )
        session.commit()

        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE, pattern_limit=2)

        assert [p["condition_description"] for p in result.best_patterns] == ["pattern-0", "pattern-1"]
        assert [p["condition_description"] for p in result.worst_patterns] == ["pattern-5", "pattern-4"]

    def test_invalid_patterns_are_excluded_from_best_and_worst(self, session):
        session.add(
            DiscoveredPattern(
                condition_type="signal_present", condition_description="stale", evaluation_horizon_days=7,
                sample_size=40, win_rate=0.95, baseline_win_rate=0.5, still_valid=False,
                last_validated_at=datetime.now(timezone.utc),
            )
        )
        session.commit()

        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)
        assert result.best_patterns is None
        assert result.worst_patterns is None

    def test_agent_panel_stats_count_snapshots_not_opinions(self, session, stock):
        panel_only = _snapshot(session, stock)
        for agent_name in ["Technical Analyst", "Fundamental Analyst", "Risk Manager"]:
            session.add(
                AgentOpinion(
                    snapshot_id=panel_only.id, agent_name=agent_name, stance=AgentStance.NEUTRAL,
                    reasoning="r", used_llm=False,
                )
            )
        debated = _snapshot(session, stock)
        session.add(
            AgentOpinion(
                snapshot_id=debated.id, agent_name="Technical Analyst", stance=AgentStance.BULLISH,
                reasoning="r", used_llm=False,
            )
        )
        session.add(DebateSession(snapshot_id=debated.id, participants=["Technical Analyst"], rounds=1, final_decision="BUY"))
        session.commit()

        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)

        assert result.agent_panel_snapshot_count == 2
        assert result.agent_debate_count == 1
        assert float(result.agent_agreement_rate) == pytest.approx(0.5)

    def test_calibration_error_reuses_confidence_calibration_formula(self, session, stock):
        s1 = _snapshot(session, stock, confidence=90.0)
        _outcome(session, s1, RecommendationOutcomeStatus.SUCCESSFUL)
        s2 = _snapshot(session, stock, confidence=90.0)
        _outcome(session, s2, RecommendationOutcomeStatus.FAILED)

        result = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)

        # 90% stated confidence, 50% realized accuracy -> |0.9 - 0.5| = 0.4
        assert float(result.calibration_error) == pytest.approx(0.4, abs=1e-3)

    def test_idempotent_rerun_updates_the_same_row(self, session, stock):
        s1 = _snapshot(session, stock)
        _outcome(session, s1, RecommendationOutcomeStatus.SUCCESSFUL)
        first = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)
        first_id = first.id

        s2 = _snapshot(session, stock)
        _outcome(session, s2, RecommendationOutcomeStatus.FAILED)
        second = aggregate_daily_intelligence(session, snapshot_date=_SNAPSHOT_DATE)

        assert second.id == first_id
        assert session.query(DailyIntelligenceSnapshot).count() == 1
        assert second.recommendations_evaluated == 2

    def test_defaults_to_yesterday_utc_when_no_date_given(self, session, stock, monkeypatch):
        from datetime import timedelta

        import src.ai_evolution.daily_intelligence_aggregation as module

        yesterday = datetime.now(timezone.utc).date() - timedelta(days=1)
        snapshot = _snapshot(session, stock)
        snapshot.evaluated_at = datetime(yesterday.year, yesterday.month, yesterday.day, 12, tzinfo=timezone.utc)
        session.flush()
        _outcome(
            session, snapshot, RecommendationOutcomeStatus.SUCCESSFUL,
        )
        session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id).update(
            {"evaluated_at": snapshot.evaluated_at}
        )
        session.commit()

        result = module.aggregate_daily_intelligence(session)
        assert result.snapshot_date == yesterday
