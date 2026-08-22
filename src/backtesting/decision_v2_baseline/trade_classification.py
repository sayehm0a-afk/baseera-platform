"""FROZEN pre-Phase-3 snapshot of
src/analysis/decision_v2/trade_classification.py, vendored verbatim
from commit fa2acfe for the DecisionEngineV2 historical validation
harness (src.backtesting.decision_v2_baseline). See types.py in this
same package for the full provenance note.
"""

from typing import Optional, Tuple

from src.backtesting.decision_v2_baseline.types import Decision, EntryStatus, TradeType

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
    price_missed_entry_zone: bool,
) -> Tuple[EntryStatus, str]:
    """Returns (entry_status, explanation_ar)."""
    if decision in (Decision.STRONG_BUY_CANDIDATE, Decision.BUY_CANDIDATE):
        return (
            EntryStatus.READY_NOW,
            "السعر الحالي ضمن نطاق الدخول المناسب وفق التحليل.",
        )
    if decision is Decision.WAIT_FOR_ENTRY:
        if price_missed_entry_zone:
            return (
                EntryStatus.MISSED_ENTRY,
                "تجاوز السعر نطاق الدخول المناسب بالفعل -- يفضّل الانتظار بدل مطاردة السعر.",
            )
        return (
            EntryStatus.WAIT_FOR_PULLBACK,
            "يفضّل انتظار تراجع السعر نحو نطاق دخول أنسب قبل التنفيذ.",
        )
    if decision is Decision.WATCH:
        return (
            EntryStatus.NEAR_ENTRY,
            "السهم قيد المراقبة -- شروط الدخول لم تتأكد بالكامل بعد.",
        )
    return (
        EntryStatus.NOT_SUITABLE,
        "لا يُنصح بالدخول حاليًا وفق المعطيات المتاحة.",
    )
