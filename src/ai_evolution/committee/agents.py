"""The Investment Committee's eight independent analyst agents. Every
agent reads only fields Decision Engine V2 (or the shared
`InvestmentDecision` it wraps) has already computed -- no agent here
performs new indicator math, fetches new data, or (other than the News
agent, which reuses the existing grounded-LLM `NewsAnalystAgent`)
calls an LLM. Each `analyze*` function is synchronous and pure except
`analyze_news`, which is async because it awaits the existing grounded
News Analyst call.

Reuses `src.ai_evolution.agents.wrapper_agents.CategoryWrapperAgent`/
`MacroAnalystAgent` and `llm_agents.NewsAnalystAgent` rather than
duplicating their logic -- this module only adapts their
`AgentOpinionResult` output into the committee's richer `AgentVerdict`
(adding `role`, `evidence`, `rejection_reasons`) and adds the three
agents with no existing wrapper: Market Sentiment (market breadth, not
news sentiment), Liquidity & Volume, and Portfolio Allocation.
"""

from typing import List, Optional

from sqlalchemy.orm import Session

from src.ai_evolution.agents.llm_agents import NewsAnalystAgent
from src.ai_evolution.agents.llm_factory import get_agent_panel_llm_adapter
from src.ai_evolution.agents.wrapper_agents import MacroAnalystAgent, _find_breakdown, _stance_from_points
from src.ai_evolution.committee.types import (
    ROLE_FUNDAMENTAL,
    ROLE_LIQUIDITY_VOLUME,
    ROLE_MACRO,
    ROLE_MARKET_SENTIMENT,
    ROLE_NEWS,
    ROLE_PORTFOLIO_ALLOCATION,
    ROLE_RISK,
    ROLE_TECHNICAL,
    AgentVerdict,
)
from src.analysis.decision.types import DecisionFactorBreakdown, InvestmentDecision, PositionSize
from src.analysis.decision_v2.types import DecisionResult
from src.domain.models import AgentStance

_MIN_RISK_REWARD_FOR_STANDARD_SIZE = 1.5
_MIN_RISK_REWARD_FOR_ANY_SIZE = 1.0


def _breakdown_evidence(item: Optional[DecisionFactorBreakdown], category_ar: str) -> List[str]:
    if item is None or not item.available:
        return []
    evidence = [f"{category_ar}: {item.points:+.1f} نقطة (وزن {item.weight:.2f}، ثقة {item.confidence:.0f}%)"]
    if item.notes:
        evidence.append(item.notes)
    return evidence


def analyze_technical(investment_decision: InvestmentDecision, result: DecisionResult) -> AgentVerdict:
    item = _find_breakdown(investment_decision.breakdown, "Technical Analysis")
    if item is None or not item.available:
        return AgentVerdict(
            agent_name="Technical Analysis Agent", role=ROLE_TECHNICAL, stance=AgentStance.UNAVAILABLE,
            confidence=0.0, reasoning="لا تتوفر بيانات فنية كافية لهذا السهم.",
            rejection_reasons=["البيانات الفنية غير متاحة."],
        )
    evidence = _breakdown_evidence(item, "التحليل الفني")
    if result.trend_direction_ar and result.trend_direction_ar != "غير محدد":
        evidence.append(f"اتجاه الترند: {result.trend_direction_ar} ({result.trend_strength_label_ar})")
    if result.support_resistance_evidence_ar:
        evidence.append(result.support_resistance_evidence_ar)
    rejection_reasons = []
    if item.confidence < 40:
        rejection_reasons.append(f"ثقة التحليل الفني منخفضة ({item.confidence:.0f}%).")
    return AgentVerdict(
        agent_name="Technical Analysis Agent", role=ROLE_TECHNICAL, stance=_stance_from_points(item.points),
        confidence=item.confidence, reasoning=item.notes or f"التحليل الفني ساهم بـ {item.points:+.1f} نقطة.",
        evidence=evidence, rejection_reasons=rejection_reasons,
    )


def analyze_fundamental(investment_decision: InvestmentDecision, result: DecisionResult) -> AgentVerdict:
    item = _find_breakdown(investment_decision.breakdown, "Fundamental Analysis")
    summary = result.fundamental_summary or {}
    has_any_ratio = any(v is not None for v in summary.values())
    if (item is None or not item.available) and not has_any_ratio:
        return AgentVerdict(
            agent_name="Fundamental Analysis Agent", role=ROLE_FUNDAMENTAL, stance=AgentStance.UNAVAILABLE,
            confidence=0.0, reasoning="لا تتوفر بيانات مالية أساسية كافية لهذا السهم.",
            rejection_reasons=["البيانات المالية الأساسية غير متوفرة."],
        )
    evidence = _breakdown_evidence(item, "التحليل الأساسي") if item is not None else []
    if summary.get("revenue_growth") is not None:
        evidence.append(f"نمو الإيرادات: {summary['revenue_growth']:+.1%}")
    if summary.get("profit_growth") is not None:
        evidence.append(f"نمو الأرباح: {summary['profit_growth']:+.1%}")
    if summary.get("return_on_equity") is not None:
        evidence.append(f"العائد على حقوق الملكية: {summary['return_on_equity']:+.1%}")
    if summary.get("debt_to_equity") is not None:
        evidence.append(f"نسبة الدين إلى حقوق الملكية: {summary['debt_to_equity']:.2f}")
    if summary.get("price_to_earnings") is not None:
        evidence.append(f"مكرر الربحية: {summary['price_to_earnings']:.1f}x")
    if result.fundamental_summary_ar:
        evidence.append(result.fundamental_summary_ar)
    rejection_reasons = []
    if not has_any_ratio:
        rejection_reasons.append("لا تتوفر نسب مالية محسوبة من بيانات مبلَّغ عنها فعليًا.")
    if item is not None and item.available:
        stance = _stance_from_points(item.points)
        confidence = item.confidence
        reasoning = item.notes or f"التحليل الأساسي ساهم بـ {item.points:+.1f} نقطة."
    else:
        stance = AgentStance.NEUTRAL
        confidence = 30.0
        reasoning = "بيانات مالية جزئية متاحة دون مساهمة مباشرة في درجة القرار."
    return AgentVerdict(
        agent_name="Fundamental Analysis Agent", role=ROLE_FUNDAMENTAL, stance=stance, confidence=confidence,
        reasoning=reasoning, evidence=evidence, rejection_reasons=rejection_reasons,
    )


async def analyze_news(session: Session, symbol: str, news_events: List[dict]) -> AgentVerdict:
    llm_adapter = get_agent_panel_llm_adapter()
    opinion = await NewsAnalystAgent(llm_adapter).analyze(session, symbol)
    evidence = [
        f"\"{event['headline']}\" (تصنيف {event['category']}، ثقة {event['confidence']:.0f}%)"
        for event in news_events[:5]
    ]
    rejection_reasons = [] if news_events else ["لا توجد أخبار محلَّلة حديثة ذات صلة."]
    return AgentVerdict(
        agent_name="News Intelligence Agent", role=ROLE_NEWS, stance=opinion.stance, confidence=opinion.confidence,
        reasoning=opinion.reasoning, evidence=evidence, rejection_reasons=rejection_reasons,
        used_llm=opinion.used_llm,
    )


_BREADTH_BULLISH_MARGIN = 0.15  # buy_count must exceed sell_count by >15% of total scanned to count as a real tilt


def analyze_market_sentiment(result: DecisionResult) -> AgentVerdict:
    buy = result.market_breadth_buy_count
    sell = result.market_breadth_sell_count
    scanned = result.market_breadth_symbols_scanned
    if buy is None or sell is None or not scanned:
        return AgentVerdict(
            agent_name="Market Sentiment Agent", role=ROLE_MARKET_SENTIMENT, stance=AgentStance.UNAVAILABLE,
            confidence=0.0, reasoning="لا تتوفر بيانات اتساع السوق (Market Breadth) حاليًا.",
            rejection_reasons=["بيانات اتساع السوق غير متوفرة."],
        )
    net_tilt = (buy - sell) / scanned
    if net_tilt >= _BREADTH_BULLISH_MARGIN:
        stance = AgentStance.BULLISH
    elif net_tilt <= -_BREADTH_BULLISH_MARGIN:
        stance = AgentStance.BEARISH
    else:
        stance = AgentStance.NEUTRAL
    confidence = min(100.0, abs(net_tilt) * 200.0)
    evidence = [
        f"عدد توصيات الشراء في آخر مسح: {buy} من أصل {scanned} سهمًا ممسوحًا",
        f"عدد توصيات البيع في آخر مسح: {sell} من أصل {scanned} سهمًا ممسوحًا",
    ]
    if result.market_risk_label_ar:
        evidence.append(f"حالة مخاطر السوق: {result.market_risk_label_ar}")
    if result.market_risk_basis_ar:
        evidence.append(result.market_risk_basis_ar)
    rejection_reasons = []
    if result.market_risk_entry_permitted is False:
        rejection_reasons.append("مخاطر السوق الحالية لا تسمح بالدخول في مراكز جديدة.")
    if not result.market_risk_is_live:
        rejection_reasons.append("القراءة مبنية على آخر جلسة مكتملة وليست قراءة حية.")
    return AgentVerdict(
        agent_name="Market Sentiment Agent", role=ROLE_MARKET_SENTIMENT, stance=stance, confidence=confidence,
        reasoning=(
            f"اتساع السوق يميل نحو {'الشراء' if net_tilt > 0 else 'البيع' if net_tilt < 0 else 'التعادل'} "
            f"({buy} شراء مقابل {sell} بيع من {scanned})."
        ),
        evidence=evidence, rejection_reasons=rejection_reasons,
    )


def analyze_risk(investment_decision: InvestmentDecision, result: DecisionResult) -> AgentVerdict:
    item = _find_breakdown(investment_decision.breakdown, "Risk")
    failing_gates = [g for g in result.gates if not g.passed]
    if item is None or not item.available:
        return AgentVerdict(
            agent_name="Risk Management Agent", role=ROLE_RISK, stance=AgentStance.UNAVAILABLE, confidence=0.0,
            reasoning="لا تتوفر بيانات كافية لتقييم المخاطر.",
            rejection_reasons=["بيانات تقييم المخاطر غير متوفرة."],
        )
    evidence = _breakdown_evidence(item, "إدارة المخاطر")
    if result.risk_level_label_ar:
        evidence.append(f"مستوى المخاطرة: {result.risk_level_label_ar}")
    if result.downside_to_stop is not None:
        evidence.append(f"الهبوط المحتمل حتى وقف الخسارة: {result.downside_to_stop:+.1%}")
    rejection_reasons = [f"بوابة فشلت: {g.detail}" for g in failing_gates]
    # A high-points Risk category (favorable risk profile) still yields a
    # BULLISH stance from `_stance_from_points` (points are signed and
    # centered on 0, same convention as every other category); a low/
    # negative score correctly reads as BEARISH (unfavorable risk).
    stance = _stance_from_points(item.points)
    if failing_gates and stance is not AgentStance.BEARISH:
        stance = AgentStance.NEUTRAL
    return AgentVerdict(
        agent_name="Risk Management Agent", role=ROLE_RISK, stance=stance, confidence=item.confidence,
        reasoning=item.notes or f"إدارة المخاطر ساهمت بـ {item.points:+.1f} نقطة.",
        evidence=evidence, rejection_reasons=rejection_reasons,
    )


def analyze_liquidity_volume(result: DecisionResult) -> AgentVerdict:
    if result.liquidity_confidence is None and result.relative_volume is None:
        return AgentVerdict(
            agent_name="Liquidity & Volume Agent", role=ROLE_LIQUIDITY_VOLUME, stance=AgentStance.UNAVAILABLE,
            confidence=0.0, reasoning="لا تتوفر بيانات سيولة أو حجم تداول كافية.",
            rejection_reasons=["بيانات السيولة والحجم غير متوفرة."],
        )
    evidence = []
    if result.relative_volume is not None:
        evidence.append(f"الحجم النسبي: {result.relative_volume:.2f}x المتوسط")
    if result.liquidity_quality_ar and result.liquidity_quality_ar != "غير محدد":
        evidence.append(f"جودة السيولة: {result.liquidity_quality_ar}")
    if result.accumulation_score is not None:
        evidence.append(f"درجة التجميع: {result.accumulation_score:.0f}/100")
    if result.accumulation_assessment_ar:
        evidence.append(result.accumulation_assessment_ar)

    rejection_reasons = []
    if result.abnormal_volume:
        rejection_reasons.append("رصد حجم تداول غير اعتيادي يستدعي الحذر.")
    if result.volume_confirms_decision is False:
        rejection_reasons.append("حجم التداول لا يؤكد اتجاه القرار الحالي.")

    if result.volume_confirms_decision is True and not result.abnormal_volume:
        stance = AgentStance.BULLISH
    elif result.volume_confirms_decision is False or result.abnormal_volume:
        stance = AgentStance.BEARISH
    else:
        stance = AgentStance.NEUTRAL
    confidence = result.liquidity_confidence if result.liquidity_confidence is not None else 40.0
    reasoning = (
        result.accumulation_assessment_ar
        or f"السيولة والحجم {'تؤكدان' if stance is AgentStance.BULLISH else 'لا تؤكدان'} اتجاه القرار."
    )
    return AgentVerdict(
        agent_name="Liquidity & Volume Agent", role=ROLE_LIQUIDITY_VOLUME, stance=stance, confidence=confidence,
        reasoning=reasoning, evidence=evidence, rejection_reasons=rejection_reasons,
    )


def analyze_macro() -> AgentVerdict:
    opinion = MacroAnalystAgent().analyze([])
    return AgentVerdict(
        agent_name="Macro Economy Agent", role=ROLE_MACRO, stance=opinion.stance, confidence=opinion.confidence,
        reasoning=opinion.reasoning, rejection_reasons=[opinion.reasoning],
    )


_POSITION_SIZE_LABELS_AR = {
    PositionSize.NONE: "لا يُنصح بالدخول",
    PositionSize.SMALL: "صغير",
    PositionSize.MODERATE: "متوسط",
    PositionSize.STANDARD: "قياسي",
    PositionSize.LARGE: "كبير",
}


def analyze_portfolio_allocation(investment_decision: InvestmentDecision, result: DecisionResult) -> AgentVerdict:
    position_size = investment_decision.position_size
    risk_reward = result.risk_reward_target_1
    evidence = [f"الحجم المقترح للمركز: {_POSITION_SIZE_LABELS_AR.get(position_size, position_size.value)}"]
    if risk_reward is not None:
        evidence.append(f"نسبة العائد إلى المخاطرة (الهدف الأول): {risk_reward:.2f}")
    if result.expected_return_target_1 is not None:
        evidence.append(f"العائد المتوقع عند الهدف الأول: {result.expected_return_target_1:+.1%}")
    if result.entry_quality_label_ar:
        evidence.append(f"جودة نقطة الدخول: {result.entry_quality_label_ar}")

    rejection_reasons = []
    if position_size is PositionSize.NONE:
        rejection_reasons.append("حجم المركز الموصى به صفر -- الأدلة الحالية لا تبرر تخصيص رأس مال.")
    if risk_reward is not None and risk_reward < _MIN_RISK_REWARD_FOR_ANY_SIZE:
        rejection_reasons.append(f"نسبة العائد إلى المخاطرة ({risk_reward:.2f}) أقل من الحد الأدنى المقبول.")

    if position_size is PositionSize.NONE:
        stance = AgentStance.BEARISH
        confidence = 60.0
    elif risk_reward is not None and risk_reward >= _MIN_RISK_REWARD_FOR_STANDARD_SIZE:
        stance = AgentStance.BULLISH
        confidence = min(100.0, risk_reward * 30.0)
    elif risk_reward is not None and risk_reward < _MIN_RISK_REWARD_FOR_ANY_SIZE:
        stance = AgentStance.BEARISH
        confidence = 50.0
    else:
        stance = AgentStance.NEUTRAL
        confidence = 35.0

    reasoning = (
        f"الحجم المقترح ({_POSITION_SIZE_LABELS_AR.get(position_size, position_size.value)}) "
        + (f"بنسبة عائد/مخاطرة {risk_reward:.2f}." if risk_reward is not None else "دون نسبة عائد/مخاطرة محسوبة.")
    )
    return AgentVerdict(
        agent_name="Portfolio Allocation Agent", role=ROLE_PORTFOLIO_ALLOCATION, stance=stance,
        confidence=confidence, reasoning=reasoning, evidence=evidence, rejection_reasons=rejection_reasons,
    )
