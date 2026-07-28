"""Unit tests for E2's outcome tracking: create_pending_outcomes() (row
issuance alongside a live RecommendationSnapshot) and
evaluate_due_outcomes() (scoring against real forward price data).
Real SQLAlchemy ORM against an in-memory SQLite DB, no mocking of the
persistence layer itself -- the same discipline
tests/unit/market_intelligence/repositories already uses.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.outcome_evaluation import (
    EVALUATION_HORIZON_DAYS,
    create_pending_outcomes,
    evaluate_due_outcomes,
)
from src.core.db.database import Base
from src.domain.models import (
    PriceBar,
    RecommendationLabel,
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
    Timeframe,
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


def _make_snapshot(
    session,
    stock,
    recommendation=RecommendationLabel.BUY,
    entry_price=100.0,
    target_price=110.0,
    stop_loss=90.0,
    evaluated_at=None,
):
    evaluated_at = evaluated_at or datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = RecommendationSnapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        evaluated_at=evaluated_at,
        market_price_at_evaluation=entry_price,
        recommendation=recommendation,
        total_score=65.0,
        confidence_score=70.0,
        target_price=target_price,
        stop_loss=stop_loss,
        engine_version="1.0.0",
        source="live_scan",
        is_paper_trade=False,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _add_bar(session, stock, day, high, low, close, open_=None):
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=datetime(day.year, day.month, day.day, 16, 0, tzinfo=timezone.utc),
            open=open_ if open_ is not None else close,
            high=high,
            low=low,
            close=close,
            volume=1000,
            source="test",
            is_synthetic=False,
        )
    )


class TestCreatePendingOutcomes:
    def test_creates_one_row_per_horizon(self, session, stock):
        snapshot = _make_snapshot(session, stock)

        created = create_pending_outcomes(session, snapshot)
        session.commit()

        assert len(created) == len(EVALUATION_HORIZON_DAYS)
        rows = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id).all()
        assert {row.evaluation_horizon_days for row in rows} == set(EVALUATION_HORIZON_DAYS)
        assert all(row.status is RecommendationOutcomeStatus.PENDING for row in rows)
        assert all(row.symbol == "2222" for row in rows)

    def test_due_at_is_evaluated_at_plus_horizon(self, session, stock):
        snapshot = _make_snapshot(session, stock, evaluated_at=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_outcomes(session, snapshot)
        session.commit()

        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=7).one()
        # SQLite doesn't round-trip tzinfo -- the wall-clock value is still UTC.
        assert row.due_at.replace(tzinfo=timezone.utc) == datetime(2026, 1, 8, tzinfo=timezone.utc)

    def test_is_idempotent(self, session, stock):
        snapshot = _make_snapshot(session, stock)
        create_pending_outcomes(session, snapshot)
        session.commit()

        second_call = create_pending_outcomes(session, snapshot)
        session.commit()

        assert second_call == []
        assert session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id).count() == len(
            EVALUATION_HORIZON_DAYS
        )


class TestEvaluateDueOutcomes:
    def test_not_yet_due_rows_are_left_alone(self, session, stock):
        snapshot = _make_snapshot(session, stock, evaluated_at=datetime.now(timezone.utc))
        create_pending_outcomes(session, snapshot)
        session.commit()

        summary = evaluate_due_outcomes(session, now=datetime.now(timezone.utc))

        assert summary.evaluated == 0
        assert summary.expired_no_data == 0
        assert summary.skipped_pending == 0  # not due yet -- not even considered, not counted as skipped
        rows = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id).all()
        assert all(row.status is RecommendationOutcomeStatus.PENDING for row in rows)

    def test_classifies_successful_when_target_hit_without_stop(self, session, stock):
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(
            session, stock, recommendation=RecommendationLabel.BUY,
            entry_price=100.0, target_price=110.0, stop_loss=90.0, evaluated_at=evaluated_at,
        )
        create_pending_outcomes(session, snapshot)
        session.commit()

        _add_bar(session, stock, evaluated_at.date() + timedelta(days=1), high=112.0, low=99.0, close=111.0)
        session.commit()

        now = evaluated_at + timedelta(days=2)
        summary = evaluate_due_outcomes(session, now=now)

        assert summary.evaluated == 1  # only the 1-day horizon is due at `now`
        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=1).one()
        assert row.status is RecommendationOutcomeStatus.SUCCESSFUL
        assert row.hit_target is True
        assert row.hit_stop is False
        assert row.price_at_evaluation == pytest.approx(111.0)
        assert row.return_pct == pytest.approx(11.0)
        assert row.evaluated_at.replace(tzinfo=timezone.utc) == now

    def test_classifies_failed_when_stop_hit_without_target(self, session, stock):
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(
            session, stock, recommendation=RecommendationLabel.BUY,
            entry_price=100.0, target_price=110.0, stop_loss=90.0, evaluated_at=evaluated_at,
        )
        create_pending_outcomes(session, snapshot)
        session.commit()

        _add_bar(session, stock, evaluated_at.date() + timedelta(days=1), high=101.0, low=88.0, close=89.0)
        session.commit()

        summary = evaluate_due_outcomes(session, now=evaluated_at + timedelta(days=2))

        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=1).one()
        assert row.status is RecommendationOutcomeStatus.FAILED
        assert row.hit_target is False
        assert row.hit_stop is True
        assert summary.evaluated == 1

    def test_classifies_partial_when_both_target_and_stop_touched(self, session, stock):
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(
            session, stock, recommendation=RecommendationLabel.BUY,
            entry_price=100.0, target_price=110.0, stop_loss=90.0, evaluated_at=evaluated_at,
        )
        create_pending_outcomes(session, snapshot)
        session.commit()

        _add_bar(session, stock, evaluated_at.date() + timedelta(days=1), high=112.0, low=88.0, close=100.0)
        session.commit()

        evaluate_due_outcomes(session, now=evaluated_at + timedelta(days=2))

        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=1).one()
        assert row.status is RecommendationOutcomeStatus.PARTIAL
        assert row.hit_target is True
        assert row.hit_stop is True

    def test_classifies_partial_when_neither_threshold_reached(self, session, stock):
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(
            session, stock, recommendation=RecommendationLabel.BUY,
            entry_price=100.0, target_price=110.0, stop_loss=90.0, evaluated_at=evaluated_at,
        )
        create_pending_outcomes(session, snapshot)
        session.commit()

        _add_bar(session, stock, evaluated_at.date() + timedelta(days=1), high=103.0, low=98.0, close=102.0)
        session.commit()

        evaluate_due_outcomes(session, now=evaluated_at + timedelta(days=2))

        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=1).one()
        assert row.status is RecommendationOutcomeStatus.PARTIAL
        assert row.hit_target is False
        assert row.hit_stop is False
        assert row.return_pct == pytest.approx(2.0)

    def test_classifies_expired_when_no_target_or_stop_set(self, session, stock):
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(
            session, stock, recommendation=RecommendationLabel.HOLD,
            entry_price=100.0, target_price=None, stop_loss=None, evaluated_at=evaluated_at,
        )
        create_pending_outcomes(session, snapshot)
        session.commit()

        _add_bar(session, stock, evaluated_at.date() + timedelta(days=1), high=101.0, low=99.0, close=100.5)
        session.commit()

        evaluate_due_outcomes(session, now=evaluated_at + timedelta(days=2))

        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=1).one()
        assert row.status is RecommendationOutcomeStatus.EXPIRED
        assert row.hit_target is None
        assert row.hit_stop is None

    def test_due_row_with_no_forward_data_yet_stays_pending_within_grace_period(self, session, stock, monkeypatch):
        monkeypatch.setenv("OUTCOME_EVALUATION_STALE_GRACE_DAYS", "14")
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(session, stock, evaluated_at=evaluated_at)
        create_pending_outcomes(session, snapshot)
        session.commit()
        # No price bars ingested at all -- data-ingestion lag, not permanent absence.

        summary = evaluate_due_outcomes(session, now=evaluated_at + timedelta(days=2))

        assert summary.evaluated == 0
        assert summary.expired_no_data == 0
        assert summary.skipped_pending == 1
        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=1).one()
        assert row.status is RecommendationOutcomeStatus.PENDING

    def test_due_row_with_no_forward_data_past_grace_period_expires(self, session, stock, monkeypatch):
        monkeypatch.setenv("OUTCOME_EVALUATION_STALE_GRACE_DAYS", "14")
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(session, stock, evaluated_at=evaluated_at)
        create_pending_outcomes(session, snapshot)
        session.commit()

        summary = evaluate_due_outcomes(session, now=evaluated_at + timedelta(days=1, hours=1) + timedelta(days=14, hours=1))

        row = session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id, evaluation_horizon_days=1).one()
        assert row.status is RecommendationOutcomeStatus.EXPIRED
        assert row.price_at_evaluation is None
        assert summary.expired_no_data == 1

    def test_evaluates_multiple_due_rows_in_one_cycle(self, session, stock):
        evaluated_at = datetime(2026, 1, 1, tzinfo=timezone.utc)
        snapshot = _make_snapshot(session, stock, evaluated_at=evaluated_at)
        create_pending_outcomes(session, snapshot)
        session.commit()

        for offset in range(1, 8):
            _add_bar(
                session, stock, evaluated_at.date() + timedelta(days=offset),
                high=105.0, low=99.0, close=101.0,
            )
        session.commit()

        summary = evaluate_due_outcomes(session, now=evaluated_at + timedelta(days=8))

        # Horizons 1, 3, 7 are due within 8 days; 14/30/60/90 are not.
        assert summary.evaluated == 3
        due_statuses = {
            row.evaluation_horizon_days: row.status
            for row in session.query(RecommendationOutcome).filter_by(snapshot_id=snapshot.id).all()
        }
        assert due_statuses[1] is not RecommendationOutcomeStatus.PENDING
        assert due_statuses[3] is not RecommendationOutcomeStatus.PENDING
        assert due_statuses[7] is not RecommendationOutcomeStatus.PENDING
        assert due_statuses[14] is RecommendationOutcomeStatus.PENDING
