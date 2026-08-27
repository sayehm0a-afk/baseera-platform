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


class TestConcurrentAggregation:
    """Production evidence (2026-08-26): every Gunicorn worker runs its
    own independent DailyIntelligenceAggregationScheduler (scheduler.py
    has no leader lock for this one), so two or more workers can call
    aggregate_daily_intelligence for the same snapshot_date within
    milliseconds of each other -- reproduced a real
    sqlalchemy.exc.IntegrityError on uq_daily_intelligence_snapshot_date
    in production. These tests use two real threads against a real
    file-based SQLite database (not :memory: -- a shared in-memory DB
    doesn't exercise independent connections the way separate
    Gunicorn worker processes/connections do) with a real
    threading.Barrier forcing both threads past their own SELECT
    before either commits its INSERT, deterministically reproducing
    the exact race instead of hoping for it."""

    @pytest.fixture
    def file_engine(self, tmp_path):
        db_path = tmp_path / "race.db"
        # A real `timeout` (sqlite3.connect's busy-wait, seconds) so a
        # writer blocked behind another connection's write transaction
        # actually waits for the lock instead of immediately raising
        # "database is locked" -- without this, the second worker in
        # the tests below could fail on OperationalError before ever
        # reaching the INSERT this fix is meant to make race-safe.
        engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 30})
        Base.metadata.create_all(bind=engine)
        yield engine
        Base.metadata.drop_all(bind=engine)

    @pytest.fixture
    def file_session_factory(self, file_engine):
        return sessionmaker(bind=file_engine)

    def test_two_concurrent_first_writes_yield_exactly_one_row_no_integrity_error_escapes(
        self, file_session_factory, monkeypatch,
    ):
        import threading

        import src.ai_evolution.daily_intelligence_aggregation as module

        setup_session = file_session_factory()
        stock = Stock(symbol="1111", name_en="Stock 1111", sector="Energy")
        setup_session.add(stock)
        setup_session.commit()
        setup_session.close()

        barrier = threading.Barrier(2)
        real_agent_panel_stats = module._agent_panel_stats

        def _synced_agent_panel_stats(session, snapshot_date):
            result = real_agent_panel_stats(session, snapshot_date)
            barrier.wait(timeout=5)
            return result

        monkeypatch.setattr(module, "_agent_panel_stats", _synced_agent_panel_stats)

        results = {}
        errors = {}

        def _worker(name):
            worker_session = file_session_factory()
            try:
                results[name] = module.aggregate_daily_intelligence(worker_session, snapshot_date=_SNAPSHOT_DATE)
            except Exception as exc:  # noqa: BLE001 -- captured for the assertion below, not swallowed silently
                errors[name] = exc
            finally:
                worker_session.close()

        thread_a = threading.Thread(target=_worker, args=("a",))
        thread_b = threading.Thread(target=_worker, args=("b",))
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

        assert errors == {}, f"no IntegrityError (or any other exception) should escape either worker: {errors}"
        assert "a" in results and "b" in results

        verify_session = file_session_factory()
        rows = verify_session.query(DailyIntelligenceSnapshot).filter_by(snapshot_date=_SNAPSHOT_DATE).all()
        assert len(rows) == 1, f"expected exactly one row per date under concurrency, got {len(rows)}"
        verify_session.close()

    def test_four_concurrent_first_writes_yield_exactly_one_row(self, file_session_factory, monkeypatch):
        import threading

        import src.ai_evolution.daily_intelligence_aggregation as module

        setup_session = file_session_factory()
        stock = Stock(symbol="2222", name_en="Stock 2222", sector="Energy")
        setup_session.add(stock)
        setup_session.commit()
        setup_session.close()

        worker_count = 4
        barrier = threading.Barrier(worker_count)
        real_agent_panel_stats = module._agent_panel_stats

        def _synced_agent_panel_stats(session, snapshot_date):
            result = real_agent_panel_stats(session, snapshot_date)
            barrier.wait(timeout=5)
            return result

        monkeypatch.setattr(module, "_agent_panel_stats", _synced_agent_panel_stats)

        errors = {}

        def _worker(name):
            worker_session = file_session_factory()
            try:
                module.aggregate_daily_intelligence(worker_session, snapshot_date=_SNAPSHOT_DATE)
            except Exception as exc:  # noqa: BLE001
                errors[name] = exc
            finally:
                worker_session.close()

        threads = [threading.Thread(target=_worker, args=(i,)) for i in range(worker_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=10)

        assert errors == {}, f"no exception should escape any of the {worker_count} simulated workers: {errors}"

        verify_session = file_session_factory()
        rows = verify_session.query(DailyIntelligenceSnapshot).filter_by(snapshot_date=_SNAPSHOT_DATE).all()
        assert len(rows) == 1
        verify_session.close()

    def test_repeated_invocation_after_the_race_stays_idempotent(self, file_session_factory, monkeypatch):
        """After a real concurrent race has already resolved to one
        row, a normal (non-concurrent) re-run must still update that
        same row, not create a second one -- proving the fix didn't
        change the already-covered sequential-idempotency contract."""
        import threading

        import src.ai_evolution.daily_intelligence_aggregation as module

        setup_session = file_session_factory()
        stock = Stock(symbol="3333", name_en="Stock 3333", sector="Energy")
        setup_session.add(stock)
        setup_session.commit()
        setup_session.close()

        barrier = threading.Barrier(2)
        real_agent_panel_stats = module._agent_panel_stats

        def _synced_agent_panel_stats(session, snapshot_date):
            result = real_agent_panel_stats(session, snapshot_date)
            barrier.wait(timeout=5)
            return result

        monkeypatch.setattr(module, "_agent_panel_stats", _synced_agent_panel_stats)

        def _worker():
            worker_session = file_session_factory()
            try:
                module.aggregate_daily_intelligence(worker_session, snapshot_date=_SNAPSHOT_DATE)
            finally:
                worker_session.close()

        thread_a = threading.Thread(target=_worker)
        thread_b = threading.Thread(target=_worker)
        thread_a.start()
        thread_b.start()
        thread_a.join(timeout=10)
        thread_b.join(timeout=10)

        monkeypatch.undo()
        rerun_session = file_session_factory()
        rerun_stock = rerun_session.query(Stock).filter_by(symbol="3333").one()
        s1 = _snapshot(rerun_session, rerun_stock)
        _outcome(rerun_session, s1, RecommendationOutcomeStatus.SUCCESSFUL)
        module.aggregate_daily_intelligence(rerun_session, snapshot_date=_SNAPSHOT_DATE)
        rerun_session.close()

        verify_session = file_session_factory()
        rows = verify_session.query(DailyIntelligenceSnapshot).filter_by(snapshot_date=_SNAPSHOT_DATE).all()
        assert len(rows) == 1
        assert rows[0].recommendations_evaluated == 1
        verify_session.close()

    @pytest.mark.parametrize("worker_count", [2, 4, 8])
    def test_concurrent_first_writes_yield_exactly_one_row_at_scale(self, worker_count, tmp_path_factory, monkeypatch):
        """Independent pre-merge audit requirement: the single-trial
        2-worker and 4-worker tests above prove the fix handles the
        race at least once, but a narrow timing window could in
        principle slip through a single trial. This repeats the exact
        same real-thread, real-file-SQLite, barrier-forced race 20
        times at each of 2, 4, and 8 simultaneous workers (fresh
        on-disk DB per trial, so no trial's outcome depends on a
        previous trial's state) and requires every single trial to
        land on exactly one row with zero escaped exceptions."""
        import threading

        import src.ai_evolution.daily_intelligence_aggregation as module

        real_agent_panel_stats = module._agent_panel_stats
        trial_count = 20

        for trial in range(trial_count):
            db_path = tmp_path_factory.mktemp("race") / "race.db"
            engine = create_engine(f"sqlite:///{db_path}", connect_args={"timeout": 30})
            Base.metadata.create_all(bind=engine)
            session_factory = sessionmaker(bind=engine)

            setup_session = session_factory()
            stock = Stock(symbol="9999", name_en="Stock 9999", sector="Energy")
            setup_session.add(stock)
            setup_session.commit()
            setup_session.close()

            barrier = threading.Barrier(worker_count)

            def _synced_agent_panel_stats(session, snapshot_date, _real=real_agent_panel_stats, _barrier=barrier):
                result = _real(session, snapshot_date)
                _barrier.wait(timeout=5)
                return result

            monkeypatch.setattr(module, "_agent_panel_stats", _synced_agent_panel_stats)

            errors = {}

            def _worker(name, _factory=session_factory):
                worker_session = _factory()
                try:
                    module.aggregate_daily_intelligence(worker_session, snapshot_date=_SNAPSHOT_DATE)
                except Exception as exc:  # noqa: BLE001 -- captured for the assertion below, not swallowed silently
                    errors[name] = exc
                finally:
                    worker_session.close()

            threads = [threading.Thread(target=_worker, args=(i,)) for i in range(worker_count)]
            for t in threads:
                t.start()
            for t in threads:
                t.join(timeout=10)

            assert errors == {}, (
                f"worker_count={worker_count} trial={trial}: no exception should escape any worker: {errors}"
            )

            verify_session = session_factory()
            rows = verify_session.query(DailyIntelligenceSnapshot).filter_by(snapshot_date=_SNAPSHOT_DATE).all()
            assert len(rows) == 1, (
                f"worker_count={worker_count} trial={trial}: expected exactly one row, got {len(rows)}"
            )
            verify_session.close()
            engine.dispose()
            monkeypatch.undo()
