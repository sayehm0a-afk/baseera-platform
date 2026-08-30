"""Unit tests for src.market_data.ingestion.outcome_tracking -- the
OHLCV persistence / post-signal outcome-tracking fix (2026-08-23).
Real SQLAlchemy ORM against an in-memory SQLite DB, matching the
established fixture pattern in
tests/unit/ai_evolution/test_decision_v2_outcome.py (same models, same
session-per-test discipline)."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, PriceBar, Stock, Timeframe
from src.market_data.ingestion.outcome_tracking import (
    oldest_pending_signal_decision_timestamp,
    pending_signal_symbols,
    pending_signals_with_zero_post_signal_bars,
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


def _make_snapshot(session, stock, decision_timestamp, decision="BUY_CANDIDATE"):
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
        current_price=100.0,
        entry_zone_low=95.0,
        entry_zone_high=100.0,
        target_1=110.0,
        target_2=120.0,
        target_3=130.0,
        stop_loss=90.0,
        market_status="OPEN",
        decision_timestamp=decision_timestamp,
        analysis_version="2.0.0",
        data_source="test",
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _make_pending_outcome(session, snapshot, due_at=None):
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id,
        symbol=snapshot.symbol,
        due_at=due_at or datetime(2026, 2, 1, tzinfo=timezone.utc),
        status=DecisionV2OutcomeStatus.PENDING,
    )
    session.add(outcome)
    session.flush()
    return outcome


def _add_bar(session, stock, ts):
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=ts,
            open=100,
            high=101,
            low=99,
            close=100.5,
            volume=1000,
            source="test",
            is_synthetic=False,
        )
    )
    session.flush()


class TestPendingSignalSymbols:
    """TEST 1 (mandate): a real signal exists -> its symbol is enrolled
    in the OHLCV tracking universe. TEST 12: a historical (not just
    today's) unresolved signal remains tracked. TEST 13: a resolved
    signal is no longer part of the pending set."""

    def test_symbol_with_pending_outcome_is_returned(self, session):
        stock = Stock(symbol="2222", name_en="Stock 2222", is_active=True)
        session.add(stock)
        session.commit()
        snapshot = _make_snapshot(session, stock, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _make_pending_outcome(session, snapshot)

        assert pending_signal_symbols(session) == ["2222"]

    def test_a_symbol_deactivated_since_its_signal_is_still_tracked(self, session):
        """The exact production gap this fix closes: `Stock.is_active`
        turning False for any reason must not silently stop OHLCV
        coverage for a symbol with a real outstanding signal."""
        stock = Stock(symbol="6060", name_en="Stock 6060", is_active=False)
        session.add(stock)
        session.commit()
        snapshot = _make_snapshot(session, stock, datetime(2026, 8, 20, tzinfo=timezone.utc))
        _make_pending_outcome(session, snapshot)

        assert pending_signal_symbols(session) == ["6060"]

    def test_resolved_outcome_is_not_in_the_pending_set(self, session):
        stock = Stock(symbol="1120", name_en="Stock 1120", is_active=True)
        session.add(stock)
        session.commit()
        snapshot = _make_snapshot(session, stock, datetime(2026, 1, 1, tzinfo=timezone.utc))
        outcome = _make_pending_outcome(session, snapshot)
        outcome.status = DecisionV2OutcomeStatus.TARGET_1_HIT
        session.commit()

        assert pending_signal_symbols(session) == []

    def test_two_pending_signals_for_the_same_symbol_appear_once(self, session):
        """TEST 11 (mandate): multiple outstanding signals for one
        symbol must not cause that symbol to be requested more than
        once by the OHLCV job."""
        stock = Stock(symbol="2222", name_en="Stock 2222", is_active=True)
        session.add(stock)
        session.commit()
        s1 = _make_snapshot(session, stock, datetime(2026, 1, 1, tzinfo=timezone.utc))
        s2 = _make_snapshot(session, stock, datetime(2026, 1, 5, tzinfo=timezone.utc))
        _make_pending_outcome(session, s1)
        _make_pending_outcome(session, s2)

        assert pending_signal_symbols(session) == ["2222"]

    def test_no_pending_outcomes_returns_empty_list(self, session):
        assert pending_signal_symbols(session) == []

    def test_ordered_oldest_pending_first(self, session):
        """PR #107 Phase 6: previously an unordered DISTINCT query --
        Shadow's recurrent candidate selection fills bounded slots from
        this list, so an unspecified order was a latent determinism
        gap. Now explicitly ordered by each symbol's own earliest still-
        PENDING outcome's `created_at`, oldest first."""
        newer_stock = Stock(symbol="4260", name_en="Stock 4260", is_active=True)
        older_stock = Stock(symbol="6004", name_en="Stock 6004", is_active=True)
        session.add_all([newer_stock, older_stock])
        session.commit()

        newer_snapshot = _make_snapshot(session, newer_stock, datetime(2026, 8, 26, tzinfo=timezone.utc))
        older_snapshot = _make_snapshot(session, older_stock, datetime(2026, 8, 18, tzinfo=timezone.utc))

        newer_outcome = _make_pending_outcome(session, newer_snapshot)
        newer_outcome.created_at = datetime(2026, 8, 26, 7, 0, tzinfo=timezone.utc)
        older_outcome = _make_pending_outcome(session, older_snapshot)
        older_outcome.created_at = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
        session.commit()

        assert pending_signal_symbols(session) == ["6004", "4260"]

    def test_tie_break_is_symbol_ascending(self, session):
        stock_b = Stock(symbol="4260", name_en="Stock 4260", is_active=True)
        stock_a = Stock(symbol="1180", name_en="Stock 1180", is_active=True)
        session.add_all([stock_b, stock_a])
        session.commit()

        same_ts = datetime(2026, 8, 18, 10, 0, tzinfo=timezone.utc)
        snapshot_b = _make_snapshot(session, stock_b, same_ts)
        snapshot_a = _make_snapshot(session, stock_a, same_ts)
        outcome_b = _make_pending_outcome(session, snapshot_b)
        outcome_b.created_at = same_ts
        outcome_a = _make_pending_outcome(session, snapshot_a)
        outcome_a.created_at = same_ts
        session.commit()

        assert pending_signal_symbols(session) == ["1180", "4260"]

    def test_ordering_change_does_not_alter_which_symbols_qualify(self, session):
        """The set of returned symbols is identical to the pre-PR-107
        (unordered) behavior -- only iteration order changed."""
        stock = Stock(symbol="2222", name_en="Stock 2222", is_active=True)
        session.add(stock)
        session.commit()
        snapshot = _make_snapshot(session, stock, datetime(2026, 1, 1, tzinfo=timezone.utc))
        _make_pending_outcome(session, snapshot)

        assert set(pending_signal_symbols(session)) == {"2222"}


class TestOldestPendingSignalDecisionTimestamp:
    def test_returns_the_earliest_decision_timestamp_among_pending_rows(self, session):
        stock = Stock(symbol="2222", name_en="Stock 2222", is_active=True)
        session.add(stock)
        session.commit()
        older = _make_snapshot(session, stock, datetime(2026, 1, 1, tzinfo=timezone.utc))
        newer = _make_snapshot(session, stock, datetime(2026, 1, 10, tzinfo=timezone.utc))
        _make_pending_outcome(session, older)
        _make_pending_outcome(session, newer)

        result = oldest_pending_signal_decision_timestamp(session)
        assert result.replace(tzinfo=timezone.utc) == datetime(2026, 1, 1, tzinfo=timezone.utc)

    def test_none_when_nothing_pending(self, session):
        assert oldest_pending_signal_decision_timestamp(session) is None


class TestPendingSignalsWithZeroPostSignalBars:
    """The direct, always-accurate diagnostic that would have caught
    the real production gap (a job reporting `status=success` while
    silently making zero progress for an already-tracked symbol)."""

    def test_flags_a_signal_with_no_bar_after_its_decision_timestamp(self, session):
        stock = Stock(symbol="6060", name_en="Stock 6060", is_active=True)
        session.add(stock)
        session.commit()
        decision_ts = datetime(2026, 8, 20, 8, 53, tzinfo=timezone.utc)
        snapshot = _make_snapshot(session, stock, decision_ts)
        _make_pending_outcome(session, snapshot)
        # A bar exists, but strictly *before* the signal -- must still count as zero post-signal bars.
        _add_bar(session, stock, datetime(2026, 8, 19, 16, 0, tzinfo=timezone.utc))

        flagged = pending_signals_with_zero_post_signal_bars(session)
        assert [row["symbol"] for row in flagged] == ["6060"]
        assert flagged[0]["decision_v2_snapshot_id"] == snapshot.id

    def test_does_not_flag_a_signal_with_a_real_post_signal_bar(self, session):
        stock = Stock(symbol="2222", name_en="Stock 2222", is_active=True)
        session.add(stock)
        session.commit()
        decision_ts = datetime(2026, 8, 20, 8, 53, tzinfo=timezone.utc)
        snapshot = _make_snapshot(session, stock, decision_ts)
        _make_pending_outcome(session, snapshot)
        _add_bar(session, stock, datetime(2026, 8, 21, 16, 0, tzinfo=timezone.utc))

        assert pending_signals_with_zero_post_signal_bars(session) == []

    def test_resolved_outcomes_are_never_flagged(self, session):
        stock = Stock(symbol="1120", name_en="Stock 1120", is_active=True)
        session.add(stock)
        session.commit()
        snapshot = _make_snapshot(session, stock, datetime(2026, 1, 1, tzinfo=timezone.utc))
        outcome = _make_pending_outcome(session, snapshot)
        outcome.status = DecisionV2OutcomeStatus.EXPIRED
        session.commit()

        assert pending_signals_with_zero_post_signal_bars(session) == []
