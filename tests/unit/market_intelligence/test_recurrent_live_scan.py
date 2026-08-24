"""Unit tests for src.market_intelligence.recurrent_live_scan --
BASIRAH -- PRODUCTION-GRADE RECURRENT LIVE MARKET INTELLIGENCE mandate,
Shadow Mode (PR A). Covers candidate selection (Phase 6/7/8), the
material-change/lifecycle classifier (Phase 9/11/12), shadow ledger
emission (Phase 14), the quota-authority gate (Phase 2/17), and the
scheduler's own skip/success/failure paths (Phase 4/5/10) -- plus a
subset of the mandate's Phase 24 failure-mode matrix and Phase 25/26
non-regression proofs (Forward Test / Decision V2 immutability).

Stage 2 is always a fake, injected `run_market_scan_job_fn` here --
never the real SAHMK-touching one -- exactly like
tests/unit/market_intelligence/test_scheduler.py and test_radar_v2.py.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from typing import List

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2Snapshot,
    MarketScanRun,
    MarketScanStatus,
    RecurrentScanCycleStatus,
    ShadowLifecycleResult,
    ShadowLiveSignal,
    Stock,
)
from src.market_data.sahmk.operation_scope import get_current_operation
from src.market_data.sahmk.rate_limiter import SahmkRateLimiter
from src.market_data.sahmk.request_priority import get_current_priority, BACKGROUND
from src.market_intelligence.recurrent_live_scan import (
    ACTIVE_SIGNAL_REVALIDATION,
    NEW_STAGE1_CANDIDATE,
    RecurrentCandidateSelection,
    RecurrentLiveScanScheduler,
    _quota_allows_a_recurrent_cycle,
    classify_lifecycle,
    current_live_shadow_signal,
    emit_shadow_signals,
    is_shadow_signal_stale,
    select_recurrent_candidates,
)
from src.market_intelligence.stage1_local_scan import (
    Stage1ComponentScores,
    Stage1ScanResult,
    Stage1Signal,
    Stage1SymbolResult,
)


# ---------------------------------------------------------------------------
# Shared fixtures/helpers
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_real_shared_redis(monkeypatch):
    import src.market_data.sahmk.rate_limiter as rate_limiter_module
    import src.market_intelligence.scheduler_leader_lock as leader_lock_module

    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)
    monkeypatch.setattr(rate_limiter_module, "_get_shared_redis_client", lambda: None)
    yield


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
def factory():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    yield session_factory
    Base.metadata.drop_all(bind=engine)


def _stock(session, symbol="4050") -> Stock:
    row = Stock(symbol=symbol, name_en=f"Stock {symbol}", is_active=True)
    session.add(row)
    session.commit()
    return row


def _snapshot(
    session,
    stock,
    scan_run_id,
    decision="BUY_CANDIDATE",
    confidence=70.0,
    current_price=100.0,
    entry_status="READY_NOW",
    entry_zone_low=99.0,
    entry_zone_high=101.0,
    stop_loss=95.0,
    target_1=110.0,
    decision_timestamp=None,
) -> DecisionV2Snapshot:
    row = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=confidence,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=current_price,
        entry_zone_low=entry_zone_low,
        entry_zone_high=entry_zone_high,
        stop_loss=stop_loss,
        target_1=target_1,
        entry_status=entry_status,
        market_status="OPEN",
        decision_timestamp=decision_timestamp or datetime.now(timezone.utc),
        analysis_version="2.0.0",
        data_source="test",
        scan_run_id=scan_run_id,
    )
    session.add(row)
    session.commit()
    return row


def _shadow_signal(session, symbol, stock_id, snapshot_id, lifecycle_result, superseded_by_id=None, **overrides):
    defaults = dict(
        cycle_id="cyc-1",
        symbol=symbol,
        stock_id=stock_id,
        decision_v2_snapshot_id=snapshot_id,
        lifecycle_result=lifecycle_result,
        classification="BUY_CANDIDATE",
        confidence_score=70.0,
        entry_status="READY_NOW",
        stage1_ranking_score=80.0,
        emitted_at=datetime.now(timezone.utc),
        decision_timestamp=datetime.now(timezone.utc),
        superseded_by_id=superseded_by_id,
    )
    defaults.update(overrides)
    row = ShadowLiveSignal(**defaults)
    session.add(row)
    session.commit()
    return row


def _stage1_candidate(symbol, score=80.0) -> Stage1SymbolResult:
    return Stage1SymbolResult(
        symbol=symbol,
        is_candidate=True,
        latest_close=100.0,
        ranking_score=score,
        component_scores=Stage1ComponentScores(trend=80.0),
        signals=[Stage1Signal("trending", "اتجاه قوي")],
        risk_reward_ratio=1.8,
    )


def _stage1_result(candidates: List[Stage1SymbolResult], universe_size=10) -> Stage1ScanResult:
    return Stage1ScanResult(
        universe_size=universe_size,
        evaluated_count=len(candidates),
        skipped_count=0,
        candidate_count=len(candidates),
        candidates=candidates,
        all_results=candidates,
    )


class _FakeProvider:
    pass


async def _fake_market_provider_getter():
    return _FakeProvider()


class _AlwaysLeaderLock:
    def try_acquire_or_renew(self, lease_seconds):
        return True

    def release(self):
        pass


class _NeverLeaderLock:
    def try_acquire_or_renew(self, lease_seconds):
        return False

    def release(self):
        pass


def _ok_rate_limiter():
    return SahmkRateLimiter(max_per_minute=20, max_per_day=4500, reserved_for_critical=1000, redis_client=None)


class _QuotaExhaustedRateLimiter:
    def get_status(self):
        return {"upstream_confirmed_exhausted": True, "remaining_today_for_background": 0}


class _LowBackgroundQuotaRateLimiter:
    def get_status(self):
        return {"upstream_confirmed_exhausted": False, "remaining_today_for_background": 1}


# ---------------------------------------------------------------------------
# Phase 6/7/8: candidate selection
# ---------------------------------------------------------------------------


class TestSelectRecurrentCandidates:
    def test_active_signals_are_selected_before_new_stage1_candidates(self, session, monkeypatch):
        stock = _stock(session, "4050")
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")
        outcome = DecisionV2Outcome(
            decision_v2_snapshot_id=snapshot.id,
            symbol="4050",
            due_at=datetime.now(timezone.utc) + timedelta(days=14),
        )
        session.add(outcome)
        session.commit()

        stage1_result = _stage1_result([_stage1_candidate("6060"), _stage1_candidate("7070")])

        selection = select_recurrent_candidates(session, max_candidates=2, stage1_result=stage1_result)

        assert selection.symbols == ["4050", "6060"]
        assert selection.selection_reason_by_symbol["4050"] == ACTIVE_SIGNAL_REVALIDATION
        assert selection.selection_reason_by_symbol["6060"] == NEW_STAGE1_CANDIDATE
        assert selection.active_signal_total_count == 1
        assert selection.new_stage1_candidate_count == 1

    def test_never_exceeds_max_candidates(self, session):
        stage1_result = _stage1_result([_stage1_candidate(f"{i}") for i in range(10)])
        selection = select_recurrent_candidates(session, max_candidates=3, stage1_result=stage1_result)
        assert len(selection.symbols) == 3

    def test_a_symbol_that_is_both_active_and_a_stage1_candidate_is_not_duplicated(self, session):
        stock = _stock(session, "4050")
        snapshot = _snapshot(session, stock, scan_run_id=1)
        session.add(
            DecisionV2Outcome(
                decision_v2_snapshot_id=snapshot.id, symbol="4050", due_at=datetime.now(timezone.utc) + timedelta(days=1)
            )
        )
        session.commit()

        stage1_result = _stage1_result([_stage1_candidate("4050"), _stage1_candidate("6060")])
        selection = select_recurrent_candidates(session, max_candidates=5, stage1_result=stage1_result)

        assert selection.symbols.count("4050") == 1
        assert selection.selection_reason_by_symbol["4050"] == ACTIVE_SIGNAL_REVALIDATION

    def test_zero_candidates_when_nothing_pending_and_stage1_empty(self, session):
        selection = select_recurrent_candidates(session, max_candidates=5, stage1_result=_stage1_result([]))
        assert selection.symbols == []
        assert selection.active_signal_total_count == 0

    def test_stage1_score_by_symbol_is_populated_from_all_results(self, session):
        stage1_result = _stage1_result([_stage1_candidate("6060", score=91.5)])
        selection = select_recurrent_candidates(session, max_candidates=5, stage1_result=stage1_result)
        assert selection.stage1_score_by_symbol["6060"] == 91.5


# ---------------------------------------------------------------------------
# Phase 9/11/12: lifecycle classification
# ---------------------------------------------------------------------------


class TestClassifyLifecycle:
    def test_first_actionable_signal_is_a_new_intraday_opportunity(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")
        result, reason = classify_lifecycle(prior=None, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY

    def test_first_non_actionable_signal_is_unchanged_not_recorded(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="WATCH")
        result, _ = classify_lifecycle(prior=None, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.UNCHANGED_SIGNAL

    def test_decision_v2_reject_is_invalidated(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="REJECT")
        prior = _shadow_signal(session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY)
        result, _ = classify_lifecycle(prior=prior, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.INVALIDATED_SIGNAL

    def test_entry_status_missed_entry_is_missed_entry(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="WAIT_FOR_ENTRY", entry_status="MISSED_ENTRY")
        prior = _shadow_signal(session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY)
        result, _ = classify_lifecycle(prior=prior, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.MISSED_ENTRY

    def test_actionable_downgraded_without_missed_entry_is_chase_risk(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="WATCH", entry_status="NOT_SUITABLE")
        prior = _shadow_signal(
            session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            classification="BUY_CANDIDATE",
        )
        result, _ = classify_lifecycle(prior=prior, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.CHASE_RISK

    def test_confidence_move_past_threshold_is_refreshed(self, session, monkeypatch):
        monkeypatch.setenv("MARKET_CONFIDENCE_CHANGE_THRESHOLD", "5.0")
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=80.0)
        prior = _shadow_signal(
            session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            classification="BUY_CANDIDATE", confidence_score=70.0,
        )
        result, _ = classify_lifecycle(prior=prior, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.REFRESHED_SIGNAL

    def test_target_price_move_past_threshold_is_refreshed(self, session, monkeypatch):
        monkeypatch.setenv("MARKET_TARGET_PRICE_CHANGE_THRESHOLD_PCT", "5.0")
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE", target_1=120.0)
        prior = _shadow_signal(
            session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            classification="BUY_CANDIDATE", confidence_score=70.0, target_1=100.0,
        )
        result, _ = classify_lifecycle(prior=prior, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.REFRESHED_SIGNAL

    def test_nothing_changed_is_unchanged(self, session):
        stock = _stock(session)
        snapshot = _snapshot(
            session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0,
            entry_status="READY_NOW", entry_zone_low=99.0, entry_zone_high=101.0, stop_loss=95.0, target_1=110.0,
        )
        prior = _shadow_signal(
            session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            classification="BUY_CANDIDATE", confidence_score=70.0, entry_status="READY_NOW",
            entry_zone_low=99.0, entry_zone_high=101.0, stop_loss=95.0, target_1=110.0,
        )
        result, _ = classify_lifecycle(prior=prior, snapshot=snapshot, new_stage1_score=None)
        assert result == ShadowLifecycleResult.UNCHANGED_SIGNAL


class TestIsShadowSignalStale:
    def test_a_signal_from_the_operative_session_is_not_stale(self, session):
        stock = _stock(session)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision_timestamp=datetime.now(timezone.utc))
        signal = _shadow_signal(
            session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            decision_timestamp=datetime.now(timezone.utc),
        )
        assert is_shadow_signal_stale(signal) is False

    def test_a_signal_from_a_prior_session_is_stale(self, session):
        stock = _stock(session)
        old = datetime.now(timezone.utc) - timedelta(days=30)
        snapshot = _snapshot(session, stock, scan_run_id=1, decision_timestamp=old)
        signal = _shadow_signal(
            session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            decision_timestamp=old,
        )
        assert is_shadow_signal_stale(signal) is True


# ---------------------------------------------------------------------------
# Phase 14: shadow ledger emission
# ---------------------------------------------------------------------------


class TestEmitShadowSignals:
    def test_new_opportunity_is_persisted_and_forward_test_tracked(self, session):
        stock = _stock(session, "4050")
        _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE")
        selection = RecurrentCandidateSelection(
            symbols=["4050"], selection_reason_by_symbol={"4050": NEW_STAGE1_CANDIDATE},
            active_signal_total_count=0, new_stage1_candidate_count=1,
            stage1_universe_size=1, stage1_candidate_count=1, stage1_evaluated_count=1,
        )

        emission = emit_shadow_signals(session, "cyc-1", scan_run_id=1, selection=selection, stage1_score_by_symbol={})

        assert emission.count(ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY) == 1
        row = session.query(ShadowLiveSignal).filter_by(symbol="4050").one()
        assert row.lifecycle_result == ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY
        assert row.superseded_by_id is None
        assert current_live_shadow_signal(session, "4050").id == row.id
        assert session.query(DecisionV2Outcome).filter_by(symbol="4050").count() == 1

    def test_unchanged_signal_is_never_persisted(self, session):
        stock = _stock(session, "4050")
        snapshot1 = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0)
        prior = _shadow_signal(
            session, "4050", stock.id, snapshot1.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            classification="BUY_CANDIDATE", confidence_score=70.0, entry_status="READY_NOW",
            entry_zone_low=99.0, entry_zone_high=101.0, stop_loss=95.0, target_1=110.0,
        )
        _snapshot(
            session, stock, scan_run_id=2, decision="BUY_CANDIDATE", confidence=70.0,
            entry_status="READY_NOW", entry_zone_low=99.0, entry_zone_high=101.0, stop_loss=95.0, target_1=110.0,
        )
        selection = RecurrentCandidateSelection(
            symbols=["4050"], selection_reason_by_symbol={"4050": ACTIVE_SIGNAL_REVALIDATION},
            active_signal_total_count=1, new_stage1_candidate_count=0,
            stage1_universe_size=1, stage1_candidate_count=0, stage1_evaluated_count=1,
        )

        emission = emit_shadow_signals(session, "cyc-2", scan_run_id=2, selection=selection, stage1_score_by_symbol={})

        assert emission.count(ShadowLifecycleResult.UNCHANGED_SIGNAL) == 1
        assert session.query(ShadowLiveSignal).count() == 1  # only the original prior row
        assert current_live_shadow_signal(session, "4050").id == prior.id

    def test_material_change_supersedes_the_prior_row_without_mutating_it(self, session):
        stock = _stock(session, "4050")
        snapshot1 = _snapshot(session, stock, scan_run_id=1, decision="BUY_CANDIDATE", confidence=70.0)
        prior = _shadow_signal(
            session, "4050", stock.id, snapshot1.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            classification="BUY_CANDIDATE", confidence_score=70.0,
        )
        prior_confidence = prior.confidence_score
        snapshot2 = _snapshot(session, stock, scan_run_id=2, decision="BUY_CANDIDATE", confidence=90.0)
        selection = RecurrentCandidateSelection(
            symbols=["4050"], selection_reason_by_symbol={"4050": ACTIVE_SIGNAL_REVALIDATION},
            active_signal_total_count=1, new_stage1_candidate_count=0,
            stage1_universe_size=1, stage1_candidate_count=0, stage1_evaluated_count=1,
        )

        emit_shadow_signals(session, "cyc-2", scan_run_id=2, selection=selection, stage1_score_by_symbol={})

        session.refresh(prior)
        assert prior.superseded_by_id is not None
        assert prior.confidence_score == prior_confidence  # never mutated, only pointed forward
        live = current_live_shadow_signal(session, "4050")
        assert live.id != prior.id
        assert live.decision_v2_snapshot_id == snapshot2.id
        assert live.previous_confidence_score == prior_confidence

        # The DecisionV2Snapshot rows themselves are never mutated either --
        # both remain exactly as originally written (Phase 25/26 non-
        # regression: no historical snapshot is ever overwritten).
        session.refresh(snapshot1)
        assert snapshot1.confidence_score == 70.0
        assert snapshot1.scan_run_id == 1


# ---------------------------------------------------------------------------
# Phase 2/17: quota authority
# ---------------------------------------------------------------------------


class TestQuotaAllowsARecurrentCycle:
    def test_fails_closed_on_upstream_confirmed_exhaustion(self):
        ok, reason, _ = _quota_allows_a_recurrent_cycle(_QuotaExhaustedRateLimiter(), max_candidates=3)
        assert ok is False
        assert reason == "upstream_confirmed_exhausted"

    def test_fails_when_background_quota_below_required_reserve(self, monkeypatch):
        monkeypatch.setenv("LIVE_RECURRENT_SCAN_REQUEST_RESERVE", "5")
        ok, reason, _ = _quota_allows_a_recurrent_cycle(_LowBackgroundQuotaRateLimiter(), max_candidates=3)
        assert ok is False
        assert "insufficient_background_quota" in reason

    def test_allows_a_cycle_when_quota_is_healthy(self):
        ok, reason, _ = _quota_allows_a_recurrent_cycle(_ok_rate_limiter(), max_candidates=3)
        assert ok is True
        assert reason is None


# ---------------------------------------------------------------------------
# Phase 4/5/10: the scheduler
# ---------------------------------------------------------------------------


def _fake_run_market_scan_job_writing_snapshots(snapshot_specs):
    """snapshot_specs: dict[symbol -> kwargs for _snapshot(), minus
    session/stock/scan_run_id]. Simulates Stage 2 by opening its own
    session (matching the real run_market_scan_job's own contract) and
    writing one DecisionV2Snapshot per requested symbol that has a spec
    -- a symbol with no spec is silently skipped, mirroring a real
    Stage 2 failure/skip for that symbol."""

    async def _fake(run_id, session_factory, provider, symbols=None, **kwargs):
        db = session_factory()
        try:
            for symbol in symbols or []:
                if symbol not in snapshot_specs:
                    continue
                stock = db.query(Stock).filter_by(symbol=symbol).one()
                _snapshot(db, stock, scan_run_id=run_id, **snapshot_specs[symbol])
        finally:
            db.close()

    return _fake


class TestRunOneCycle:
    @pytest.mark.asyncio
    async def test_skips_with_zero_db_writes_when_quota_exhausted(self, factory):
        session = factory()
        _stock(session, "4050")
        session.close()

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_QuotaExhaustedRateLimiter(),
        )
        cycle = await scheduler._run_one_cycle()

        assert cycle.status == RecurrentScanCycleStatus.SKIPPED_QUOTA
        session = factory()
        assert session.query(MarketScanRun).count() == 0
        assert session.query(ShadowLiveSignal).count() == 0
        session.close()

    @pytest.mark.asyncio
    async def test_skips_when_a_scan_is_already_in_flight(self, factory):
        session = factory()
        session.add(MarketScanRun(status=MarketScanStatus.RUNNING, symbols_requested=1))
        session.commit()
        session.close()

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_ok_rate_limiter(),
        )
        cycle = await scheduler._run_one_cycle()
        assert cycle.status == RecurrentScanCycleStatus.SKIPPED_LOCKED

    @pytest.mark.asyncio
    async def test_skips_when_there_are_no_candidates(self, factory):
        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_ok_rate_limiter(),
        )
        cycle = await scheduler._run_one_cycle()
        assert cycle.status == RecurrentScanCycleStatus.SKIPPED_NO_CANDIDATES

    @pytest.mark.asyncio
    async def test_success_path_persists_shadow_signal_and_cycle_row(self, factory, monkeypatch):
        session = factory()
        stock = _stock(session, "4050")
        outcome_snapshot = _snapshot(session, stock, scan_run_id=999, decision="WATCH")
        session.add(
            DecisionV2Outcome(
                decision_v2_snapshot_id=outcome_snapshot.id, symbol="4050",
                due_at=datetime.now(timezone.utc) + timedelta(days=1),
            )
        )
        session.commit()
        session.close()

        fake_job = _fake_run_market_scan_job_writing_snapshots({"4050": {"decision": "BUY_CANDIDATE"}})

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_ok_rate_limiter(), run_market_scan_job_fn=fake_job,
        )
        cycle = await scheduler._run_one_cycle()

        assert cycle.status == RecurrentScanCycleStatus.SUCCESS
        assert cycle.signals_new_opportunity_count == 1
        assert cycle.symbols_selected_count == 1

        session = factory()
        assert session.query(ShadowLiveSignal).filter_by(symbol="4050").count() == 1
        session.close()

    @pytest.mark.asyncio
    async def test_no_material_change_is_success_no_change(self, factory):
        session = factory()
        stock = _stock(session, "4050")
        snapshot = _snapshot(session, stock, scan_run_id=999, decision="BUY_CANDIDATE", confidence=70.0)
        _shadow_signal(
            session, "4050", stock.id, snapshot.id, ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
            classification="BUY_CANDIDATE", confidence_score=70.0, entry_status="READY_NOW",
            entry_zone_low=99.0, entry_zone_high=101.0, stop_loss=95.0, target_1=110.0,
        )
        session.add(
            DecisionV2Outcome(
                decision_v2_snapshot_id=snapshot.id, symbol="4050", due_at=datetime.now(timezone.utc) + timedelta(days=1)
            )
        )
        session.commit()
        session.close()

        fake_job = _fake_run_market_scan_job_writing_snapshots(
            {
                "4050": dict(
                    decision="BUY_CANDIDATE", confidence=70.0, entry_status="READY_NOW",
                    entry_zone_low=99.0, entry_zone_high=101.0, stop_loss=95.0, target_1=110.0,
                )
            }
        )
        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_ok_rate_limiter(), run_market_scan_job_fn=fake_job,
        )
        cycle = await scheduler._run_one_cycle()

        assert cycle.status == RecurrentScanCycleStatus.SUCCESS_NO_CHANGE
        assert cycle.signals_unchanged_count == 1

    @pytest.mark.asyncio
    async def test_stage2_runs_under_background_priority_and_live_recurrent_scan_operation(self, factory):
        session = factory()
        stock = _stock(session, "4050")
        snapshot = _snapshot(session, stock, scan_run_id=999, decision="BUY_CANDIDATE")
        session.add(
            DecisionV2Outcome(
                decision_v2_snapshot_id=snapshot.id, symbol="4050", due_at=datetime.now(timezone.utc) + timedelta(days=1)
            )
        )
        session.commit()
        session.close()

        observed = {}

        async def _observing_job(run_id, session_factory, provider, symbols=None, **kwargs):
            observed["priority"] = get_current_priority()
            observed["operation"] = get_current_operation()

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_ok_rate_limiter(), run_market_scan_job_fn=_observing_job,
        )
        await scheduler._run_one_cycle()

        assert observed["priority"] == BACKGROUND
        assert observed["operation"] == "live_recurrent_scan"

    @pytest.mark.asyncio
    async def test_failure_is_recorded_as_failed_status_not_raised(self, factory):
        async def _raising_job(run_id, session_factory, provider, symbols=None, **kwargs):
            raise RuntimeError("provider exploded")

        session = factory()
        stock = _stock(session, "4050")
        snapshot = _snapshot(session, stock, scan_run_id=999, decision="BUY_CANDIDATE")
        session.add(
            DecisionV2Outcome(
                decision_v2_snapshot_id=snapshot.id, symbol="4050", due_at=datetime.now(timezone.utc) + timedelta(days=1)
            )
        )
        session.commit()
        session.close()

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_ok_rate_limiter(), run_market_scan_job_fn=_raising_job,
        )
        cycle = await scheduler._run_one_cycle()

        assert cycle.status == RecurrentScanCycleStatus.FAILED
        assert "provider exploded" in cycle.error_summary

    @pytest.mark.asyncio
    async def test_a_session_factory_failure_still_records_a_failed_cycle_via_a_fresh_session(self, factory):
        """The quota check and the very first session_factory() call are
        inside the same outer try/except as everything else -- a
        transient DB-connect failure on the FIRST attempt must not
        escape _run_one_cycle() uncaught, and must still leave an
        auditable FAILED row (written via a fresh session opened
        specifically for that purpose)."""
        attempts = {"n": 0}
        real_factory = factory

        def _flaky_factory():
            attempts["n"] += 1
            if attempts["n"] == 1:
                raise RuntimeError("connection refused")
            return real_factory()

        scheduler = RecurrentLiveScanScheduler(
            session_factory=_flaky_factory, market_provider_getter=_fake_market_provider_getter,
            rate_limiter=_ok_rate_limiter(),
        )
        cycle = await scheduler._run_one_cycle()

        assert cycle.status == RecurrentScanCycleStatus.FAILED
        assert "connection refused" in cycle.error_summary


class TestSchedulerLifecycleAndLeadership:
    def test_is_not_running_before_start(self):
        scheduler = RecurrentLiveScanScheduler()
        assert scheduler.is_running is False

    @pytest.mark.asyncio
    async def test_loop_only_runs_a_cycle_while_this_worker_is_leader(self, factory, monkeypatch):
        import src.market_intelligence.recurrent_live_scan as module

        monkeypatch.setattr(module, "get_live_recurrent_scan_interval_minutes", lambda: 0)

        call_count = {"n": 0}

        async def _counting():
            call_count["n"] += 1

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            leader_lock=_NeverLeaderLock(),
        )
        scheduler._run_one_cycle = _counting

        scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()

        assert call_count["n"] == 0

    @pytest.mark.asyncio
    async def test_loop_runs_cycles_while_this_worker_is_leader(self, factory, monkeypatch):
        import src.market_intelligence.recurrent_live_scan as module

        monkeypatch.setattr(module, "get_live_recurrent_scan_interval_minutes", lambda: 0)

        call_count = {"n": 0}

        async def _counting():
            call_count["n"] += 1

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            leader_lock=_AlwaysLeaderLock(),
        )
        scheduler._run_one_cycle = _counting

        scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()

        assert call_count["n"] >= 1

    @pytest.mark.asyncio
    async def test_loop_survives_an_exception_and_keeps_scheduling(self, factory, monkeypatch):
        import src.market_intelligence.recurrent_live_scan as module

        monkeypatch.setattr(module, "get_live_recurrent_scan_interval_minutes", lambda: 0)

        call_count = {"n": 0}

        async def _raising():
            call_count["n"] += 1
            raise RuntimeError("boom")

        scheduler = RecurrentLiveScanScheduler(
            session_factory=factory, market_provider_getter=_fake_market_provider_getter,
            leader_lock=_AlwaysLeaderLock(),
        )
        scheduler._run_one_cycle = _raising

        scheduler.start()
        await asyncio.sleep(0.05)
        await scheduler.stop()

        assert call_count["n"] >= 1
