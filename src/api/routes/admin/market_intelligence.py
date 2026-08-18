"""POST /api/v1/admin/market-intelligence/diagnostic-scan -- staff-only.

Runs one controlled real SAHMK market-data poll through the *exact
same* production code path the Live Market Mode scheduler and the
customer-facing POST /api/v1/market/scan already use
(get_market_data_provider -> run_market_scan_job ->
MarketIntelligenceEngine.execute_scan -> MarketScanner.scan ->
build_analysis_context -> SahmkMarketDataProvider), never a
parallel diagnostic-only implementation. Unlike POST /market/scan (a
BackgroundTask that returns immediately), this route awaits the scan
inline so the response can report real, immediate evidence -- SAHMK
connectivity outcome, rows written, sample symbols, price/timestamp
freshness -- instead of requiring a follow-up poll.

Defaults to a small, fixed set of liquid Tadawul symbols ("one
controlled poll", not a full-market scan); a caller may override with
its own short list. If the real SAHMK connectivity probe does not
succeed (current_provider_kind != "sahmk"), no scan is run and no
recommendation rows are written -- this route never lets a diagnostic
call publish anything off synthetic/fallback data.

Never logs or returns the SAHMK API key -- only its configured
presence (sahmk_key_present) and the outcome of the connectivity
attempt are ever surfaced, matching get_market_data_health()'s
existing secret-free contract.
"""

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query
from sqlalchemy import func, text
from sqlalchemy.orm import Session

from src.analysis.decision_v2.types import DECISION_LABELS_AR, Decision

from src.api.schemas.market_intelligence import (
    ConfidenceBucketCountOut,
    ContinueScanCycleOut,
    DbConsistencyOut,
    DecisionCountOut,
    DecisionIntelligenceOut,
    DiagnosticDecisionV2SampleOut,
    DiagnosticSampleSymbolOut,
    DiagnosticScanOut,
    DirectoryPaginationDiagnosticsOut,
    FullDiscoveryTriggerOut,
    IngestionJobStatusOut,
    MarketCoverageOut,
    MarketScanRequest,
    MarketScanRunOut,
    ObservedFieldOut,
    ObservedFieldValueOut,
    PipelineStageOut,
    RadarOpportunityDetailOut,
    RadarOpportunitySummaryOut,
    RadarStage1ComponentScoresOut,
    RadarV2ExtendedPerformanceOut,
    RadarV2GroupPerformanceOut,
    RadarV2PerformanceOut,
    RadarV2SahmkConsumptionOut,
    RadarV2ScanOut,
    RadarV2SummaryOut,
    RejectedOpportunityOut,
    RejectionReasonCountOut,
    RiskCountOut,
    SectorCoverageOut,
    SectorRankingOut,
    Stage1CandidateOut,
    Stage1ComponentScoresOut,
    Stage1ScanOut,
    Stage1SignalOut,
    Stage2ValidateRequest,
    SymbolLookupCheckOut,
    SymbolLookupDiagnosticOut,
    SymbolLookupDiagnosticsOut,
    TopOpportunityOut,
    UniverseBucketCountOut,
    UniverseDiagnosticsOut,
    UniverseSampleEntryOut,
)
from src.auth.rbac import require_any_staff_role, require_staff_role
from src.auth.token_store import get_redis_client
from src.core.db.database import get_db
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2Snapshot,
    Dividend,
    FundamentalSnapshot,
    IngestionRunLog,
    MarketScanProgress,
    MarketScanRun,
    PriceBar,
    RadarOpportunity,
    StaffRole,
    Stock,
    SymbolIntelligenceRecord,
    User,
)
from src.market_data.ingestion import config as ingestion_config
from src.market_data.providers.sector_provider import get_sector_classification_provider
from src.market_data.sahmk.operation_scope import ADMIN_DIAGNOSTICS, MARKET_SCAN, RADAR_V2, operation_scope
from src.market_data.sahmk.rate_limiter import get_default_rate_limiter
from src.market_data.sahmk.request_priority import BACKGROUND, priority_scope
from src.market_data.strict_mode import StrictRealDataUnavailableError
from src.market_intelligence.config import (
    get_scan_min_background_quota_remaining,
    get_market_scan_symbols_per_cycle,
    get_max_scan_run_duration_hours,
    get_radar_stage2_candidate_cap,
    get_scan_leader_lease_seconds,
)
from src.market_intelligence.radar_v2 import (
    compute_radar_v2_extended_performance,
    compute_radar_v2_performance,
    list_live_opportunities,
    run_radar_v2_cycle,
)
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock
from src.market_intelligence.services.scan_job_runner import run_market_scan_job
from src.market_intelligence.stage1_local_scan import run_stage1_local_scan
from src.market_intelligence.symbol_selector import SymbolSelector

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/market-intelligence", tags=["admin"])

_repository = MarketIntelligenceRepository()

# A small, fixed set of well-known, liquid Tadawul symbols -- real
# securities (Saudi Aramco, Al Rajhi Bank, Saudi National Bank), used
# only when the caller doesn't supply its own list. Deliberately short:
# this route exists to prove connectivity/persistence work right now,
# not to run a full-market scan.
_DEFAULT_DIAGNOSTIC_SYMBOLS = ["2222", "1120", "1180"]


@router.post("/diagnostic-scan", response_model=DiagnosticScanOut)
async def trigger_diagnostic_scan(
    request: MarketScanRequest,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> DiagnosticScanOut:
    from src.market_data import config as market_data_config
    from src.market_data.provider_factory import get_market_data_health, get_market_data_provider

    triggered_at = datetime.now(timezone.utc)

    def _scrub(message: str) -> str:
        # Defense in depth: no code path today puts the raw key into an
        # exception message, but a diagnostic endpoint whose whole job
        # is surfacing error text must never trust that invariant
        # blindly -- strip the configured key's exact value if it ever
        # appears, same rule get_market_data_health() already
        # guarantees for its own fields.
        key = market_data_config.get_sahmk_api_key()
        return message.replace(key, "***") if key else message

    sahmk_error: Optional[str] = None
    try:
        # force_refresh=True: a diagnostic endpoint whose entire purpose
        # is proving connectivity *right now* must never answer from a
        # stale cached selection (default cache window is 60s).
        # priority=BACKGROUND: this route is an admin diagnostic, not
        # the live Decision Engine scan pipeline -- it must draw from
        # the background-eligible portion of today's SAHMK quota, never
        # the reserve set aside for live-market-critical operations
        # (see src.market_data.sahmk.rate_limiter/request_priority).
        with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
            await get_market_data_provider(force_refresh=True)
    except StrictRealDataUnavailableError as exc:
        sahmk_error = _scrub(f"{type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 -- report every failure mode, never crash this diagnostic route itself
        sahmk_error = _scrub(f"{type(exc).__name__}: {exc}")

    health = get_market_data_health()
    provider_kind = health["current_provider_kind"]

    run = None
    rows_written = 0
    sample_symbols: List[DiagnosticSampleSymbolOut] = []
    data_is_fresh = None
    freshness_note = ""
    decision_v2_rows_written = 0
    decision_v2_sample: List[DiagnosticDecisionV2SampleOut] = []

    if provider_kind == "sahmk":
        symbols = request.symbols or list(_DEFAULT_DIAGNOSTIC_SYMBOLS)

        _repository.reap_stale_runs(session, get_max_scan_run_duration_hours())
        in_flight = _repository.has_in_flight_run(session)
        if in_flight is not None:
            sahmk_error = (
                f"Skipped: a market scan (run {in_flight.id}, {in_flight.status.value}) "
                "is already in progress -- wait for it to finish before running a diagnostic scan."
            )
        else:
            provider = await get_market_data_provider()
            run = _repository.create_scan_run(session, symbols_requested=len(symbols))

            # Local import so a test's monkeypatch of
            # src.core.db.database.get_session_factory is honored, same
            # reasoning src/api/routes/market.py's create_scan documents.
            from src.core.db.database import get_session_factory

            with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
                await run_market_scan_job(run.id, get_session_factory(), provider, symbols)

            session.expire_all()
            run = _repository.get_run(session, run.id)

            records = (
                session.query(SymbolIntelligenceRecord)
                .filter(SymbolIntelligenceRecord.scan_run_id == run.id)
                .all()
            )
            rows_written = len(records)
            sample_symbols = [
                DiagnosticSampleSymbolOut(
                    symbol=r.symbol,
                    recommendation=r.recommendation.value,
                    latest_price=float(r.latest_price) if r.latest_price is not None else None,
                    evaluated_at=r.evaluated_at,
                )
                for r in records[:10]
            ]
            # Phase 3A evidence: the same scan just persisted a
            # DecisionV2Snapshot row per successful symbol via
            # MarketIntelligenceRepository.save_symbol_records -- read
            # them back the same way SymbolIntelligenceRecord is read
            # back above, so this diagnostic response is direct,
            # unambiguous proof that the scheduled-scan pipeline (not
            # just the on-demand /decision-v2 route) computes and
            # persists Decision Engine V2 results with scan_run_id set.
            v2_records = (
                session.query(DecisionV2Snapshot)
                .filter(DecisionV2Snapshot.scan_run_id == run.id)
                .all()
            )
            decision_v2_rows_written = len(v2_records)
            decision_v2_sample = [
                DiagnosticDecisionV2SampleOut(
                    symbol=r.symbol,
                    decision=r.decision,
                    decision_label_ar=r.decision_label_ar,
                    confidence_score=float(r.confidence_score),
                    entry_zone_low=float(r.entry_zone_low) if r.entry_zone_low is not None else None,
                    entry_zone_high=float(r.entry_zone_high) if r.entry_zone_high is not None else None,
                    scan_run_id=r.scan_run_id,
                    decision_timestamp=r.decision_timestamp,
                )
                for r in v2_records[:10]
            ]
            if records:
                now = datetime.now(timezone.utc)
                oldest = min(r.evaluated_at for r in records)
                # SQLite (used in tests, possibly a deployment without
                # Postgres) does not round-trip a timezone-aware
                # DateTime faithfully -- same pitfall
                # MarketIntelligenceRepository.mark_running already
                # documents; treat a naive value as UTC rather than let
                # the subtraction raise.
                if oldest.tzinfo is None:
                    oldest = oldest.replace(tzinfo=timezone.utc)
                age_seconds = (now - oldest).total_seconds()
                # Generous freshness bound: this route's own scan just
                # ran, so anything not within 15 minutes of triggering
                # indicates a stale quote was served, not a transient
                # timing artifact.
                data_is_fresh = age_seconds < 900
                freshness_note = f"oldest of {len(records)} record(s) evaluated {age_seconds:.0f}s ago"

    # Evidence of the most recent *completed* scheduled/diagnostic scan
    # (V1 SymbolIntelligenceRecord + Phase 3A's DecisionV2Snapshot),
    # looked up regardless of whether this call itself triggered a new
    # scan -- this is the only reliable way to observe real V1/V2
    # output from the Live Market Mode scheduler's own runs, since a
    # diagnostic scan dispatched while a scheduled scan is RUNNING is
    # correctly skipped by the overlap guard above and would otherwise
    # report nothing at all. Clearly a separate, explicitly-labeled
    # "latest completed run" block -- never conflated with this call's
    # own (possibly skipped) run_id/run_status fields above.
    latest_completed_run = _repository.get_latest_successful_run(session)
    latest_completed_run_v1_rows_written = 0
    latest_completed_run_v1_sample_symbols: List[DiagnosticSampleSymbolOut] = []
    latest_completed_run_decision_v2_rows_written = 0
    latest_completed_run_decision_v2_sample: List[DiagnosticDecisionV2SampleOut] = []
    if latest_completed_run is not None:
        latest_v1_records = (
            session.query(SymbolIntelligenceRecord)
            .filter(SymbolIntelligenceRecord.scan_run_id == latest_completed_run.id)
            .all()
        )
        latest_completed_run_v1_rows_written = len(latest_v1_records)
        latest_completed_run_v1_sample_symbols = [
            DiagnosticSampleSymbolOut(
                symbol=r.symbol,
                recommendation=r.recommendation.value,
                latest_price=float(r.latest_price) if r.latest_price is not None else None,
                evaluated_at=r.evaluated_at,
            )
            for r in latest_v1_records[:5]
        ]
        latest_v2_records = (
            session.query(DecisionV2Snapshot)
            .filter(DecisionV2Snapshot.scan_run_id == latest_completed_run.id)
            .all()
        )
        latest_completed_run_decision_v2_rows_written = len(latest_v2_records)
        latest_completed_run_decision_v2_sample = [
            DiagnosticDecisionV2SampleOut(
                symbol=r.symbol,
                decision=r.decision,
                decision_label_ar=r.decision_label_ar,
                confidence_score=float(r.confidence_score),
                entry_zone_low=float(r.entry_zone_low) if r.entry_zone_low is not None else None,
                entry_zone_high=float(r.entry_zone_high) if r.entry_zone_high is not None else None,
                scan_run_id=r.scan_run_id,
                decision_timestamp=r.decision_timestamp,
            )
            for r in latest_v2_records[:5]
        ]

    # Re-read health after the scan: run_market_scan_job's own preflight
    # (or the scan itself) may have updated last_connectivity_status.
    final_health = get_market_data_health()
    can_publish = (
        final_health["current_provider_kind"] == "sahmk" if final_health["strict_real_data"] else True
    )
    last_scan_source = {"sahmk": "SAHMK_REAL", "dev": "DEV_SYNTHETIC"}.get(final_health["current_provider_kind"])

    return DiagnosticScanOut(
        triggered_at=triggered_at,
        operation_tested="GET /market/summary/ (auth probe) + GET /quote/{symbol}/ (per-symbol poll)",
        sahmk_connectivity_status=final_health["last_connectivity_status"] or "UNKNOWN",
        sahmk_error=sahmk_error,
        current_provider_kind=final_health["current_provider_kind"],
        last_connectivity_status=final_health["last_connectivity_status"],
        last_connectivity_at=final_health["last_connectivity_at"],
        can_publish_recommendations=can_publish,
        strict_real_data=final_health["strict_real_data"],
        synthetic_allowed=final_health["synthetic_allowed"],
        sahmk_key_present=final_health["sahmk_key_present"],
        run_id=run.id if run else None,
        run_status=run.status.value if run else None,
        run_error_summary=run.error_summary if run else None,
        symbols_requested=run.symbols_requested if run else 0,
        symbols_succeeded=run.symbols_succeeded if run else 0,
        symbols_failed=run.symbols_failed if run else 0,
        rows_written=rows_written,
        sample_symbols=sample_symbols,
        last_scan_source=last_scan_source,
        data_is_fresh=data_is_fresh,
        freshness_note=freshness_note,
        decision_v2_rows_written=decision_v2_rows_written,
        decision_v2_sample=decision_v2_sample,
        latest_completed_run_id=latest_completed_run.id if latest_completed_run else None,
        latest_completed_run_v1_rows_written=latest_completed_run_v1_rows_written,
        latest_completed_run_v1_sample_symbols=latest_completed_run_v1_sample_symbols,
        latest_completed_run_decision_v2_rows_written=latest_completed_run_decision_v2_rows_written,
        latest_completed_run_decision_v2_sample=latest_completed_run_decision_v2_sample,
    )


async def _run_one_bounded_background_cycle(
    session: Session, caller: str, resolve_symbols, *, operation: str = MARKET_SCAN,
) -> ContinueScanCycleOut:
    """Shared implementation behind every manually triggered scan
    cycle -- `/continue-scan-cycle` (stale-first rotation) and
    `/stage2-validate-candidates` (an explicit, Stage-1-narrowed
    symbol list). Every safety guard a manually triggered cycle needs
    lives here exactly once, so a new symbol-resolution strategy never
    has to duplicate any of them:

      * upstream_confirmed_exhausted / background_quota_low checks --
        a cycle costs at most MARKET_SCAN_SYMBOLS_PER_CYCLE real
        provider calls (fewer once cache hits are counted); refusing
        to start unless that full worst case still fits comfortably
        inside the remaining background budget is what actually
        prevents this path from ever running the critical reserve
        down.
      * database/redis health probes.
      * SAHMK connectivity probe (current_provider_kind == "sahmk").
      * The same overlap guard (`has_in_flight_run`) every other
        scan-triggering route already applies.
      * SchedulerLeaderLock (the same shared Redis lease key the
        scheduler's own loop uses) -- only one cycle, from any source,
        can run at a time.
      * priority_scope(BACKGROUND) around the scan job -- these SAHMK
        requests are background-eligible only; they can never draw on
        `reserved_for_critical`.

    `operation` tags the run's SAHMK per-operation accounting (default
    MARKET_SCAN, matching this function's original two callers below
    unchanged); Radar V2's own route passes `operation=RADAR_V2` so its
    consumption is separately attributable in `by_operation` without a
    second accounting mechanism.

    `resolve_symbols` is called only after every zero-cost pre-flight
    check has already passed and the leader lock has been acquired --
    a caller's own symbol-resolution logic never needs to re-check any
    of the above itself. `executed=False` always means no scan ran and
    no SAHMK quota was spent this call."""
    triggered_at = datetime.now(timezone.utc)

    def _stopped(reason: str, quota_before=None, in_flight_run_id: Optional[int] = None) -> ContinueScanCycleOut:
        return ContinueScanCycleOut(
            triggered_at=triggered_at, executed=False, stop_reason=reason,
            quota_before=quota_before, in_flight_run_id=in_flight_run_id,
        )

    # --- Pre-cycle safety checks (all zero SAHMK cost) ---
    quota_before = get_default_rate_limiter().get_status()
    if quota_before.get("upstream_confirmed_exhausted"):
        return _stopped("upstream_confirmed_exhausted", quota_before)

    remaining_bg = quota_before.get("remaining_today_for_background")
    safety_threshold = max(get_market_scan_symbols_per_cycle(), get_scan_min_background_quota_remaining())
    if remaining_bg is not None and remaining_bg < safety_threshold:
        return _stopped("background_quota_low", quota_before)

    try:
        session.execute(text("SELECT 1"))
    except Exception:
        logger.error("%s: database health probe failed.", caller, exc_info=True)
        return _stopped("database_unhealthy", quota_before)

    try:
        get_redis_client().ping()
    except Exception:
        logger.error("%s: redis health probe failed.", caller, exc_info=True)
        return _stopped("redis_unhealthy", quota_before)

    from src.market_data.provider_factory import get_market_data_health, get_market_data_provider

    health = get_market_data_health()
    if health.get("current_provider_kind") != "sahmk" or health.get("last_connectivity_status") != "SUCCESS":
        return _stopped("sahmk_not_live", quota_before)

    _repository.reap_stale_runs(session, get_max_scan_run_duration_hours())
    in_flight = _repository.has_in_flight_run(session)
    if in_flight is not None:
        return _stopped("scan_in_progress", quota_before, in_flight_run_id=in_flight.id)

    leader_lock = SchedulerLeaderLock()
    if not leader_lock.try_acquire_or_renew(get_scan_leader_lease_seconds()):
        return _stopped("not_leader", quota_before)

    symbols = resolve_symbols()
    if not symbols:
        return _stopped("universe_complete", quota_before)

    run = _repository.create_scan_run(session, symbols_requested=len(symbols))
    run_id = run.id

    provider = await get_market_data_provider()

    # Local import so a test's monkeypatch of
    # src.core.db.database.get_session_factory is honored, same
    # reasoning src/api/routes/market.py's create_scan documents.
    from src.core.db.database import get_session_factory

    with priority_scope(BACKGROUND), operation_scope(operation):
        await run_market_scan_job(run_id, get_session_factory(), provider, symbols)

    session.expire_all()
    run = _repository.get_run(session, run_id)
    quota_after = get_default_rate_limiter().get_status()

    v1_records = (
        session.query(SymbolIntelligenceRecord).filter(SymbolIntelligenceRecord.scan_run_id == run_id).all()
    )
    v2_records = session.query(DecisionV2Snapshot).filter(DecisionV2Snapshot.scan_run_id == run_id).all()

    recommendation_counts: Dict[str, int] = {}
    for record in v1_records:
        key = record.recommendation.value
        recommendation_counts[key] = recommendation_counts.get(key, 0) + 1

    decision_counts: Dict[str, int] = {}
    for record in v2_records:
        decision_counts[record.decision] = decision_counts.get(record.decision, 0) + 1

    progress = session.query(MarketScanProgress).filter(MarketScanProgress.run_id == run_id).first()

    return ContinueScanCycleOut(
        triggered_at=triggered_at,
        executed=True,
        stop_reason=None,
        run_id=run.id,
        run_status=run.status.value,
        symbols_requested=run.symbols_requested,
        symbols_succeeded=run.symbols_succeeded,
        symbols_skipped=run.symbols_skipped,
        symbols_failed=run.symbols_failed,
        skipped_symbols_summary=run.skipped_symbols_summary,
        symbols_scanned=sorted(symbols),
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=float(run.duration_seconds) if run.duration_seconds is not None else None,
        quota_before=quota_before,
        quota_after=quota_after,
        recommendation_counts=recommendation_counts,
        decision_counts=decision_counts,
        published_count=progress.published_count if progress else 0,
        rejected_count=progress.rejected_count if progress else 0,
        watch_only_count=progress.watch_only_count if progress else 0,
    )


@router.post("/continue-scan-cycle", response_model=ContinueScanCycleOut)
async def continue_scan_cycle(
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ADMIN, StaffRole.OWNER)),
) -> ContinueScanCycleOut:
    """Staff/OWNER-only: manually advances ONE more cycle of the exact
    same bounded, stale-first, BACKGROUND-priority, leader-locked
    rotation `IntervalMarketIntelligenceScheduler._run_one_cycle()`
    already runs on its own (env-configured, defaults to daily)
    interval -- so a real full-universe coverage pass can be advanced
    within a single trading day without waiting for the next scheduled
    cycle. Every safety guard lives in `_run_one_bounded_background_
    cycle` (see its own docstring); this route only supplies the
    symbol-resolution strategy: `SymbolSelector(prioritize_stale=True)`
    -- the identical oldest-data-first selection the scheduler uses,
    capped at `get_market_scan_symbols_per_cycle()`, never the full
    universe in one call.

    `stop_reason="universe_complete"` (an empty `SymbolSelector`
    result -- zero active, price-history-eligible symbols exist at
    all) is a genuine but rare edge case, NOT the normal way a
    full-universe pass finishes: because a symbol's `evaluated_at`
    only ever moves forward, the selector keeps rotating through the
    whole eligible universe forever, cycle after cycle, and never
    returns empty once every symbol has a real evaluation. The caller
    is expected to call this endpoint repeatedly, once per cycle,
    accumulating the distinct `symbols_scanned` across calls and
    comparing that count against the real active-and-eligible universe
    size (e.g. from `GET .../coverage`'s `stocks_with_price_history`)
    to know when a full pass is done -- not by waiting for an empty
    response.

    Since the SAHMK quota optimization mandate (2026-08-16), Stage 1
    of the two-stage scan (`GET .../stage1-scan`, zero SAHMK cost)
    offers a cheaper way to know which symbols are actually worth a
    live cycle -- see `POST .../stage2-validate-candidates` for the
    candidate-list-driven equivalent of this route."""
    return await _run_one_bounded_background_cycle(
        session,
        "continue_scan_cycle",
        lambda: SymbolSelector().select(session, limit=get_market_scan_symbols_per_cycle(), prioritize_stale=True),
    )


@router.post("/stage2-validate-candidates", response_model=ContinueScanCycleOut)
async def stage2_validate_candidates(
    request: Stage2ValidateRequest,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ADMIN, StaffRole.OWNER)),
) -> ContinueScanCycleOut:
    """Stage 2 of the two-stage Radar scan (SAHMK quota optimization
    mandate, 2026-08-16): spends real, live SAHMK quota ONLY on the
    exact candidate symbols Stage 1's local-only scan
    (`GET .../stage1-scan`, zero SAHMK cost) already narrowed the
    universe down to -- the caller supplies that list in the request
    body. Runs through the identical bounded, BACKGROUND-priority,
    leader-locked, quota-gated cycle `/continue-scan-cycle` uses (see
    `_run_one_bounded_background_cycle`'s own docstring for every
    guard), just symbol-list-driven instead of stale-first-rotation-
    driven.

    Capped at `get_market_scan_symbols_per_cycle()` per call, same as
    every other manually triggered cycle -- call again with the
    remaining slice of a larger candidate list to validate all of it,
    exactly like `/continue-scan-cycle`'s own repeated-call contract."""
    symbols = request.symbols[: get_market_scan_symbols_per_cycle()]
    return await _run_one_bounded_background_cycle(session, "stage2_validate_candidates", lambda: symbols)


# ============================================================================
# Basirah Radar V2 (2026-08-16) -- Phase D REST API
# ============================================================================


def radar_summary_out(opportunity: RadarOpportunity) -> RadarOpportunitySummaryOut:
    snapshot = opportunity.snapshot
    return RadarOpportunitySummaryOut(
        id=opportunity.id,
        symbol=opportunity.symbol,
        company_name_ar=snapshot.company_name_ar,
        company_name_en=snapshot.company_name_en,
        classification=opportunity.classification,
        classification_label_ar=opportunity.classification_label_ar,
        confidence_score=float(opportunity.confidence_score),
        calibrated_confidence_score=(
            float(snapshot.calibrated_confidence_score) if snapshot.calibrated_confidence_score is not None else None
        ),
        calibration_version=snapshot.calibration_version,
        price_at_signal=float(opportunity.price_at_signal) if opportunity.price_at_signal is not None else None,
        entry_zone_low=float(snapshot.entry_zone_low) if snapshot.entry_zone_low is not None else None,
        entry_zone_high=float(snapshot.entry_zone_high) if snapshot.entry_zone_high is not None else None,
        stop_loss=float(snapshot.stop_loss) if snapshot.stop_loss is not None else None,
        target_1=float(snapshot.target_1) if snapshot.target_1 is not None else None,
        target_2=float(snapshot.target_2) if snapshot.target_2 is not None else None,
        target_3=float(snapshot.target_3) if snapshot.target_3 is not None else None,
        expected_return_target_1=(
            float(snapshot.expected_return_target_1) if snapshot.expected_return_target_1 is not None else None
        ),
        risk_reward_target_1=(
            float(snapshot.risk_reward_target_1) if snapshot.risk_reward_target_1 is not None else None
        ),
        risk_level=snapshot.risk_level,
        risk_level_label_ar=snapshot.risk_level_label_ar,
        data_freshness_status=snapshot.data_freshness_status,
        stage1_rank=opportunity.stage1_rank,
        stage1_ranking_score=(
            float(opportunity.stage1_ranking_score) if opportunity.stage1_ranking_score is not None else None
        ),
        ranking_reason_ar=opportunity.ranking_reason_ar,
        emitted_at=opportunity.emitted_at,
        decision_v2_snapshot_id=opportunity.decision_v2_snapshot_id,
    )


def radar_detail_out(opportunity: RadarOpportunity, outcome: Optional[DecisionV2Outcome]) -> RadarOpportunityDetailOut:
    snapshot = opportunity.snapshot
    summary = radar_summary_out(opportunity)
    component_scores = opportunity.stage1_component_scores or {}
    signals = opportunity.stage1_signals or []
    return RadarOpportunityDetailOut(
        **summary.model_dump(),
        stage1_component_scores=RadarStage1ComponentScoresOut(**component_scores),
        stage1_signals=[Stage1SignalOut(name=s["name"], detail_ar=s["detail_ar"]) for s in signals],
        stage1_risk_reward_ratio=(
            float(opportunity.stage1_risk_reward_ratio) if opportunity.stage1_risk_reward_ratio is not None else None
        ),
        expected_holding_period_min_days=snapshot.expected_holding_period_min_days,
        expected_holding_period_max_days=snapshot.expected_holding_period_max_days,
        expected_holding_period_label_ar=snapshot.expected_holding_period_label_ar,
        positive_reasons=snapshot.positive_reasons or [],
        negative_reasons=snapshot.negative_reasons or [],
        warnings=snapshot.warnings or [],
        recommendation_basis=snapshot.recommendation_basis,
        liquidity_quality_ar=snapshot.liquidity_quality_ar,
        relative_volume=float(snapshot.relative_volume) if snapshot.relative_volume is not None else None,
        accumulation_assessment_ar=snapshot.accumulation_assessment_ar,
        decision_timestamp=snapshot.decision_timestamp,
        market_status=snapshot.market_status,
        outcome_status=outcome.status.value if outcome is not None else None,
        outcome_return_pct=float(outcome.return_pct) if outcome is not None and outcome.return_pct is not None else None,
        outcome_evaluated_at=outcome.evaluated_at if outcome is not None else None,
    )


@router.post("/radar-v2/scan", response_model=RadarV2ScanOut)
async def run_radar_v2_scan(
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ADMIN, StaffRole.OWNER)),
) -> RadarV2ScanOut:
    """Basirah Radar V2 (2026-08-16): the full ranked-opportunity pass
    -- Stage 1 (zero SAHMK cost) narrows and ranks the local universe,
    then the top `get_radar_stage2_candidate_cap()` candidates (never
    more, regardless of how many Stage 1 found) go through the exact
    same bounded, quota-gated, leader-locked Stage 2 cycle
    `/continue-scan-cycle`/`/stage2-validate-candidates` use -- tagged
    `RADAR_V2` for separately attributable SAHMK accounting (see
    `GET .../radar-v2/sahmk-consumption`). `stage2_executed=False`
    always means Radar V2 degraded gracefully rather than spending
    quota it did not have; `stage2_stop_reason` says why. See
    `run_radar_v2_cycle`'s own docstring for the complete guarantee."""
    result = await run_radar_v2_cycle(
        session,
        lambda s, caller, resolve_symbols: _run_one_bounded_background_cycle(
            s, caller, resolve_symbols, operation=RADAR_V2
        ),
    )
    return RadarV2ScanOut(
        triggered_at=result.triggered_at,
        stage1_universe_size=result.stage1_universe_size,
        stage1_candidate_count=result.stage1_candidate_count,
        stage2_candidate_cap=result.stage2_candidate_cap,
        stage2_symbols_selected=result.stage2_symbols_selected,
        stage2_executed=result.stage2_executed,
        stage2_stop_reason=result.stage2_stop_reason,
        scan_run_id=result.scan_run_id,
        opportunities_emitted=[radar_summary_out(o) for o in result.opportunities_emitted],
        opportunities_suppressed_as_duplicate=result.opportunities_suppressed_as_duplicate,
    )


@router.get("/radar-v2/opportunities", response_model=List[RadarOpportunitySummaryOut])
async def list_radar_v2_opportunities(
    classification: Optional[str] = Query(default=None, description="Filter to one classification value, e.g. BUY_CANDIDATE."),
    limit: int = Query(default=50, ge=1, le=200),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> List[RadarOpportunitySummaryOut]:
    """The current, ranked radar: only each symbol's live opportunity
    (`superseded_by_id IS NULL`) appears, ordered by stage1_ranking_score
    descending -- a symbol that was re-emitted after a material change
    appears once, as its newest row, never as a duplicate alongside the
    stale one it replaced."""
    rows = list_live_opportunities(session, classification=classification, limit=limit)
    return [radar_summary_out(o) for o in rows]


@router.get("/radar-v2/opportunities/{opportunity_id}", response_model=RadarOpportunityDetailOut)
async def get_radar_v2_opportunity(
    opportunity_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> RadarOpportunityDetailOut:
    """Full evidence for one radar opportunity, including its Stage 1
    ranking breakdown and (once real forward market data exists) its
    tracked outcome -- see RadarOpportunityDetailOut's own docstring
    for exactly which fields this does and does not include."""
    opportunity = session.query(RadarOpportunity).filter_by(id=opportunity_id).first()
    if opportunity is None:
        raise HTTPException(status_code=404, detail="Radar opportunity not found.")
    outcome = (
        session.query(DecisionV2Outcome)
        .filter_by(decision_v2_snapshot_id=opportunity.decision_v2_snapshot_id)
        .first()
    )
    return radar_detail_out(opportunity, outcome)


@router.get("/radar-v2/summary", response_model=RadarV2SummaryOut)
async def get_radar_v2_summary(
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> RadarV2SummaryOut:
    """The radar's current composition at a glance -- how many live
    opportunities exist, their classification mix, and when the radar
    last ran, without listing every opportunity."""
    live = session.query(RadarOpportunity).filter(RadarOpportunity.superseded_by_id.is_(None)).all()
    by_classification: Dict[str, int] = {}
    for o in live:
        by_classification[o.classification] = by_classification.get(o.classification, 0) + 1
    average_confidence = (
        round(sum(float(o.confidence_score) for o in live) / len(live), 1) if live else None
    )
    most_recent = max(live, key=lambda o: o.emitted_at, default=None)
    return RadarV2SummaryOut(
        generated_at=datetime.now(timezone.utc),
        live_opportunity_count=len(live),
        live_by_classification=by_classification,
        average_confidence=average_confidence,
        most_recent_scan_run_id=most_recent.scan_run_id if most_recent else None,
        most_recent_emitted_at=most_recent.emitted_at if most_recent else None,
        stage2_candidate_cap=get_radar_stage2_candidate_cap(),
    )


@router.get("/radar-v2/performance", response_model=RadarV2PerformanceOut)
async def get_radar_v2_performance(
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> RadarV2PerformanceOut:
    """Phase B forward-testing metrics -- see `compute_radar_v2_
    performance`'s own docstring. Every rate is null, not 0.0, until
    real forward market data has actually resolved outcomes; this
    route never fabricates a rate from insufficient data."""
    metrics = compute_radar_v2_performance(session)
    return RadarV2PerformanceOut(
        generated_at=datetime.now(timezone.utc),
        total_opportunities_emitted=metrics.total_opportunities_emitted,
        total_outcomes_tracked=metrics.total_outcomes_tracked,
        pending_count=metrics.pending_count,
        resolved_count=metrics.resolved_count,
        target_hit_count=metrics.target_hit_count,
        stop_loss_hit_count=metrics.stop_loss_hit_count,
        partial_count=metrics.partial_count,
        expired_count=metrics.expired_count,
        data_unavailable_count=metrics.data_unavailable_count,
        target_hit_rate=metrics.target_hit_rate,
        stop_loss_hit_rate=metrics.stop_loss_hit_rate,
        average_return_pct=metrics.average_return_pct,
        live_opportunities_by_classification=metrics.live_opportunities_by_classification,
    )


@router.get("/radar-v2/performance/extended", response_model=RadarV2ExtendedPerformanceOut)
async def get_radar_v2_extended_performance(
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> RadarV2ExtendedPerformanceOut:
    """RADAR-C Phase D -- see `compute_radar_v2_extended_performance`'s
    own docstring for the exact breakdowns and why each group's
    win_rate/return stays null rather than a fabricated 0.0 with no
    resolved outcomes behind it."""
    metrics = compute_radar_v2_extended_performance(session)

    def _groups(items):
        return [
            RadarV2GroupPerformanceOut(
                label=g.label, signal_count=g.signal_count, win_rate=g.win_rate,
                average_return_pct=g.average_return_pct,
            )
            for g in items
        ]

    return RadarV2ExtendedPerformanceOut(
        generated_at=datetime.now(timezone.utc),
        win_rate_by_classification=_groups(metrics.win_rate_by_classification),
        win_rate_by_confidence_band=_groups(metrics.win_rate_by_confidence_band),
        win_rate_by_market_regime=_groups(metrics.win_rate_by_market_regime),
        performance_by_sector=_groups(metrics.performance_by_sector),
        performance_by_holding_horizon=_groups(metrics.performance_by_holding_horizon),
        average_return_pct=metrics.average_return_pct,
        median_return_pct=metrics.median_return_pct,
        average_favorable_excursion_pct=metrics.average_favorable_excursion_pct,
        average_adverse_excursion_pct=metrics.average_adverse_excursion_pct,
        calibration_pair_count=metrics.calibration_pair_count,
        expected_calibration_error=metrics.expected_calibration_error,
    )


@router.get("/radar-v2/sahmk-consumption", response_model=RadarV2SahmkConsumptionOut)
async def get_radar_v2_sahmk_consumption(
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> RadarV2SahmkConsumptionOut:
    """SAHMK quota consumption attributable specifically to Radar V2 --
    read verbatim from the existing per-operation rate-limiter/cache
    telemetry's "radar_v2" tag (see RADAR_V2 in operation_scope.py and
    this route's own `/radar-v2/scan` handler, which is the only place
    that tag is ever applied). No secrets: never includes the SAHMK API
    key or any credential, matching every other admin diagnostics
    route's existing contract.

    2026-08-18 real-market validation audit finding, fixed here: the
    telemetry's `by_operation` keys are compound `"<operation>:
    <endpoint>"` strings (e.g. `"radar_v2:quote"`,
    `"radar_v2:market_summary"` -- confirmed against real production
    data in `GET .../admin/system/summary`'s own `sahmk_quota_status.
    by_operation`), never a bare `"radar_v2"` key. A plain `.get(RADAR_V2)`
    could therefore never match anything and this route always returned
    `None`/`None`, silently, since it was first built -- a real,
    previously undetected observability gap, not a fabricated-data
    concern (an honestly empty `None` is still not what the route's own
    contract promises). Fixed by filtering every compound key that
    starts with the `radar_v2:` prefix instead of looking for an exact
    match."""
    from src.market_data.caching.redis_shared_cache import get_default_sahmk_cache, get_observability_snapshot

    def _radar_v2_subset(by_operation: Optional[Dict]) -> Optional[Dict]:
        prefix = f"{RADAR_V2}:"
        subset = {k: v for k, v in (by_operation or {}).items() if k.startswith(prefix)}
        return subset or None

    rate_status = get_default_rate_limiter().get_status()
    cache_status = get_observability_snapshot({"sahmk_market_data": get_default_sahmk_cache()})
    return RadarV2SahmkConsumptionOut(
        generated_at=datetime.now(timezone.utc),
        rate_limiter_by_operation=_radar_v2_subset(rate_status.get("by_operation")),
        cache_by_operation=_radar_v2_subset(cache_status.get("by_operation")),
    )


@router.get("/stage1-scan", response_model=Stage1ScanOut)
async def get_stage1_scan(
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> Stage1ScanOut:
    """Stage 1 of the two-stage Radar scan (SAHMK quota optimization
    mandate, 2026-08-16): narrows the full eligible Saudi-market
    universe down to genuine candidates using ONLY already-persisted
    local data (PriceBar rows + locally computed technical indicators)
    -- zero SAHMK requests, no matter how large the universe is (see
    `run_stage1_local_scan`'s own docstring for the exact local-only
    signals used and why). A GET, not a POST: this route makes no live
    provider call and writes nothing to the database, so it is safe to
    call as often as needed to inspect the current local candidate set
    before spending any real SAHMK quota on Stage 2
    (`POST .../stage2-validate-candidates`)."""
    result = run_stage1_local_scan(session)
    return Stage1ScanOut(
        generated_at=datetime.now(timezone.utc),
        universe_size=result.universe_size,
        evaluated_count=result.evaluated_count,
        skipped_count=result.skipped_count,
        candidate_count=result.candidate_count,
        candidates=[
            Stage1CandidateOut(
                symbol=c.symbol,
                latest_close=c.latest_close,
                latest_bar_timestamp=c.latest_bar_timestamp,
                dollar_volume=c.dollar_volume,
                relative_volume=c.relative_volume,
                adx_14=c.adx_14,
                rsi_14=c.rsi_14,
                atr_pct=c.atr_pct,
                signals=[Stage1SignalOut(name=s.name, detail_ar=s.detail_ar) for s in c.signals],
                ranking_score=c.ranking_score,
                component_scores=Stage1ComponentScoresOut(
                    trend=c.component_scores.trend,
                    momentum=c.component_scores.momentum,
                    volume=c.component_scores.volume,
                    liquidity=c.component_scores.liquidity,
                    volatility=c.component_scores.volatility,
                    risk_reward=c.component_scores.risk_reward,
                ),
                risk_reward_ratio=c.risk_reward_ratio,
            )
            for c in result.candidates
        ],
    )


@router.get("/universe-diagnostics", response_model=UniverseDiagnosticsOut)
async def get_universe_diagnostics(
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> UniverseDiagnosticsOut:
    """Real evidence for why nomu_market_stocks may read 0 despite a
    large discovered universe: runs a fresh (cached 24h, so cheap)
    SAHMK /companies/ directory call through
    universe_policy.classify_universe and surfaces its full per-field
    distinct-value breakdown -- the data that module's own docstring
    always intended to be inspectable, but that nothing previously
    exposed anywhere (classify_universe's `distinct_observed_values`
    and SahmkMarketDataProvider.last_universe_classification were both
    computed and then silently discarded). Never fabricates a verdict:
    if SAHMK is unreachable or a non-SahmkMarketDataProvider is
    currently selected, `sahmk_error`/`provider_kind` say so plainly
    and every other field stays empty."""
    from src.market_data import config as market_data_config
    from src.market_data.provider_factory import get_market_data_provider
    from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider

    def _pagination_diagnostics_out(provider: "SahmkMarketDataProvider") -> Optional[DirectoryPaginationDiagnosticsOut]:
        diag = provider.last_directory_diagnostics
        if diag is None:
            return None
        return DirectoryPaginationDiagnosticsOut(
            pages_fetched=diag.pages_fetched,
            total_fetched=diag.total_fetched,
            pagination_signal=diag.pagination_signal,
            reported_total=diag.reported_total,
            universe_verdict=diag.universe_verdict,
            first_page_keys=diag.first_page_keys,
            first_item_keys=diag.first_item_keys,
            sector_populated_count=diag.sector_populated_count,
            name_ar_populated_count=diag.name_ar_populated_count,
        )

    generated_at = datetime.now(timezone.utc)

    def _scrub(message: str) -> str:
        key = market_data_config.get_sahmk_api_key()
        return message.replace(key, "***") if key else message

    try:
        # priority=BACKGROUND: an admin diagnostic, not the live
        # Decision Engine scan pipeline (see request_priority.py).
        with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
            provider = await get_market_data_provider(force_refresh=True)
    except StrictRealDataUnavailableError as exc:
        return UniverseDiagnosticsOut(
            generated_at=generated_at, sahmk_error=_scrub(f"{type(exc).__name__}: {exc}")
        )

    if not isinstance(provider, SahmkMarketDataProvider):
        return UniverseDiagnosticsOut(
            generated_at=generated_at,
            provider_kind="dev",
            sahmk_error="A real SahmkMarketDataProvider is not currently selected -- "
            "no live directory call was made.",
        )

    try:
        # Return value intentionally unused here -- get_symbol_directory()'s
        # side effect (populating provider.last_universe_classification
        # with the full bucket/distinct-value breakdown) is what this
        # route actually needs; the per-entry dicts it returns are a
        # differently-shaped, UI-facing view of the same classification.
        with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
            await provider.get_symbol_directory()
    except Exception as exc:  # noqa: BLE001 -- report every failure mode, never crash this diagnostic route
        return UniverseDiagnosticsOut(
            generated_at=generated_at,
            provider_kind="sahmk",
            sahmk_error=_scrub(f"{type(exc).__name__}: {exc}"),
        )

    classification = provider.last_universe_classification
    if classification is None:
        return UniverseDiagnosticsOut(
            generated_at=generated_at, provider_kind="sahmk", pagination=_pagination_diagnostics_out(provider)
        )

    observed_fields = [
        ObservedFieldOut(
            field=field_name,
            distinct_values=[
                ObservedFieldValueOut(value=value, count=count)
                for value, count in sorted(values.items(), key=lambda kv: kv[1], reverse=True)
            ],
        )
        for field_name, values in classification.distinct_observed_values.items()
    ]

    non_main_bucket_classifications = [
        c for c in classification.classifications if not c.bucket.startswith("MAIN_MARKET_EQUITY")
    ]
    sample_source = non_main_bucket_classifications or classification.classifications
    sample_entries = [
        UniverseSampleEntryOut(
            symbol=c.symbol,
            name_en=c.name_en,
            market=c.market,
            market_segment=c.market_segment,
            security_type=c.security_type,
            status=c.status,
            bucket=c.bucket,
        )
        for c in sample_source[:15]
    ]

    return UniverseDiagnosticsOut(
        generated_at=generated_at,
        provider_kind="sahmk",
        total_instruments=classification.total_instruments,
        bucket_counts=classification.bucket_counts,
        observed_fields=observed_fields,
        sample_entries=sample_entries,
        pagination=_pagination_diagnostics_out(provider),
    )


# Real, independently verified symbols (news citations, not guessed) used
# only as a small representative TEST sample for symbol-lookup-diagnostics
# -- never as a stand-in for the real market universe, and never written
# to the Stock table. 1111 = Saudi Tadawul Group Holding Co (Main Market,
# listed 2023 -- a plausible candidate for a symbol newer than SAHMK's
# /companies/ directory snapshot). 9606 = Tharwah (Nomu Parallel Market).
_DEFAULT_SYMBOL_LOOKUP_TEST_SYMBOLS = ["1111", "9606"]


@router.get("/symbol-lookup-diagnostics", response_model=SymbolLookupDiagnosticsOut)
async def get_symbol_lookup_diagnostics(
    symbols: Optional[str] = None,
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> SymbolLookupDiagnosticsOut:
    """Answers, with real evidence, whether SAHMK's ~100-instrument
    /companies/ directory cap is a DISCOVERY-only limitation or a
    genuine DATA-coverage limitation: for each symbol (default: a
    small, real, independently-verified test set spanning Main Market
    and Nomu -- see _DEFAULT_SYMBOL_LOOKUP_TEST_SYMBOLS), calls SAHMK's
    per-symbol quote/company-profile/historical/fundamentals/dividends
    endpoints directly, bypassing the directory entirely. If these
    succeed for a symbol the directory never listed, the fix is
    symbol-discovery (feeding a real official symbol list into these
    already-working per-symbol endpoints), not a data-provider
    replacement. Every result is a real API call outcome -- `available`
    is never assumed true, and no price/fundamental value is ever
    fabricated when a call fails."""
    from src.market_data import config as market_data_config
    from src.market_data.fundamental_provider_factory import get_fundamental_data_provider
    from src.market_data.provider_factory import get_market_data_provider
    from src.market_data.providers.sahmk_fundamental_data_provider import SahmkFundamentalDataProvider
    from src.market_data.providers.sahmk_market_data_provider import SahmkMarketDataProvider

    generated_at = datetime.now(timezone.utc)

    def _scrub(message: str) -> str:
        key = market_data_config.get_sahmk_api_key()
        return message.replace(key, "***") if key else message

    symbol_list = [s.strip() for s in symbols.split(",") if s.strip()] if symbols else _DEFAULT_SYMBOL_LOOKUP_TEST_SYMBOLS

    try:
        # priority=BACKGROUND: an admin diagnostic, not the live
        # Decision Engine scan pipeline (see request_priority.py) --
        # this route is also the single most expensive diagnostic call
        # per invocation (~6 real requests/symbol), so it must never
        # draw from the reserve set aside for live-market operations.
        with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
            market_provider = await get_market_data_provider(force_refresh=True)
    except StrictRealDataUnavailableError as exc:
        return SymbolLookupDiagnosticsOut(
            generated_at=generated_at, sahmk_error=_scrub(f"{type(exc).__name__}: {exc}")
        )

    if not isinstance(market_provider, SahmkMarketDataProvider):
        return SymbolLookupDiagnosticsOut(
            generated_at=generated_at,
            provider_kind="dev",
            sahmk_error="A real SahmkMarketDataProvider is not currently selected -- no live calls were made.",
        )

    try:
        with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
            fundamental_provider = await get_fundamental_data_provider(force_refresh=True)
    except StrictRealDataUnavailableError:
        fundamental_provider = None
    if not isinstance(fundamental_provider, SahmkFundamentalDataProvider):
        fundamental_provider = None

    # A fresh directory fetch is already 24h-cached by the service, so
    # this costs nothing extra beyond the first call -- used only to
    # report whether each test symbol is a directory member, real
    # evidence for the "discovery vs data" question, never to gate
    # whether the per-symbol calls below are attempted.
    known_symbols: Optional[set] = None
    try:
        with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
            directory = await market_provider.get_symbol_directory()
        known_symbols = {c["symbol"] for c in directory}
    except Exception:  # noqa: BLE001 -- directory membership is informational only
        known_symbols = None

    async def _check(coro) -> SymbolLookupCheckOut:
        # Success means SAHMK answered with a real, non-error response --
        # never that the payload happened to be non-empty. An empty
        # dividend list for a real symbol that has simply never paid a
        # dividend is a legitimate, available answer, not a failure; any
        # genuine "no such symbol" case surfaces as an exception (a
        # non-2xx SahmkRequestError/SahmkAuthenticationError), which is
        # the only thing that marks this check unavailable.
        try:
            result = await coro
        except Exception as exc:  # noqa: BLE001 -- report every failure mode, never crash this diagnostic route
            return SymbolLookupCheckOut(available=False, detail=_scrub(f"{type(exc).__name__}: {exc}"))
        if result is None:
            return SymbolLookupCheckOut(available=False, detail="Empty response.")
        # SahmkMarketDataProvider.get_company_profile() returns a plain
        # dict with sector/industry already flattened (see its own
        # docstring) -- surfacing those two real values here (never
        # fabricated, straight passthrough) answers, with direct
        # evidence, whether SAHMK's per-symbol /company/{symbol}/
        # endpoint carries sector/industry data that the bulk
        # /companies/ directory (see universe_policy.py's module
        # docstring: no sector field for ~99% of directory entries)
        # does not. Every other check type's result has no such keys,
        # so this is a no-op for them.
        raw_sector = None
        raw_industry = None
        raw_keys = None
        if isinstance(result, dict):
            raw_sector = result.get("sector")
            raw_industry = result.get("industry")
            # Always expose the real top-level key set for ANY dict result --
            # not just when sector/industry happen to be present -- so this
            # same generic passthrough also answers "what keys did SAHMK's
            # raw dividends response actually use" (see dividends_raw below),
            # never guessed or assumed.
            raw_keys = sorted(result.keys())
        return SymbolLookupCheckOut(
            available=True, detail=None, raw_sector=raw_sector, raw_industry=raw_industry, raw_keys=raw_keys
        )

    async def _check_raw_dividends(symbol: str) -> SymbolLookupCheckOut:
        # Bypasses SahmkMarketDataService.get_dividends()'s
        # `data.get("dividends", data.get("results", []))` key lookup and
        # SahmkFundamentalDataProvider's further reshaping entirely --
        # calls the SAHMK client directly so the true raw JSON shape is
        # visible. Real evidence for why dividend coverage reads 0/384
        # despite the ingestion job reporting per-symbol success: either
        # SAHMK's actual top-level key differs from "dividends"/"results"
        # (a parsing-code fix), or the raw response genuinely has zero
        # entries for that symbol (a real, non-fabricated absence).
        if not isinstance(fundamental_provider, SahmkFundamentalDataProvider):
            return SymbolLookupCheckOut(available=False, detail="No real SAHMK fundamental provider selected.")
        try:
            raw = await fundamental_provider._service._client.get_dividends(symbol)  # noqa: SLF001 -- diagnostic-only, bypasses parsing on purpose
        except Exception as exc:  # noqa: BLE001 -- report every failure mode, never crash this diagnostic route
            return SymbolLookupCheckOut(available=False, detail=_scrub(f"{type(exc).__name__}: {exc}"))
        if not isinstance(raw, dict):
            return SymbolLookupCheckOut(available=True, detail=f"Non-dict raw response: {type(raw).__name__}")
        keys = sorted(raw.keys())
        items = None
        matched_key = None
        for candidate in ("dividends", "results", "data", "items", "dividend_history", "history"):
            if isinstance(raw.get(candidate), list):
                items = raw[candidate]
                matched_key = candidate
                break
        if items is None:
            detail = f"top_level_keys={keys}; no list found under any known key (dividends/results/data/items/dividend_history/history)"
        else:
            detail = f"top_level_keys={keys}; matched_key={matched_key!r}; item_count={len(items)}"
            if items:
                first = items[0]
                detail += f"; first_item_keys={sorted(first.keys())}" if isinstance(first, dict) else f"; first_item_type={type(first).__name__}"
        return SymbolLookupCheckOut(available=True, detail=detail, raw_keys=keys)

    results: List[SymbolLookupDiagnosticOut] = []
    for symbol in symbol_list:
        with priority_scope(BACKGROUND), operation_scope(ADMIN_DIAGNOSTICS):
            quote = await _check(market_provider.get_latest_quote(symbol))
            company_profile = await _check(market_provider.get_company_profile(symbol))
            historical_bar = await _check(market_provider.get_stock_data(symbol))
            if fundamental_provider is not None:
                dividends = await _check(fundamental_provider.get_dividends(symbol))
                dividends_raw = await _check_raw_dividends(symbol)
                fundamentals = await _check(fundamental_provider.get_fundamentals(symbol))
            else:
                no_provider = SymbolLookupCheckOut(
                    available=False, detail="No real fundamental provider selected."
                )
                dividends = no_provider
                dividends_raw = no_provider
                fundamentals = no_provider

        results.append(
            SymbolLookupDiagnosticOut(
                symbol=symbol,
                in_last_known_directory=(symbol in known_symbols) if known_symbols is not None else None,
                quote=quote,
                company_profile=company_profile,
                historical_bar=historical_bar,
                dividends=dividends,
                dividends_raw=dividends_raw,
                fundamentals=fundamentals,
            )
        )

    return SymbolLookupDiagnosticsOut(generated_at=generated_at, provider_kind="sahmk", results=results)


_INGESTION_JOB_NAMES = ["symbols", "historical_ohlcv", "fundamentals", "dividends"]


def _ingestion_job_status_out(job_name: str, latest: Optional[IngestionRunLog]) -> IngestionJobStatusOut:
    if latest is None:
        return IngestionJobStatusOut(job_name=job_name, status=None)
    return IngestionJobStatusOut(
        job_name=job_name,
        status=latest.status.value,
        symbols_requested=latest.symbols_requested,
        symbols_succeeded=latest.symbols_succeeded,
        symbols_failed=latest.symbols_failed,
        rows_upserted=latest.rows_upserted,
        retry_count=latest.retry_count,
        started_at=latest.started_at,
        finished_at=latest.finished_at,
        duration_seconds=float(latest.duration_seconds) if latest.duration_seconds is not None else None,
        error_summary=latest.error_summary,
        zero_progress_summary=latest.zero_progress_summary,
        next_retry_at=latest.next_retry_at,
    )


@router.post("/full-discovery", response_model=FullDiscoveryTriggerOut)
async def trigger_full_discovery(
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> FullDiscoveryTriggerOut:
    """Staff-only: manually runs one full pass of the same four
    ingestion jobs (symbols -> historical_ohlcv -> fundamentals ->
    dividends) the recurring IngestionScheduler would eventually run on
    its own schedule (see IngestionScheduler.run_all_jobs_once) --
    without requiring INGESTION_SCHEDULER_ENABLED to be turned on.

    When INGESTION_AUTO_DISCOVER_SYMBOLS is enabled (as it already is
    in this deployment), the symbols job registers every symbol
    SahmkMarketDataProvider.get_symbol_directory() reports, and the
    other three jobs then pick up every newly discovered active Stock
    row automatically (IngestionScheduler._resolve_target_symbols) --
    this route is the one production-safe way to grow the tracked
    universe past its cold-start seed on demand, since the diagnostic-
    scan route deliberately never runs discovery (see its own
    docstring). Dispatched as a background task -- a full-market
    backfill can take many minutes -- so this call returns immediately;
    poll GET /coverage's latest_ingestion_runs for real progress and
    counts.
    """
    triggered_at = datetime.now(timezone.utc)

    from src.market_data.ingestion.scheduler import reap_stale_ingestion_runs

    reap_stale_ingestion_runs(session, ingestion_config.get_max_ingestion_job_run_duration_hours())

    in_flight = (
        session.query(IngestionRunLog)
        .filter(IngestionRunLog.job_name.in_(_INGESTION_JOB_NAMES))
        .filter(IngestionRunLog.finished_at.is_(None))
        .first()
    )
    if in_flight is not None:
        return FullDiscoveryTriggerOut(
            triggered_at=triggered_at,
            accepted=False,
            message=(
                f"Skipped: ingestion job '{in_flight.job_name}' (started {in_flight.started_at.isoformat()}) "
                "is already running -- wait for it to finish before triggering another full discovery pass."
            ),
            job_names=[],
        )

    from src.market_data.ingestion.scheduler import IngestionScheduler

    scheduler = IngestionScheduler()
    background_tasks.add_task(scheduler.run_all_jobs_once)

    return FullDiscoveryTriggerOut(
        triggered_at=triggered_at,
        accepted=True,
        message="Full discovery/ingestion pass started in the background.",
        job_names=list(_INGESTION_JOB_NAMES),
    )


@router.get("/coverage", response_model=MarketCoverageOut)
async def get_market_coverage(
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> MarketCoverageOut:
    """Real, SQL-backed evidence of how much of the Saudi market Basirah
    actually tracks and scans right now -- direct query results, never
    estimated. Exists to make "is the platform only covering a handful
    of stocks" an answerable question instead of an impression: total/
    active/inactive Stock rows, the ETF/REIT/sukuk/rights/suspended
    breakdown universe_policy already computes (see ingest_symbols.py),
    how many active symbols actually have price history to scan (the
    real SymbolSelector eligibility condition), the current ingestion
    scheduler configuration, the last run of each of the 4 ingestion
    jobs, and the most recent market scan."""
    total_stocks = session.query(func.count(Stock.id)).scalar() or 0
    active_stocks = session.query(func.count(Stock.id)).filter(Stock.is_active.is_(True)).scalar() or 0
    inactive_stocks = total_stocks - active_stocks

    symbols_with_bars = session.query(PriceBar.stock_id).distinct().subquery()
    stocks_with_price_history = (
        session.query(func.count(Stock.id))
        .filter(Stock.is_active.is_(True))
        .filter(Stock.id.in_(session.query(symbols_with_bars.c.stock_id)))
        .scalar()
        or 0
    )
    stocks_without_price_history = active_stocks - stocks_with_price_history

    bucket_rows = (
        session.query(Stock.instrument_bucket, func.count(Stock.id)).group_by(Stock.instrument_bucket).all()
    )
    instrument_bucket_counts = [
        UniverseBucketCountOut(bucket=bucket, count=count) for bucket, count in bucket_rows
    ]

    latest_ingestion_runs: List[IngestionJobStatusOut] = []
    for job_name in _INGESTION_JOB_NAMES:
        latest = (
            session.query(IngestionRunLog)
            .filter(IngestionRunLog.job_name == job_name)
            .order_by(IngestionRunLog.started_at.desc())
            .first()
        )
        latest_ingestion_runs.append(_ingestion_job_status_out(job_name, latest))

    latest_scan = session.query(MarketScanRun).order_by(MarketScanRun.id.desc()).first()
    latest_scan_run = (
        MarketScanRunOut(
            id=latest_scan.id,
            status=latest_scan.status.value,
            symbols_requested=latest_scan.symbols_requested,
            symbols_succeeded=latest_scan.symbols_succeeded,
            symbols_skipped=latest_scan.symbols_skipped,
            symbols_failed=latest_scan.symbols_failed,
            error_summary=latest_scan.error_summary,
            skipped_symbols_summary=latest_scan.skipped_symbols_summary,
            started_at=latest_scan.started_at,
            finished_at=latest_scan.finished_at,
            duration_seconds=(
                float(latest_scan.duration_seconds) if latest_scan.duration_seconds is not None else None
            ),
            created_at=latest_scan.created_at,
        )
        if latest_scan is not None
        else None
    )

    coverage_pct = (stocks_with_price_history / active_stocks * 100) if active_stocks > 0 else None

    # Main Market vs Nomu split, derived from the bucket
    # universe_policy.classify_universe already assigned -- see that
    # module's MAIN_SEGMENT_MARKERS/NOMU_SEGMENT_MARKERS.
    main_market_stocks = sum(
        count for bucket, count in bucket_rows if bucket and bucket.startswith("MAIN_MARKET_EQUITY")
    )
    nomu_market_stocks = sum(
        count for bucket, count in bucket_rows if bucket and bucket.startswith("NOMU_EQUITY")
    )
    _EXCLUSION_BUCKETS = {"ETF_FUND", "REIT", "SUKUK_BOND", "RIGHTS_ISSUE", "SUSPENDED", "INACTIVE_DELISTED"}
    excluded_instrument_counts = [
        UniverseBucketCountOut(bucket=bucket, count=count) for bucket, count in bucket_rows if bucket in _EXCLUSION_BUCKETS
    ]
    total_excluded_non_equity = sum(count for bucket, count in bucket_rows if bucket in _EXCLUSION_BUCKETS)
    unclassified_market_segment_stocks = (
        total_stocks - main_market_stocks - nomu_market_stocks - total_excluded_non_equity
    )

    fundamentals_subq = session.query(FundamentalSnapshot.stock_id).distinct().subquery()
    stocks_with_fundamentals = (
        session.query(func.count(Stock.id))
        .filter(Stock.is_active.is_(True))
        .filter(Stock.id.in_(session.query(fundamentals_subq.c.stock_id)))
        .scalar()
        or 0
    )
    stocks_without_fundamentals = active_stocks - stocks_with_fundamentals

    dividends_subq = session.query(Dividend.stock_id).distinct().subquery()
    stocks_with_dividends = (
        session.query(func.count(Stock.id))
        .filter(Stock.is_active.is_(True))
        .filter(Stock.id.in_(session.query(dividends_subq.c.stock_id)))
        .scalar()
        or 0
    )
    stocks_without_dividends = active_stocks - stocks_with_dividends

    # Per-sector coverage. `Stock.sector` is nullable (SAHMK's directory
    # response has no confirmed sector field -- see universe_policy.py's
    # docstring), so a None group is real evidence of that gap, not an
    # ingestion bug, and is reported the same way as any named sector.
    sector_values = [row[0] for row in session.query(Stock.sector).distinct().all()]
    sector_coverage: List[SectorCoverageOut] = []
    for sector in sector_values:
        sector_predicate = Stock.sector.is_(None) if sector is None else Stock.sector == sector
        sector_total = session.query(func.count(Stock.id)).filter(sector_predicate).scalar() or 0
        sector_active = (
            session.query(func.count(Stock.id)).filter(sector_predicate).filter(Stock.is_active.is_(True)).scalar()
            or 0
        )
        sector_with_bars = (
            session.query(func.count(Stock.id))
            .filter(sector_predicate)
            .filter(Stock.is_active.is_(True))
            .filter(Stock.id.in_(session.query(symbols_with_bars.c.stock_id)))
            .scalar()
            or 0
        )
        sector_coverage.append(
            SectorCoverageOut(
                sector=sector,
                total_stocks=sector_total,
                active_stocks=sector_active,
                stocks_with_price_history=sector_with_bars,
                coverage_pct=(sector_with_bars / sector_active * 100) if sector_active > 0 else None,
            )
        )
    sector_coverage.sort(key=lambda s: s.total_stocks, reverse=True)

    _MISSING_PRICE_HISTORY_CAP = 50
    symbols_missing_price_history = [
        row[0]
        for row in session.query(Stock.symbol)
        .filter(Stock.is_active.is_(True))
        .filter(~Stock.id.in_(session.query(symbols_with_bars.c.stock_id)))
        .order_by(Stock.symbol)
        .limit(_MISSING_PRICE_HISTORY_CAP)
        .all()
    ]

    latest_scan_symbols_entering_decision_engine = 0
    latest_scan_recommendations_generated = 0
    latest_scan_skipped_symbols: List[str] = []
    if latest_scan is not None:
        latest_scan_symbols_entering_decision_engine = (
            session.query(func.count(DecisionV2Snapshot.id))
            .filter(DecisionV2Snapshot.scan_run_id == latest_scan.id)
            .scalar()
            or 0
        )
        latest_scan_recommendations_generated = (
            session.query(func.count(SymbolIntelligenceRecord.id))
            .filter(SymbolIntelligenceRecord.scan_run_id == latest_scan.id)
            .scalar()
            or 0
        )
        if latest_scan.skipped_symbols_summary:
            # The real per-symbol reason, written by
            # MarketIntelligenceEngine._build_skipped_symbols_summary at
            # scan time -- authoritative, not a guess.
            latest_scan_skipped_symbols = [
                entry.split(":", 1)[0].strip()
                for entry in latest_scan.skipped_symbols_summary.split(";")
                if entry.strip()
            ]
        elif latest_scan.symbols_skipped > 0:
            # A scan that ran before skipped_symbols_summary existed
            # (or otherwise left it null): best-effort retroactive diff,
            # exact only if the universe hasn't changed since -- true
            # whenever no ingestion has run between that scan and now.
            scanned_symbols = (
                session.query(SymbolIntelligenceRecord.symbol)
                .filter(SymbolIntelligenceRecord.scan_run_id == latest_scan.id)
                .distinct()
                .subquery()
            )
            latest_scan_skipped_symbols = [
                row[0]
                for row in session.query(Stock.symbol)
                .filter(Stock.is_active.is_(True))
                .filter(Stock.id.in_(session.query(symbols_with_bars.c.stock_id)))
                .filter(~Stock.symbol.in_(session.query(scanned_symbols.c.symbol)))
                .order_by(Stock.symbol)
                .all()
            ]

    db_consistency = DbConsistencyOut(
        active_stocks_missing_instrument_bucket=(
            session.query(func.count(Stock.id))
            .filter(Stock.is_active.is_(True))
            .filter(Stock.instrument_bucket.is_(None))
            .scalar()
            or 0
        ),
        active_stocks_missing_sector=(
            session.query(func.count(Stock.id))
            .filter(Stock.is_active.is_(True))
            .filter(Stock.sector.is_(None))
            .scalar()
            or 0
        ),
        active_stocks_missing_exchange=(
            session.query(func.count(Stock.id))
            .filter(Stock.is_active.is_(True))
            .filter(Stock.exchange.is_(None))
            .scalar()
            or 0
        ),
        inactive_stocks_missing_exclusion_reason=(
            session.query(func.count(Stock.id))
            .filter(Stock.is_active.is_(False))
            .filter(Stock.exclusion_reason.is_(None))
            .scalar()
            or 0
        ),
        active_stocks_with_exclusion_reason_set=(
            session.query(func.count(Stock.id))
            .filter(Stock.is_active.is_(True))
            .filter(Stock.exclusion_reason.isnot(None))
            .scalar()
            or 0
        ),
    )

    no_scan_reason_ar = "لم يكتمل أي مسح للسوق بعد."
    pipeline_funnel = [
        PipelineStageOut(
            stage="الاكتشاف (إجمالي الأسهم المسجّلة)",
            output_count=total_stocks,
            relative_to=total_stocks,
            dropped=0,
            reason="كل رمز ظهر في مزامنة دليل الشركات من SAHMK، إضافة إلى أي رمز مُضاف يدوياً.",
        ),
        PipelineStageOut(
            stage="الأهلية (نشط وغير مستبعد)",
            output_count=active_stocks,
            relative_to=total_stocks,
            dropped=total_stocks - active_stocks,
            reason="مستبعد بواسطة قاعدة تصنيف الكون الاستثماري بصفته صندوق مؤشرات/صندوق عقاري/صكوكاً/حقوق أولوية/موقوفاً/مشطوباً.",
        ),
        PipelineStageOut(
            stage="استيراد بيانات الأسعار (OHLCV)",
            output_count=stocks_with_price_history,
            relative_to=active_stocks,
            dropped=active_stocks - stocks_with_price_history,
            reason="لا تتوفر بيانات أسعار تاريخية بعد لهذا السهم النشط؛ يلزم توفر شمعة سعرية واحدة على الأقل لفحصه.",
        ),
        PipelineStageOut(
            stage="استيراد البيانات المالية",
            output_count=stocks_with_fundamentals,
            relative_to=active_stocks,
            dropped=active_stocks - stocks_with_fundamentals,
            reason="لا تتوفر بيانات مالية بعد لهذا السهم النشط.",
        ),
        PipelineStageOut(
            stage="استيراد بيانات التوزيعات",
            output_count=stocks_with_dividends,
            relative_to=active_stocks,
            dropped=active_stocks - stocks_with_dividends,
            reason="لا تتوفر بيانات توزيعات أرباح بعد لهذا السهم (كثير من الشركات فعلياً لا توزّع أرباحاً، فغياب البيانات وحده ليس خللاً).",
        ),
        PipelineStageOut(
            stage="دخل محرك القرار (آخر مسح)",
            output_count=latest_scan_symbols_entering_decision_engine,
            relative_to=stocks_with_price_history,
            dropped=max(stocks_with_price_history - latest_scan_symbols_entering_decision_engine, 0),
            reason=(
                "الرموز التي صدر لها قرار من محرك القرار مرتبط بآخر مسح للسوق."
                if latest_scan is not None
                else no_scan_reason_ar
            ),
        ),
        PipelineStageOut(
            stage="توصيات صادرة (آخر مسح)",
            output_count=latest_scan_recommendations_generated,
            relative_to=(
                latest_scan_symbols_entering_decision_engine
                if latest_scan_symbols_entering_decision_engine
                else stocks_with_price_history
            ),
            dropped=max(
                (
                    latest_scan_symbols_entering_decision_engine
                    if latest_scan_symbols_entering_decision_engine
                    else stocks_with_price_history
                )
                - latest_scan_recommendations_generated,
                0,
            ),
            reason=(
                "توصيات صدرت فعلياً في آخر مسح للسوق."
                if latest_scan is not None
                else no_scan_reason_ar
            ),
        ),
    ]

    return MarketCoverageOut(
        generated_at=datetime.now(timezone.utc),
        total_stocks=total_stocks,
        active_stocks=active_stocks,
        inactive_stocks=inactive_stocks,
        stocks_with_price_history=stocks_with_price_history,
        stocks_without_price_history=stocks_without_price_history,
        instrument_bucket_counts=instrument_bucket_counts,
        ingestion_auto_discover_enabled=ingestion_config.is_symbol_auto_discovery_enabled(),
        ingestion_configured_seed_symbols=len(ingestion_config.get_ingestion_symbol_universe()),
        latest_ingestion_runs=latest_ingestion_runs,
        latest_scan_run=latest_scan_run,
        coverage_pct=coverage_pct,
        main_market_stocks=main_market_stocks,
        nomu_market_stocks=nomu_market_stocks,
        unclassified_market_segment_stocks=unclassified_market_segment_stocks,
        excluded_instrument_counts=excluded_instrument_counts,
        total_excluded_non_equity=total_excluded_non_equity,
        stocks_with_fundamentals=stocks_with_fundamentals,
        stocks_without_fundamentals=stocks_without_fundamentals,
        stocks_with_dividends=stocks_with_dividends,
        stocks_without_dividends=stocks_without_dividends,
        sector_coverage=sector_coverage,
        sector_provider_configured=get_sector_classification_provider().is_configured,
        latest_scan_symbols_entering_decision_engine=latest_scan_symbols_entering_decision_engine,
        latest_scan_recommendations_generated=latest_scan_recommendations_generated,
        db_consistency=db_consistency,
        pipeline_funnel=pipeline_funnel,
        symbols_missing_price_history=symbols_missing_price_history,
        latest_scan_skipped_symbols=latest_scan_skipped_symbols,
    )


_BUY_DECISIONS = {"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"}
_REJECTED_DECISIONS = {"REJECT", "INSUFFICIENT_DATA"}


def _decision_label_ar(decision: str) -> str:
    """`DecisionV2Snapshot.decision` is persisted as the raw enum
    value (e.g. "BUY_CANDIDATE") -- translate it through the same
    canonical Arabic taxonomy every other decision-carrying response
    already uses, so this dashboard never surfaces the raw enum name
    to a human reader."""
    try:
        return DECISION_LABELS_AR[Decision(decision)]
    except ValueError:
        return decision


def _confidence_bucket_label(score: float) -> str:
    lo = min(int(score) // 20 * 20, 80)
    return f"{lo}-{lo + 20}"


@router.get("/decision-intelligence", response_model=DecisionIntelligenceOut)
async def get_decision_intelligence(
    within_hours: int = Query(72, ge=1, le=24 * 30),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)),
) -> DecisionIntelligenceOut:
    """Real, SQL-backed statistics over each symbol's most recent
    Decision Engine V2 snapshot within the last `within_hours` hours --
    what an administrator needs to answer "what is Basirah actually
    deciding right now, and why did it reject what it rejected."
    Multiple `/decision-v2` requests for the same symbol within the
    window are collapsed to that symbol's single latest snapshot (this
    table is an insert-only request log, so counting every row would
    double-count a symbol a user simply opened more than once) -- never
    an estimate, always a direct aggregate over decision_v2_snapshots."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)

    latest_ts_subq = (
        session.query(
            DecisionV2Snapshot.stock_id.label("stock_id"),
            func.max(DecisionV2Snapshot.decision_timestamp).label("max_ts"),
        )
        .filter(DecisionV2Snapshot.decision_timestamp >= cutoff)
        .group_by(DecisionV2Snapshot.stock_id)
        .subquery()
    )
    latest_rows: List[DecisionV2Snapshot] = (
        session.query(DecisionV2Snapshot)
        .join(
            latest_ts_subq,
            (DecisionV2Snapshot.stock_id == latest_ts_subq.c.stock_id)
            & (DecisionV2Snapshot.decision_timestamp == latest_ts_subq.c.max_ts),
        )
        .all()
    )

    decision_counter: Counter = Counter()
    bucket_counter: Counter = Counter()
    risk_counter: Counter = Counter()
    gate_fail_counter: Counter = Counter()
    sector_stats: Dict[Optional[str], Dict[str, Any]] = {}

    for row in latest_rows:
        decision_counter[row.decision] += 1
        risk_counter[row.risk_level] += 1
        confidence = float(row.confidence_score)
        bucket_counter[_confidence_bucket_label(confidence)] += 1

        stats = sector_stats.setdefault(
            row.sector_ar, {"symbols_evaluated": 0, "confidence_sum": 0.0, "buy_candidate_count": 0}
        )
        stats["symbols_evaluated"] += 1
        stats["confidence_sum"] += confidence
        if row.decision in _BUY_DECISIONS:
            stats["buy_candidate_count"] += 1

        if row.decision in _REJECTED_DECISIONS:
            for gate in row.gates or []:
                if gate.get("status") == "FAIL":
                    gate_fail_counter[gate.get("name", "unknown")] += 1

    top_opportunities = sorted(
        (row for row in latest_rows if row.decision in _BUY_DECISIONS),
        key=lambda r: float(r.confidence_score),
        reverse=True,
    )[:10]
    rejected_opportunities = sorted(
        (row for row in latest_rows if row.decision in _REJECTED_DECISIONS),
        key=lambda r: r.decision_timestamp,
        reverse=True,
    )[:10]

    return DecisionIntelligenceOut(
        generated_at=datetime.now(timezone.utc),
        window_hours=within_hours,
        total_symbols_evaluated=len(latest_rows),
        decision_distribution=[
            DecisionCountOut(decision=decision, decision_label_ar=_decision_label_ar(decision), count=count)
            for decision, count in decision_counter.items()
        ],
        confidence_buckets=[
            ConfidenceBucketCountOut(bucket_label=label, count=count) for label, count in bucket_counter.items()
        ],
        risk_distribution=[
            RiskCountOut(risk_level=risk_level, count=count) for risk_level, count in risk_counter.items()
        ],
        top_opportunities=[
            TopOpportunityOut(
                symbol=row.symbol,
                company_name_ar=row.company_name_ar,
                sector_ar=row.sector_ar,
                decision=row.decision,
                decision_label_ar=row.decision_label_ar,
                confidence_score=float(row.confidence_score),
                risk_level=row.risk_level,
                decision_timestamp=row.decision_timestamp,
            )
            for row in top_opportunities
        ],
        rejected_opportunities=[
            RejectedOpportunityOut(
                symbol=row.symbol,
                company_name_ar=row.company_name_ar,
                sector_ar=row.sector_ar,
                decision=row.decision,
                decision_label_ar=_decision_label_ar(row.decision),
                failed_gate_names=[g.get("name", "unknown") for g in (row.gates or []) if g.get("status") == "FAIL"],
                decision_timestamp=row.decision_timestamp,
            )
            for row in rejected_opportunities
        ],
        rejection_reason_counts=[
            RejectionReasonCountOut(gate_name=gate_name, fail_count=count)
            for gate_name, count in gate_fail_counter.most_common()
        ],
        sector_ranking=sorted(
            (
                SectorRankingOut(
                    sector_ar=sector_ar,
                    symbols_evaluated=stats["symbols_evaluated"],
                    average_confidence=(
                        stats["confidence_sum"] / stats["symbols_evaluated"]
                        if stats["symbols_evaluated"] > 0
                        else None
                    ),
                    buy_candidate_count=stats["buy_candidate_count"],
                )
                for sector_ar, stats in sector_stats.items()
            ),
            key=lambda s: s.average_confidence or 0.0,
            reverse=True,
        ),
    )
