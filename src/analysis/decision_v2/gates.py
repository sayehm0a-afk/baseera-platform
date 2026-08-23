"""The publication gates from the Phase 1 brief (15) plus Phase 2B's
extension (5 more, to the 20-gate list: quote-timestamp, volume-quality,
trend-consistency/contradiction, market-context, confidence-calibration,
price-limit-proximity, and risk-warning-disclosure -- several of these
share one gate entry where the underlying evidence is identical, see
each gate's own comment below) plus Phase 2C's `market_risk_permits_entry`
gate (a market-wide, not per-symbol, entry-permission check -- see
`market_risk.py`), applied uniformly to every single-stock decision --
not only to the market-wide scanner, which is what
`src.market_intelligence.publication_gate` already does today. Several
gates below reuse that module's exact threshold getters
(`get_min_risk_reward_ratio`, `get_min_average_traded_value`,
`get_max_data_age_hours`) so a Saudi-market liquidity/freshness/reward
policy is configured in exactly one place, not two.

This module computes no new evidence -- every field on `GateInputs` is
something `engine.py` already collected from AIDecisionEngine/
TechnicalAnalysisResult/market-status/scoring.py. Its only job is to
turn that evidence into (a) a list of transparent PASS/FAIL/NOT_EVALUATED
records and (b) the one `Decision` value the evidence actually supports.

Two gates are honestly `NOT_EVALUATED` rather than faked: duplicate-
signal suppression (only meaningful across a scan run's many symbols,
not a single `decide()` call -- see `ChangeDetector`) and stale-
recommendation detection (would require comparing against this
symbol's *previous* stored `DecisionV2Snapshot`, a route/DB-layer
concern this pure-function module deliberately has no access to).

Per the Product Owner rule "a شراء قوي decision must be rare and
require stricter gates than شراء": `STRONG_BUY_CANDIDATE` additionally
requires full 8/8 sub-score coverage and a confidence floor
(`DecisionV2Tuning.strong_buy_minimum_confidence`) -- failing either
downgrades to `BUY_CANDIDATE`, never a rejection, since the underlying
thesis can still be sound.
"""

from dataclasses import dataclass, field
from typing import List, Optional

from src.analysis.decision.types import EntryQuality
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.types import Decision, GateOutcome, GateStatus
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
    ohlcv_latest_bar_age_days: Optional[float]
    max_ohlcv_staleness_days: float

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

    # --- Phase 2B additions -------------------------------------------
    trend_momentum_conflict: Optional[str]  # scoring.conflicting_indicators()'s Arabic note, or None
    volume_confirms_decision: Optional[bool]
    change_percent: Optional[float]
    price_limit_proximity_pct: float
    risk_level: str
    strong_buy_minimum_confidence: float
    confidence_score: float
    market_context_score: Optional[float]

    # --- Phase 2C additions -------------------------------------------
    market_risk_entry_permitted: bool
    market_risk_label_ar: str

    # --- Phase 3 area 2 (confidence calibration) -----------------------
    # `None` (every caller today) means no ConfidenceCalibrationEngine
    # model is active yet, or the caller chose not to apply one -- the
    # gate below reports NOT_EVALUATED, never a fabricated PASS/FAIL,
    # matching get_min_calibrated_success_probability()'s own docstring.
    calibrated_success_probability: Optional[float] = None
    min_calibrated_success_probability: float = 0.0

    # --- Phase 3 decision-authority repair -----------------------------
    # Both fields reuse evidence this engine already computes for
    # display/labeling purposes (structure.price_severely_missed_entry_zone
    # and context.extra["breakout_confirmation"]["status"]) -- no new
    # indicator, no new threshold. Defaults preserve exact existing
    # behavior for any caller that doesn't pass them.
    price_severely_missed_entry_zone: bool = False
    breakout_status: str = "NOT_APPLICABLE"


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
        gates.append(GateOutcome("real_data_source", GateStatus.FAIL, "بيانات تجريبية غير حقيقية -- لا يمكن نشر توصية.", True))
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)
    gates.append(GateOutcome(
        "real_data_source", GateStatus.PASS,
        "مصدر بيانات حقيقي (SAHMK)" if inputs.is_synthetic is False else "مصدر البيانات غير مؤكد لهذا التحليل",
        False,
    ))

    # Data availability -----------------------------------------------------
    if not inputs.has_technical or inputs.recommendation is None:
        gates.append(GateOutcome("data_availability", GateStatus.FAIL, "لا تتوفر بيانات فنية كافية لهذا السهم.", True))
        return GateEvaluation(Decision.INSUFFICIENT_DATA, gates, warnings, disclosures)
    gates.append(GateOutcome("data_availability", GateStatus.PASS, "تتوفر بيانات فنية كافية.", True))

    # Gate 2: current price valid and positive --------------------------------
    price_ok = inputs.price is not None and inputs.price > 0
    gates.append(GateOutcome(
        "price_validity", GateStatus.PASS if price_ok else GateStatus.FAIL,
        "السعر الحالي صالح." if price_ok else "لا يتوفر سعر حالي صالح.", True,
    ))
    if not price_ok:
        return GateEvaluation(Decision.INSUFFICIENT_DATA, gates, warnings, disclosures)

    # Gate 1b: freshness (the DataFreshnessStatus classification itself
    # -- LIVE/LAST_SESSION/STALE/UNKNOWN -- is computed once in
    # engine.py, which also knows market_is_open; this gate only needs
    # the pass/fail boolean). ---------------------------------------
    is_stale = inputs.data_age_hours is not None and inputs.data_age_hours > inputs.max_age_hours
    gates.append(GateOutcome(
        "data_freshness", GateStatus.FAIL if is_stale else GateStatus.PASS,
        f"عمر البيانات {inputs.data_age_hours:.1f} ساعة" if inputs.data_age_hours is not None else "عمر البيانات غير معروف",
        False,
    ))
    if is_stale:
        warnings.append("البيانات المستخدمة أقدم من الحد المسموح -- التحليل معروض للاطلاع فقط وليس للتنفيذ الفوري.")

    # OHLCV staleness: distinct from data_freshness above, which only
    # checks the scan/live-quote's own recency -- the live quote is
    # always fetched fresh regardless of ingestion health, so it says
    # nothing about whether the multi-day daily-bar history the
    # technical sub-scores (trend/momentum/volatility) are computed
    # from has actually kept up. Only catches this when
    # historical_ohlcv ingestion has genuinely fallen behind (e.g.
    # deferred on SAHMK quota protection -- see
    # src.market_data.ingestion.scheduler) -- the same real production
    # gap this gate closed in the legacy market-scan publication path
    # (src.market_intelligence.publication_gate._ohlcv_staleness_gate).
    ohlcv_is_stale = (
        inputs.ohlcv_latest_bar_age_days is not None
        and inputs.ohlcv_latest_bar_age_days > inputs.max_ohlcv_staleness_days
    )
    if inputs.ohlcv_latest_bar_age_days is None:
        gates.append(GateOutcome("ohlcv_staleness", GateStatus.NOT_EVALUATED, "عمر بيانات الشموع اليومية غير معروف.", False))
    else:
        gates.append(GateOutcome(
            "ohlcv_staleness", GateStatus.FAIL if ohlcv_is_stale else GateStatus.PASS,
            f"أحدث شمعة يومية عمرها {inputs.ohlcv_latest_bar_age_days:.1f} يوم"
            + (" -- يتجاوز الحد المسموح." if ohlcv_is_stale else "."),
            False,
        ))
    if ohlcv_is_stale:
        warnings.append("المؤشرات الفنية محسوبة من بيانات شموع يومية قديمة (تأخر تحديث البيانات) -- التحليل معروض للاطلاع فقط.")

    # Gate 11: market status known --------------------------------------------
    gates.append(GateOutcome(
        "market_status_known", GateStatus.PASS if inputs.market_status_known else GateStatus.FAIL,
        "حالة السوق معروفة." if inputs.market_status_known else "حالة السوق غير مؤكدة.", False,
    ))
    if not inputs.market_status_known:
        warnings.append("حالة السوق (مفتوح/مغلق) غير مؤكدة حاليًا.")

    # Phase 2B, quote-timestamp gate: informational -- data_freshness
    # (above) already turns a *stale* timestamp into a fail; this gate
    # separately surfaces whether a timestamp exists at all.
    gates.append(GateOutcome(
        "quote_timestamp_known", GateStatus.PASS if inputs.data_age_hours is not None else GateStatus.FAIL,
        "توقيت آخر تحديث للسعر معروف." if inputs.data_age_hours is not None else "توقيت آخر تحديث للسعر غير معروف.",
        False,
    ))

    # Phase 2B, market-context gate: informational -- market_context_score
    # already feeds opportunity_quality_score; this gate makes that
    # input individually visible/auditable rather than buried in the
    # weighted blend.
    if inputs.market_context_score is not None:
        gates.append(GateOutcome(
            "market_context", GateStatus.PASS if inputs.market_context_score >= 50.0 else GateStatus.FAIL,
            f"سياق السوق العام: {inputs.market_context_score:.0f}/100.", False,
        ))

    # Phase 2B, price-limit-proximity gate: a caution flag only -- built
    # from the real, already-fetched quote change_percent, not a
    # verified per-instrument Tadawul limit band (not ingested).
    if inputs.change_percent is not None and abs(inputs.change_percent) >= inputs.price_limit_proximity_pct:
        gates.append(GateOutcome(
            "price_limit_proximity", GateStatus.FAIL,
            f"تغيّر السعر اليوم {inputs.change_percent:+.1f}٪ -- قريب من نطاق التحرك اليومي المعتاد بشدة.",
            False,
        ))
        warnings.append("السعر تحرك بنسبة كبيرة اليوم -- قد يقترب من حد التداول اليومي المعتاد.")
    else:
        gates.append(GateOutcome("price_limit_proximity", GateStatus.PASS, "لا يوجد اقتراب غير معتاد من حدود التحرك اليومي.", False))

    # Gate 13: fundamentals/news disclosure (never blocking) -------------------
    if not inputs.fundamentals_available:
        disclosures.append("لا تتوفر بيانات أساسية (مالية) حقيقية لهذا السهم حاليًا -- هذا التحليل فني بالدرجة الأولى.")
    if not inputs.news_available:
        disclosures.append("لا تتوفر بيانات إخبارية محللة لهذا السهم حاليًا.")

    # Gate 14: duplicate suppression -- genuinely NOT_EVALUATED, not a
    # fabricated pass: not implemented at single-stock level:
    # deduplication exists at the market-scan layer (ChangeDetector).
    gates.append(GateOutcome(
        "duplicate_suppression", GateStatus.NOT_EVALUATED,
        "غير مطبّق على مستوى تحليل السهم الفردي (متاح على مستوى المسح الشامل).", False,
    ))

    # Phase 2B, stale-recommendation gate: honestly NOT_EVALUATED here --
    # would require comparing against this symbol's previous stored
    # DecisionV2Snapshot, a route/DB-layer concern.
    gates.append(GateOutcome(
        "stale_recommendation", GateStatus.NOT_EVALUATED,
        "غير مطبّق على مستوى هذا الاستدعاء الفردي -- يتطلب مقارنة بالتوصية السابقة المخزّنة لهذا السهم.", False,
    ))

    # Phase 2B, risk-warning-disclosure gate: guarantees an explicit,
    # itemized risk statement always appears in the gates list itself,
    # not only in the separate `warnings` array.
    if inputs.risk_level in ("HIGH", "VERY_HIGH"):
        gates.append(GateOutcome(
            "risk_warning_disclosed", GateStatus.PASS,
            "مستوى مخاطرة مرتفع لهذا السهم -- يُنصح بحجم مركز أصغر وإدارة مخاطر أكثر تحفظًا.", False,
        ))
    else:
        gates.append(GateOutcome("risk_warning_disclosed", GateStatus.PASS, f"مستوى المخاطرة: {inputs.risk_level}.", False))

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
    if ohlcv_is_stale:
        warnings.append("لا يمكن اعتبار هذا فرصة شراء فعلية والمؤشرات الفنية مبنية على بيانات شموع قديمة -- تم تصنيفه للمراقبة فقط.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)

    # Gate 3: entry zone valid ------------------------------------------------
    entry_zone_ok = (
        inputs.entry_zone_low is not None and inputs.entry_zone_high is not None
        and inputs.entry_zone_low <= inputs.entry_zone_high
    )
    gates.append(GateOutcome(
        "entry_zone_valid", GateStatus.PASS if entry_zone_ok else GateStatus.FAIL,
        "نطاق الدخول متسق." if entry_zone_ok else "نطاق الدخول غير متاح أو غير متسق.", True,
    ))
    if not entry_zone_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 4: stop below entry zone (long) -------------------------------------
    stop_ok = inputs.stop_loss is not None and inputs.stop_loss < inputs.entry_zone_low
    gates.append(GateOutcome(
        "stop_below_entry", GateStatus.PASS if stop_ok else GateStatus.FAIL,
        "وقف الخسارة أسفل نطاق الدخول." if stop_ok else "وقف الخسارة غير منطقي بالنسبة لنطاق الدخول.", True,
    ))
    if not stop_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 5: target above entry zone ------------------------------------------
    target_ok = inputs.target_1 is not None and inputs.target_1 > inputs.entry_zone_high
    gates.append(GateOutcome(
        "target_above_entry", GateStatus.PASS if target_ok else GateStatus.FAIL,
        "الهدف أعلى نطاق الدخول." if target_ok else "الهدف غير منطقي بالنسبة لنطاق الدخول.", True,
    ))
    if not target_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 15: price already ran past the entry zone --------------------------
    # Phase 3 decision-authority repair: severity now has real decision
    # consequence, using the same already-computed, non-arbitrary
    # signal (structure.price_severely_missed_entry_zone -- reuses the
    # entry zone's own ATR-derived width, no new threshold). A mild
    # overrun keeps the exact prior behavior (WAIT_FOR_ENTRY, setup
    # preserved). A severe overrun (price has run a further full
    # entry-zone-width beyond the top edge) moves to Decision.WATCH,
    # deliberately NOT Decision.REJECT and NOT any SELL-like state --
    # this is a bullish extension, not an invalidated setup, and WATCH
    # is the only existing Decision value every downstream consumer
    # already treats as "still monitored, not exited" (see
    # src.api.routes.portfolio._HOLDER_GUIDANCE_MAP mapping WATCH to
    # continued-monitoring guidance, and the frontend DecisionBadge
    # coloring WATCH the same neutral bucket as WAIT_FOR_ENTRY, never
    # the sell/red bucket REJECT/REDUCE/EXIT share).
    if inputs.price_missed_entry_zone:
        if inputs.price_severely_missed_entry_zone:
            gates.append(GateOutcome(
                "entry_not_missed", GateStatus.FAIL,
                "السعر تجاوز نطاق الدخول بفارق كبير -- لم يعد هذا الإعداد فرصة دخول فورية.", True,
            ))
            warnings.append(
                "السعر ابتعد كثيرًا عن نطاق الدخول المناسب -- لا يُنصح بمطاردة السعر حاليًا، وتم نقل الفرصة للمراقبة."
            )
            return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
        gates.append(GateOutcome("entry_not_missed", GateStatus.FAIL, "السعر تجاوز نطاق الدخول المحدد بالفعل.", True))
        warnings.append("السعر الحالي أعلى من نطاق الدخول المناسب -- يفضّل الانتظار بدل مطاردة السعر.")
        return GateEvaluation(Decision.WAIT_FOR_ENTRY, gates, warnings, disclosures)
    gates.append(GateOutcome("entry_not_missed", GateStatus.PASS, "السعر لا يزال ضمن نطاق دخول معقول.", True))

    # Gate 6: risk/reward minimum -----------------------------------------------
    rr_ok = inputs.risk_reward_ratio is not None and inputs.risk_reward_ratio >= inputs.min_risk_reward_ratio
    gates.append(GateOutcome(
        "risk_reward_minimum", GateStatus.PASS if rr_ok else GateStatus.FAIL,
        f"العائد إلى المخاطرة {inputs.risk_reward_ratio:.2f}" if inputs.risk_reward_ratio is not None else "تعذر حساب العائد إلى المخاطرة",
        True,
    ))
    if not rr_ok:
        return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 8: liquidity (NOT_EVALUATED, not blocking, when unknown) -----------
    if inputs.average_traded_value is None:
        gates.append(GateOutcome("liquidity", GateStatus.NOT_EVALUATED, "متوسط قيمة التداول غير متاح.", False))
    else:
        liquidity_ok = inputs.average_traded_value >= inputs.min_average_traded_value
        gates.append(GateOutcome(
            "liquidity", GateStatus.PASS if liquidity_ok else GateStatus.FAIL,
            f"متوسط قيمة التداول اليومي ~{inputs.average_traded_value:,.0f} ريال", True,
        ))
        if not liquidity_ok:
            return GateEvaluation(Decision.REJECT, gates, warnings, disclosures)

    # Gate 9: no excessive volatility/gap risk ----------------------------------
    if inputs.atr_pct is not None and inputs.atr_pct > inputs.excessive_volatility_pct:
        gates.append(GateOutcome("volatility_acceptable", GateStatus.FAIL, f"تقلب مرتفع جدًا (ATR% = {inputs.atr_pct * 100:.1f}%).", True))
        warnings.append("تقلب السهم مرتفع بشكل غير معتاد حاليًا -- خطر فجوات سعرية حقيقي.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
    gates.append(GateOutcome("volatility_acceptable", GateStatus.PASS, "مستوى التقلب مقبول.", False))

    # Phase 2B, trend-consistency / contradiction gate: reuses
    # scoring.conflicting_indicators()'s already-computed note (the
    # trend and momentum sub-scores clearly disagree) -- previously only
    # capped confidence in engine.py; now also formally downgrades to
    # WATCH, since a positive decision should not publish on the
    # strength of a trend the momentum evidence contradicts.
    if inputs.trend_momentum_conflict:
        gates.append(GateOutcome("trend_momentum_consistency", GateStatus.FAIL, inputs.trend_momentum_conflict, True))
        warnings.append(inputs.trend_momentum_conflict)
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
    gates.append(GateOutcome("trend_momentum_consistency", GateStatus.PASS, "الاتجاه والزخم متوافقان.", False))

    # Phase 2B, volume-quality gate: downgrades to WATCH only when
    # volume evidence actively CONTRADICTS the recommended direction
    # (accumulation/distribution reading opposes a BUY) -- an unknown
    # reading (None, e.g. no OBV history yet) is not treated as a
    # contradiction.
    if inputs.volume_confirms_decision is False:
        gates.append(GateOutcome("volume_quality", GateStatus.FAIL, "حجم التداول لا يدعم اتجاه القرار الحالي.", True))
        warnings.append("حجم التداول الحالي لا يؤكد الاتجاه المقترح -- يفضّل انتظار تأكيد حجمي.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
    # `volume_confirms_decision is None` (no OBV/volume-trend history
    # yet) is genuinely NOT_EVALUATED, not a fabricated pass -- the
    # comment above already documented "not treated as a contradiction"
    # but the status previously collapsed that into the same PASS as an
    # actual confirming reading.
    gates.append(GateOutcome(
        "volume_quality", GateStatus.PASS if inputs.volume_confirms_decision else GateStatus.NOT_EVALUATED,
        "حجم التداول يدعم اتجاه القرار." if inputs.volume_confirms_decision else "لا يوجد تأكيد أو تعارض حجمي واضح.",
        False,
    ))

    # Phase 2C, market-risk entry-permission gate: a market-wide risk
    # state (see market_risk.py, derived from real scan-run breadth) of
    # REDUCE_POSITIONS/PARTIAL_EXIT/DEFENSIVE_EXIT blocks *new* entries.
    # HOLD/REDUCE/EXIT decisions (already returned above) are never
    # affected -- trimming or exiting a position during a risk-off
    # market is exactly the defensive behavior this gate exists to
    # encourage, not discourage.
    if not inputs.market_risk_entry_permitted:
        gates.append(GateOutcome(
            "market_risk_permits_entry", GateStatus.FAIL,
            f"حالة مخاطر السوق الحالية: «{inputs.market_risk_label_ar}» -- يتم تعليق توصيات الدخول الجديدة مؤقتًا.",
            True,
        ))
        warnings.append(
            f"حالة مخاطر السوق العامة حاليًا «{inputs.market_risk_label_ar}» -- "
            "يُفضّل تجنب فتح مراكز جديدة حتى تتحسن الحالة."
        )
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
    gates.append(GateOutcome(
        "market_risk_permits_entry", GateStatus.PASS,
        f"حالة مخاطر السوق الحالية: «{inputs.market_risk_label_ar}» -- لا تمنع الدخول.", False,
    ))

    # Phase 3 decision-authority repair, failed-breakout gate: a real,
    # already-in-progress breakout attempt for this symbol that has
    # already reverted is contradicting technical evidence for a BUY
    # thesis right now -- downgrades to WATCH (never REJECT: the
    # underlying thesis may still be sound once the level is retested),
    # the identical FAIL->WATCH pattern trend_momentum_consistency and
    # volume_quality already use for contradicting evidence above.
    # `breakout_status` defaults to NOT_APPLICABLE (no breakout thesis
    # in play for this symbol) and is otherwise one of
    # SEQUENCE_UNVERIFIED/CONFIRMED_BREAKOUT/EARLY_BREAKOUT/
    # UNCONFIRMED_BREAKOUT/FAILED_BREAKOUT -- only the exact
    # FAILED_BREAKOUT string triggers this gate; every other value
    # (including the safe default) PASSes through unchanged.
    if inputs.breakout_status == "FAILED_BREAKOUT":
        gates.append(GateOutcome(
            "breakout_not_failed", GateStatus.FAIL,
            "محاولة اختراق سابقة لهذا المستوى تراجعت بالفعل -- الدليل الفني الحالي يتعارض مع فرضية الشراء.",
            True,
        ))
        warnings.append("محاولة اختراق سابقة لهذا السهم فشلت وتراجع السعر دون المستوى -- يفضّل الحذر قبل الدخول.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
    gates.append(GateOutcome(
        "breakout_not_failed", GateStatus.PASS, "لا توجد محاولة اختراق فاشلة نشطة حاليًا.", False,
    ))

    # Phase 3 area 2, confidence-calibration gate: the one place this
    # engine's real, already-trained-and-activated ConfidenceCalibrationEngine
    # model (see src.ai_evolution.confidence_calibration) can affect a
    # Decision -- caller-computed and passed in via `decide()`'s own
    # `calibrated_success_probability` parameter (this engine never
    # queries the database itself, see that parameter's own docstring).
    # `None` (every caller that doesn't pass a value, and the honest
    # state until enough real outcome history exists to activate a
    # model) is NOT_EVALUATED, never a fabricated PASS/FAIL -- mirrors
    # `src.market_intelligence.publication_gate`'s identical
    # `_confidence_calibration_gate` for the legacy V1 pipeline, reusing
    # its exact same threshold getter so the bar is configured in one
    # place, not two. A caution-level downgrade to WATCH, not REJECT --
    # a poorly-calibrated confidence score means the evidence is
    # shakier than it looks, not that there is no evidence at all, the
    # same reasoning trend_momentum_consistency/volume_quality above
    # already apply.
    if inputs.calibrated_success_probability is None:
        gates.append(GateOutcome(
            "confidence_calibration_applied", GateStatus.NOT_EVALUATED,
            "لا يوجد نموذج معايرة ثقة نشط حاليًا -- لم يتم تطبيق معايرة على درجة الثقة.", False,
        ))
    elif inputs.calibrated_success_probability < inputs.min_calibrated_success_probability:
        gates.append(GateOutcome(
            "confidence_calibration_applied", GateStatus.FAIL,
            (
                f"احتمال النجاح المعايَر {inputs.calibrated_success_probability:.0%} أقل من الحد الأدنى "
                f"{inputs.min_calibrated_success_probability:.0%}."
            ),
            True,
        ))
        warnings.append("درجة الثقة بعد المعايرة الإحصائية أضعف من الحد الأدنى المعتمد -- تم تخفيض التوصية للمراقبة.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)
    else:
        gates.append(GateOutcome(
            "confidence_calibration_applied", GateStatus.PASS,
            f"احتمال النجاح المعايَر {inputs.calibrated_success_probability:.0%}.", False,
        ))

    # Gate 12: confidence not based on a single indicator -----------------------
    multi_factor_ok = inputs.available_sub_score_count >= 3
    gates.append(GateOutcome(
        "multi_factor_evidence", GateStatus.PASS if multi_factor_ok else GateStatus.FAIL,
        f"{inputs.available_sub_score_count} من أصل 8 عناصر تحليل متاحة.", True,
    ))
    if not multi_factor_ok:
        warnings.append("عدد الأدلة المتاحة محدود -- التوصية أقل اكتمالًا من المعتاد.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)

    # Entry quality: a poor entry downgrades to WATCH rather than REJECT
    # (matches publication_gate.py's identical reasoning: the thesis
    # can still be sound even when *this specific price* is a bad entry).
    entry_quality_ok = inputs.entry_quality is not EntryQuality.POOR
    gates.append(GateOutcome(
        "entry_quality", GateStatus.PASS if entry_quality_ok else GateStatus.FAIL,
        f"جودة نقطة الدخول: {inputs.entry_quality.value}", True,
    ))
    if not entry_quality_ok:
        warnings.append("جودة نقطة الدخول الحالية ضعيفة -- يفضّل الانتظار.")
        return GateEvaluation(Decision.WATCH, gates, warnings, disclosures)

    strong = inputs.recommendation is Recommendation.STRONG_BUY

    if strong:
        # Phase 2B, confidence-calibration gate: a STRONG_BUY_CANDIDATE
        # must be rare and stricter than BUY_CANDIDATE (Product Owner
        # rule) -- full evidence coverage AND a confidence floor, or it
        # downgrades to BUY_CANDIDATE (the thesis itself is still sound).
        full_coverage = inputs.available_sub_score_count >= 8
        confidence_ok = inputs.confidence_score >= inputs.strong_buy_minimum_confidence
        gates.append(GateOutcome(
            "confidence_calibration_minimum", GateStatus.PASS if (full_coverage and confidence_ok) else GateStatus.FAIL,
            (
                f"تغطية الأدلة {inputs.available_sub_score_count}/8، الثقة {inputs.confidence_score:.0f}٪ "
                f"(الحد الأدنى المطلوب لـ«شراء قوي»: تغطية كاملة وثقة {inputs.strong_buy_minimum_confidence:.0f}٪ فأكثر)."
            ),
            True,
        ))
        if not (full_coverage and confidence_ok):
            warnings.append("الأدلة إيجابية لكنها لم تبلغ بعد المعايير الصارمة لتصنيف «شراء قوي».")
            strong = False

    return GateEvaluation(
        Decision.STRONG_BUY_CANDIDATE if strong else Decision.BUY_CANDIDATE,
        gates, warnings, disclosures,
    )
