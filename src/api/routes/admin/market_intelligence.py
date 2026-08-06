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
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.schemas.market_intelligence import (
    DiagnosticDecisionV2SampleOut,
    DiagnosticSampleSymbolOut,
    DiagnosticScanOut,
    MarketScanRequest,
)
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import (
    DecisionV2Snapshot,
    MarketScanRun,
    MarketScanStatus,
    StaffRole,
    SymbolIntelligenceRecord,
    User,
)
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
