"""Phase 2A section D (trade duration) and section E's `entry_status`
field. Both classify already-computed evidence into a finer,
user-facing label set -- neither computes a new indicator.

Trade type: the eight labels the Product Owner spec requires. This
platform ingests daily bars only (no intraday time-series), so
`TradeType.SCALP` and `TradeType.INTRADAY` -- same-session
classifications -- have no real evidence behind them and are never
assigned here; see `classify_trade_type`'s docstring. The remaining
six honestly split `AIDecisionEngine`'s three `TimeHorizon` buckets
(SHORT_TERM/MEDIUM_TERM/LONG_TERM) using momentum/volatility -- real,
already-computed sub-scores -- as the within-bucket tie-breaker,
because each `TimeHorizon` bucket's configured day-range
(`DecisionV2Tuning`) is fixed regardless of conviction, so day-count
alone cannot distinguish e.g. a 2-day swing from a 5-day one within
the SHORT_TERM bucket.

Entry status: maps the already-decided `Decision` plus the entry-zone/
missed-entry evidence `structure.py` already computed onto the six
user-facing entry-status labels. `EntryStatus.CONDITIONAL_ON_BREAKOUT`
was never assigned before Phase 3 area 5 -- it required a real
breakout-pattern detector, which Phase 2F explicitly deferred. Now
assigned, conservatively, only for a WATCH decision where
`breakout_confirmation.py` found a real, already-in-progress breakout
that simply hasn't held/volume-confirmed long enough yet
(EARLY_BREAKOUT/UNCONFIRMED_BREAKOUT) -- never for a level that hasn't
been touched at all (NOT_APPLICABLE), a breakout that already reverted
(FAILED_BREAKOUT), one already fully confirmed (CONFIRMED_BREAKOUT --
if the decision is still only WATCH despite a confirmed breakout, the
reason is some other gate, not the breakout itself), or when there
isn't enough history to judge the sequence at all
(SEQUENCE_UNVERIFIED). This keeps the label evidence-gated: it is
never assigned from a bare "price is near resistance" guess.
"""

from typing import List, Optional, Tuple

from src.analysis.decision_v2.breakout_confirmation import BreakoutStatus
from src.analysis.decision_v2.types import DataFreshnessStatus, Decision, EntryStatus, TradeType

_CONDITIONAL_ON_BREAKOUT_STATUSES = {
    BreakoutStatus.EARLY_BREAKOUT.value,
    BreakoutStatus.UNCONFIRMED_BREAKOUT.value,
}

_HIGH_QUALITY_BUY_MIN_CONFIDENCE = 75.0
_HIGH_QUALITY_BUY_MIN_RISK_REWARD = 2.0

_MOMENTUM_INTRADAY_TO_TWO_DAYS = 70.0
_MOMENTUM_SHORT_SWING = 55.0
_VOLATILITY_SWING_TRADE = 65.0
_LONG_TERM_MEDIUM_CUTOFF_DAYS = 120


def classify_trade_type(
    horizon_type: str,
    holding_min_days: Optional[int],
    holding_max_days: Optional[int],
    momentum_score: Optional[float],
    volatility_score: Optional[float],
) -> Tuple[Optional[TradeType], str]:
    """Returns (trade_type, rationale_ar). `trade_type` is `None` (with
    a "not determinable" rationale) only when the holding-period range
    itself wasn't computable -- i.e. HOLD/no direction, matching
    `structure.compute_holding_period`'s own preconditions."""
    if holding_min_days is None or holding_max_days is None:
        return None, "لا يمكن تحديد نوع الصفقة دون اتجاه توصية واضح."

    if horizon_type == "SHORT_TERM":
        if momentum_score is not None and momentum_score >= _MOMENTUM_INTRADAY_TO_TWO_DAYS:
            return (
                TradeType.SHORT_SWING_2_5_DAYS,
                "زخم قوي جدًا يدعم حركة سعرية سريعة خلال أيام قليلة.",
            )
        if momentum_score is not None and momentum_score >= _MOMENTUM_SHORT_SWING:
            return (
                TradeType.SHORT_SWING_2_5_DAYS,
                "زخم إيجابي معتدل يدعم مضاربة قصيرة من يومين إلى خمسة أيام.",
            )
        return (
            TradeType.WEEKLY_SWING,
            "زخم غير حاسم حاليًا -- الأنسب متابعة الفرصة على مدى أسبوع تداول تقريبًا.",
        )

    if horizon_type == "MEDIUM_TERM":
        if volatility_score is not None and volatility_score >= _VOLATILITY_SWING_TRADE:
            return (
                TradeType.SWING_TRADE,
                "مستوى تذبذب يدعم حركة سعرية متكاملة على مدى عدة أسابيع (تداول متأرجح).",
            )
        return (
            TradeType.MONTHLY_INVESTMENT,
            "الأنسب أفق شهري تقريبًا لتحقق الفرضية الفنية الحالية.",
        )

    if horizon_type == "LONG_TERM":
        if holding_max_days <= _LONG_TERM_MEDIUM_CUTOFF_DAYS:
            return (
                TradeType.MEDIUM_TERM_INVESTMENT,
                "أفق استثماري متوسط المدى بناءً على المعطيات الفنية الحالية.",
            )
        return (
            TradeType.LONG_TERM_INVESTMENT,
            "أفق استثماري طويل المدى بناءً على المعطيات الفنية الحالية.",
        )

    return None, "لا يمكن تحديد نوع الصفقة."


def classify_entry_status(
    decision: Decision,
    price: Optional[float],
    entry_zone_high: Optional[float],
    price_severely_missed_entry_zone: bool,
    breakout_status: Optional[str] = None,
) -> Tuple[EntryStatus, str]:
    """Returns (entry_status, explanation_ar). `breakout_status` is
    `context.extra["breakout_confirmation"]["status"]` (see this
    module's docstring for exactly which statuses can produce
    `CONDITIONAL_ON_BREAKOUT`) -- optional, and irrelevant for any
    decision other than WATCH.

    `price_severely_missed_entry_zone` (see `structure.
    price_severely_missed_entry_zone`) is a magnitude-aware signal,
    deliberately distinct from the plain "has it missed at all"
    boolean that already decided `Decision.WAIT_FOR_ENTRY` itself
    (Gate 15) -- reusing that same plain boolean here would make it
    impossible to ever reach this branch's WAIT_FOR_PULLBACK case,
    since arriving at `decision is WAIT_FOR_ENTRY` already required it
    to be True."""
    if decision in (Decision.STRONG_BUY_CANDIDATE, Decision.BUY_CANDIDATE):
        return (
            EntryStatus.READY_NOW,
            "السعر الحالي ضمن نطاق الدخول المناسب وفق التحليل.",
        )
    if decision is Decision.WAIT_FOR_ENTRY:
        if price_severely_missed_entry_zone:
            return (
                EntryStatus.MISSED_ENTRY,
                "تجاوز السعر نطاق الدخول المناسب بفارق كبير -- الإعداد الحالي لم يعد صالحًا حتى مع تراجع محتمل.",
            )
        return (
            EntryStatus.WAIT_FOR_PULLBACK,
            "تجاوز السعر نطاق الدخول قليلاً -- يفضّل انتظار تراجع نحو نطاق دخول أنسب قبل التنفيذ.",
        )
    if decision is Decision.WATCH:
        if breakout_status in _CONDITIONAL_ON_BREAKOUT_STATUSES:
            return (
                EntryStatus.CONDITIONAL_ON_BREAKOUT,
                "السعر بدأ فعليًا باختراق مستوى مقاومة قريب، لكن الاختراق لم يتأكد بعد "
                "بالصمود أو حجم التداول -- الدخول مشروط بتأكد الاختراق.",
            )
        return (
            EntryStatus.NEAR_ENTRY,
            "السهم قيد المراقبة -- شروط الدخول لم تتأكد بالكامل بعد.",
        )
    return (
        EntryStatus.NOT_SUITABLE,
        "لا يُنصح بالدخول حاليًا وفق المعطيات المتاحة.",
    )


def classify_high_quality_buy(
    decision: Decision,
    confidence_score: float,
    data_freshness_status: DataFreshnessStatus,
    entry_status: EntryStatus,
    risk_reward_target_1: Optional[float],
    volume_confirms_decision: Optional[bool],
    sector_strength_used: bool,
    stock_vs_sector_relative_strength: Optional[float],
    breakout_status: str,
    warnings: List[str],
) -> Tuple[bool, str]:
    """Phase 3: the HIGH_QUALITY_BUY tier -- an additive tag on an
    already-issued STRONG_BUY_CANDIDATE/BUY_CANDIDATE, never a 10th
    `Decision` value and never a path that can override the gates
    above (same "one canonical decision taxonomy" rule
    `DECISION_LABELS_AR`'s own docstring already states for
    `entry_status`). Deliberately conjunctive over real, already-
    computed evidence -- every condition below reads a field this
    engine already produced, no new indicator, no fabricated score --
    so it is expected to return `False` most of the time; there is no
    threshold tuned to guarantee a nonzero rate. All of the following
    must hold:

      * the decision is already a buy candidate (STRONG_BUY_CANDIDATE
        or BUY_CANDIDATE);
      * `confidence_score` (already gate-adjusted, and already
        calibrated when Phase 3 area 2's calibration is active) clears
        a high bar;
      * the data behind the decision is genuinely LIVE, not stale or
        last-session;
      * the price is actually in the entry zone right now (READY_NOW),
        not merely a candidate pending a pullback or a breakout;
      * the risk/reward on the first target clears a real minimum;
      * real volume evidence (OBV direction) confirms the decision's
        direction, not merely absent;
      * when Phase 3 area 4's sector-relative-strength evidence is
        available, it does not contradict the decision (a stock
        underperforming its own sector peers is never tagged high
        quality) -- but its absence (insufficient peer data) does not
        by itself disqualify a candidate, since that data is not
        always available;
      * Phase 3 area 5's breakout confirmation, when a breakout thesis
        was even in play, never shows FAILED_BREAKOUT;
      * there are no active warnings at all -- any caution flag
        (thin liquidity, market caution, stale data, conflicting
        indicators, contradictory news, ...) disqualifies the tag.

    Returns (is_high_quality_buy, explanation_ar) -- the explanation is
    only ever the positive case; callers show nothing for `False`, the
    same "silence, not a fabricated negative narrative" convention
    `why_not_buy_reasons` already follows for gate rejections.
    """
    if decision not in (Decision.STRONG_BUY_CANDIDATE, Decision.BUY_CANDIDATE):
        return False, ""
    if confidence_score < _HIGH_QUALITY_BUY_MIN_CONFIDENCE:
        return False, ""
    if data_freshness_status is not DataFreshnessStatus.LIVE:
        return False, ""
    if entry_status is not EntryStatus.READY_NOW:
        return False, ""
    if risk_reward_target_1 is None or risk_reward_target_1 < _HIGH_QUALITY_BUY_MIN_RISK_REWARD:
        return False, ""
    if volume_confirms_decision is not True:
        return False, ""
    if sector_strength_used and stock_vs_sector_relative_strength is not None:
        if stock_vs_sector_relative_strength < 0:
            return False, ""
    if breakout_status == BreakoutStatus.FAILED_BREAKOUT.value:
        return False, ""
    if warnings:
        return False, ""

    return (
        True,
        "فرصة عالية الجودة: ثقة مرتفعة، بيانات حية، دخول جاهز الآن، عائد إلى مخاطرة قوي، "
        "وتأكيد حجمي حقيقي دون أي تحذيرات نشطة حاليًا.",
    )
