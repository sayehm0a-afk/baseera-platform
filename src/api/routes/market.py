"""GET/POST /api/v1/market/* -- REST layer over
src.market_intelligence, following the same conventions as
src/api/routes/backtests.py (APIError subclasses + register_error_
handlers, a BackgroundTask that never blocks the request, GET routes
that only read already-persisted state).

`POST /api/v1/market/scan` never scans inline -- it resolves the
symbol universe, creates a `MarketScanRun` row (PENDING), and schedules
`run_market_scan_job` as a background task, then returns immediately.
Every read route (`/summary`, `/rankings`, `/watchlists`, `/sectors`,
`/changes`, `/alerts`) reads a specific (or the latest successful)
`MarketScanRun`'s already-persisted `SymbolIntelligenceRecord`/
`SectorIntelligenceSummary`/`MarketChangeEvent`/`MarketAlert` rows --
none of them re-runs a scan. `/rankings`/`/watchlists`/`/summary`
reconstruct `SymbolScanOutcome`s from those persisted rows (via
`src.market_intelligence.read_model`) and hand them to the exact same
`RankingEngine`/`WatchlistEngine`/`MarketSnapshotBuilder` the scan
itself used, so no ranking/watchlist/sentiment rule is duplicated here.
"""

import logging
from typing import List, Optional

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from src.api.dependencies import get_market_provider
from src.api.exceptions import MarketScanRunNotFoundError, NoMarketScanDataError
from src.api.schemas.market_intelligence import (
    AlertOut,
    AlertsOut,
    ChangeEventOut,
    ChangesOut,
    MarketScanRequest,
    MarketScanRunOut,
    MarketSummaryOut,
    RankingEntryOut,
    RankingListOut,
    RankingsOut,
    SectorsOut,
    SectorSummaryOut,
    WatchlistEntryOut,
    WatchlistResultOut,
    WatchlistsOut,
)
from src.core.db.database import get_db
from src.domain.models import MarketChangeEvent, MarketScanRun, SectorIntelligenceSummary
from src.market_data.providers.market_data_provider import IMarketDataProvider
from src.market_intelligence.market_snapshot import MarketSnapshotBuilder
from src.market_intelligence.ranking import RankingEngine
from src.market_intelligence.read_model import outcome_from_record
from src.market_intelligence.repositories.market_intelligence_repository import MarketIntelligenceRepository
from src.market_intelligence.services.scan_job_runner import run_market_scan_job
from src.market_intelligence.symbol_selector import SymbolSelector
from src.market_intelligence.types import ChangeDetectionResult, ChangeEvent, ChangeType, SectorSummary
from src.market_intelligence.watchlist import WatchlistEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/market", tags=["market"])

_repository = MarketIntelligenceRepository()


def _to_run_out(run: MarketScanRun) -> MarketScanRunOut:
    return MarketScanRunOut(
        id=run.id,
        status=run.status.value,
        symbols_requested=run.symbols_requested,
        symbols_succeeded=run.symbols_succeeded,
        symbols_skipped=run.symbols_skipped,
        symbols_failed=run.symbols_failed,
        error_summary=run.error_summary,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=float(run.duration_seconds) if run.duration_seconds is not None else None,
        created_at=run.created_at,
    )


def _resolve_run(session: Session, run_id: Optional[int]) -> MarketScanRun:
    if run_id is not None:
        run = _repository.get_run(session, run_id)
        if run is None:
            raise MarketScanRunNotFoundError(f"No market scan run {run_id}.")
        return run
    run = _repository.get_latest_successful_run(session)
    if run is None:
        raise NoMarketScanDataError("No completed market scan exists yet -- POST /api/v1/market/scan to run one.")
    return run


def _to_sector_summary(row: SectorIntelligenceSummary) -> SectorSummary:
    """One shared mapper from the persisted row to the plain
    dataclass every consumer below needs (`SectorAnalyzer.
    strongest_and_weakest()` via `MarketSnapshotBuilder`, and the
    `SectorSummaryOut` REST shape) -- written once, not duplicated
    per route."""
    return SectorSummary(
        sector=row.sector,
        symbol_count=row.symbol_count,
        average_confidence=float(row.average_confidence) if row.average_confidence is not None else None,
        average_final_score=float(row.average_final_score) if row.average_final_score is not None else None,
        average_expected_return_pct=float(row.average_expected_return_pct) if row.average_expected_return_pct is not None else None,
        average_technical_score=float(row.average_technical_score) if row.average_technical_score is not None else None,
        average_fundamental_score=float(row.average_fundamental_score) if row.average_fundamental_score is not None else None,
        buy_count=row.buy_count,
        sell_count=row.sell_count,
        hold_count=row.hold_count,
        breadth=float(row.breadth),
        momentum=float(row.momentum) if row.momentum is not None else None,
    )


def _to_sector_summary_out(summary: SectorSummary) -> SectorSummaryOut:
    return SectorSummaryOut(
        sector=summary.sector, symbol_count=summary.symbol_count,
        average_confidence=summary.average_confidence, average_final_score=summary.average_final_score,
        average_expected_return_pct=summary.average_expected_return_pct,
        average_technical_score=summary.average_technical_score,
        average_fundamental_score=summary.average_fundamental_score,
        buy_count=summary.buy_count, sell_count=summary.sell_count, hold_count=summary.hold_count,
        breadth=summary.breadth, momentum=summary.momentum,
    )


def _change_detection_result_from_events(
    events: List[MarketChangeEvent], previous_scan_run_id: Optional[int]
) -> ChangeDetectionResult:
    """Reconstructs `ChangeDetectionResult` from the persisted event
    log for one run, rather than re-running `ChangeDetector` at read
    time -- what a GET route reports as "what changed" for a given
    scan is exactly what was recorded during that scan, never
    re-derived. `new_symbols`/`removed_symbols` are not persisted
    separately from the event log, so they are empty here -- a
    disclosed, minor gap: NEW_OPPORTUNITIES read this way reflects
    recommendation upgrades into BUY/STRONG_BUY (fully covered by the
    persisted RECOMMENDATION_CHANGE events) but not a brand-new symbol
    first seen already rated BUY/STRONG_BUY.
    """
    return ChangeDetectionResult(
        events=[
            ChangeEvent(
                symbol=e.symbol, change_type=ChangeType(e.change_type.value),
                previous_value=e.previous_value, new_value=e.new_value,
                delta=float(e.delta) if e.delta is not None else None, detected_at=e.detected_at,
            )
            for e in events
        ],
        new_symbols=[],
        removed_symbols=[],
        previous_scan_run_id=previous_scan_run_id,
    )


@router.post("/scan", response_model=MarketScanRunOut)
async def create_scan(
    request: MarketScanRequest,
    background_tasks: BackgroundTasks,
    session: Session = Depends(get_db),
    market_provider: IMarketDataProvider = Depends(get_market_provider),
) -> MarketScanRunOut:
    symbols = SymbolSelector().select(session, request.symbols)
    run = _repository.create_scan_run(session, symbols_requested=len(symbols))
    run_out = _to_run_out(run)

    # Local import (not module-level) so a test's monkeypatch of
    # src.core.db.database.get_session_factory is honored -- same
    # reasoning src/api/routes/backtests.py's create_backtest already
    # documents for its own identical import.
    from src.core.db.database import get_session_factory

    background_tasks.add_task(run_market_scan_job, run.id, get_session_factory(), market_provider, symbols)
    return run_out


@router.get("/scan/{run_id}", response_model=MarketScanRunOut)
def get_scan(run_id: int, session: Session = Depends(get_db)) -> MarketScanRunOut:
    return _to_run_out(_resolve_run(session, run_id))


@router.get("/summary", response_model=MarketSummaryOut)
def get_summary(run_id: Optional[int] = Query(None), session: Session = Depends(get_db)) -> MarketSummaryOut:
    run = _resolve_run(session, run_id)
    records = _repository.get_symbol_records_by_symbol(session, run.id)
    outcomes = [outcome_from_record(r) for r in records.values()]

    sector_summaries = [_to_sector_summary(row) for row in _repository.get_sector_summaries(session, run.id)]

    _, change_rows = _repository.get_change_events(session, limit=1000, offset=0, run_id=run.id)
    change_result = _change_detection_result_from_events(change_rows, None)

    snapshot = MarketSnapshotBuilder().build(outcomes, sector_summaries, change_result)

    return MarketSummaryOut(
        scan_run_id=run.id,
        generated_at=snapshot.generated_at,
        symbols_scanned=snapshot.symbols_scanned,
        bull_bear_ratio=snapshot.bull_bear_ratio,
        average_confidence=snapshot.average_confidence,
        average_recommendation_score=snapshot.average_recommendation_score,
        buy_signal_count=snapshot.buy_signal_count,
        sell_signal_count=snapshot.sell_signal_count,
        strongest_sectors=snapshot.strongest_sectors,
        weakest_sectors=snapshot.weakest_sectors,
        most_important_changes=[
            ChangeEventOut(
                symbol=e.symbol, change_type=e.change_type.value, previous_value=e.previous_value,
                new_value=e.new_value, delta=e.delta, detected_at=e.detected_at,
            )
            for e in snapshot.most_important_changes
        ],
    )


@router.get("/rankings", response_model=RankingsOut)
def get_rankings(
    run_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    session: Session = Depends(get_db),
) -> RankingsOut:
    run = _resolve_run(session, run_id)
    records = _repository.get_symbol_records_by_symbol(session, run.id)
    outcomes = [outcome_from_record(r) for r in records.values()]

    previous_run = _repository.get_latest_successful_run(session, before_run_id=run.id)
    _, change_rows = _repository.get_change_events(session, limit=1000, offset=0, run_id=run.id)
    change_result = _change_detection_result_from_events(
        change_rows, previous_run.id if previous_run is not None else None
    )

    rankings = RankingEngine().rank(outcomes, change_result)
    if category is not None:
        rankings = {k: v for k, v in rankings.items() if k.value == category}

    return RankingsOut(
        scan_run_id=run.id,
        rankings=[
            RankingListOut(
                category=ranking_list.category.value,
                entries=[
                    RankingEntryOut(
                        symbol=e.symbol, sector=e.sector, recommendation=e.recommendation,
                        confidence=e.confidence, final_score=e.final_score, target_price=e.target_price,
                        expected_return_pct=e.expected_return_pct, risk_level=e.risk_level, rank_value=e.rank_value,
                    )
                    for e in ranking_list.entries
                ],
                generated_at=ranking_list.generated_at,
            )
            for ranking_list in rankings.values()
        ],
    )


@router.get("/top-buy", response_model=RankingListOut)
def get_top_buy(run_id: Optional[int] = Query(None), session: Session = Depends(get_db)) -> RankingListOut:
    return get_rankings(run_id=run_id, category="TOP_BUY", session=session).rankings[0]


@router.get("/top-strong-buy", response_model=RankingListOut)
def get_top_strong_buy(run_id: Optional[int] = Query(None), session: Session = Depends(get_db)) -> RankingListOut:
    return get_rankings(run_id=run_id, category="TOP_STRONG_BUY", session=session).rankings[0]


@router.get("/watchlists", response_model=WatchlistsOut)
def get_watchlists(
    run_id: Optional[int] = Query(None),
    category: Optional[str] = Query(None),
    session: Session = Depends(get_db),
) -> WatchlistsOut:
    run = _resolve_run(session, run_id)
    records = _repository.get_symbol_records_by_symbol(session, run.id)
    outcomes = [outcome_from_record(r) for r in records.values()]

    watchlists = WatchlistEngine().build(outcomes)
    if category is not None:
        watchlists = {k: v for k, v in watchlists.items() if k.value == category}

    return WatchlistsOut(
        scan_run_id=run.id,
        watchlists=[
            WatchlistResultOut(
                category=result.category.value,
                entries=[
                    WatchlistEntryOut(
                        symbol=e.symbol, sector=e.sector, recommendation=e.recommendation,
                        confidence=e.confidence, reason=e.reason,
                    )
                    for e in result.entries
                ],
                generated_at=result.generated_at,
            )
            for result in watchlists.values()
        ],
    )


@router.get("/sectors", response_model=SectorsOut)
def get_sectors(run_id: Optional[int] = Query(None), session: Session = Depends(get_db)) -> SectorsOut:
    run = _resolve_run(session, run_id)
    sector_rows = _repository.get_sector_summaries(session, run.id)
    return SectorsOut(
        scan_run_id=run.id,
        sectors=[_to_sector_summary_out(_to_sector_summary(row)) for row in sector_rows],
    )


@router.get("/changes", response_model=ChangesOut)
def get_changes(
    run_id: Optional[int] = Query(None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> ChangesOut:
    resolved_run_id = None
    if run_id is not None:
        resolved_run_id = _resolve_run(session, run_id).id
    total, rows = _repository.get_change_events(session, limit=limit, offset=offset, run_id=resolved_run_id)
    return ChangesOut(
        total=total, limit=limit, offset=offset,
        changes=[
            ChangeEventOut(
                symbol=r.symbol, change_type=r.change_type.value, previous_value=r.previous_value,
                new_value=r.new_value, delta=float(r.delta) if r.delta is not None else None,
                detected_at=r.detected_at,
            )
            for r in rows
        ],
    )


@router.get("/alerts", response_model=AlertsOut)
def get_alerts(
    severity: Optional[str] = Query(None),
    alert_type: Optional[str] = Query(None),
    limit: int = Query(default=50, ge=1, le=500),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> AlertsOut:
    total, rows = _repository.get_alerts(session, limit=limit, offset=offset, severity=severity, alert_type=alert_type)
    return AlertsOut(
        total=total, limit=limit, offset=offset,
        alerts=[
            AlertOut(
                alert_type=r.alert_type.value, severity=r.severity.value, symbol=r.symbol,
                sector=r.sector, message=r.message, generated_at=r.generated_at,
            )
            for r in rows
        ],
    )
