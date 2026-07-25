"""BacktestingEngine: evaluates one symbol, a group of symbols, or a
full configured universe over a historical period, strictly using
only as-of-date-safe data (src.backtesting.data_access), and scores
the result with src.backtesting.metrics.

This module owns *when* to evaluate and *how to score what happened
afterward* -- it never computes an indicator, a ratio, or a
recommendation itself. Each evaluation delegates to a `Strategy`
(src.backtesting.baselines), the same interface for the real
AIDecisionEngine-backed strategy and every transparent baseline, so
"run a backtest" means exactly the same thing regardless of which
strategy produced the call.
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from typing import Callable, Dict, List, Optional

from sqlalchemy.orm import Session

from src.analysis.decision.ai_decision_engine import ENGINE_VERSION
from src.backtesting.baselines import StrategyCall, build_strategy
from src.backtesting.data_access import (
    AsOfDataset,
    DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    bars_match_provenance,
    load_as_of_dataset,
    load_forward_price_path,
)
from src.backtesting.metrics import EvaluationOutcome, full_report
from src.backtesting.regime import classify_market_regime
from src.domain.models import DataProvenanceMode, RecommendationLabel, RecommendationSnapshot, Stock

logger = logging.getLogger(__name__)

_BULLISH = {"STRONG_BUY", "BUY"}
_BEARISH = {"STRONG_SELL", "SELL"}


@dataclass(frozen=True)
class BacktestConfig:
    """Everything one BacktestingEngine.run() call needs -- deliberately
    the same shape BacktestRun persists, so a run's configuration is
    always exactly reproducible from its database row."""

    symbols: List[str]
    start_date: date
    end_date: date
    data_provenance_mode: DataProvenanceMode
    strategy: str = "ai_decision_engine"
    strategy_kwargs: Optional[dict] = None
    evaluation_frequency_days: int = 7
    holding_horizon_days: int = 20
    target_price_horizon_days: int = 60
    transaction_cost_bps: float = 0.0
    slippage_bps: float = 0.0
    confidence_threshold: Optional[float] = None
    recommendation_threshold: Optional[str] = None  # "BUY" or "SELL" -- see _meets_thresholds
    fundamental_reporting_lag_days: int = DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS
    calibration_version: Optional[str] = None


def _evaluation_dates(start: date, end: date, frequency_days: int) -> List[date]:
    if frequency_days <= 0:
        raise ValueError("evaluation_frequency_days must be positive")
    dates = []
    current = start
    while current <= end:
        dates.append(current)
        current += timedelta(days=frequency_days)
    return dates


def _round_trip_cost_pct(transaction_cost_bps: float, slippage_bps: float) -> float:
    """Basis points -> percent, doubled for one entry + one exit --
    applied uniformly to every directional call's forward return, a
    single transparent number rather than modeling entry/exit price
    impact separately (there is no order-book/liquidity model in this
    codebase to make that more precise a meaningful improvement)."""
    return 2.0 * (transaction_cost_bps + slippage_bps) / 100.0


def _compute_forward_return(entry_price: Optional[float], holding_df, cost_pct: float) -> Optional[float]:
    if entry_price is None or entry_price <= 0 or holding_df is None or holding_df.empty:
        return None
    exit_price = float(holding_df["close"].iloc[-1])
    raw_return = (exit_price - entry_price) / entry_price * 100.0
    return raw_return - cost_pct


def _compute_hit_target_stop(call: StrategyCall, horizon_df):
    if horizon_df is None or horizon_df.empty:
        return None, None
    bullish = call.recommendation in _BULLISH
    bearish = call.recommendation in _BEARISH
    if not bullish and not bearish:
        return None, None  # HOLD implies no position -- hit/miss is undefined, not False

    hit_target = None
    if call.target_price is not None:
        hit_target = bool((horizon_df["high"] >= call.target_price).any() if bullish else (horizon_df["low"] <= call.target_price).any())

    hit_stop = None
    if call.stop_loss is not None:
        hit_stop = bool((horizon_df["low"] <= call.stop_loss).any() if bullish else (horizon_df["high"] >= call.stop_loss).any())

    return hit_target, hit_stop


def _meets_thresholds(outcome: EvaluationOutcome, confidence_threshold: Optional[float], recommendation_threshold: Optional[str]) -> bool:
    if confidence_threshold is not None and outcome.confidence < confidence_threshold:
        return False
    if recommendation_threshold == "BUY" and outcome.recommendation not in _BULLISH:
        return False
    if recommendation_threshold == "SELL" and outcome.recommendation not in _BEARISH:
        return False
    return True


def _upsert_snapshot(
    session: Session,
    run_id: Optional[int],
    stock: Stock,
    evaluated_at: datetime,
    dataset: AsOfDataset,
    call: StrategyCall,
    config: BacktestConfig,
) -> None:
    """Idempotent: re-running the same (run, symbol, date) updates the
    existing row in place instead of violating the unique constraint
    or accumulating duplicates -- the same discipline PriceBar/
    FundamentalSnapshot upserts already follow."""
    existing = (
        session.query(RecommendationSnapshot)
        .filter_by(run_id=run_id, stock_id=stock.id, evaluated_at=evaluated_at)
        .one_or_none()
    )

    price = dataset.context.latest_price
    expected_return_pct = (
        (call.target_price - price) / price * 100.0 if call.target_price is not None and price else None
    )

    fields = dict(
        market_price_at_evaluation=price,
        recommendation=RecommendationLabel(call.recommendation),
        total_score=call.total_score,
        confidence_score=call.confidence,
        technical_score=call.technical_score,
        fundamental_score=call.fundamental_score,
        momentum_score=call.momentum_score,
        volume_score=call.volume_score,
        risk_score=call.risk_score,
        contributor_breakdown=call.contributor_breakdown,
        signals=call.signals,
        reasons=call.reasons,
        target_price=call.target_price,
        stop_loss=call.stop_loss,
        expected_return_pct=expected_return_pct,
        time_horizon=call.time_horizon,
        risk_level=call.risk_level,
        position_size=call.position_size,
        technical_input_as_of=dataset.technical_input_as_of,
        fundamental_input_as_of=dataset.fundamental_input_as_of,
        price_bar_source=dataset.price_bar_source,
        price_bar_is_synthetic=dataset.price_bar_is_synthetic,
        engine_version=ENGINE_VERSION,
        calibration_version=config.calibration_version,
    )

    if existing is not None:
        for key, value in fields.items():
            setattr(existing, key, value)
        return

    session.add(
        RecommendationSnapshot(
            run_id=run_id, stock_id=stock.id, symbol=stock.symbol, evaluated_at=evaluated_at, **fields
        )
    )


class BacktestingEngine:
    """Runs one BacktestConfig to completion against already-ingested
    database data. Never calls a live market-data provider -- every
    price/fundamental input comes from src.backtesting.data_access,
    which only reads PriceBar/FundamentalSnapshot rows already in the
    database (respecting rate limits and "prefer already-ingested
    data" is automatic, not a separate mechanism)."""

    def run(
        self,
        session: Session,
        config: BacktestConfig,
        run_id: Optional[int] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> Dict:
        strategy = build_strategy(config.strategy, **(config.strategy_kwargs or {}))
        eval_dates = _evaluation_dates(config.start_date, config.end_date, config.evaluation_frequency_days)
        total = len(config.symbols) * len(eval_dates)
        done = 0
        cancelled = False

        outcomes: List[EvaluationOutcome] = []
        skipped = {"symbol_not_found": 0, "provenance_mismatch": 0, "insufficient_data": 0, "no_call": 0}
        cost_pct = _round_trip_cost_pct(config.transaction_cost_bps, config.slippage_bps)
        expect_synthetic = config.data_provenance_mode == DataProvenanceMode.SYNTHETIC

        for symbol in config.symbols:
            if is_cancelled and is_cancelled():
                cancelled = True
                break

            stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
            if stock is None:
                skipped["symbol_not_found"] += len(eval_dates)
                done += len(eval_dates)
                if progress_callback:
                    progress_callback(done, total)
                continue

            for eval_date in eval_dates:
                if is_cancelled and is_cancelled():
                    cancelled = True
                    break

                if not bars_match_provenance(session, stock.id, config.start_date, eval_date, expect_synthetic):
                    skipped["provenance_mismatch"] += 1
                    done += 1
                    if progress_callback:
                        progress_callback(done, total)
                    continue

                dataset = load_as_of_dataset(session, stock, eval_date, config.fundamental_reporting_lag_days)
                if not dataset.has_any_input:
                    skipped["insufficient_data"] += 1
                    done += 1
                    if progress_callback:
                        progress_callback(done, total)
                    continue

                call = strategy.evaluate(dataset)
                if call is None:
                    skipped["no_call"] += 1
                    done += 1
                    if progress_callback:
                        progress_callback(done, total)
                    continue

                evaluated_at = datetime.combine(eval_date, time.min, tzinfo=timezone.utc)
                _upsert_snapshot(session, run_id, stock, evaluated_at, dataset, call, config)

                holding_df = load_forward_price_path(session, stock, eval_date, config.holding_horizon_days)
                forward_return_pct = _compute_forward_return(dataset.context.latest_price, holding_df, cost_pct)

                target_horizon_df = load_forward_price_path(session, stock, eval_date, config.target_price_horizon_days)
                hit_target, hit_stop = _compute_hit_target_stop(call, target_horizon_df)

                regime = classify_market_regime(dataset.price_bars_df) if dataset.price_bars_df is not None else None

                outcomes.append(
                    EvaluationOutcome(
                        symbol=symbol,
                        evaluated_at=eval_date,
                        recommendation=call.recommendation,
                        confidence=call.confidence,
                        total_score=call.total_score,
                        risk_level=call.risk_level,
                        time_horizon=call.time_horizon,
                        sector=stock.sector,
                        market_regime=regime,
                        market_price_at_evaluation=dataset.context.latest_price,
                        target_price=call.target_price,
                        stop_loss=call.stop_loss,
                        forward_return_pct=forward_return_pct,
                        hit_target=hit_target,
                        hit_stop_loss=hit_stop,
                    )
                )

                done += 1
                if progress_callback:
                    progress_callback(done, total)

            session.commit()  # durable per-symbol -- a later failure doesn't lose already-evaluated symbols
            if cancelled:
                break

        filtered = [o for o in outcomes if _meets_thresholds(o, config.confidence_threshold, config.recommendation_threshold)]
        report = full_report(filtered)
        report["evaluated_count"] = len(outcomes)
        report["filtered_count"] = len(filtered)
        report["skipped"] = skipped
        report["cancelled"] = cancelled
        return report
