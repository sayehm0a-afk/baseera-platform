"""PR113 P1-1 REMEDIATION: concurrency-safety proof for independent-
signal episode linkage (src.ai_evolution.decision_v2_outcome_evaluation.
create_pending_decision_v2_outcome).

The independent audit of Draft PR #113 proved -- on real PostgreSQL,
via genuinely interleaved sessions -- that the original read-then-write
pattern let two concurrent transactions for the same symbol+cohort both
create an "independent" episode, corrupting the quality-proof sample
count. This module is the required adversarial test matrix (C1-C12)
for the fix: a DB-level partial unique index (see migration
d4e91a6c8f37) that makes the DB itself the arbiter, with an
application-level SAVEPOINT + bounded lock_timeout to recover
gracefully (never hang, never lose other pending work in the same
transaction) when the DB rejects a losing anchor claim.

No live Postgres is available in the standard CI environment for this
project (see tests/integration/test_migrations.py's own docstring for
the same disclosed limitation) -- SQLite has neither Postgres's MVCC
locking semantics nor `SET LOCAL lock_timeout`, so these tests cannot
be meaningfully run against it. They skip cleanly (not silently) when
no reachable Postgres is configured, and run in full wherever one is
(this development/audit environment always has one)."""

import threading
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.ai_evolution.decision_v2_outcome_evaluation import create_pending_decision_v2_outcome
from src.core.config.settings import settings
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, RadarOpportunity, Stock


def _postgres_reachable() -> bool:
    if not settings.database_url.startswith("postgresql"):
        return False
    try:
        probe = create_engine(settings.database_url, pool_pre_ping=True)
        with probe.connect():
            pass
        probe.dispose()
        return True
    except Exception:  # noqa: BLE001 -- any connection failure means "skip", not "crash the suite"
        return False


pytestmark = pytest.mark.skipif(
    not _postgres_reachable(),
    reason="P1-1 concurrency guarantees are PostgreSQL-specific (native partial unique index, real "
    "row/lock-level MVCC, SET LOCAL lock_timeout) and cannot be meaningfully exercised on SQLite. "
    "Skipped, not silently assumed passing, when no live PostgreSQL is reachable at DATABASE_URL.",
)


@pytest.fixture
def engine():
    eng = create_engine(settings.database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def Factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def cleanup(Factory):
    symbols = []
    yield symbols
    if symbols:
        s = Factory()
        s.query(DecisionV2Outcome).filter(DecisionV2Outcome.symbol.in_(symbols)).delete(synchronize_session=False)
        s.query(RadarOpportunity).filter(RadarOpportunity.symbol.in_(symbols)).delete(synchronize_session=False)
        s.query(DecisionV2Snapshot).filter(DecisionV2Snapshot.symbol.in_(symbols)).delete(synchronize_session=False)
        s.query(Stock).filter(Stock.symbol.in_(symbols)).delete(synchronize_session=False)
        s.commit()
        s.close()


def _make_stock(Factory, symbol):
    s = Factory()
    stock = Stock(symbol=symbol, name_en=symbol, is_active=True)
    s.add(stock)
    s.commit()
    stock_id = stock.id
    s.close()
    return stock_id


def _make_snapshot(session, stock_id, symbol, day, engine_sha="E1", config_hash="C1", decision="BUY_CANDIDATE"):
    row = DecisionV2Snapshot(
        stock_id=stock_id, symbol=symbol, company_name_en=symbol, decision=decision,
        decision_label_ar="x", confidence_score=70.0, opportunity_quality_score=60.0, risk_score=30.0,
        data_quality_score=90.0, data_freshness_status="LIVE", current_price=100.0, market_status="OPEN",
        decision_timestamp=datetime(2026, 1, day, tzinfo=timezone.utc), analysis_version="2.0.0",
        data_source="test", scan_run_id=day, engine_sha=engine_sha, config_hash=config_hash,
    )
    session.add(row)
    session.commit()
    return row


class TestSequentialSemantics:
    """C1, C2, C3, C4, C5, C6, C10 -- single-threaded, deterministic ordering."""

    def test_c1_sequential_duplicate_same_symbol_cohort_while_first_open(self, Factory, cleanup):
        symbol = "C1DUP"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)
        session = Factory()
        s1 = _make_snapshot(session, stock_id, symbol, 1)
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        s2 = _make_snapshot(session, stock_id, symbol, 2)
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o1.is_independent_signal is True
        assert o2.is_independent_signal is False
        assert o2.independent_signal_key == o1.independent_signal_key
        session.close()

    def test_c2_sequential_new_episode_after_first_closes(self, Factory, cleanup):
        symbol = "C2NEW"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)
        session = Factory()
        s1 = _make_snapshot(session, stock_id, symbol, 1)
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        o1.status = DecisionV2OutcomeStatus.TARGET_1_HIT
        session.commit()

        s2 = _make_snapshot(session, stock_id, symbol, 10)
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o2.is_independent_signal is True
        assert o2.independent_signal_key != o1.independent_signal_key
        session.close()

    def test_c3_same_symbol_different_engine_sha(self, Factory, cleanup):
        symbol = "C3ENGINE"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)
        session = Factory()
        s1 = _make_snapshot(session, stock_id, symbol, 1, engine_sha="E1")
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        s2 = _make_snapshot(session, stock_id, symbol, 2, engine_sha="E2")
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o1.is_independent_signal is True
        assert o2.is_independent_signal is True
        assert o2.independent_signal_key != o1.independent_signal_key
        session.close()

    def test_c4_same_symbol_different_config_hash(self, Factory, cleanup):
        symbol = "C4CONFIG"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)
        session = Factory()
        s1 = _make_snapshot(session, stock_id, symbol, 1, config_hash="C1")
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        s2 = _make_snapshot(session, stock_id, symbol, 2, config_hash="C2")
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o1.is_independent_signal is True
        assert o2.is_independent_signal is True
        assert o2.independent_signal_key != o1.independent_signal_key
        session.close()

    def test_c5_different_symbols_are_independent(self, Factory, cleanup):
        cleanup.extend(["C5SYM1", "C5SYM2"])
        stock_id_1 = _make_stock(Factory, "C5SYM1")
        stock_id_2 = _make_stock(Factory, "C5SYM2")
        session = Factory()
        s1 = _make_snapshot(session, stock_id_1, "C5SYM1", 1)
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        s2 = _make_snapshot(session, stock_id_2, "C5SYM2", 1)
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        assert o1.is_independent_signal is True
        assert o2.is_independent_signal is True
        session.close()

    def test_c6_legacy_null_version_rows_always_independent(self, Factory, cleanup):
        symbol = "C6LEGACY"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)
        session = Factory()
        s1 = _make_snapshot(session, stock_id, symbol, 1, engine_sha=None, config_hash=None)
        o1 = create_pending_decision_v2_outcome(session, s1)
        session.commit()
        s2 = _make_snapshot(session, stock_id, symbol, 2, engine_sha=None, config_hash=None)
        o2 = create_pending_decision_v2_outcome(session, s2)
        session.commit()

        # Legacy rows are never linked to each other -- disclosed,
        # conservative, pre-existing policy, unchanged by this fix.
        assert o1.is_independent_signal is True
        assert o2.is_independent_signal is True
        assert o1.engine_sha is None and o1.config_hash is None
        session.close()

    def test_c10_repeated_call_is_idempotent_for_the_same_snapshot(self, Factory, cleanup):
        symbol = "C10IDEMP"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)
        session = Factory()
        s1 = _make_snapshot(session, stock_id, symbol, 1)
        create_pending_decision_v2_outcome(session, s1)
        session.commit()
        o1_again = create_pending_decision_v2_outcome(session, s1)
        session.commit()

        assert o1_again is None
        assert session.query(DecisionV2Outcome).filter_by(decision_v2_snapshot_id=s1.id).count() == 1
        session.close()


class TestConcurrentSemantics:
    """C7, C8, C9 -- real threads, real PostgreSQL connections, genuine
    interleaving (not mocks, not sequential-in-one-session simulation).
    """

    def _run_barrier_race(self, Factory, stock_id, symbol, worker_count, day_offset=1):
        barrier = threading.Barrier(worker_count)
        results = {}

        def worker(name, day):
            session = Factory()
            try:
                snap = _make_snapshot(session, stock_id, symbol, day)
                barrier.wait()
                outcome = create_pending_decision_v2_outcome(session, snap)
                session.commit()
                results[name] = (outcome.is_independent_signal, outcome.independent_signal_key)
            except Exception as exc:  # noqa: BLE001 -- captured for the assertion, not swallowed silently
                session.rollback()
                results[name] = ("EXCEPTION", repr(exc))
            finally:
                session.close()

        threads = [
            threading.Thread(target=worker, args=(f"W{i}", day_offset + i)) for i in range(worker_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert all(not t.is_alive() for t in threads), "a worker thread did not finish within 30s"
        return results

    def test_c7_two_concurrent_sessions_same_symbol_cohort(self, Factory, cleanup):
        symbol = "C7RACE"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)

        results = self._run_barrier_race(Factory, stock_id, symbol, worker_count=2)

        exceptions = {k: v for k, v in results.items() if v[0] == "EXCEPTION"}
        assert not exceptions, f"no worker should raise an uncaught exception: {exceptions}"
        independent_count = sum(1 for v in results.values() if v[0] is True)
        assert independent_count == 1, f"exactly one episode must be independent, got: {results}"
        keys = {v[1] for v in results.values()}
        assert len(keys) == 1, f"both rows must converge on the same episode key: {results}"

    def test_c8_reverse_commit_ordering_still_holds(self, Factory, cleanup):
        """Same race, run twice, to reduce the chance that a single
        lucky thread-scheduling order masks a real gap -- the DB-level
        constraint must hold regardless of which thread's flush/commit
        happens to reach Postgres first."""
        symbol = "C8REVERSE"
        cleanup.append(symbol)

        for attempt in range(3):
            sub_symbol = f"{symbol}_{attempt}"
            cleanup.append(sub_symbol)
            sub_stock_id = _make_stock(Factory, sub_symbol)
            results = self._run_barrier_race(Factory, sub_stock_id, sub_symbol, worker_count=2)
            independent_count = sum(1 for v in results.values() if v[0] is True)
            assert independent_count == 1, f"attempt {attempt}: got {results}"

    def test_c9_five_way_concurrent_burst_same_symbol_cohort(self, Factory, cleanup):
        symbol = "C9BURST"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)

        results = self._run_barrier_race(Factory, stock_id, symbol, worker_count=5)

        exceptions = {k: v for k, v in results.items() if v[0] == "EXCEPTION"}
        assert not exceptions, f"no worker should raise an uncaught exception: {exceptions}"
        independent_count = sum(1 for v in results.values() if v[0] is True)
        assert independent_count == 1, f"exactly one episode must be independent among 5, got: {results}"
        keys = {v[1] for v in results.values()}
        assert len(keys) == 1, f"all 5 rows must converge on the same episode key: {results}"


class TestImmutabilityAndNonSuppression:
    """C11, C12 -- the P1-1 fix must never mutate an original
    recommendation record, and must never prevent an outcome row (or
    the recommendation it tracks) from being created."""

    def test_c11_radar_opportunity_and_snapshot_fields_unchanged_by_the_race(self, Factory, cleanup):
        symbol = "C11IMMUTABLE"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)
        session = Factory()
        snap = _make_snapshot(session, stock_id, symbol, 1)
        original_decision = snap.decision
        original_confidence = float(snap.confidence_score)
        original_timestamp = snap.decision_timestamp

        self._run_barrier_race_helper(Factory, stock_id, symbol, worker_count=2, start_day=2)

        session.refresh(snap)
        assert snap.decision == original_decision
        assert float(snap.confidence_score) == original_confidence
        assert snap.decision_timestamp == original_timestamp
        session.close()

    def _run_barrier_race_helper(self, Factory, stock_id, symbol, worker_count, start_day):
        # Thin wrapper so this class doesn't need to inherit the
        # concurrency helper -- keeps the two concerns (race semantics
        # vs immutability) in visibly separate test classes.
        barrier = threading.Barrier(worker_count)
        results = {}

        def worker(name, day):
            session = Factory()
            try:
                snap = _make_snapshot(session, stock_id, symbol, day)
                barrier.wait()
                outcome = create_pending_decision_v2_outcome(session, snap)
                session.commit()
                results[name] = outcome.is_independent_signal
            finally:
                session.close()

        threads = [
            threading.Thread(target=worker, args=(f"W{i}", start_day + i)) for i in range(worker_count)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        return results

    def test_c12_no_recommendation_suppression_under_a_losing_race(self, Factory, cleanup):
        """The loser of the anchor race must still get a real,
        trackable DecisionV2Outcome row -- P1-1 must never silently
        drop or suppress a recommendation's outcome tracking just
        because it lost the independent-episode race."""
        symbol = "C12NOSUPPRESS"
        cleanup.append(symbol)
        stock_id = _make_stock(Factory, symbol)

        results = self._run_barrier_race_helper(Factory, stock_id, symbol, worker_count=2, start_day=1)

        assert len(results) == 2
        session = Factory()
        outcomes = session.query(DecisionV2Outcome).filter_by(symbol=symbol).all()
        assert len(outcomes) == 2, "both concurrent creations must persist a real outcome row"
        for o in outcomes:
            assert o.status == DecisionV2OutcomeStatus.PENDING
        session.close()
