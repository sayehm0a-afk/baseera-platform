"""The 15 mandatory publication gates from the Phase 1 brief, applied
uniformly to every single-stock decision -- not only to the market-wide
scanner, which is what `src.market_intelligence.publication_gate`
already does today. Several gates below reuse that module's exact
threshold getters (`get_min_risk_reward_ratio`, `get_min_average_traded_value`,
`get_max_data_age_hours`) so a Saudi-market liquidity/freshness/reward
policy is configured in exactly one place, not two.

This module computes no new evidence -- every field on `GateInputs` is
something `engine.py` already collected from AIDecisionEngine/
TechnicalAnalysisResult/market-status/scoring.py. Its only job is to
turn that evidence into (a) a list of transparent PASS/FAIL/NOT_EVALUATED
records and (b) the one `Decision` value the evidence actually supports.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.analysis.decision.types import EntryQuality
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.types import Decision, GateOutcome
from src.analysis.recommendation.types import Recommendation

_BUY_LIKE = {Recommendation.BUY, Recommendation.STRONG_BUY}
_SELL_LIKE = {Recommendation.SELL, Recommendation.STRONG_SELL}


@dataclass(frozen=True)
class GateInputs:
    has_technical: bool
    recommendation: Optional[Recommendation]
    direction: int  # +1 long / -1 sell-side / 0 hold

    is_synthetic: Optional[bool]
    data_age_hours: Optional[float]
    max_age_hours: float

    price: Optional[float]
    entry_zone_low: Optional[float]
    entry_zone_high: Optional[float]
    stop_loss: Optional[float]
    target_1: Optional[float]

    risk_reward_ratio: Optional[float]
    min_risk_reward_ratio: float

    average_traded_value: Optional[float]
    min_average_traded_value: float

    atr_pct: Optional[float]
    excessive_volatility_pct: float

    market_status_known: bool

    available_sub_score_count: int
    fundamentals_available: bool
    news_available: bool

    entry_quality: EntryQuality
    price_missed_entry_zone: bool


@dataclass
class GateEvaluation:
    decision: Decision
    gates: List[GateOutcome] = field(default_factory=list)
    warnings: List[str] = field(default_factory=list)
    disclosures: List[str] = field(default_factory=list)


def evaluate_decision(inputs: GateInputs, tuning: DecisionV2Tuning) -> GateEvaluation:
    gates: List[GateOutcome] = []
    warnings: List[str] = []
    disclosures: List[str] = []

    # Gate 1a: data authenticity ------------------------------------------------
    if inputs.is_synthetic is True:
        gates.append(GateOutcome("real_data_source", False, "بيانات تجريبية غير حقيقية -- لا يمكن نشر توصية.", True))
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)
    gates.append(GateOutcome(
        "real_data_source", True,
        "مصدر بيانات حقيقي (SAHMK)" if inputs.is_synthetic is False else "مصدر البيانات غير مؤكد لهذا التحليل",
        False,
    ))

    # Data availability -----------------------------------------------------
    if not inputs.has_technical or inputs.recommendation is None:
        gates.append(GateOutcome("data_availability", False, "لا تتوفر بيانات فنية كافية لهذا السهم.", True))
        return GateEvaluation(Decision.INSUFFICIENT_DATA, gates, warnings, disclosures)
    gates.append(GateOutcome("data_availability", True, "تتوفر بيانات فنية كافية.", True))

    # Gate 2: current price valid and positive --------------------------------
    price_ok = inputs.price is not None and inputs.price > 0
    gates.append(GateOutcome("price_validity", price_ok, "السعر الحالي صالح." if price_ok else "لا يتوفر سعر حالي صالح.", True))
    if not price_ok:
        return GateEvaluation(Decision.INSUFFICIENT_DATA, gates, warnings, disclosures)

    # Gate 1b: freshness (the DataFreshnessStatus classification itself
    # -- LIVE/LAST_SESSION/STALE/UNKNOWN -- is computed once in
    # engine.py, which also knows market_is_open; this gate only needs
    # the pass/fail boolean). ---------------------------------------
    is_stale = inputs.data_age_hours is not None and inputs.data_age_hours > inputs.max_age_hours
    gates.append(GateOutcome(
        "data_freshness", not is_stale,
        f"عمر البيانات {inputs.data_age_hours:.1f} ساعة" if inputs.data_age_hours is not None else "عمر البيانات غير معروف",
        False,
    ))
    if is_stale:
        warnings.append("البيانات المستخدمة أقدم من الحد المسموح -- التحليل معروض للاطلاع فقط وليس للتنفيذ الفوري.")

    # Gate 11: market status known --------------------------------------------
    gates.append(GateOutcome("market_status_known", inputs.market_status_known, "حالة السوق معروفة." if inputs.market_status_known else "حالة السوق غير مؤكدة.", False))
    if not inputs.market_status_known:
        warnings.append("حالة السوق (مفتوح/مغلق) غير مؤكدة حاليًا.")

    # Gate 13: fundamentals/news disclosure (never blocking) -------------------
    if not inputs.fundamentals_available:
        disclosures.append("لا تتوفر بيانات أساسية (مالية) حقيقية لهذا السهم حاليًا -- هذا التحليل فني بالدرجة الأولى.")
    if not inputs.news_available:
        disclosures.append("لا تتوفر بيانات إخبارية محللة لهذا السهم حاليًا.")

    # Gate 14: duplicate suppression -- not implemented at single-stock
    # level; deduplication exists at the market-scan layer (ChangeDetector).
    gates.append(GateOutcome("duplicate_suppression", True, "غير مطبّق على مستوى تحليل السهم الفردي (متاح على مستوى المسح الشامل).", False))

    # Non-actionable base recommendations map directly, but a stale/
    # missing-data condition can never let SELL-side urgency (EXIT) be
    # presented as more certain than the data actually supports either
    # -- still downgraded to HOLD's neighbor caution via a warning, not
    # a decision change, since exiting a position is a defensive action
    # a user should not be discouraged from on stale data.
    if inputs.recommendation is Recommendation.HOLD:
        return GateEvaluation(Decision.HOLD, gates, warnings, disclosures)
    if inputs.recommendation is Recommendation.STRONG_SELL:
        return GateEvaluation(Decision.EXIT, gates, warnings, disclosures)
    if inputs.recommendation is Recommendation.SELL:
        return GateEvaluation(Decision.REDUCE, gates, warnings, disclosures)

    # From here on: recommendation is BUY-like (BUY/STRONG_BUY) -----------------
    if is_stale:
        warnings.append("لا يمكن اعتبار هذا فرصة شراء فعلية أثناء عدم توفر بيانات حديثة -- تم تصنيفه للمراقبة فقط.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)

    # Gate 3: entry zone valid ------------------------------------------------
    entry_zone_ok = (
        inputs.entry_zone_low is not None and inputs.entry_zone_high is not None
        and inputs.entry_zone_low <= inputs.entry_zone_high
    )
    gates.append(GateOutcome("entry_zone_valid", entry_zone_ok, "نطاق الدخول متسق." if entry_zone_ok else "نطاق الدخول غير متاح أو غير متسق.", True))
    if not entry_zone_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 4: stop below entry zone (long) -------------------------------------
    stop_ok = inputs.stop_loss is not None and inputs.stop_loss < inputs.entry_zone_low
    gates.append(GateOutcome("stop_below_entry", stop_ok, "وقف الخسارة أسفل نطاق الدخول." if stop_ok else "وقف الخسارة غير منطقي بالنسبة لنطاق الدخول.", True))
    if not stop_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 5: target above entry zone ------------------------------------------
    target_ok = inputs.target_1 is not None and inputs.target_1 > inputs.entry_zone_high
    gates.append(GateOutcome("target_above_entry", target_ok, "الهدف أعلى نطاق الدخول." if target_ok else "الهدف غير منطقي بالنسبة لنطاق الدخول.", True))
    if not target_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 15: price already ran past the entry zone --------------------------
    if inputs.price_missed_entry_zone:
        gates.append(GateOutcome("entry_not_missed", False, "السعر تجاوز نطاق الدخول المحدد بالفعل.", True))
        warnings.append("السعر الحالي أعلى من نطاق الدخول المناسب -- يفضّل الانتظار بدل مطاردة السعر.")
        return GateEvaluation(Decision.WAIT_FOR_ENTRY, gates, warnings, disclosures)
    gates.append(GateOutcome("entry_not_missed", True, "السعر لا يزال ضمن نطاق دخول معقول.", True))

    # Gate 6: risk/reward minimum -----------------------------------------------
    rr_ok = inputs.risk_reward_ratio is not None and inputs.risk_reward_ratio >= inputs.min_risk_reward_ratio
    gates.append(GateOutcome(
        "risk_reward_minimum", rr_ok,
        f"العائد إلى المخاطرة {inputs.risk_reward_ratio:.2f}" if inputs.risk_reward_ratio is not None else "تعذر حساب العائد إلى المخاطرة",
        True,
    ))
    if not rr_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 8: liquidity (NOT_EVALUATED, not blocking, when unknown) -----------
    if inputs.average_traded_value is None:
        gates.append(GateOutcome("liquidity", True, "متوسط قيمة التداول غير متاح.", False))
    else:
        liquidity_ok = inputs.average_traded_value >= inputs.min_average_traded_value
        gates.append(GateOutcome(
            "liquidity", liquidity_ok,
            f"متوسط قيمة التداول اليومي ~{inputs.average_traded_value:,.0f} ريال", True,
        ))
        if not liquidity_ok:
            return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 9: no excessive volatility/gap risk ----------------------------------
    if inputs.atr_pct is not None and inputs.atr_pct > inputs.excessive_volatility_pct:
        gates.append(GateOutcome("volatility_acceptable", False, f"تقلب مرتفع جدًا (ATR% = {inputs.atr_pct * 100:.1f}%).", True))
        warnings.append("تقلب السهم مرتفع بشكل غير معتاد حاليًا -- خطر فجوات سعرية حقيقي.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
    gates.append(GateOutcome("volatility_acceptable", True, "مستوى التقلب مقبول.", False))

    # Gate 12: confidence not based on a single indicator -----------------------
    multi_factor_ok = inputs.available_sub_score_count >= 3
    gates.append(GateOutcome(
        "multi_factor_evidence", multi_factor_ok,
        f"{inputs.available_sub_score_count} من أصل 8 عناصر تحليل متاحة.", True,
    ))
    if not multi_factor_ok:
        warnings.append("عدد الأدلة المتاحة محدود -- التوصية أقل اكتمالًا من المعتاد.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)

    # Entry quality: a poor entry downgrades to WATCH rather than REJECT
    # (matches publication_gate.py's identical reasoning: the thesis
    # can still be sound even when *this specific price* is a bad entry).
    entry_quality_ok = inputs.entry_quality is not EntryQuality.POOR
    gates.append(GateOutcome("entry_quality", entry_quality_ok, f"جودة نقطة الدخول: {inputs.entry_quality.value}", True))
    if not entry_quality_ok:
        warnings.append("جودة نقطة الدخول الحالية ضعيفة -- يفضّل الانتظار.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)

    strong = inputs.recommendation is Recommendation.STRONG_BUY
    return GateEvaluation(
        Decision.STRONG_BUY_CANDIDATE if strong else Decision.BUY_CANDIDATE,
        gates, warnings, disclosures,
    )
