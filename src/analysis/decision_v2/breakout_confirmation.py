"""Phase 3 area 5: real breakout/false-breakout confirmation layer.

Fills the long-deferred gap `trade_classification.py` and
`EntryStatus.CONDITIONAL_ON_BREAKOUT`'s own docstrings both name
explicitly: "requires a real breakout-pattern detector," previously
not implemented. This module is that detector -- built entirely from
data already ingested (daily OHLCV closes/volume plus the existing
`support_resistance` swing-pivot indicator), computing zero new
indicators.

This platform ingests daily bars only (no intraday time-series), so
"breakout confirmation" here is judged strictly on daily closes, never
on an intraday wick above a level -- a single high-of-day poke above
resistance that closes back below it is not treated as a breakout at
all, by construction, because only the close is ever compared to the
level.

Five real evidence checks, all computed directly from ingested daily
bars:
  A. Level cleared    -- the latest close is past `breakout_level`.
  B. Close-based hold -- how many consecutive most-recent daily closes
     have stayed past the level (capped at `lookback_days`).
  C. Retest/failure   -- did price close back on the wrong side of the
     level at any point after first clearing it, within the lookback
     window? One such close is a confirmed false breakout, not "still
     developing" -- this check runs before, and can override, every
     other check below.
  D. Volume confirmation -- was the latest bar's volume elevated
     versus its already-computed 20-day average (`volume_sma_20`)?
  E. Follow-through distance -- how far past the level the latest
     close has extended, as a percentage of the level itself. A
     0.05%-above-resistance close is statistically indistinguishable
     from "sitting at resistance," so a thin, single/two-day clear
     with no real distance is not scored as a genuine early breakout.

`BreakoutStatus` is a read of what already happened in real bars, not
a prediction of what will happen next: `CONFIRMED_BREAKOUT` means
"this stock already broke out and has held," never "this stock will
break out."
"""

from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING, Optional

import pandas as pd

if TYPE_CHECKING:
    from src.analysis.types import SupportResistanceLevels

LOOKBACK_DAYS = 10
MIN_BARS_FOR_SEQUENCE = 3
_MIN_HOLD_DAYS_FOR_CONFIRMED = 3
_VOLUME_CONFIRMATION_RATIO = 1.3
_MIN_FOLLOW_THROUGH_PCT = 0.3


class BreakoutStatus(str, Enum):
    NOT_APPLICABLE = "NOT_APPLICABLE"
    SEQUENCE_UNVERIFIED = "SEQUENCE_UNVERIFIED"
    CONFIRMED_BREAKOUT = "CONFIRMED_BREAKOUT"
    EARLY_BREAKOUT = "EARLY_BREAKOUT"
    UNCONFIRMED_BREAKOUT = "UNCONFIRMED_BREAKOUT"
    FAILED_BREAKOUT = "FAILED_BREAKOUT"


@dataclass(frozen=True)
class BreakoutConfirmation:
    status: BreakoutStatus
    level: Optional[float]
    hold_days: Optional[int]
    volume_confirmed: Optional[bool]
    follow_through_pct: Optional[float]
    explanation_ar: str


_NOT_APPLICABLE = BreakoutConfirmation(
    status=BreakoutStatus.NOT_APPLICABLE,
    level=None,
    hold_days=None,
    volume_confirmed=None,
    follow_through_pct=None,
    explanation_ar="",
)


def resolve_breakout_reference_level(
    df: pd.DataFrame,
    levels: Optional["SupportResistanceLevels"],
    lookback_days: int = LOOKBACK_DAYS,
) -> Optional[float]:
    """The resistance level a breakout is judged against -- selected
    using the close price from BEFORE the lookback window this module
    evaluates, never the current/latest close.

    Structural repair: `evidence.derive_support_resistance()`'s own
    `breakout_level` field (nearest resistance to the CURRENT price)
    exists for a legitimate, different purpose -- "what level would a
    NEW breakout need to clear from here," a live display field.
    Feeding that same value into `compute_breakout_confirmation` (the
    original design, before this fix) made its own `latest_close <=
    breakout_level` guard tautological: a level the price has already
    broken is, by definition, no longer >= the current price, so it
    would silently be swapped for the next, still-untested level
    further up -- which can never have been broken. No amount of
    historical data fixes that; the level being tested has to be
    fixed independently of the very price action it is meant to
    judge.

    Anchoring the reference instead to the close price at the START of
    the lookback window lets a real, already-in-progress breakout stay
    testable against the same level for the whole window it is judged
    over. `None` when there isn't yet enough history to distinguish
    "prior structure" from the lookback window itself -- the same
    conservative "not enough data to judge" default this module
    already returns as SEQUENCE_UNVERIFIED for a related reason."""
    if levels is None or not levels.resistance:
        return None
    if df is None or df.empty or "close" not in df.columns:
        return None
    closes = df["close"]
    prior_index = len(closes) - lookback_days - 1
    if prior_index < 0:
        return None
    prior_price = float(closes.iloc[prior_index])
    candidates = sorted(r for r in levels.resistance if r >= prior_price)
    return candidates[0] if candidates else None


def compute_breakout_confirmation(
    df: pd.DataFrame,
    breakout_level: Optional[float],
    volume_sma_20: Optional[pd.Series],
    lookback_days: int = LOOKBACK_DAYS,
) -> BreakoutConfirmation:
    """`breakout_level` is `evidence.derive_support_resistance()`'s own
    `breakout_level` (the nearest overhead resistance) -- this function
    computes no support/resistance levels of its own, only whether
    price has genuinely cleared and held the level it's given.
    `volume_sma_20` is the already-registered `volume_sma_20` indicator
    series (same one `engine.py` already reads), not recomputed here.
    """
    if breakout_level is None or breakout_level <= 0:
        # No overhead resistance was even detected -- there is no
        # breakout thesis in play for this symbol at all.
        return _NOT_APPLICABLE
    if df is None or df.empty or "close" not in df.columns:
        return _NOT_APPLICABLE

    closes = df["close"]
    latest_close = float(closes.iloc[-1])

    if latest_close <= breakout_level:
        # The level hasn't been cleared yet -- nothing to confirm or
        # fail; this is a pre-breakout state, not a broken breakout.
        return _NOT_APPLICABLE

    if len(closes) < MIN_BARS_FOR_SEQUENCE:
        return BreakoutConfirmation(
            status=BreakoutStatus.SEQUENCE_UNVERIFIED,
            level=breakout_level,
            hold_days=None,
            volume_confirmed=None,
            follow_through_pct=None,
            explanation_ar="السعر تجاوز المستوى، لكن لا تتوفر بيانات تاريخية كافية للتحقق من تسلسل الاختراق.",
        )

    window = closes.tail(min(lookback_days, len(closes))).tolist()

    # C. Retest/failure -- walk the window in chronological order; any
    # close back at/below the level after an earlier close above it is
    # a confirmed false breakout. Checked first because it overrides
    # every other read below.
    cleared_once = False
    reverted_after_clearing = False
    for value in window:
        if value > breakout_level:
            cleared_once = True
        elif cleared_once:
            reverted_after_clearing = True
    if reverted_after_clearing:
        return BreakoutConfirmation(
            status=BreakoutStatus.FAILED_BREAKOUT,
            level=breakout_level,
            hold_days=None,
            volume_confirmed=None,
            follow_through_pct=None,
            explanation_ar="تم اختراق المستوى مؤقتًا ثم عاد السعر للإغلاق دونه -- اختراق كاذب غير مؤكد.",
        )

    # B. Close-based hold -- consecutive most-recent closes above the
    # level (the latest close is already confirmed > breakout_level
    # above, so this is always >= 1).
    hold_days = 0
    for value in reversed(window):
        if value <= breakout_level:
            break
        hold_days += 1

    # D. Volume confirmation -- latest bar's volume vs. its own 20-day
    # average, when both are available.
    volume_confirmed: Optional[bool] = None
    if volume_sma_20 is not None and len(volume_sma_20) > 0 and "volume" in df.columns:
        latest_avg_volume = volume_sma_20.iloc[-1]
        if latest_avg_volume is not None and not pd.isna(latest_avg_volume) and latest_avg_volume > 0:
            latest_volume = float(df["volume"].iloc[-1])
            volume_confirmed = (latest_volume / float(latest_avg_volume)) >= _VOLUME_CONFIRMATION_RATIO

    # E. Follow-through distance.
    follow_through_pct = round((latest_close - breakout_level) / breakout_level * 100.0, 2)

    if hold_days >= _MIN_HOLD_DAYS_FOR_CONFIRMED:
        if volume_confirmed is False:
            return BreakoutConfirmation(
                status=BreakoutStatus.UNCONFIRMED_BREAKOUT,
                level=breakout_level, hold_days=hold_days,
                volume_confirmed=volume_confirmed, follow_through_pct=follow_through_pct,
                explanation_ar=f"السعر صامد فوق المستوى منذ {hold_days} جلسات، لكن دون تأكيد من حجم التداول.",
            )
        return BreakoutConfirmation(
            status=BreakoutStatus.CONFIRMED_BREAKOUT,
            level=breakout_level, hold_days=hold_days,
            volume_confirmed=volume_confirmed, follow_through_pct=follow_through_pct,
            explanation_ar=f"اختراق مؤكد -- أغلق السعر فوق المستوى لمدة {hold_days} جلسات متتالية.",
        )

    if follow_through_pct < _MIN_FOLLOW_THROUGH_PCT:
        return BreakoutConfirmation(
            status=BreakoutStatus.UNCONFIRMED_BREAKOUT,
            level=breakout_level, hold_days=hold_days,
            volume_confirmed=volume_confirmed, follow_through_pct=follow_through_pct,
            explanation_ar="تجاوز السعر المستوى بفارق ضئيل جدًا -- غير كافٍ بعد لاعتباره اختراقًا حقيقيًا.",
        )

    return BreakoutConfirmation(
        status=BreakoutStatus.EARLY_BREAKOUT,
        level=breakout_level, hold_days=hold_days,
        volume_confirmed=volume_confirmed, follow_through_pct=follow_through_pct,
        explanation_ar=f"اختراق مبكر -- أغلق السعر فوق المستوى منذ {hold_days} جلسة/جلسات فقط، ولم يتأكد الصمود بعد.",
    )
