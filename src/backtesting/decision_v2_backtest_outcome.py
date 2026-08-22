"""Outcome evaluation for the DecisionEngineV2 historical validation
harness -- deliberately reuses, not reimplements, the exact
entry-trigger/target/stop/same-bar-ambiguity methodology
`src.ai_evolution.decision_v2_outcome_evaluation.evaluate_pending_outcomes`
already uses for live forward-testing (item 6's explicit instruction:
"Reuse or adapt the existing DecisionV2Outcome methodology where
possible"). Two of that module's own private helpers are imported
directly rather than re-derived: `_first_touch` (first-touch detection
by intraday high/low, not just a close) and `_max_favorable_adverse_
excursion` (MFE/MAE) -- both are pure functions of a price-bar
DataFrame, carry no live-polling state, and this module never mutates
a production `DecisionV2Outcome` row.

Same-bar target/stop ambiguity is resolved the same, already-real way
the live pipeline does: by comparing each event's own first-touch
*timestamp* (not a "target wins" default) -- when both timestamps are
literally identical (touched on the same bar), `DecisionV2OutcomeStatus.
PARTIAL` is used, never a guessed winner. This module never invents a
different rule.

`load_forward_price_path` (src.backtesting.data_access) is what makes
this evaluation itself as-of-safe here: it only reads bars strictly
*after* the decision's own as-of date, exactly the "forward data used
only to score a decision already made, never to make it" split that
module's own docstring documents.
"""

from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from typing import Optional

import pandas as pd
from sqlalchemy.orm import Session

from src.ai_evolution.decision_v2_outcome_evaluation import _first_touch, _max_favorable_adverse_excursion
from src.analysis.decision_v2.types import DecisionResult
from src.backtesting.data_access import load_forward_price_path
from src.domain.models import Stock
from src.domain.models.decision_v2_outcome import DecisionV2OutcomeStatus

_ACTIONABLE_BUY_DECISIONS = {"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"}


def _as_utc(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


@dataclass(frozen=True)
class DecisionV2BacktestOutcome:
    """One symbol/date/variant outcome -- the backtest-harness sibling
    of the live `DecisionV2Outcome` row, same statuses, same
    methodology, computed in one pass over an already-materialized
    forward window instead of repeated live polling."""

    status: DecisionV2OutcomeStatus
    entry_triggered: bool
    entry_triggered_at: Optional[datetime]
    entry_price: Optional[float]
    target_1_hit: Optional[bool]
    target_2_hit: Optional[bool]
    target_3_hit: Optional[bool]
    stop_loss_hit: Optional[bool]
    max_favorable_excursion_pct: Optional[float]
    max_adverse_excursion_pct: Optional[float]
    return_pct: Optional[float]
    time_to_target_days: Optional[int]
    time_to_stop_days: Optional[int]
    first_event: Optional[str]  # "TARGET" / "STOP" / "TIE" / None


_PENDING = DecisionV2BacktestOutcome(
    status=DecisionV2OutcomeStatus.PENDING, entry_triggered=False, entry_triggered_at=None, entry_price=None,
    target_1_hit=None, target_2_hit=None, target_3_hit=None, stop_loss_hit=None,
    max_favorable_excursion_pct=None, max_adverse_excursion_pct=None, return_pct=None,
    time_to_target_days=None, time_to_stop_days=None, first_event=None,
)


def evaluate_decision_v2_backtest_outcome(
    session: Session,
    stock: Stock,
    decision: DecisionResult,
    decision_date: date,
    entry_expiry_days: int,
    resolution_horizon_days: int,
) -> DecisionV2BacktestOutcome:
    """`decision_date` is the as-of evaluation date this `decision` was
    produced for -- forward bars are read starting the NEXT calendar
    day (never the decision's own bar), via `load_forward_price_path`,
    which is itself already as-of-safe by construction. `entry_expiry_
    days` bounds how long an entry zone may still be waited for before
    the setup is marked `ENTRY_NEVER_TRIGGERED`/`INVALIDATED`;
    `resolution_horizon_days` bounds the full target/stop tracking
    window (mirrors `due_at` in the live pipeline)."""
    if decision.decision.value not in _ACTIONABLE_BUY_DECISIONS:
        return _PENDING

    entry_low = decision.entry_zone_low
    entry_high = decision.entry_zone_high
    stop_loss = decision.stop_loss
    if entry_low is None or entry_high is None:
        return _PENDING

    decision_timestamp = datetime.combine(decision_date, datetime.min.time(), tzinfo=timezone.utc)
    entry_window_df = load_forward_price_path(session, stock, decision_date, entry_expiry_days)

    if entry_window_df.empty:
        return DecisionV2BacktestOutcome(
            status=DecisionV2OutcomeStatus.DATA_UNAVAILABLE, entry_triggered=False, entry_triggered_at=None,
            entry_price=None, target_1_hit=None, target_2_hit=None, target_3_hit=None, stop_loss_hit=None,
            max_favorable_excursion_pct=None, max_adverse_excursion_pct=None, return_pct=None,
            time_to_target_days=None, time_to_stop_days=None, first_event=None,
        )

    entered_mask = (entry_window_df["low"] <= entry_high) & (entry_window_df["high"] >= entry_low)
    entered_idx = entry_window_df.index[entered_mask]
    entered_at = _as_utc(pd.Timestamp(entered_idx[0]).to_pydatetime()) if len(entered_idx) > 0 else None

    if entered_at is None:
        pre_entry_stop_hit = stop_loss is not None and (entry_window_df["low"] <= stop_loss).any()
        if pre_entry_stop_hit:
            return DecisionV2BacktestOutcome(
                status=DecisionV2OutcomeStatus.INVALIDATED, entry_triggered=False, entry_triggered_at=None,
                entry_price=None, target_1_hit=None, target_2_hit=None, target_3_hit=None, stop_loss_hit=None,
                max_favorable_excursion_pct=None, max_adverse_excursion_pct=None, return_pct=None,
                time_to_target_days=None, time_to_stop_days=None, first_event=None,
            )
        return DecisionV2BacktestOutcome(
            status=DecisionV2OutcomeStatus.ENTRY_NEVER_TRIGGERED, entry_triggered=False, entry_triggered_at=None,
            entry_price=None, target_1_hit=None, target_2_hit=None, target_3_hit=None, stop_loss_hit=None,
            max_favorable_excursion_pct=None, max_adverse_excursion_pct=None, return_pct=None,
            time_to_target_days=None, time_to_stop_days=None, first_event=None,
        )

    # Same conservative, disclosed fill convention as the live pipeline:
    # the least favorable real price still inside the recommended zone.
    entry_price = entry_high

    full_horizon_df = load_forward_price_path(session, stock, decision_date, resolution_horizon_days)
    horizon_df = full_horizon_df[
        full_horizon_df.index.map(lambda ts: _as_utc(pd.Timestamp(ts).to_pydatetime()) >= entered_at)
    ]
    if horizon_df.empty:
        return DecisionV2BacktestOutcome(
            status=DecisionV2OutcomeStatus.PENDING, entry_triggered=True, entry_triggered_at=entered_at,
            entry_price=entry_price, target_1_hit=None, target_2_hit=None, target_3_hit=None, stop_loss_hit=None,
            max_favorable_excursion_pct=None, max_adverse_excursion_pct=None, return_pct=None,
            time_to_target_days=None, time_to_stop_days=None, first_event=None,
        )

    is_bullish = True  # every actionable decision this harness scores is BUY-like
    target_1_hit, target_1_at = _first_touch(is_bullish, decision.target_1, "target", horizon_df)
    target_2_hit, target_2_at = _first_touch(is_bullish, decision.target_2, "target", horizon_df)
    target_3_hit, target_3_at = _first_touch(is_bullish, decision.target_3, "target", horizon_df)
    stop_hit, stop_at = _first_touch(is_bullish, stop_loss, "stop", horizon_df)
    mfe, mae = _max_favorable_adverse_excursion(is_bullish, entry_price, horizon_df)

    touches = [(1, target_1_at, decision.target_1), (2, target_2_at, decision.target_2), (3, target_3_at, decision.target_3)]
    earliest_target = min((t for t in touches if t[1] is not None), key=lambda t: t[1], default=None)

    status: Optional[DecisionV2OutcomeStatus] = None
    terminal_price: Optional[float] = None
    first_event: Optional[str] = None
    if earliest_target is not None and stop_at is not None:
        if earliest_target[1] < stop_at:
            status = {1: DecisionV2OutcomeStatus.TARGET_1_HIT, 2: DecisionV2OutcomeStatus.TARGET_2_HIT, 3: DecisionV2OutcomeStatus.TARGET_3_HIT}[earliest_target[0]]
            terminal_price, first_event = earliest_target[2], "TARGET"
        elif stop_at < earliest_target[1]:
            status, terminal_price, first_event = DecisionV2OutcomeStatus.STOP_LOSS_HIT, stop_loss, "STOP"
        else:
            status, first_event = DecisionV2OutcomeStatus.PARTIAL, "TIE"  # same bar -- genuinely undecidable, never guessed
    elif earliest_target is not None:
        status = {1: DecisionV2OutcomeStatus.TARGET_1_HIT, 2: DecisionV2OutcomeStatus.TARGET_2_HIT, 3: DecisionV2OutcomeStatus.TARGET_3_HIT}[earliest_target[0]]
        terminal_price, first_event = earliest_target[2], "TARGET"
    elif stop_at is not None:
        status, terminal_price, first_event = DecisionV2OutcomeStatus.STOP_LOSS_HIT, stop_loss, "STOP"

    return_pct = None
    time_to_target_days = None
    time_to_stop_days = None
    if status is not None and status is not DecisionV2OutcomeStatus.PARTIAL and terminal_price is not None:
        return_pct = (terminal_price - entry_price) / entry_price * 100.0
    if target_1_at is not None or target_2_at is not None or target_3_at is not None:
        reached = [t for t in (target_1_at, target_2_at, target_3_at) if t is not None]
        time_to_target_days = (min(reached) - decision_timestamp).days
    if stop_at is not None:
        time_to_stop_days = (stop_at - decision_timestamp).days

    if status is None:
        due_at = decision_timestamp + timedelta(days=resolution_horizon_days)
        if _as_utc(pd.Timestamp(full_horizon_df.index[-1]).to_pydatetime()) >= due_at:
            status = DecisionV2OutcomeStatus.EXPIRED
            last_close = float(horizon_df["close"].iloc[-1])
            return_pct = (last_close - entry_price) / entry_price * 100.0
        else:
            status = DecisionV2OutcomeStatus.PENDING

    return DecisionV2BacktestOutcome(
        status=status, entry_triggered=True, entry_triggered_at=entered_at, entry_price=entry_price,
        target_1_hit=target_1_hit, target_2_hit=target_2_hit, target_3_hit=target_3_hit, stop_loss_hit=stop_hit,
        max_favorable_excursion_pct=mfe, max_adverse_excursion_pct=mae, return_pct=return_pct,
        time_to_target_days=time_to_target_days, time_to_stop_days=time_to_stop_days, first_event=first_event,
    )
