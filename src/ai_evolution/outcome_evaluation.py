"""E2 of the AI Evolution Layer: issuing PENDING `RecommendationOutcome`
rows alongside a live `RecommendationSnapshot`, and evaluating them once
their horizon has elapsed and real forward price data exists.

Two entry points:
  - `create_pending_outcomes()` -- called once per snapshot, at write
    time (see `MarketIntelligenceRepository.save_symbol_records`).
  - `evaluate_due_outcomes()` -- called on a schedule
    (`OutcomeEvaluationScheduler`) to score whatever has come due.

Never judges a recommendation before its horizon has actually elapsed
(`due_at <= now`), and never invents forward price data -- a due row
with no forward bars yet simply stays PENDING and is retried on the
next cycle, up to `OUTCOME_EVALUATION_STALE_GRACE_DAYS` past due before
it's given up on (EXPIRED, not silently dropped).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import List, Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from src.ai_evolution.config import get_outcome_evaluation_stale_grace_days
from src.backtesting.data_access import load_forward_price_path
from src.domain.models import (
    RecommendationOutcome,
    RecommendationOutcomeStatus,
    RecommendationSnapshot,
    Stock,
)

# Fixed evaluation horizons, in days -- every live recommendation is
# scored at each of these checkpoints, matching the AI Evolution Layer
# design's Part 1 spec verbatim.
EVALUATION_HORIZON_DAYS: Tuple[int, ...] = (1, 3, 7, 14, 30, 60, 90)

_BULLISH = {"STRONG_BUY", "BUY"}
_BEARISH = {"STRONG_SELL", "SELL"}


def _as_utc(value: datetime) -> datetime:
    """SQLite (every unit test in this codebase) does not round-trip a
    timezone-aware `DateTime` faithfully -- a value re-queried from the
    DB comes back naive, though its wall-clock value is still UTC (the
    only timezone this codebase ever writes). Comparing that against
    an aware `datetime` would otherwise raise `TypeError` under SQLite
    while working fine under real, tz-preserving PostgreSQL -- the same
    pitfall `MarketIntelligenceRepository.mark_running`'s docstring
    already documents for this exact reason."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def create_pending_outcomes(session: Session, snapshot: RecommendationSnapshot) -> List[RecommendationOutcome]:
    """Idempotent: re-calling for a snapshot that already has some/all
    horizon rows only creates the missing ones."""
    if snapshot.id is None:
        session.flush()

    existing_horizons = {
        row.evaluation_horizon_days
        for row in session.query(RecommendationOutcome.evaluation_horizon_days).filter_by(snapshot_id=snapshot.id).all()
    }

    created = []
    for horizon_days in EVALUATION_HORIZON_DAYS:
        if horizon_days in existing_horizons:
            continue
        outcome = RecommendationOutcome(
            snapshot_id=snapshot.id,
            symbol=snapshot.symbol,
            evaluation_horizon_days=horizon_days,
            due_at=snapshot.evaluated_at + timedelta(days=horizon_days),
            status=RecommendationOutcomeStatus.PENDING,
        )
        session.add(outcome)
        created.append(outcome)
    return created


def _hit_target_and_stop(
    recommendation: str,
    target_price: Optional[float],
    stop_loss: Optional[float],
    horizon_df: pd.DataFrame,
) -> Tuple[Optional[bool], Optional[bool]]:
    """Mirrors `src.backtesting.engine._compute_hit_target_stop`'s exact
    convention (an intraday touch of the bar's high/low counts, not
    just a close) so live and backtest outcome classification stay
    consistent. Reimplemented locally rather than imported because
    that function is a module-private helper keyed to `StrategyCall`'s
    shape, not a public, reusable utility -- this is the same ~15-line
    logic, not a divergent rule."""
    if horizon_df is None or horizon_df.empty:
        return None, None
    bullish = recommendation in _BULLISH
    bearish = recommendation in _BEARISH
    if not bullish and not bearish:
        return None, None  # HOLD implies no position -- hit/miss is undefined, not False

    hit_target = None
    if target_price is not None:
        hit_target = bool(
            (horizon_df["high"] >= target_price).any() if bullish else (horizon_df["low"] <= target_price).any()
        )

    hit_stop = None
    if stop_loss is not None:
        hit_stop = bool(
            (horizon_df["low"] <= stop_loss).any() if bullish else (horizon_df["high"] >= stop_loss).any()
        )

    return hit_target, hit_stop


def _first_target_touch(
    recommendation: str, target_price: Optional[float], horizon_df: pd.DataFrame,
) -> Tuple[Optional[bool], Optional[datetime]]:
    """True + the real bar timestamp of the first intraday touch of
    `target_price` within `horizon_df` -- high >= target for a bullish
    call, low <= target for a bearish one, the same convention
    `_hit_target_and_stop` already uses. `(None, None)` for a HOLD (no
    position to reach a target) or when this particular target was
    never set (e.g. target_2/target_3 on a call Decision Engine V2
    didn't compute for)."""
    if target_price is None or horizon_df is None or horizon_df.empty:
        return None, None
    bullish = recommendation in _BULLISH
    bearish = recommendation in _BEARISH
    if not bullish and not bearish:
        return None, None
    touched = horizon_df["high"] >= target_price if bullish else horizon_df["low"] <= target_price
    touched_at = horizon_df.index[touched]
    if len(touched_at) == 0:
        return False, None
    return True, _as_utc(pd.Timestamp(touched_at[0]).to_pydatetime())


def _max_favorable_adverse_excursion(
    recommendation: str, entry_price: Optional[float], horizon_df: pd.DataFrame,
) -> Tuple[Optional[float], Optional[float]]:
    """MFE/MAE: the best/worst the position's real forward price path
    ever looked across the whole horizon window, as a percent of entry
    price -- independent of whether target/stop was actually touched.
    MFE is always >= 0 (an excursion starts at exactly 0 the instant a
    position opens); MAE is always <= 0. `(None, None)` for a HOLD (no
    position to measure an excursion for) or a missing/invalid entry
    price."""
    if entry_price is None or entry_price <= 0 or horizon_df is None or horizon_df.empty:
        return None, None
    bullish = recommendation in _BULLISH
    bearish = recommendation in _BEARISH
    if not bullish and not bearish:
        return None, None
    if bullish:
        best_gain_pct = (horizon_df["high"] - entry_price) / entry_price * 100.0
        worst_gain_pct = (horizon_df["low"] - entry_price) / entry_price * 100.0
    else:
        best_gain_pct = (entry_price - horizon_df["low"]) / entry_price * 100.0
        worst_gain_pct = (entry_price - horizon_df["high"]) / entry_price * 100.0
    return max(float(best_gain_pct.max()), 0.0), min(float(worst_gain_pct.min()), 0.0)


def _classify_status(
    target_price: Optional[float],
    stop_loss: Optional[float],
    hit_target: Optional[bool],
    hit_stop: Optional[bool],
) -> RecommendationOutcomeStatus:
    """SUCCESSFUL/FAILED require a clean, single-threshold read; a call
    with no target or stop set (e.g. a HOLD) has nothing to judge it
    against, and both thresholds touched within the same window is
    genuinely ambiguous with only daily OHLC (no way to tell which
    came first) -- both map to EXPIRED/PARTIAL rather than a guessed
    verdict."""
    if target_price is None and stop_loss is None:
        return RecommendationOutcomeStatus.EXPIRED
    if hit_target and hit_stop:
        return RecommendationOutcomeStatus.PARTIAL
    if hit_target:
        return RecommendationOutcomeStatus.SUCCESSFUL
    if hit_stop:
        return RecommendationOutcomeStatus.FAILED
    return RecommendationOutcomeStatus.PARTIAL


@dataclass(frozen=True)
class OutcomeEvaluationSummary:
    evaluated: int
    expired_no_data: int
    skipped_pending: int


def evaluate_due_outcomes(
    session: Session,
    now: Optional[datetime] = None,
    batch_limit: int = 500,
) -> OutcomeEvaluationSummary:
    now = now or datetime.now(timezone.utc)
    stale_cutoff = now - timedelta(days=get_outcome_evaluation_stale_grace_days())

    due_rows = (
        session.query(RecommendationOutcome)
        .filter(
            RecommendationOutcome.status == RecommendationOutcomeStatus.PENDING,
            RecommendationOutcome.due_at <= now,
        )
        .order_by(RecommendationOutcome.due_at.asc())
        .limit(batch_limit)
        .all()
    )

    evaluated = 0
    expired_no_data = 0
    skipped_pending = 0

    for row in due_rows:
        snapshot = session.query(RecommendationSnapshot).filter_by(id=row.snapshot_id).one_or_none()
        if snapshot is None:
            # Orphaned row (its snapshot no longer exists) -- nothing left to score against.
            row.status = RecommendationOutcomeStatus.CANCELLED
            row.evaluated_at = now
            evaluated += 1
            continue

        stock = session.query(Stock).filter_by(id=snapshot.stock_id).one_or_none()
        if stock is None:
            row.status = RecommendationOutcomeStatus.CANCELLED
            row.evaluated_at = now
            evaluated += 1
            continue

        horizon_df = load_forward_price_path(session, stock, snapshot.evaluated_at.date(), row.evaluation_horizon_days)

        if horizon_df.empty:
            if _as_utc(row.due_at) < stale_cutoff:
                row.status = RecommendationOutcomeStatus.EXPIRED
                row.evaluated_at = now
                expired_no_data += 1
            else:
                skipped_pending += 1
            continue

        target_price = float(snapshot.target_price) if snapshot.target_price is not None else None
        stop_loss = float(snapshot.stop_loss) if snapshot.stop_loss is not None else None
        hit_target, hit_stop = _hit_target_and_stop(snapshot.recommendation.value, target_price, stop_loss, horizon_df)

        entry_price = float(snapshot.market_price_at_evaluation) if snapshot.market_price_at_evaluation is not None else None
        exit_price = float(horizon_df["close"].iloc[-1])
        return_pct = (
            (exit_price - entry_price) / entry_price * 100.0 if entry_price is not None and entry_price > 0 else None
        )

        recommendation_value = snapshot.recommendation.value
        target_1_reached, target_1_reached_at = _first_target_touch(recommendation_value, target_price, horizon_df)
        target_price_2 = float(snapshot.target_price_2) if snapshot.target_price_2 is not None else None
        target_price_3 = float(snapshot.target_price_3) if snapshot.target_price_3 is not None else None
        target_2_reached, target_2_reached_at = _first_target_touch(recommendation_value, target_price_2, horizon_df)
        target_3_reached, target_3_reached_at = _first_target_touch(recommendation_value, target_price_3, horizon_df)
        mfe, mae = _max_favorable_adverse_excursion(recommendation_value, entry_price, horizon_df)

        reached_ats = [t for t in (target_1_reached_at, target_2_reached_at, target_3_reached_at) if t is not None]
        time_to_target_days = (min(reached_ats) - _as_utc(snapshot.evaluated_at)).days if reached_ats else None

        row.status = _classify_status(target_price, stop_loss, hit_target, hit_stop)
        row.price_at_evaluation = exit_price
        row.return_pct = return_pct
        row.hit_target = hit_target
        row.hit_stop = hit_stop
        row.target_1_reached = target_1_reached
        row.target_1_reached_at = target_1_reached_at
        row.target_2_reached = target_2_reached
        row.target_2_reached_at = target_2_reached_at
        row.target_3_reached = target_3_reached
        row.target_3_reached_at = target_3_reached_at
        row.max_favorable_excursion_pct = mfe
        row.max_adverse_excursion_pct = mae
        row.time_to_target_days = time_to_target_days
        row.evaluated_at = now
        evaluated += 1

    session.commit()
    return OutcomeEvaluationSummary(evaluated=evaluated, expired_no_data=expired_no_data, skipped_pending=skipped_pending)
