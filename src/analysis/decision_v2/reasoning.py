"""Phase 2A section K: the eight Arabic reasoning fields, built as
deterministic sentence templates over evidence `engine.py` already
computed (the decision, its gates, its warnings, support/resistance,
entry status) -- never free-form LLM text and never a sentence that
doesn't trace to a real field on `DecisionResult`. Matches the existing
`recommendation_basis` string's own style (see engine.py), just split
into the eight named questions the Product Owner spec asks for instead
of one paragraph.

Section C's "confidence breakdown" is also handled here in one place:
it is a direct alias of five of the eight already-computed sub-scores
(see `confidence_breakdown`), not a second scoring system -- computing
it in this module keeps engine.py's own body from having to name each
alias inline.
"""

from typing import List, Optional, Tuple

from src.analysis.decision_v2.types import Decision, EntryStatus, GateOutcome

_MAX_LIST_ITEMS = 4


def confidence_breakdown(sub: dict) -> Tuple[
    Optional[float], Optional[float], Optional[float], Optional[float], Optional[float]
]:
    """Returns (technical, momentum, liquidity, market_context,
    data_quality) confidence, aliasing `trend_score` as "technical
    confidence" -- the closest existing sub-score to what a trader
    means by "how solid is the technical picture," distinct from
    `momentum_score` itself."""
    return (
        sub.get("trend_score"),
        sub.get("momentum_score"),
        sub.get("liquidity_score"),
        sub.get("market_context_score"),
        sub.get("data_quality_score"),
    )


def build_decision_summary(
    decision_label_ar: str, confidence_score: float, trade_type_label_ar: str
) -> str:
    return f"{decision_label_ar} -- بثقة {confidence_score:.0f}٪، مصنّف كـ«{trade_type_label_ar}»."


def build_why_now(
    decision: Decision, positive_reasons: List[str], entry_status_label_ar: str
) -> str:
    if decision in (Decision.STRONG_BUY_CANDIDATE, Decision.BUY_CANDIDATE):
        lead = positive_reasons[0] if positive_reasons else "توافق عدة عناصر فنية إيجابية"
        return f"{lead}، وحالة الدخول الحالية: {entry_status_label_ar}."
    if decision is Decision.WAIT_FOR_ENTRY:
        return f"الفرضية الفنية إيجابية لكن حالة الدخول الحالية: {entry_status_label_ar}."
    if decision is Decision.WATCH:
        return "السهم يستحق المتابعة لكن الأدلة الحالية غير كافية لاتخاذ قرار دخول."
    if decision is Decision.HOLD:
        return "لا توجد أدلة كافية لتغيير الوضع الحالي -- الاحتفاظ هو الأنسب."
    if decision in (Decision.REDUCE, Decision.EXIT):
        return "تراجعت الأدلة الداعمة للاستمرار في المركز الحالي."
    if decision is Decision.REJECT:
        return "لم تجتز الفرصة الحد الأدنى من معايير النشر الآمنة."
    return "البيانات المتاحة غير كافية لإصدار قرار حاليًا."


def build_why_not_stronger(decision: Decision, gates: List[GateOutcome], warnings: List[str]) -> str:
    if decision is Decision.STRONG_BUY_CANDIDATE:
        return "استوفت الفرصة أعلى مستوى من معايير النشر الحالية."
    failed_blocking = [g for g in gates if g.blocking and not g.passed]
    if failed_blocking:
        reasons = "، ".join(g.detail for g in failed_blocking[:_MAX_LIST_ITEMS])
        return f"لم يتحقق قرار أقوى بسبب: {reasons}."
    if warnings:
        return f"لم يتحقق قرار أقوى بسبب: {warnings[0]}"
    if decision in (Decision.BUY_CANDIDATE, Decision.WAIT_FOR_ENTRY, Decision.WATCH):
        return "الأدلة إيجابية لكنها لم تبلغ بعد مستوى «شراء قوي» وفق المعايير الصارمة المعتمدة."
    return "غير قابل للتطبيق لهذا التصنيف من القرار."


def build_entry_confirmation_conditions(
    decision: Decision,
    entry_status: EntryStatus,
    nearest_resistance: Optional[float],
    entry_zone_high: Optional[float],
) -> List[str]:
    if decision not in (Decision.STRONG_BUY_CANDIDATE, Decision.BUY_CANDIDATE, Decision.WAIT_FOR_ENTRY, Decision.WATCH):
        return []
    conditions: List[str] = []
    if entry_status is EntryStatus.WAIT_FOR_PULLBACK and entry_zone_high is not None:
        conditions.append(f"تراجع السعر إلى داخل نطاق الدخول (حتى {entry_zone_high:.2f}) دون كسر الدعم الأقرب.")
    if entry_status is EntryStatus.READY_NOW:
        conditions.append("استمرار تماسك السعر أعلى وقف الخسارة المحدد.")
    if nearest_resistance is not None:
        conditions.append(f"اختراق حقيقي لمستوى {nearest_resistance:.2f} مدعوم بحجم تداول أعلى من المتوسط يعزز الفرضية.")
    return conditions


def build_watch_next_session(
    nearest_support: Optional[float],
    nearest_resistance: Optional[float],
    relative_volume: Optional[float],
    warnings: List[str],
) -> List[str]:
    items: List[str] = []
    if nearest_resistance is not None:
        items.append(f"رد فعل السعر عند مستوى المقاومة القريب ({nearest_resistance:.2f}).")
    if nearest_support is not None:
        items.append(f"ثبات السعر أعلى مستوى الدعم القريب ({nearest_support:.2f}).")
    if relative_volume is not None and relative_volume < 0.7:
        items.append("حجم التداول ضعيف نسبيًا حاليًا -- يُفضّل متابعة تحسّنه.")
    items.extend(warnings[:_MAX_LIST_ITEMS - len(items)])
    return items[:_MAX_LIST_ITEMS]
