"""M10 unit tests: `DecisionV2Outcome` issuance/evaluation, correctly
linked to `DecisionV2Snapshot` (not the older `RecommendationSnapshot`),
with a status vocabulary that distinguishes target-specific hits,
stop-loss hits, and DATA_UNAVAILABLE. Real SQLAlchemy ORM against an
in-memory SQLite DB, matching the discipline of
tests/unit/ai_evolution/test_outcome_evaluation.py.
"""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.decision_v2_outcome_evaluation import (
    create_pending_decision_v2_outcome,
    evaluate_pending_outcomes,
    is_actionable_buy_decision,
)
from src.core.db.database import Base
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, PriceBar, Stock, Timeframe


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
    decision="BUY_CANDIDATE",
    decision_timestamp=None,
    current_price=100.0,
    target_1=110.0,
    target_2=120.0,
    target_3=130.0,
    stop_loss=90.0,
    expected_holding_period_max_days=None,
    validation_session_id=None,
):
    decision_timestamp = decision_timestamp or datetime(2026, 1, 1, tzinfo=timezone.utc)
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=70.0,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=current_price,
        target_1=target_1,
        target_2=target_2,
        target_3=target_3,
        stop_loss=stop_loss,
        expected_holding_period_max_days=expected_holding_period_max_days,
        market_status="OPEN",
        decision_timestamp=decision_timestamp,
        analysis_version="2.0.0",
        data_source="test",
        validation_session_id=validation_session_id,
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
    session.flush()


class TestIsActionableBuyDecision:
    def test_buy_like_decisions_are_actionable(self):
        assert is_actionable_buy_decision("STRONG_BUY_CANDIDATE") is True
        assert is_actionable_buy_decision("BUY_CANDIDATE") is True

    def test_non_buy_decisions_are_not_actionable(self):
        assert is_actionable_buy_decision("WATCH") is False
        assert is_actionable_buy_decision("HOLD") is False
        assert is_actionable_buy_decision("REJECT") is False


class TestCreatePendingDecisionV2Outcome:
    def test_creates_row_for_actionable_decision(self, session, stock):
        snapshot = _make_snapshot(session, stock, decision="BUY_CANDIDATE")

        outcome = create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        assert outcome is not None
        assert outcome.decision_v2_snapshot_id == snapshot.id
        assert outcome.status == DecisionV2OutcomeStatus.PENDING
        assert outcome.entry_price == snapshot.current_price
        assert outcome.symbol == "2222"

    def test_returns_none_for_non_actionable_decision(self, session, stock):
        snapshot = _make_snapshot(session, stock, decision="WATCH")

        outcome = create_pending_decision_v2_outcome(session, snapshot)

        assert outcome is None
        assert session.query(DecisionV2Outcome).count() == 0

    def test_idempotent_second_call_is_noop(self, session, stock):
        snapshot = _make_snapshot(session, stock)

        first = create_pending_decision_v2_outcome(session, snapshot)
        session.commit()
        second = create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        assert first is not None
        assert second is None
        assert session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).count() == 1

    def test_due_at_uses_expected_holding_period(self, session, stock):
        snapshot = _make_snapshot(
            session,
            stock,
            decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expected_holding_period_max_days=14,
        )

        outcome = create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        assert outcome.due_at == datetime(2026, 1, 15)

    def test_due_at_falls_back_to_default_horizon(self, session, stock):
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc)
        )

        outcome = create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        assert outcome.due_at == datetime(2026, 1, 31)

    def test_validation_session_id_is_carried_through(self, session, stock):
        snapshot = _make_snapshot(session, stock, validation_session_id=42)

        outcome = create_pending_decision_v2_outcome(session, snapshot, validation_session_id=42)
        session.commit()

        assert outcome.validation_session_id == 42


class TestEvaluatePendingOutcomes:
    def test_target_1_hit_before_stop(self, session, stock):
        snapshot = _make_snapshot(session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=112.0, low=98.0, close=111.0)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        summary = evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.TARGET_1_HIT
        assert row.target_1_hit is True
        assert row.first_event == "TARGET"
        assert row.return_pct == pytest.approx(10.0)
        assert summary.evaluated_terminal == 1

    def test_re_evaluating_a_terminal_row_is_a_no_op_and_never_mutates_the_snapshot(self, session, stock):
        """VAL-8: repeated scheduler cycles must not corrupt or alter an
        already-resolved outcome, and must never touch the immutable
        original DecisionV2Snapshot -- a terminal row is excluded from
        the PENDING query entirely on every subsequent pass."""
        snapshot = _make_snapshot(session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=112.0, low=98.0, close=111.0)
        session.commit()

        first_summary = evaluate_pending_outcomes(session, now=datetime(2026, 1, 3, tzinfo=timezone.utc))
        assert first_summary.evaluated_terminal == 1

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        first_status = row.status
        first_return_pct = row.return_pct
        first_target_1_hit_at = row.target_1_hit_at
        first_evaluated_at = row.evaluated_at

        snapshot_before = (
            snapshot.current_price, snapshot.target_1, snapshot.target_2,
            snapshot.target_3, snapshot.stop_loss, snapshot.decision,
        )

        # A later scheduler cycle, with the exact same real price data
        # still the only evidence available.
        second_summary = evaluate_pending_outcomes(session, now=datetime(2026, 1, 10, tzinfo=timezone.utc))
        assert second_summary.evaluated_terminal == 0  # already-terminal row never re-picked-up

        session.refresh(row)
        assert row.status == first_status
        assert row.return_pct == first_return_pct
        assert row.target_1_hit_at == first_target_1_hit_at
        assert row.evaluated_at == first_evaluated_at  # never re-stamped by the no-op pass

        session.refresh(snapshot)
        snapshot_after = (
            snapshot.current_price, snapshot.target_1, snapshot.target_2,
            snapshot.target_3, snapshot.stop_loss, snapshot.decision,
        )
        assert snapshot_after == snapshot_before

    def test_stop_loss_hit_before_target(self, session, stock):
        snapshot = _make_snapshot(session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=101.0, low=88.0, close=89.0)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.STOP_LOSS_HIT
        assert row.stop_loss_hit is True
        assert row.first_event == "STOP"
        assert row.return_pct == pytest.approx(-10.0)

    def test_same_bar_tie_is_partial_never_win_or_loss(self, session, stock):
        snapshot = _make_snapshot(session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        # Same bar touches both target_1 (110) and stop_loss (90) -- a
        # genuinely undecidable ordering with only daily OHLC.
        _add_bar(session, stock, datetime(2026, 1, 2), high=112.0, low=88.0, close=100.0)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.PARTIAL
        assert row.first_event == "TIE"
        assert row.return_pct is None

    def test_expires_when_due_and_nothing_decisive_happened(self, session, stock):
        snapshot = _make_snapshot(
            session,
            stock,
            decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            expected_holding_period_max_days=5,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=105.0, low=98.0, close=102.0)
        session.commit()

        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.EXPIRED
        assert row.return_pct == pytest.approx(2.0)

    def test_data_unavailable_after_stale_grace_period_never_a_win_or_loss(self, session, stock, monkeypatch):
        from src.ai_evolution import decision_v2_outcome_evaluation as mod

        monkeypatch.setattr(mod, "get_outcome_evaluation_stale_grace_days", lambda: 3)

        snapshot = _make_snapshot(session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()
        # Deliberately no PriceBar rows at all.

        now = datetime(2026, 1, 10, tzinfo=timezone.utc)
        summary = evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.DATA_UNAVAILABLE
        assert row.return_pct is None
        assert summary.data_unavailable == 1

    def test_stays_pending_within_stale_grace_period_with_no_data(self, session, stock, monkeypatch):
        from src.ai_evolution import decision_v2_outcome_evaluation as mod

        monkeypatch.setattr(mod, "get_outcome_evaluation_stale_grace_days", lambda: 30)

        snapshot = _make_snapshot(session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        summary = evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.PENDING
        assert summary.still_pending == 1

    def test_cancelled_when_snapshot_deleted(self, session, stock):
        snapshot = _make_snapshot(session, stock)
        outcome = create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        snapshot_id = snapshot.id
        session.delete(snapshot)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        summary = evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(id=outcome.id).one()
        assert row.status == DecisionV2OutcomeStatus.CANCELLED
        assert summary.cancelled == 1
        assert row.decision_v2_snapshot_id == snapshot_id
