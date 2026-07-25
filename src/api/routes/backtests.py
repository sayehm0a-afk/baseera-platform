"""GET/POST /api/v1/backtests/* -- REST layer over
src.backtesting.engine.BacktestingEngine, following the same
conventions as src/api/routes/stocks.py (APIError subclasses +
register_error_handlers for a consistent error envelope, a plain
`Depends(get_db)` sync session, read-only where possible).

`POST /api/v1/backtests` never runs a backtest inline -- it creates a
BacktestRun row (PENDING) and schedules src.backtesting.job_runner.run_backtest_job
as a background asyncio task, then returns immediately. Every other
route here only reads already-persisted state, so no route can block
on a long-running backtest.
"""

import hashlib
import json
import logging

from fastapi import APIRouter, BackgroundTasks, Depends, Query
from sqlalchemy.orm import Session

from src.api.exceptions import BacktestRunNotFoundError, DuplicateBacktestError, InvalidBacktestConfigError
from src.api.schemas.backtesting import (
    BacktestComparisonOut,
    BacktestCreateRequest,
    BacktestMetricsOut,
    BacktestRunOut,
    BacktestStatusOut,
    BacktestTradesOut,
    ComparisonEntryOut,
    ConfidenceCalibrationOut,
    RecommendationSnapshotOut,
)
from src.backtesting.baselines import DEFAULT_STRATEGIES
from src.backtesting.config import get_full_market_symbol_threshold, get_max_trades_page_size
from src.backtesting.job_runner import run_backtest_job
from src.core.db.database import get_db
from src.domain.models import BacktestRun, BacktestRunStatus, DataProvenanceMode, RecommendationSnapshot

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/backtests", tags=["backtests"])


def _compute_idempotency_key(request: BacktestCreateRequest) -> str:
    """A deterministic hash of every field that defines what the
    backtest actually does -- resubmitting the identical configuration
    always maps to the same key, which is what makes execution
    idempotent (Phase 8): the route returns the existing run instead of
    creating a duplicate."""
    canonical = json.dumps(request.model_dump(mode="json"), sort_keys=True, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:32]


def _to_run_out(run: BacktestRun) -> BacktestRunOut:
    return BacktestRunOut(
        id=run.id,
        idempotency_key=run.idempotency_key,
        status=run.status.value,
        symbols=run.symbols,
        strategy=run.strategy,
        data_provenance_mode=run.data_provenance_mode.value,
        start_date=run.start_date,
        end_date=run.end_date,
        evaluation_frequency_days=run.evaluation_frequency_days,
        holding_horizon_days=run.holding_horizon_days,
        target_price_horizon_days=run.target_price_horizon_days,
        transaction_cost_bps=float(run.transaction_cost_bps),
        slippage_bps=float(run.slippage_bps),
        confidence_threshold=float(run.confidence_threshold) if run.confidence_threshold is not None else None,
        recommendation_threshold=run.recommendation_threshold,
        fundamental_reporting_lag_days=run.fundamental_reporting_lag_days,
        calibration_version=run.calibration_version,
        progress_current=run.progress_current,
        progress_total=run.progress_total,
        error_message=run.error_message,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=float(run.duration_seconds) if run.duration_seconds is not None else None,
        created_at=run.created_at,
    )


def _get_run_or_404(session: Session, run_id: int) -> BacktestRun:
    run = session.query(BacktestRun).filter_by(id=run_id).one_or_none()
    if run is None:
        raise BacktestRunNotFoundError(f"No backtest run {run_id}.")
    return run


@router.post("", response_model=BacktestRunOut)
async def create_backtest(
    request: BacktestCreateRequest, background_tasks: BackgroundTasks, session: Session = Depends(get_db)
) -> BacktestRunOut:
    if request.strategy not in DEFAULT_STRATEGIES:
        raise InvalidBacktestConfigError(
            f"Unknown strategy {request.strategy!r}. Known strategies: {sorted(DEFAULT_STRATEGIES)}"
        )

    idempotency_key = _compute_idempotency_key(request)
    existing = session.query(BacktestRun).filter_by(idempotency_key=idempotency_key).one_or_none()
    if existing is not None:
        logger.info("Backtest request matches existing run %d (idempotent) -- not creating a duplicate.", existing.id)
        return _to_run_out(existing)

    threshold = get_full_market_symbol_threshold()
    if len(request.symbols) >= threshold:
        in_flight = (
            session.query(BacktestRun)
            .filter(BacktestRun.status.in_([BacktestRunStatus.PENDING, BacktestRunStatus.RUNNING]))
            .all()
        )
        for run in in_flight:
            if len(run.symbols or []) >= threshold:
                raise DuplicateBacktestError(
                    f"A large-scope backtest (run {run.id}, {run.status.value}) covering "
                    f"{len(run.symbols)} symbols is already in progress -- wait for it to finish "
                    "before starting another full-market-scale backtest."
                )

    run = BacktestRun(
        idempotency_key=idempotency_key,
        status=BacktestRunStatus.PENDING,
        symbols=request.symbols,
        data_provenance_mode=DataProvenanceMode(request.data_provenance_mode),
        strategy=request.strategy,
        start_date=request.start_date,
        end_date=request.end_date,
        evaluation_frequency_days=request.evaluation_frequency_days,
        holding_horizon_days=request.holding_horizon_days,
        target_price_horizon_days=request.target_price_horizon_days,
        transaction_cost_bps=request.transaction_cost_bps,
        slippage_bps=request.slippage_bps,
        confidence_threshold=request.confidence_threshold,
        recommendation_threshold=request.recommendation_threshold,
        fundamental_reporting_lag_days=request.fundamental_reporting_lag_days,
        calibration_version=request.calibration_version,
    )
    session.add(run)
    session.commit()

    # Local import (not a module-level one) so a test's monkeypatch of
    # src.core.db.database.get_session_factory is honored -- an
    # already-bound `from ... import get_session_factory` at module
    # scope would keep referencing whatever the function object was at
    # import time, the same gotcha main.py's /ingestion/status route
    # already works around the same way.
    from src.core.db.database import get_session_factory

    # FastAPI's BackgroundTasks (not a detached asyncio.ensure_future)
    # -- runs after this response is sent, on the same event loop, so
    # the client never waits for the backtest itself, but the task is
    # still tied to a request the ASGI server keeps genuinely alive
    # for (unlike a fire-and-forget task, which has nothing anchoring
    # its event loop to stay open across various ASGI server/test
    # harness implementations).
    background_tasks.add_task(run_backtest_job, run.id, get_session_factory())

    return _to_run_out(run)


@router.get("/{run_id}", response_model=BacktestRunOut)
def get_backtest(run_id: int, session: Session = Depends(get_db)) -> BacktestRunOut:
    return _to_run_out(_get_run_or_404(session, run_id))


@router.get("/{run_id}/status", response_model=BacktestStatusOut)
def get_backtest_status(run_id: int, session: Session = Depends(get_db)) -> BacktestStatusOut:
    run = _get_run_or_404(session, run_id)
    return BacktestStatusOut(
        id=run.id,
        status=run.status.value,
        progress_current=run.progress_current,
        progress_total=run.progress_total,
        cancel_requested=run.cancel_requested,
        started_at=run.started_at,
        finished_at=run.finished_at,
        duration_seconds=float(run.duration_seconds) if run.duration_seconds is not None else None,
    )


@router.post("/{run_id}/cancel", response_model=BacktestStatusOut)
def cancel_backtest(run_id: int, session: Session = Depends(get_db)) -> BacktestStatusOut:
    """Cooperative cancellation (Phase 8): sets cancel_requested, which
    the running job checks between evaluations and honors as soon as
    practical -- not an immediate hard stop, since a snapshot already
    being written should finish cleanly rather than leave a torn row."""
    run = _get_run_or_404(session, run_id)
    if run.status in (BacktestRunStatus.PENDING, BacktestRunStatus.RUNNING):
        run.cancel_requested = True
        session.commit()
    return get_backtest_status(run_id, session)


@router.get("/{run_id}/metrics", response_model=BacktestMetricsOut)
def get_backtest_metrics(run_id: int, session: Session = Depends(get_db)) -> BacktestMetricsOut:
    run = _get_run_or_404(session, run_id)
    return BacktestMetricsOut(
        id=run.id, status=run.status.value, data_provenance_mode=run.data_provenance_mode.value,
        symbols=run.symbols, metrics=run.metrics,
    )


@router.get("/{run_id}/trades", response_model=BacktestTradesOut)
def get_backtest_trades(
    run_id: int,
    limit: int = Query(default=50, ge=1),
    offset: int = Query(default=0, ge=0),
    session: Session = Depends(get_db),
) -> BacktestTradesOut:
    _get_run_or_404(session, run_id)
    limit = min(limit, get_max_trades_page_size())

    query = session.query(RecommendationSnapshot).filter_by(run_id=run_id).order_by(
        RecommendationSnapshot.symbol, RecommendationSnapshot.evaluated_at
    )
    total = query.count()
    rows = query.offset(offset).limit(limit).all()

    return BacktestTradesOut(
        id=run_id, total=total, limit=limit, offset=offset,
        trades=[
            RecommendationSnapshotOut(
                id=row.id, symbol=row.symbol, evaluated_at=row.evaluated_at,
                market_price_at_evaluation=float(row.market_price_at_evaluation) if row.market_price_at_evaluation is not None else None,
                recommendation=row.recommendation.value, total_score=float(row.total_score),
                confidence_score=float(row.confidence_score),
                target_price=float(row.target_price) if row.target_price is not None else None,
                stop_loss=float(row.stop_loss) if row.stop_loss is not None else None,
                expected_return_pct=float(row.expected_return_pct) if row.expected_return_pct is not None else None,
                time_horizon=row.time_horizon, risk_level=row.risk_level, position_size=row.position_size,
                price_bar_source=row.price_bar_source, price_bar_is_synthetic=row.price_bar_is_synthetic,
                engine_version=row.engine_version, calibration_version=row.calibration_version,
            )
            for row in rows
        ],
    )


@router.get("/{run_id}/confidence-calibration", response_model=ConfidenceCalibrationOut)
def get_backtest_confidence_calibration(run_id: int, session: Session = Depends(get_db)) -> ConfidenceCalibrationOut:
    run = _get_run_or_404(session, run_id)
    calibration = ((run.metrics or {}).get("overall") or {}).get("calibration_error")
    if calibration is None:
        return ConfidenceCalibrationOut(id=run_id, overall_error=None, buckets=[])
    return ConfidenceCalibrationOut(id=run_id, overall_error=calibration.get("overall_error"), buckets=calibration.get("buckets", []))


@router.get("/{run_id}/comparison", response_model=BacktestComparisonOut)
def get_backtest_comparison(run_id: int, session: Session = Depends(get_db)) -> BacktestComparisonOut:
    """Compares this run against any *other already-run* backtest that
    shares the same symbols/date range/provenance but a different
    strategy -- e.g. run the same configuration once per baseline
    (buy_and_hold, sma_crossover, ...) to populate a real comparison.
    Never triggers new backtests itself (this is a GET); a strategy
    with no matching run yet simply doesn't appear.
    """
    run = _get_run_or_404(session, run_id)

    candidates = (
        session.query(BacktestRun)
        .filter(
            BacktestRun.start_date == run.start_date,
            BacktestRun.end_date == run.end_date,
            BacktestRun.data_provenance_mode == run.data_provenance_mode,
            BacktestRun.status == BacktestRunStatus.SUCCESS,
        )
        .all()
    )
    same_symbols = set(run.symbols)
    comparisons = [
        ComparisonEntryOut(
            run_id=candidate.id, strategy=candidate.strategy, status=candidate.status.value,
            data_provenance_mode=candidate.data_provenance_mode.value,
            metrics=(candidate.metrics or {}).get("overall"),
        )
        for candidate in candidates
        if set(candidate.symbols) == same_symbols
    ]

    return BacktestComparisonOut(
        id=run_id,
        comparisons=comparisons,
        note=(
            "Only strategies with a completed backtest over the identical symbols/date range/"
            "data provenance are shown. Submit a POST /api/v1/backtests with the same symbols, "
            "start_date, end_date, and data_provenance_mode but a different `strategy` (e.g. "
            "buy_and_hold, sma_crossover, rsi_only, technical_only, fundamental_only, "
            "uncalibrated_ai_decision_engine) to add it to this comparison."
        ),
    )
