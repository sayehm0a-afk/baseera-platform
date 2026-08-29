"""RecurrentLiveScanScheduler: Shadow Mode recurrent live intelligence
-- "BASIRAH -- PRODUCTION-GRADE RECURRENT LIVE MARKET INTELLIGENCE"
mandate, Phases 4-14.

A SEPARATE scheduler from `src.market_intelligence.scheduler.
IntervalMarketIntelligenceScheduler` (the proven, once-per-session
opening scan) -- this module adds no new ranking math, scoring,
classification, threshold, entry-gate, or anti-chase logic anywhere.
Every real decision is made by the exact same, unmodified pieces the
opening scan already uses:

  * Stage 1 candidate ranking: `stage1_local_scan.run_stage1_local_scan`
    (zero SAHMK cost, unmodified).
  * Stage 2 live validation + Decision V2 evaluation: the same
    `run_market_scan_job`/`MarketScanRun`/`DecisionV2Snapshot` path
    `radar_v2.run_radar_v2_cycle`'s own injected Stage 2 runner uses.
  * Active/pending-signal discovery:
    `src.market_data.ingestion.outcome_tracking.pending_signal_symbols`
    (unmodified -- the same function PR #96 already uses to prioritize
    OHLCV ingestion).
  * Decision freshness / stale-truthfulness:
    `src.analysis.decision_v2.decision_freshness` (unmodified).
  * Multi-worker safety: `scheduler_leader_lock.SchedulerLeaderLock`
    (unmodified, under this module's own, independent lease key).
  * Market-hours gating: `live_market_mode.LiveMarketModeScheduler`
    (unmodified -- see main.py's wiring, which wraps this scheduler in
    a SECOND, independent `LiveMarketModeScheduler` instance rather
    than reimplementing Tadawul-session awareness here).

SHADOW MODE ONLY: this module writes exclusively to
`RecurrentScanCycle`/`ShadowLiveSignal` -- it never creates, updates,
or reads `RadarOpportunity`, and never calls
`radar_v2.emit_radar_opportunities`. The consumer-facing Radar/
Watchlist/analysis feed (everything built from `RadarOpportunity`) is
therefore provably unaffected by this module's existence, by
construction, regardless of how often this scheduler runs -- there is
no code path here that could make a Shadow Mode signal visible to a
real user. Going live is a deliberately separate, later, explicitly
authorized PR (Phase 30 of the mandate) that would add a new emission
path gated on `get_live_recurrent_scan_shadow_mode()`==False; no such
path exists yet.
"""

import asyncio
import contextlib
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, List, Optional, Protocol, Tuple, runtime_checkable

from sqlalchemy.orm import Session

from src.ai_evolution.decision_v2_outcome_evaluation import (
    create_pending_decision_v2_outcome,
    is_actionable_buy_decision,
)
from src.analysis.decision_v2.decision_freshness import is_decision_fresh
from src.analysis.decision_v2.types import Decision, EntryStatus
from src.domain.models import (
    DecisionV2Snapshot,
    MarketScanStatus,
    RecurrentScanCycle,
    RecurrentScanCycleStatus,
    ShadowLifecycleResult,
    ShadowLiveSignal,
)
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_data.sahmk.operation_scope import LIVE_RECURRENT_SCAN, operation_scope
from src.market_data.sahmk.rate_limiter import SahmkRateLimiter, get_default_rate_limiter
from src.market_data.sahmk.request_priority import LIVE_SCAN, priority_scope
from src.market_data.ingestion.outcome_tracking import pending_signal_symbols
from src.market_intelligence.config import (
    get_confidence_change_threshold,
    get_live_recurrent_scan_interval_minutes,
    get_live_recurrent_scan_leader_lease_seconds,
    get_live_recurrent_scan_max_candidates,
    get_live_recurrent_scan_request_reserve,
    get_max_scan_run_duration_hours,
    get_score_change_threshold,
    get_scan_min_background_quota_remaining,
    get_target_price_change_threshold_pct,
    is_live_recurrent_scan_shadow_mode,
)
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock
from src.market_intelligence.services.scan_job_runner import run_market_scan_job
from src.market_intelligence.stage1_local_scan import Stage1ScanResult, run_stage1_local_scan

logger = logging.getLogger(__name__)

_LEASE_KEY = "basirah:scheduler:recurrent_live_scan:leader"

_INVALIDATING_DECISIONS = frozenset({Decision.REJECT.value, Decision.EXIT.value})

ACTIVE_SIGNAL_REVALIDATION = "ACTIVE_SIGNAL_REVALIDATION"
NEW_STAGE1_CANDIDATE = "NEW_STAGE1_CANDIDATE"


# ---------------------------------------------------------------------------
# Phase 6/7/8: candidate selection -- reuses Stage 1's own ranking and
# pending_signal_symbols() unmodified; the only new logic here is the
# bounded merge/priority order between the two.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RecurrentCandidateSelection:
    symbols: List[str]
    selection_reason_by_symbol: Dict[str, str]
    # Total distinct symbols with a real pending/active signal this
    # cycle -- may exceed len(symbols) if the cap truncated the list;
    # see RecurrentScanCycle.active_signal_candidate_count.
    active_signal_total_count: int
    new_stage1_candidate_count: int
    stage1_universe_size: int
    stage1_candidate_count: int
    stage1_evaluated_count: int
    # Stage 1's own ranking_score for every symbol it evaluated this
    # cycle (from Stage1ScanResult.all_results, not just .candidates),
    # so classify_lifecycle can apply the existing score-change
    # threshold even for an active-signal symbol Stage 1 evaluated but
    # did not itself flag as a fresh candidate. None for a symbol Stage
    # 1 never scored (not present in this dict at all).
    stage1_score_by_symbol: Dict[str, float] = field(default_factory=dict)


def select_recurrent_candidates(
    session: Session, max_candidates: int, stage1_result: Optional[Stage1ScanResult] = None
) -> RecurrentCandidateSelection:
    """Phase 7 (active-signal revalidation) always fills available slots
    before Phase 8 (new Stage 1 candidates) -- an existing signal
    silently going unrevalidated is worse than missing one new
    candidate this cycle; it will simply be picked up again next cycle,
    while a missed revalidation could leave a stale/invalidated
    recommendation looking current for longer. `stage1_result` may be
    injected (tests / callers that already ran Stage 1 this cycle for
    another reason); computed fresh otherwise."""
    active_symbols = pending_signal_symbols(session)
    stage1_result = stage1_result if stage1_result is not None else run_stage1_local_scan(session)

    selected: List[str] = []
    reasons: Dict[str, str] = {}

    for symbol in active_symbols:
        if len(selected) >= max_candidates:
            break
        if symbol not in reasons:
            selected.append(symbol)
            reasons[symbol] = ACTIVE_SIGNAL_REVALIDATION

    for candidate in stage1_result.candidates:
        if len(selected) >= max_candidates:
            break
        if candidate.symbol in reasons:
            continue
        selected.append(candidate.symbol)
        reasons[candidate.symbol] = NEW_STAGE1_CANDIDATE

    new_count = sum(1 for r in reasons.values() if r == NEW_STAGE1_CANDIDATE)
    score_by_symbol = {
        result.symbol: result.ranking_score
        for result in stage1_result.all_results
        if result.ranking_score is not None
    }
    return RecurrentCandidateSelection(
        symbols=selected,
        selection_reason_by_symbol=reasons,
        active_signal_total_count=len(active_symbols),
        new_stage1_candidate_count=new_count,
        stage1_universe_size=stage1_result.universe_size,
        stage1_candidate_count=stage1_result.candidate_count,
        stage1_evaluated_count=stage1_result.evaluated_count,
        stage1_score_by_symbol=score_by_symbol,
    )


# ---------------------------------------------------------------------------
# Phase 9/11/12: material-change comparator + lifecycle classification.
# Every branch below reuses an EXISTING Decision V2 field/threshold --
# no new scoring, gate, or anti-chase logic is computed here.
# ---------------------------------------------------------------------------


def current_live_shadow_signal(session: Session, symbol: str) -> Optional[ShadowLiveSignal]:
    """Mirrors radar_v2.current_live_opportunity exactly, for
    ShadowLiveSignal instead of RadarOpportunity."""
    return (
        session.query(ShadowLiveSignal)
        .filter(ShadowLiveSignal.symbol == symbol, ShadowLiveSignal.superseded_by_id.is_(None))
        .order_by(ShadowLiveSignal.emitted_at.desc())
        .first()
    )


def is_shadow_signal_stale(signal: ShadowLiveSignal) -> bool:
    """Derived, read-time-only staleness check -- see
    ShadowLifecycleResult.STALE_SIGNAL's own docstring for why this is
    never persisted as a row. Reuses is_decision_fresh unmodified."""
    return not is_decision_fresh(signal.decision_timestamp)


def _prices_within_tolerance(old_value, new_value, tolerance_fraction: float) -> bool:
    if old_value is None or new_value is None:
        return old_value == new_value
    old_f = float(old_value)
    if old_f == 0:
        return float(new_value) == 0
    return abs(float(new_value) - old_f) / abs(old_f) < tolerance_fraction


def _is_material_change(
    prior: ShadowLiveSignal,
    snapshot: DecisionV2Snapshot,
    new_stage1_score: Optional[float],
) -> bool:
    """Same reasoning as radar_v2._is_material_change, extended with
    the entry-status/price-plan fields a lifecycle ledger specifically
    needs to track, using the SAME already-existing config thresholds
    (get_confidence_change_threshold/get_score_change_threshold/
    get_target_price_change_threshold_pct) radar_v2.py and
    market_intelligence_repository.py already use elsewhere."""
    if prior.classification != snapshot.decision:
        return True
    if abs(float(snapshot.confidence_score) - float(prior.confidence_score)) >= get_confidence_change_threshold():
        return True
    if new_stage1_score is not None and prior.stage1_ranking_score is not None:
        if abs(float(new_stage1_score) - float(prior.stage1_ranking_score)) >= get_score_change_threshold():
            return True
    if prior.entry_status != snapshot.entry_status:
        return True
    tolerance_fraction = get_target_price_change_threshold_pct() / 100.0
    for field_name in ("entry_zone_low", "entry_zone_high", "stop_loss", "target_1"):
        if not _prices_within_tolerance(getattr(prior, field_name), getattr(snapshot, field_name), tolerance_fraction):
            return True
    return False


def classify_lifecycle(
    prior: Optional[ShadowLiveSignal],
    snapshot: DecisionV2Snapshot,
    new_stage1_score: Optional[float],
) -> Tuple[ShadowLifecycleResult, str]:
    """The Phase 9 material-change comparator. `snapshot` is always a
    FRESH DecisionV2Snapshot this cycle's own Stage 2 call just
    produced -- classify_lifecycle is only ever invoked for a symbol
    that was actually re-evaluated this cycle (see
    RecurrentLiveScanScheduler._run_one_cycle); a symbol that fell out
    of the bounded candidate slate is never passed here at all (its
    existing live shadow row, if any, may separately be observed as
    STALE via is_shadow_signal_stale at read time -- never as a write
    here, since there is no fresh evidence to anchor a new row to)."""
    new_classification = snapshot.decision

    if prior is None:
        if is_actionable_buy_decision(new_classification):
            return (
                ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
                f"First live shadow signal for {snapshot.symbol}: reached actionable decision "
                f"{new_classification} with no prior shadow state for this symbol.",
            )
        return (
            ShadowLifecycleResult.UNCHANGED_SIGNAL,
            f"No prior shadow signal for {snapshot.symbol} and {new_classification} is not actionable "
            "-- nothing to record yet.",
        )

    if new_classification in _INVALIDATING_DECISIONS:
        return (
            ShadowLifecycleResult.INVALIDATED_SIGNAL,
            f"Decision V2 moved {snapshot.symbol} to {new_classification} -- the underlying thesis "
            "no longer holds (decision_v2 output, unmodified).",
        )

    if snapshot.entry_status == EntryStatus.MISSED_ENTRY.value:
        return (
            ShadowLifecycleResult.MISSED_ENTRY,
            f"Decision V2 entry_status for {snapshot.symbol} is MISSED_ENTRY -- price already moved "
            "past the recommended entry zone (decision_v2 output, unmodified).",
        )

    was_actionable = is_actionable_buy_decision(prior.classification)
    is_actionable_now = is_actionable_buy_decision(new_classification)
    if was_actionable and not is_actionable_now:
        return (
            ShadowLifecycleResult.CHASE_RISK,
            f"{snapshot.symbol} was actionable ({prior.classification}) and Decision V2 downgraded it to "
            f"{new_classification} without ever flagging MISSED_ENTRY -- consistent with price having "
            "run away too fast for a safe entry (decision_v2's own anti-chase behavior, unmodified).",
        )

    if _is_material_change(prior, snapshot, new_stage1_score):
        return (
            ShadowLifecycleResult.REFRESHED_SIGNAL,
            f"{snapshot.symbol}'s classification/confidence/score/entry-status/price-plan changed "
            "materially since its last live shadow signal.",
        )

    return (
        ShadowLifecycleResult.UNCHANGED_SIGNAL,
        f"No material change for {snapshot.symbol} since its last live shadow signal.",
    )


# ---------------------------------------------------------------------------
# Phase 14: shadow ledger emission.
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ShadowEmissionResult:
    signals_by_result: Dict[ShadowLifecycleResult, int] = field(default_factory=dict)

    def count(self, result: ShadowLifecycleResult) -> int:
        return self.signals_by_result.get(result, 0)


def emit_shadow_signals(
    session: Session,
    cycle_id: str,
    scan_run_id: int,
    selection: RecurrentCandidateSelection,
    stage1_score_by_symbol: Dict[str, float],
    emitted_at: Optional[datetime] = None,
) -> ShadowEmissionResult:
    """Reads the real DecisionV2Snapshot rows this cycle's Stage 2 call
    just wrote for scan_run_id, classifies each symbol's lifecycle
    transition, and persists a ShadowLiveSignal row for every
    PERSISTED_LIFECYCLE_RESULTS outcome -- exactly the same
    read-snapshots-back-by-scan_run_id pattern
    radar_v2.emit_radar_opportunities already uses, applied to the
    shadow ledger instead of RadarOpportunity. Also creates a pending
    DecisionV2Outcome for every actionable snapshot Stage 2 produced
    this cycle (idempotent, unconditional -- identical to what
    emit_radar_opportunities already does), so Shadow Mode's own
    detections get real forward-test measurement independent of
    whether a ledger row was written for display."""
    emitted_at = emitted_at or datetime.now(timezone.utc)
    counts: Dict[ShadowLifecycleResult, int] = {}

    snapshots = (
        session.query(DecisionV2Snapshot)
        .filter(
            DecisionV2Snapshot.scan_run_id == scan_run_id,
            DecisionV2Snapshot.symbol.in_(selection.symbols),
        )
        .all()
    )

    for snapshot in snapshots:
        create_pending_decision_v2_outcome(session, snapshot)

        prior = current_live_shadow_signal(session, snapshot.symbol)
        new_stage1_score = stage1_score_by_symbol.get(snapshot.symbol)
        result, reason = classify_lifecycle(prior, snapshot, new_stage1_score)
        counts[result] = counts.get(result, 0) + 1

        if result == ShadowLifecycleResult.UNCHANGED_SIGNAL:
            continue

        row = ShadowLiveSignal(
            cycle_id=cycle_id,
            symbol=snapshot.symbol,
            stock_id=snapshot.stock_id,
            decision_v2_snapshot_id=snapshot.id,
            lifecycle_result=result,
            change_reason=reason,
            selection_reason=selection.selection_reason_by_symbol.get(snapshot.symbol),
            previous_classification=prior.classification if prior else None,
            classification=snapshot.decision,
            previous_confidence_score=prior.confidence_score if prior else None,
            confidence_score=snapshot.confidence_score,
            previous_entry_status=prior.entry_status if prior else None,
            entry_status=snapshot.entry_status,
            previous_stage1_ranking_score=prior.stage1_ranking_score if prior else None,
            stage1_ranking_score=new_stage1_score,
            price_at_signal=snapshot.current_price,
            entry_zone_low=snapshot.entry_zone_low,
            entry_zone_high=snapshot.entry_zone_high,
            stop_loss=snapshot.stop_loss,
            target_1=snapshot.target_1,
            target_2=snapshot.target_2,
            target_3=snapshot.target_3,
            risk_reward_target_1=snapshot.risk_reward_target_1,
            data_freshness_status=snapshot.data_freshness_status,
            decision_timestamp=snapshot.decision_timestamp,
            decision_engine_version=snapshot.analysis_version,
            emitted_at=emitted_at,
        )
        session.add(row)
        session.flush()  # assigns row.id, needed to point the prior row at it

        if prior is not None:
            prior.superseded_by_id = row.id

    session.commit()
    return ShadowEmissionResult(signals_by_result=counts)


# ---------------------------------------------------------------------------
# Phase 2/17/18: quota authority + degradation.
# ---------------------------------------------------------------------------


def _quota_allows_a_recurrent_cycle(
    rate_limiter: SahmkRateLimiter, max_candidates: int
) -> Tuple[bool, Optional[str], Dict[str, Any]]:
    """Fails closed: upstream-confirmed-exhaustion (the highest-priority
    truth in SahmkRateLimiter.get_status() -- see that module's own
    docstring) always wins over any local optimistic counter, exactly
    like IntervalMarketIntelligenceScheduler's own
    _quota_allows_a_new_cycle. On top of that existing check, this
    scheduler additionally requires enough of its OWN reserved
    live-scan-eligible quota (remaining_today_for_live_scan -- P0 quota
    architecture repair, protected from routine ingestion the same way
    the critical reserve is protected from background work) to cover
    its own worst-case per-cycle spend (max_candidates) PLUS a further
    self-imposed margin (get_live_recurrent_scan_request_reserve()) so
    a recurrent cycle never itself pushes its own remaining reserve
    down to the point where the NEXT cycle later the same day would be
    starved."""
    status = rate_limiter.get_status()
    if status.get("upstream_confirmed_exhausted"):
        return False, "upstream_confirmed_exhausted", status

    # P0 quota architecture repair: this cycle now spends its requests
    # at priority=LIVE_SCAN (see the call site below), which draws from
    # its own protected reserve -- remaining_today_for_live_scan --
    # rather than the undivided background pool routine ingestion also
    # draws from. Checked here as a pre-flight (this scheduler's own
    # existing self-limiting guard, unchanged in spirit) purely to fail
    # fast with a clear skip_reason before even selecting candidates;
    # the rate limiter's own acquire() cutoff (SahmkRateLimiter,
    # reserved_for_live_scan) remains the true, authoritative guarantee
    # this cycle cannot spend below its reserve even if this pre-check
    # were ever skipped or wrong.
    remaining_live_scan = status.get("remaining_today_for_live_scan")
    floor = get_scan_min_background_quota_remaining()
    required = max(floor, max_candidates + get_live_recurrent_scan_request_reserve())
    if remaining_live_scan is not None and remaining_live_scan < required:
        return (
            False,
            f"insufficient_live_scan_quota:remaining={remaining_live_scan},required={required}",
            status,
        )

    return True, None, status


# ---------------------------------------------------------------------------
# Phase 4/5/10: the scheduler itself.
# ---------------------------------------------------------------------------


@runtime_checkable
class _StartStoppable(Protocol):
    def start(self) -> None:
        ...

    async def stop(self) -> None:
        ...

    @property
    def is_running(self) -> bool:
        ...


class RecurrentLiveScanScheduler:
    """Satisfies the same `_StartStoppable` shape
    `IntervalMarketIntelligenceScheduler`/`LiveMarketModeScheduler`
    already use, so main.py can wrap an instance of this class in its
    OWN, second `LiveMarketModeScheduler` for Tadawul-hours gating
    without any change to that proven class -- see this module's own
    docstring."""

    def __init__(
        self,
        session_factory=None,
        market_provider_getter: Optional[Callable[[], Awaitable[IMarketDataProvider]]] = None,
        repository: Optional[MarketIntelligenceRepository] = None,
        leader_lock: Optional[SchedulerLeaderLock] = None,
        rate_limiter: Optional[SahmkRateLimiter] = None,
        clock: Optional[Callable[[], datetime]] = None,
        run_market_scan_job_fn: Optional[Callable[..., Awaitable[Any]]] = None,
    ):
        self._session_factory = session_factory or self._default_session_factory
        self._get_market_provider = market_provider_getter or self._default_market_provider_getter
        self._repository = repository or MarketIntelligenceRepository()
        self._leader_lock = leader_lock or SchedulerLeaderLock(lease_key=_LEASE_KEY)
        self._rate_limiter = rate_limiter or get_default_rate_limiter()
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._run_market_scan_job = run_market_scan_job_fn or run_market_scan_job
        self._task = None

    @staticmethod
    def _default_session_factory() -> Session:
        from src.core.db import database

        return database.get_session_factory()()

    @staticmethod
    async def _default_market_provider_getter() -> IMarketDataProvider:
        from src.market_data.provider_factory import get_market_data_provider

        return await get_market_data_provider()

    @property
    def is_running(self) -> bool:
        return self._task is not None

    def start(self) -> None:
        """No internal LIVE_RECURRENT_SCAN_ENABLED gate here, matching
        every other scheduler in this codebase (IngestionScheduler,
        IntervalMarketIntelligenceScheduler): the enable flag is
        checked once by the caller (main.py's startup wiring) before
        ever constructing an instance, not re-checked on every
        start()."""
        if self._task is not None:
            logger.warning("RecurrentLiveScanScheduler.start() called while already running -- ignoring.")
            return
        self._task = asyncio.ensure_future(self._loop())
        logger.info(
            "RecurrentLiveScanScheduler started (interval=%dmin, shadow_mode=%s).",
            get_live_recurrent_scan_interval_minutes(),
            is_live_recurrent_scan_shadow_mode(),
        )

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
        self._leader_lock.release()
        logger.info("RecurrentLiveScanScheduler stopped.")

    async def _loop(self) -> None:
        interval_seconds = get_live_recurrent_scan_interval_minutes() * 60
        lease_seconds = get_live_recurrent_scan_leader_lease_seconds()
        while True:
            try:
                if self._leader_lock.try_acquire_or_renew(lease_seconds):
                    await self._run_one_cycle()
                else:
                    logger.debug("RecurrentLiveScanScheduler: not leader this tick -- skipping.")
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Unexpected error running a recurrent live-scan cycle.")
            await asyncio.sleep(interval_seconds)

    def _persist_cycle(
        self,
        session: Session,
        cycle_id: str,
        triggered_at: datetime,
        status: RecurrentScanCycleStatus,
        *,
        skip_reason: Optional[str] = None,
        error_summary: Optional[str] = None,
        market_status: Optional[str] = None,
        active_signal_candidate_count: Optional[int] = None,
        new_stage1_candidate_count: Optional[int] = None,
        symbols_selected_count: Optional[int] = None,
        symbols_evaluated_count: Optional[int] = None,
        emission: Optional[ShadowEmissionResult] = None,
        quota_remaining_before: Optional[int] = None,
        quota_remaining_after: Optional[int] = None,
        requests_used_estimate: Optional[int] = None,
        scan_run_id: Optional[int] = None,
    ) -> RecurrentScanCycle:
        emission = emission or ShadowEmissionResult()
        row = RecurrentScanCycle(
            cycle_id=cycle_id,
            status=status,
            skip_reason=skip_reason,
            error_summary=error_summary,
            market_status=market_status,
            active_signal_candidate_count=active_signal_candidate_count,
            new_stage1_candidate_count=new_stage1_candidate_count,
            symbols_selected_count=symbols_selected_count,
            symbols_evaluated_count=symbols_evaluated_count,
            signals_new_opportunity_count=emission.count(ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY),
            signals_refreshed_count=emission.count(ShadowLifecycleResult.REFRESHED_SIGNAL),
            signals_missed_entry_count=emission.count(ShadowLifecycleResult.MISSED_ENTRY),
            signals_chase_risk_count=emission.count(ShadowLifecycleResult.CHASE_RISK),
            signals_invalidated_count=emission.count(ShadowLifecycleResult.INVALIDATED_SIGNAL),
            signals_unchanged_count=emission.count(ShadowLifecycleResult.UNCHANGED_SIGNAL),
            quota_remaining_before=quota_remaining_before,
            quota_remaining_after=quota_remaining_after,
            requests_used_estimate=requests_used_estimate,
            scan_run_id=scan_run_id,
            triggered_at=triggered_at,
            finished_at=datetime.now(timezone.utc),
        )
        session.add(row)
        session.commit()
        logger.info(
            "RecurrentLiveScanScheduler cycle %s: status=%s skip_reason=%s "
            "selected=%s evaluated=%s new_opportunity=%d refreshed=%d missed_entry=%d "
            "chase_risk=%d invalidated=%d unchanged=%d",
            cycle_id, status.value, skip_reason,
            symbols_selected_count, symbols_evaluated_count,
            row.signals_new_opportunity_count, row.signals_refreshed_count,
            row.signals_missed_entry_count, row.signals_chase_risk_count,
            row.signals_invalidated_count, row.signals_unchanged_count,
        )
        return row

    async def _run_one_cycle(self) -> Optional[RecurrentScanCycle]:
        """Every failure mode below -- including the quota check itself
        and acquiring a DB session -- is inside the same outer
        try/except, so a cycle NEVER raises out to `_loop()` uncaught:
        either a real RecurrentScanCycle row records what happened, or
        (only if persistence itself is impossible, e.g. the DB is
        unreachable) this is logged and swallowed -- matching every
        other scheduler in this codebase's own "a bad cycle must never
        kill the loop" guarantee."""
        cycle_id = uuid.uuid4().hex
        triggered_at = self._clock()
        quota_remaining_before = None
        session = None

        try:
            quota_ok, quota_skip_reason, quota_status = _quota_allows_a_recurrent_cycle(
                self._rate_limiter, get_live_recurrent_scan_max_candidates()
            )
            quota_remaining_before = quota_status.get("remaining_today_for_background")
            session = self._session_factory()

            if not quota_ok:
                logger.warning("RecurrentLiveScanScheduler: skipping cycle %s -- %s.", cycle_id, quota_skip_reason)
                return self._persist_cycle(
                    session, cycle_id, triggered_at, RecurrentScanCycleStatus.SKIPPED_QUOTA,
                    skip_reason=quota_skip_reason, quota_remaining_before=quota_remaining_before,
                    quota_remaining_after=quota_remaining_before,
                )

            self._repository.reap_stale_runs(session, get_max_scan_run_duration_hours())
            in_flight = self._repository.has_in_flight_run(session)
            if in_flight is not None:
                logger.info(
                    "RecurrentLiveScanScheduler: skipping cycle %s -- scan run %d (%s) already in progress.",
                    cycle_id, in_flight.id, in_flight.status.value,
                )
                return self._persist_cycle(
                    session, cycle_id, triggered_at, RecurrentScanCycleStatus.SKIPPED_LOCKED,
                    skip_reason=f"in_flight_run:{in_flight.id}",
                    quota_remaining_before=quota_remaining_before, quota_remaining_after=quota_remaining_before,
                )

            selection = select_recurrent_candidates(session, get_live_recurrent_scan_max_candidates())

            if not selection.symbols:
                return self._persist_cycle(
                    session, cycle_id, triggered_at, RecurrentScanCycleStatus.SKIPPED_NO_CANDIDATES,
                    skip_reason="no_candidates",
                    active_signal_candidate_count=selection.active_signal_total_count,
                    new_stage1_candidate_count=selection.new_stage1_candidate_count,
                    symbols_selected_count=0,
                    quota_remaining_before=quota_remaining_before, quota_remaining_after=quota_remaining_before,
                )

            run = self._repository.create_scan_run(
                session, symbols_requested=len(selection.symbols), is_shadow_internal=True
            )
            run_id = run.id

            with priority_scope(LIVE_SCAN), operation_scope(LIVE_RECURRENT_SCAN):
                provider = await self._get_market_provider()
                await self._run_market_scan_job(run_id, self._session_factory, provider, symbols=selection.symbols)

            session.expire_all()

            # The canonical, already-computed per-symbol accounting for
            # scan_run_id lives on the MarketScanRun row itself --
            # MarketIntelligenceEngine.execute_scan always calls
            # repository.finish_run() with real symbols_succeeded/
            # symbols_skipped/symbols_failed (and a final SUCCESS/FAILED
            # status) before returning, on every path including its own
            # exception handler (see market_engine.py). Reading it back
            # here -- rather than assuming every selected symbol was
            # evaluated -- is the single source of truth this cycle's
            # own counters must agree with; no second, independently-
            # maintained accounting is introduced.
            run_row = self._repository.get_run(session, run_id)
            symbols_succeeded = (run_row.symbols_succeeded or 0) if run_row is not None else 0
            symbols_failed = (run_row.symbols_failed or 0) if run_row is not None else 0
            stage2_run_status = run_row.status if run_row is not None else None

            emission = emit_shadow_signals(
                session, cycle_id, run_id, selection, selection.stage1_score_by_symbol, emitted_at=triggered_at
            )

            quota_status_after = self._rate_limiter.get_status()
            quota_remaining_after = quota_status_after.get("remaining_today_for_background")
            requests_used_estimate = (
                quota_remaining_before - quota_remaining_after
                if quota_remaining_before is not None and quota_remaining_after is not None
                else None
            )

            total_persisted = sum(
                emission.count(r)
                for r in (
                    ShadowLifecycleResult.NEW_INTRADAY_OPPORTUNITY,
                    ShadowLifecycleResult.REFRESHED_SIGNAL,
                    ShadowLifecycleResult.MISSED_ENTRY,
                    ShadowLifecycleResult.CHASE_RISK,
                    ShadowLifecycleResult.INVALIDATED_SIGNAL,
                )
            )

            # A cycle whose Stage 2 run produced zero successful
            # evaluations (the engine's own exception path, or every
            # selected symbol individually failed even though the
            # engine itself did not raise) is FAILED -- there is no
            # usable output to call partial. A cycle that produced SOME
            # real evaluations but also had real per-symbol failures,
            # or discovered upstream-confirmed SAHMK exhaustion by the
            # time it finished, is PARTIAL_PROVIDER_FAILURE: usable
            # output exists, but the cycle did not complete as
            # intended. Everything else is a clean SUCCESS/
            # SUCCESS_NO_CHANGE, exactly as before. `skipped` symbols
            # (insufficient data -- a normal candidate-eligibility
            # outcome, tracked separately from `failed`) are never
            # counted as a provider failure here.
            provider_signal = symbols_failed > 0 or bool(quota_status_after.get("upstream_confirmed_exhausted"))
            error_summary = None
            if stage2_run_status == MarketScanStatus.FAILED or (symbols_succeeded == 0 and symbols_failed > 0):
                final_status = RecurrentScanCycleStatus.FAILED
                error_summary = (
                    f"Stage 2 scan run {run_id} produced zero successful evaluations "
                    f"(status={stage2_run_status}, succeeded={symbols_succeeded}, failed={symbols_failed})."
                )
            elif symbols_succeeded > 0 and provider_signal:
                final_status = RecurrentScanCycleStatus.PARTIAL_PROVIDER_FAILURE
                error_summary = (
                    f"{symbols_failed} of {len(selection.symbols)} selected symbol(s) failed during Stage 2 "
                    f"(succeeded={symbols_succeeded})."
                )
            else:
                final_status = (
                    RecurrentScanCycleStatus.SUCCESS if total_persisted > 0 else RecurrentScanCycleStatus.SUCCESS_NO_CHANGE
                )

            return self._persist_cycle(
                session, cycle_id, triggered_at, final_status,
                error_summary=error_summary,
                active_signal_candidate_count=selection.active_signal_total_count,
                new_stage1_candidate_count=selection.new_stage1_candidate_count,
                symbols_selected_count=len(selection.symbols),
                symbols_evaluated_count=symbols_succeeded,
                emission=emission,
                quota_remaining_before=quota_remaining_before,
                quota_remaining_after=quota_remaining_after,
                requests_used_estimate=requests_used_estimate,
                scan_run_id=run_id,
            )
        except Exception as exc:
            logger.exception("RecurrentLiveScanScheduler: cycle %s failed.", cycle_id)
            persist_session = session
            try:
                if persist_session is not None:
                    persist_session.rollback()
                else:
                    # The failure happened before a session could even be
                    # opened (e.g. the DB itself is unreachable) -- try a
                    # fresh one purely to record the FAILED cycle; if that
                    # also fails, there is nowhere left to record this and
                    # the failure is logged only (never re-raised -- the
                    # loop must keep scheduling).
                    persist_session = self._session_factory()
                return self._persist_cycle(
                    persist_session, cycle_id, triggered_at, RecurrentScanCycleStatus.FAILED,
                    error_summary=str(exc),
                    quota_remaining_before=quota_remaining_before, quota_remaining_after=quota_remaining_before,
                )
            except Exception:
                logger.exception(
                    "RecurrentLiveScanScheduler: cycle %s failed AND could not be recorded (persistence itself "
                    "failed) -- swallowed so the scheduler loop keeps running.",
                    cycle_id,
                )
                return None
            finally:
                if persist_session is not None and persist_session is not session:
                    persist_session.close()
        finally:
            if session is not None:
                session.close()
