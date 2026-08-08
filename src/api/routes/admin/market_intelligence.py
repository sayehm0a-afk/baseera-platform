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

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from src.api.schemas.market_intelligence import (
    ConfidenceBucketCountOut,
    DbConsistencyOut,
    DecisionCountOut,
    DecisionIntelligenceOut,
    DiagnosticDecisionV2SampleOut,
    DiagnosticSampleSymbolOut,
    DiagnosticScanOut,
    FullDiscoveryTriggerOut,
    IngestionJobStatusOut,
    MarketCoverageOut,
    MarketScanRequest,
    MarketScanRunOut,
    PipelineStageOut,
    RejectedOpportunityOut,
    RejectionReasonCountOut,
    RiskCountOut,
    SectorCoverageOut,
    SectorRankingOut,
    TopOpportunityOut,
    UniverseBucketCountOut,
)
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import (
    DecisionV2Snapshot,
    Dividend,
    FundamentalSnapshot,
    IngestionRunLog,
    MarketScanRun,
    MarketScanStatus,
    PriceBar,
    StaffRole,
    Stock,
    SymbolIntelligenceRecord,
    User,
)
from src.market_data.ingestion import config as ingestion_config
from src.market_data.strict_mode import StrictRealDataUnavailableError
from src.market_intelligence.config import get_max_scan_run_duration_hours
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.services.scan_job_runner import run_market_scan_job

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
        in_flight = (
            session.query(MarketScanRun)
            .filter(MarketScanRun.status.in_([MarketScanStatus.PENDING, MarketScanStatus.RUNNING]))
            .first()
        )
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
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
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

    latest_scan_symbols_entering_decision_engine = 0
    latest_scan_recommendations_generated = 0
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

    pipeline_funnel = [
        PipelineStageOut(
            stage="Discovery (total Stock rows)",
            output_count=total_stocks,
            relative_to=total_stocks,
            dropped=0,
            reason="Every symbol a SAHMK directory sync has ever seen, plus any explicitly configured symbol.",
        ),
        PipelineStageOut(
            stage="Eligibility (active, non-excluded)",
            output_count=active_stocks,
            relative_to=total_stocks,
            dropped=total_stocks - active_stocks,
            reason="Excluded by universe_policy.classify_universe as ETF/REIT/sukuk/rights/suspended/delisted.",
        ),
        PipelineStageOut(
            stage="OHLCV ingested",
            output_count=stocks_with_price_history,
            relative_to=active_stocks,
            dropped=active_stocks - stocks_with_price_history,
            reason="Active stock has no PriceBar rows yet; SymbolSelector requires at least one bar to scan it.",
        ),
        PipelineStageOut(
            stage="Fundamentals ingested",
            output_count=stocks_with_fundamentals,
            relative_to=active_stocks,
            dropped=active_stocks - stocks_with_fundamentals,
            reason="Active stock has no FundamentalSnapshot rows yet.",
        ),
        PipelineStageOut(
            stage="Dividends ingested",
            output_count=stocks_with_dividends,
            relative_to=active_stocks,
            dropped=active_stocks - stocks_with_dividends,
            reason="Active stock has no Dividend rows yet (many real companies pay none -- absence alone is not a defect).",
        ),
        PipelineStageOut(
            stage="Entered Decision Engine (latest scan)",
            output_count=latest_scan_symbols_entering_decision_engine,
            relative_to=stocks_with_price_history,
            dropped=max(stocks_with_price_history - latest_scan_symbols_entering_decision_engine, 0),
            reason=(
                "Symbols with a DecisionV2Snapshot tied to the latest MarketScanRun."
                if latest_scan is not None
                else "No MarketScanRun has completed yet."
            ),
        ),
        PipelineStageOut(
            stage="Recommendations generated (latest scan)",
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
                "SymbolIntelligenceRecord rows written by the latest MarketScanRun."
                if latest_scan is not None
                else "No MarketScanRun has completed yet."
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
        latest_scan_symbols_entering_decision_engine=latest_scan_symbols_entering_decision_engine,
        latest_scan_recommendations_generated=latest_scan_recommendations_generated,
        db_consistency=db_consistency,
        pipeline_funnel=pipeline_funnel,
    )


_BUY_DECISIONS = {"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"}
_REJECTED_DECISIONS = {"REJECT", "INSUFFICIENT_DATA"}


def _confidence_bucket_label(score: float) -> str:
    lo = min(int(score) // 20 * 20, 80)
    return f"{lo}-{lo + 20}"


@router.get("/decision-intelligence", response_model=DecisionIntelligenceOut)
async def get_decision_intelligence(
    within_hours: int = Query(72, ge=1, le=24 * 30),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
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
            DecisionCountOut(decision=decision, count=count) for decision, count in decision_counter.items()
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
