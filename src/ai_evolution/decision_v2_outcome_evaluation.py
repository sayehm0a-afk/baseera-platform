"""M10: issuing and evaluating `DecisionV2Outcome` rows -- the outcome
tracker correctly linked to `DecisionV2Snapshot` (the richer,
user-facing decision shape), unlike `RecommendationOutcome` (E2), which
stays linked to the older `RecommendationSnapshot` and continues to
serve backtesting/paper-trading unchanged.

Two entry points, matching `src.ai_evolution.outcome_evaluation`'s
shape:
  - `create_pending_decision_v2_outcome()` -- called once per snapshot,
    at write time, but ONLY for an actionable BUY-like decision
    (STRONG_BUY_CANDIDATE/BUY_CANDIDATE). WATCH/HOLD/WAIT_FOR_ENTRY/
    REJECT/etc. open no position, so there is nothing for target/stop
    tracking to judge -- those decisions are counted directly from
    `DecisionV2Snapshot.decision` by the M10 metrics module instead.
  - `evaluate_pending_outcomes()` -- called on a schedule. Unlike E2's
    fixed-horizon design, this checks every still-PENDING row against
    ALL real price data available since its decision_timestamp on
    every pass, so a target hit on day 2 is reported on day 2, not
    held back until the full expected-duration horizon elapses.

Never invents forward price data: a row with no forward bars at all
gets DATA_UNAVAILABLE only after `get_outcome_evaluation_stale_grace_
days()` has passed with nothing to judge against -- never scored as a
win or a loss (see `NON_RESOLVING_STATUSES`).
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple

import pandas as pd
from sqlalchemy.orm import Session

from src.ai_evolution.config import get_outcome_evaluation_stale_grace_days, get_decision_v2_outcome_default_horizon_days
from src.analysis.decision_v2.types import Decision
from src.analysis.ohlcv_loader import load_price_bars
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, Stock, Timeframe

_ACTIONABLE_BUY_DECISIONS = {Decision.STRONG_BUY_CANDIDATE.value, Decision.BUY_CANDIDATE.value}


def _as_utc(value: datetime) -> datetime:
    """SQLite (every unit test in this codebase) does not round-trip a
    timezone-aware `DateTime` faithfully -- matches the identical
    helper in outcome_evaluation.py, for the identical reason."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def is_actionable_buy_decision(decision_value: str) -> bool:
    return decision_value in _ACTIONABLE_BUY_DECISIONS


def create_pending_decision_v2_outcome(
    session: Session, snapshot: DecisionV2Snapshot, validation_session_id: Optional[int] = None
) -> Optional[DecisionV2Outcome]:
    """Idempotent (unique constraint on decision_v2_snapshot_id): a
    second call for the same snapshot is a no-op. Returns None (no row
    created) for a non-actionable decision -- there is nothing to
    track."""
    if not is_actionable_buy_decision(snapshot.decision):
        return None
    if snapshot.id is None:
        session.flush()

    existing = (
        session.query(DecisionV2Outcome.id).filter_by(decision_v2_snapshot_id=snapshot.id).first()
    )
    if existing is not None:
        return None

    horizon_days = snapshot.expected_holding_period_max_days or get_decision_v2_outcome_default_horizon_days()
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id,
        validation_session_id=validation_session_id,
        symbol=snapshot.symbol,
        due_at=snapshot.decision_timestamp + timedelta(days=horizon_days),
        status=DecisionV2OutcomeStatus.PENDING,
        entry_price=snapshot.current_price,
    )
    session.add(outcome)
    return outcome


def _first_touch(
    is_bullish: bool, price_level: Optional[float], direction: str, horizon_df: pd.DataFrame,
) -> Tuple[Optional[bool], Optional[datetime]]:
    """`direction` is "target" (favorable touch: price rises to/through
    a bullish target) or "stop" (adverse touch: price falls to/through
    a bullish stop) -- mirrors src.ai_evolution.outcome_evaluation's
    `_first_target_touch` convention exactly (intraday high/low touch,
    not just a close), reimplemented locally rather than imported for
    the same reason that module already documents: this is the same
    ~10-line logic applied to a continuously-growing window instead of
    a fixed horizon, not a divergent rule. Basirah is long-only (every
    actionable decision here is bullish), so only the bullish case is
    implemented; `is_bullish=False` is accepted for forward-compat but
    never currently reached."""
    if price_level is None or horizon_df is None or horizon_df.empty:
        return None, None
    if direction == "target":
        touched = horizon_df["high"] >= price_level if is_bullish else horizon_df["low"] <= price_level
    else:
        touched = horizon_df["low"] <= price_level if is_bullish else horizon_df["high"] >= price_level
    touched_at = horizon_df.index[touched]
    if len(touched_at) == 0:
        return False, None
    return True, _as_utc(pd.Timestamp(touched_at[0]).to_pydatetime())


def _max_favorable_adverse_excursion(
    is_bullish: bool, entry_price: Optional[float], horizon_df: pd.DataFrame,
) -> Tuple[Optional[float], Optional[float]]:
    """Identical convention to outcome_evaluation.py's helper of the
    same name."""
    if entry_price is None or entry_price <= 0 or horizon_df is None or horizon_df.empty:
        return None, None
    if is_bullish:
        best = (horizon_df["high"] - entry_price) / entry_price * 100.0
        worst = (horizon_df["low"] - entry_price) / entry_price * 100.0
    else:
        best = (entry_price - horizon_df["low"]) / entry_price * 100.0
        worst = (entry_price - horizon_df["high"]) / entry_price * 100.0
    return max(float(best.max()), 0.0), min(float(worst.min()), 0.0)


def _price_on_or_before(horizon_df: pd.DataFrame, cutoff: datetime) -> Optional[float]:
    cutoff = _as_utc(cutoff)
    eligible = horizon_df[horizon_df.index.map(lambda ts: _as_utc(pd.Timestamp(ts).to_pydatetime()) <= cutoff)]
    if eligible.empty:
        return None
    return float(eligible["close"].iloc[-1])


@dataclass(frozen=True)
class DecisionV2OutcomeEvaluationSummary:
    evaluated_terminal: int
    still_pending: int
    data_unavailable: int
    cancelled: int


def evaluate_pending_outcomes(
    session: Session, now: Optional[datetime] = None, batch_limit: int = 500
) -> DecisionV2OutcomeEvaluationSummary:
    now = now or datetime.now(timezone.utc)
    stale_cutoff_days = get_outcome_evaluation_stale_grace_days()

    pending_rows = (
        session.query(DecisionV2Outcome)
        .filter(DecisionV2Outcome.status == DecisionV2OutcomeStatus.PENDING)
        .order_by(DecisionV2Outcome.due_at.asc())
        .limit(batch_limit)
        .all()
    )

    evaluated_terminal = 0
    still_pending = 0
    data_unavailable = 0
    cancelled = 0

    for row in pending_rows:
        snapshot = session.query(DecisionV2Snapshot).filter_by(id=row.decision_v2_snapshot_id).one_or_none()
        if snapshot is None:
            row.status = DecisionV2OutcomeStatus.CANCELLED
            row.evaluated_at = now
            cancelled += 1
            continue

        stock = session.query(Stock).filter_by(id=snapshot.stock_id).one_or_none()
        if stock is None:
            row.status = DecisionV2OutcomeStatus.CANCELLED
            row.evaluated_at = now
            cancelled += 1
            continue

        decision_timestamp = _as_utc(snapshot.decision_timestamp)
        window_start = decision_timestamp + timedelta(seconds=1)
        horizon_df = load_price_bars(session, stock.id, Timeframe.ONE_DAY, start=window_start, end=now)
        row.last_checked_at = now

        if horizon_df.empty:
            if (now - decision_timestamp).days > stale_cutoff_days:
                row.status = DecisionV2OutcomeStatus.DATA_UNAVAILABLE
                row.evaluated_at = now
                data_unavailable += 1
            else:
                still_pending += 1
            continue

        entry_price = float(snapshot.current_price) if snapshot.current_price is not None else None
        is_bullish = True  # every actionable decision this table tracks is BUY-like (see _ACTIONABLE_BUY_DECISIONS)

        target_1 = float(snapshot.target_1) if snapshot.target_1 is not None else None
        target_2 = float(snapshot.target_2) if snapshot.target_2 is not None else None
        target_3 = float(snapshot.target_3) if snapshot.target_3 is not None else None
        stop_loss = float(snapshot.stop_loss) if snapshot.stop_loss is not None else None

        target_1_hit, target_1_at = _first_touch(is_bullish, target_1, "target", horizon_df)
        target_2_hit, target_2_at = _first_touch(is_bullish, target_2, "target", horizon_df)
        target_3_hit, target_3_at = _first_touch(is_bullish, target_3, "target", horizon_df)
        stop_hit, stop_at = _first_touch(is_bullish, stop_loss, "stop", horizon_df)
        mfe, mae = _max_favorable_adverse_excursion(is_bullish, entry_price, horizon_df)

        row.target_1_hit, row.target_1_hit_at = target_1_hit, target_1_at
        row.target_2_hit, row.target_2_hit_at = target_2_hit, target_2_at
        row.target_3_hit, row.target_3_hit_at = target_3_hit, target_3_at
        row.stop_loss_hit, row.stop_loss_hit_at = stop_hit, stop_at
        row.max_favorable_excursion_pct = mfe
        row.max_adverse_excursion_pct = mae

        if row.first_price_after_signal is None:
            row.first_price_after_signal = float(horizon_df["close"].iloc[0])
            row.first_price_after_signal_at = _as_utc(pd.Timestamp(horizon_df.index[0]).to_pydatetime())
        # "End of session" = the decision's own trading day close if it
        # exists yet, else the first forward close available -- never
        # a later re-evaluation's price mistaken for that day's own.
        if row.end_of_session_price is None:
            row.end_of_session_price = row.first_price_after_signal
        if row.next_session_price is None and len(horizon_df) >= 2:
            row.next_session_price = float(horizon_df["close"].iloc[1])
        if row.price_at_expected_duration is None:
            price_at_due = _price_on_or_before(horizon_df, row.due_at)
            if price_at_due is not None:
                row.price_at_expected_duration = price_at_due
                row.return_pct_at_expected_duration = (
                    (price_at_due - entry_price) / entry_price * 100.0
                    if entry_price is not None and entry_price > 0
                    else None
                )

        touches = [
            (1, target_1_at, target_1),
            (2, target_2_at, target_2),
            (3, target_3_at, target_3),
        ]
        earliest_target = min((t for t in touches if t[1] is not None), key=lambda t: t[1], default=None)

        terminal_status = None
        terminal_price = None
        if earliest_target is not None and stop_at is not None:
            if earliest_target[1] < stop_at:
                terminal_status = {1: DecisionV2OutcomeStatus.TARGET_1_HIT, 2: DecisionV2OutcomeStatus.TARGET_2_HIT, 3: DecisionV2OutcomeStatus.TARGET_3_HIT}[earliest_target[0]]
                terminal_price = earliest_target[2]
                row.first_event = "TARGET"
            elif stop_at < earliest_target[1]:
                terminal_status = DecisionV2OutcomeStatus.STOP_LOSS_HIT
                terminal_price = stop_loss
                row.first_event = "STOP"
            else:
                # Same bar -- genuinely undecidable with only daily OHLC.
                terminal_status = DecisionV2OutcomeStatus.PARTIAL
                row.first_event = "TIE"
        elif earliest_target is not None:
            terminal_status = {1: DecisionV2OutcomeStatus.TARGET_1_HIT, 2: DecisionV2OutcomeStatus.TARGET_2_HIT, 3: DecisionV2OutcomeStatus.TARGET_3_HIT}[earliest_target[0]]
            terminal_price = earliest_target[2]
            row.first_event = "TARGET"
        elif stop_at is not None:
            terminal_status = DecisionV2OutcomeStatus.STOP_LOSS_HIT
            terminal_price = stop_loss
            row.first_event = "STOP"

        if terminal_status is not None:
            row.status = terminal_status
            row.evaluated_at = now
            if entry_price is not None and entry_price > 0 and terminal_price is not None:
                row.return_pct = (terminal_price - entry_price) / entry_price * 100.0
            if target_1_at is not None or target_2_at is not None or target_3_at is not None:
                reached = [t for t in (target_1_at, target_2_at, target_3_at) if t is not None]
                row.time_to_target_days = (min(reached) - decision_timestamp).days
            if stop_at is not None:
                row.time_to_stop_days = (stop_at - decision_timestamp).days
            evaluated_terminal += 1
        elif now >= _as_utc(row.due_at):
            row.status = DecisionV2OutcomeStatus.EXPIRED
            row.evaluated_at = now
            last_close = float(horizon_df["close"].iloc[-1])
            if entry_price is not None and entry_price > 0:
                row.return_pct = (last_close - entry_price) / entry_price * 100.0
            evaluated_terminal += 1
        else:
            still_pending += 1

    session.commit()
    return DecisionV2OutcomeEvaluationSummary(
        evaluated_terminal=evaluated_terminal,
        still_pending=still_pending,
        data_unavailable=data_unavailable,
        cancelled=cancelled,
    )
