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
from src.domain.models import (
    NON_RESOLVING_STATUSES,
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    PriceBar,
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
    decision="BUY_CANDIDATE",
    decision_timestamp=None,
    current_price=100.0,
    entry_zone_low=95.0,
    entry_zone_high=100.0,
    target_1=110.0,
    target_2=120.0,
    target_3=130.0,
    stop_loss=90.0,
    expected_holding_period_max_days=None,
    validation_session_id=None,
    engine_sha=None,
    config_hash=None,
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
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
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
        engine_sha=engine_sha,
        config_hash=config_hash,
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
        # BASIRAH LIVE VALIDATION TRACKING: entry_price is never assumed
        # to be the signal price -- it stays unset until price actually
        # trades into the entry zone.
        assert outcome.entry_price is None
        assert outcome.entry_triggered is False
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


class TestEntryTriggeredGating:
    """BASIRAH LIVE VALIDATION TRACKING: the outcome evaluator must
    never assume a fill at the signal price -- target/stop tracking
    only begins once price has genuinely traded into
    entry_zone_low..entry_zone_high. Regression coverage for the exact
    bug this fixes: previously, a stop-level touch before price ever
    reached the entry zone was wrongly scored as a real STOP_LOSS_HIT."""

    def test_regression_stop_touch_before_entry_is_invalidated_not_a_loss(self, session, stock):
        """The core bug: entry zone is 95-100, but the very first (and
        only) forward bar never trades above 92 -- it touches
        stop_loss (90) without ever having entered the recommended
        zone. Before this fix this was wrongly scored STOP_LOSS_HIT;
        it must now be INVALIDATED, never counted as a loss."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=92.0, low=88.0, close=89.0)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.INVALIDATED
        assert row.invalidated is True
        assert row.invalidated_at is not None
        assert row.entry_triggered is False
        assert row.stop_loss_hit is None  # stop/target tracking never even ran
        assert row.status in NON_RESOLVING_STATUSES

    def test_regression_gap_through_stop_then_later_recovery_into_zone_is_invalidated(self, session, stock):
        """A second, subtler variant of the same class of bug: the stop
        breach and the later entry-zone touch are on DIFFERENT bars,
        so the original fix's "no entry found anywhere" check never
        even ran (`entered_at` WAS found -- just too late). Day 2 gaps
        straight through both the zone (95-100) and the stop (90)
        without its own low/high range ever overlapping the zone
        itself; day 3 recovers and genuinely trades within the zone.
        Before this fix, `entered_mask` found day 3's touch and
        happily marked the row entry_triggered from there, silently
        ignoring that the setup had already died on day 2 -- corrupting
        the row into a trackable (and potentially winning) trade that
        should never have existed."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=92.0, low=85.0, close=86.0)
        _add_bar(session, stock, datetime(2026, 1, 3), high=99.0, low=96.0, close=98.0)
        session.commit()

        now = datetime(2026, 1, 4, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.INVALIDATED
        assert row.invalidated is True
        # SQLite does not round-trip a timezone-aware DateTime (see
        # _as_utc's own docstring) -- compare naive, matching this
        # file's existing convention for exact-timestamp assertions.
        assert row.invalidated_at == datetime(2026, 1, 2, 16, 0)
        assert row.entry_triggered is False
        assert row.entry_triggered_at is None
        assert row.status in NON_RESOLVING_STATUSES

    def test_stop_breach_on_or_after_the_entry_bar_is_ordinary_post_entry_tracking(self, session, stock):
        """Guards the fix above from over-firing: once price has
        genuinely entered the zone, a LATER stop breach is a normal
        losing trade (STOP_LOSS_HIT), not a pre-entry invalidation --
        the new pre-entry-only window must not swallow legitimate
        post-entry stop hits."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=99.0, low=96.0, close=98.0)
        _add_bar(session, stock, datetime(2026, 1, 3), high=91.0, low=88.0, close=89.0)
        session.commit()

        now = datetime(2026, 1, 4, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.entry_triggered is True
        assert row.entry_triggered_at == datetime(2026, 1, 2, 16, 0)
        assert row.status == DecisionV2OutcomeStatus.STOP_LOSS_HIT
        assert row.invalidated is False

    def test_entry_never_triggered_when_horizon_elapses_untouched(self, session, stock):
        """Price stays entirely above the entry zone for the whole
        horizon -- never a real position, never a loss, never a win."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, stop_loss=90.0,
            expected_holding_period_max_days=5,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=115.0, low=105.0, close=110.0)
        session.commit()

        now = datetime(2026, 1, 10, tzinfo=timezone.utc)  # past due_at (2026-01-06)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.ENTRY_NEVER_TRIGGERED
        assert row.entry_triggered is False
        assert row.status in NON_RESOLVING_STATUSES

    def test_stays_pending_pre_entry_within_horizon(self, session, stock):
        """Price hasn't reached the zone yet, but the horizon hasn't
        elapsed either -- still genuinely open, not a terminal state."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, stop_loss=90.0,
            expected_holding_period_max_days=30,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=115.0, low=105.0, close=110.0)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        summary = evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.PENDING
        assert row.entry_triggered is False
        assert summary.still_pending == 1

    def test_entry_triggers_on_a_later_bar_then_target_hit_from_there(self, session, stock):
        """Bar 1 never reaches the zone; bar 2 trades into it and also
        touches target_1 -- entry_triggered_at must be bar 2's
        timestamp, and the win must be scored, not missed."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, target_1=110.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=115.0, low=105.0, close=110.0)  # never in zone
        _add_bar(session, stock, datetime(2026, 1, 3), high=112.0, low=97.0, close=111.0)  # enters zone + hits T1
        session.commit()

        now = datetime(2026, 1, 4, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.entry_triggered is True
        # SQLite (this test's in-memory engine) does not round-trip a
        # timezone-aware DateTime faithfully -- compare naively,
        # matching this file's other datetime assertions (e.g. due_at).
        assert row.entry_triggered_at.replace(tzinfo=None) == datetime(2026, 1, 3, 16, 0)
        assert row.status == DecisionV2OutcomeStatus.TARGET_1_HIT
        assert row.highest_price_after_entry == pytest.approx(112.0)
        assert row.lowest_price_after_entry == pytest.approx(97.0)

    def test_entry_price_uses_conservative_zone_high_not_signal_price(self, session, stock):
        """Signal price and entry zone can genuinely differ (e.g. a
        WAIT_FOR_PULLBACK-style zone below the price at signal time in
        real Decision V2 output) -- entry_price must reflect the real,
        conservative assumed fill (zone top), not the original signal
        price, once triggered."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            current_price=105.0, entry_zone_low=95.0, entry_zone_high=98.0,
            target_1=110.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        _add_bar(session, stock, datetime(2026, 1, 2), high=112.0, low=96.0, close=111.0)
        session.commit()

        now = datetime(2026, 1, 3, tzinfo=timezone.utc)
        evaluate_pending_outcomes(session, now=now)

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.entry_triggered is True
        assert row.entry_price == pytest.approx(98.0)  # entry_zone_high, never 105.0 (the signal price)


class TestIndependentSignalGrouping:
    """QUALITY PROOF INSTRUMENTATION HARDENING (2026-09-06), P1-A:
    duplicate-signal / independent-episode grouping. Purely a
    measurement-layer concern -- every row below is still created
    exactly as it always was (is_actionable_buy_decision/idempotency
    behavior unchanged); these tests only cover the new
    independent_signal_key/is_independent_signal bookkeeping. The
    grouping decision is made once, at creation time, from only
    already-existing PENDING rows -- never from a future outcome."""

    def test_first_signal_for_a_symbol_is_independent(self, session, stock):
        snapshot = _make_snapshot(session, stock, engine_sha="sha1", config_hash="cfg1")
        outcome = create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        assert outcome.is_independent_signal is True
        assert outcome.independent_signal_key is not None

    def test_exact_duplicate_emission_while_still_pending_is_not_independent(self, session, stock):
        s1 = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            engine_sha="sha1", config_hash="cfg1",
        )
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()

        s2 = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 2, tzinfo=timezone.utc),
            engine_sha="sha1", config_hash="cfg1",
        )
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o1.is_independent_signal is True
        assert o2.is_independent_signal is False
        assert o2.independent_signal_key == o1.independent_signal_key

    def test_repeated_signal_while_previous_trade_idea_remains_active_is_not_independent(self, session, stock):
        s1 = _make_snapshot(session, stock, engine_sha="sha1", config_hash="cfg1")
        create_pending_decision_v2_outcome(session, s1)
        session.commit()

        s2 = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
            engine_sha="sha1", config_hash="cfg1",
        )
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o2.is_independent_signal is False

    def test_genuinely_new_trade_idea_after_prior_lifecycle_complete_is_independent(self, session, stock):
        s1 = _make_snapshot(session, stock, engine_sha="sha1", config_hash="cfg1")
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        o1.status = DecisionV2OutcomeStatus.TARGET_1_HIT  # prior episode fully resolved
        session.commit()

        s2 = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 10, tzinfo=timezone.utc),
            engine_sha="sha1", config_hash="cfg1",
        )
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o2.is_independent_signal is True
        assert o2.independent_signal_key != o1.independent_signal_key

    def test_different_symbols_are_each_independent(self, session):
        stock_a = Stock(symbol="1111", name_en="A")
        stock_b = Stock(symbol="3333", name_en="B")
        session.add_all([stock_a, stock_b])
        session.commit()

        sa = _make_snapshot(session, stock_a, engine_sha="sha1", config_hash="cfg1")
        sb = _make_snapshot(session, stock_b, engine_sha="sha1", config_hash="cfg1")
        oa = create_pending_decision_v2_outcome(session, sa)
        ob = create_pending_decision_v2_outcome(session, sb)
        session.commit()

        assert oa.is_independent_signal is True
        assert ob.is_independent_signal is True
        assert oa.independent_signal_key != ob.independent_signal_key

    def test_same_symbol_different_engine_version_is_independent_despite_open_pending(self, session, stock):
        s1 = _make_snapshot(session, stock, engine_sha="sha1", config_hash="cfg1")
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()

        s2 = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
            engine_sha="sha2", config_hash="cfg1",
        )
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        # A code-version change always starts a new episode, even though
        # a PENDING row for the same symbol is still open -- mixing
        # engine versions within one episode would corrupt cohort isolation.
        assert o2.is_independent_signal is True
        assert o2.independent_signal_key != o1.independent_signal_key

    def test_same_symbol_different_config_version_is_independent_despite_open_pending(self, session, stock):
        s1 = _make_snapshot(session, stock, engine_sha="sha1", config_hash="cfgA")
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()

        s2 = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
            engine_sha="sha1", config_hash="cfgB",
        )
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o2.is_independent_signal is True
        assert o2.independent_signal_key != o1.independent_signal_key

    def test_legacy_row_without_engine_metadata_never_falsely_links(self, session, stock):
        legacy_snapshot = _make_snapshot(session, stock, engine_sha=None, config_hash=None)
        legacy_outcome = create_pending_decision_v2_outcome(session, legacy_snapshot)
        session.commit()

        # Cannot positively identify a legacy row's episode -> conservative
        # fresh episode, never a silent guess.
        assert legacy_outcome.is_independent_signal is True
        assert legacy_outcome.independent_signal_key is not None

        versioned_snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 5, tzinfo=timezone.utc),
            engine_sha="sha1", config_hash="cfg1",
        )
        versioned_outcome = create_pending_decision_v2_outcome(session, versioned_snapshot)
        session.commit()

        assert versioned_outcome.is_independent_signal is True
        assert versioned_outcome.independent_signal_key != legacy_outcome.independent_signal_key

    def test_grouping_decision_is_frozen_and_never_uses_future_outcome_information(self, session, stock):
        s1 = _make_snapshot(session, stock, engine_sha="sha1", config_hash="cfg1")
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        key_before, flag_before = o1.independent_signal_key, o1.is_independent_signal

        # A real future outcome occurs -- must have zero effect on the
        # already-frozen grouping identity.
        o1.status = DecisionV2OutcomeStatus.STOP_LOSS_HIT
        session.commit()

        assert o1.independent_signal_key == key_before
        assert o1.is_independent_signal == flag_before

    def test_raw_vs_independent_count_is_not_inflated_by_repeated_emission(self, session, stock):
        s1 = _make_snapshot(session, stock, engine_sha="sha1", config_hash="cfg1")
        create_pending_decision_v2_outcome(session, s1)
        session.commit()
        for day in range(2, 6):
            s = _make_snapshot(
                session, stock, decision_timestamp=datetime(2026, 1, day, tzinfo=timezone.utc),
                engine_sha="sha1", config_hash="cfg1",
            )
            create_pending_decision_v2_outcome(session, s)
            session.commit()

        raw_signal_count = session.query(DecisionV2Outcome).count()
        independent_signal_count = (
            session.query(DecisionV2Outcome).filter_by(is_independent_signal=True).count()
        )
        assert raw_signal_count == 5
        assert independent_signal_count == 1


class TestMaxFavorableAdverseExcursion:
    """QUALITY PROOF INSTRUMENTATION HARDENING (2026-09-06), P1-C:
    MFE/MAE correctness. `max_favorable_excursion_pct`/
    `max_adverse_excursion_pct` already existed and were already
    correctly post-entry-only; these tests additionally prove the
    excursion window never extends past the bar that actually resolved
    the trade (a real, provable gap this hardening closes), and cover
    the new R-multiple representation."""

    def test_excursion_is_none_before_entry_triggers_no_matter_how_favorable_the_move(self, session, stock):
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, target_1=110.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()
        _add_bar(session, stock, datetime(2026, 1, 2), high=150.0, low=140.0, close=145.0)  # never enters zone
        session.commit()

        evaluate_pending_outcomes(session, now=datetime(2026, 1, 3, tzinfo=timezone.utc))

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.entry_triggered is False
        assert row.max_favorable_excursion_pct is None
        assert row.max_favorable_excursion_r is None
        assert row.max_adverse_excursion_r is None

    def test_excursion_never_includes_bars_after_the_resolving_touch(self, session, stock):
        """Reproduces a delayed/batched evaluation pass: the target was
        actually touched on day 3, but this evaluation only runs on
        day 5, by which point an unrelated, enormous later move (day 4)
        has occurred. MFE must reflect only price action through the
        resolving bar (day 3), never the day-4 spike -- otherwise a
        stale/delayed scheduler run would silently corrupt every
        already-closed trade's excursion statistics."""
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, target_1=110.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()
        _add_bar(session, stock, datetime(2026, 1, 2), high=100.0, low=96.0, close=99.0)  # entry day
        _add_bar(session, stock, datetime(2026, 1, 3), high=111.0, low=98.0, close=110.0)  # target hit here
        _add_bar(session, stock, datetime(2026, 1, 4), high=500.0, low=1.0, close=200.0)  # must NOT leak in
        session.commit()

        evaluate_pending_outcomes(session, now=datetime(2026, 1, 5, tzinfo=timezone.utc))

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.status == DecisionV2OutcomeStatus.TARGET_1_HIT
        entry_price = float(row.entry_price)
        expected_mfe_pct = (111.0 - entry_price) / entry_price * 100.0
        assert float(row.max_favorable_excursion_pct) == pytest.approx(expected_mfe_pct, abs=0.01)

    def test_r_multiple_matches_pct_and_risk_distance(self, session, stock):
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=95.0, entry_zone_high=100.0, target_1=130.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()
        _add_bar(session, stock, datetime(2026, 1, 2), high=100.0, low=96.0, close=99.0)
        _add_bar(session, stock, datetime(2026, 1, 3), high=115.0, low=94.0, close=110.0)
        session.commit()

        evaluate_pending_outcomes(session, now=datetime(2026, 1, 4, tzinfo=timezone.utc))

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        entry_price = float(row.entry_price)
        risk_distance = entry_price - 90.0
        expected_mfe_pct = (115.0 - entry_price) / entry_price * 100.0
        expected_mfe_r = (expected_mfe_pct / 100.0 * entry_price) / risk_distance
        assert row.max_favorable_excursion_r == pytest.approx(expected_mfe_r, abs=0.001)

    def test_missing_ohlcv_leaves_excursion_none_never_zero(self, session, stock):
        snapshot = _make_snapshot(session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc))
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()

        evaluate_pending_outcomes(session, now=datetime(2026, 1, 2, tzinfo=timezone.utc))

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.max_favorable_excursion_pct is None
        assert row.max_adverse_excursion_pct is None

    def test_zero_risk_distance_gives_none_r_multiple_not_a_fabricated_number(self, session, stock):
        snapshot = _make_snapshot(
            session, stock, decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
            entry_zone_low=90.0, entry_zone_high=90.0, target_1=110.0, stop_loss=90.0,
        )
        create_pending_decision_v2_outcome(session, snapshot)
        session.commit()
        _add_bar(session, stock, datetime(2026, 1, 2), high=95.0, low=90.0, close=93.0)
        session.commit()

        evaluate_pending_outcomes(session, now=datetime(2026, 1, 3, tzinfo=timezone.utc))

        row = session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=snapshot.id).one()
        assert row.entry_triggered is True
        assert row.max_favorable_excursion_r is None
        assert row.max_adverse_excursion_r is None
