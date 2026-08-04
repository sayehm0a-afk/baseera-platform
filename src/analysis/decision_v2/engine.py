"""DecisionEngineV2: the Phase 1 orchestrator. Wraps one already-computed
`InvestmentDecision` (from `AIDecisionEngine`, unmodified) and enriches
it into a `DecisionResult` -- entry zone, extended targets, eight
documented sub-scores, gate-checked Arabic action taxonomy, and full
explainability. Computes zero indicators of its own; see scoring.py's
module docstring for the two disclosed real limitations in what's
available from the existing indicator registry.
"""

from datetime import datetime, timezone
from typing import Optional

from src.analysis.decision.types import EntryQuality, InvestmentDecision
from src.analysis.decision_v2 import scoring, structure
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.gates import GateInputs, evaluate_decision
from src.analysis.decision_v2.types import (
    DECISION_LABELS_AR,
    DataFreshnessStatus,
    Decision,
    DecisionResult,
    SubScores,
)
from src.analysis.recommendation.types import AnalysisContext, Recommendation, SignalDirection
from src.market_intelligence.config import (
    get_max_data_age_hours,
    get_min_average_traded_value,
    get_min_risk_reward_ratio,
)

DECISION_V2_ENGINE_VERSION = "2.0.0"

_EXCESSIVE_VOLATILITY_PCT_DEFAULT = 0.08
_MAX_REASONS = 5


def _direction_of(recommendation: Optional[Recommendation]) -> int:
    if recommendation in (Recommendation.BUY, Recommendation.STRONG_BUY):
        return 1
    if recommendation in (Recommendation.SELL, Recommendation.STRONG_SELL):
        return -1
    return 0


class DecisionEngineV2:
    def __init__(self, tuning: Optional[DecisionV2Tuning] = None):
        self._tuning = tuning or DecisionV2Tuning()

    def decide(
        self,
        context: AnalysisContext,
        investment_decision: InvestmentDecision,
        *,
        company_name_ar: Optional[str],
        company_name_en: str,
        sector: Optional[str],
        sector_ar: Optional[str],
        is_synthetic: Optional[bool],
        data_source: str,
        quote_timestamp: Optional[datetime],
        market_status: str,
        market_is_open: Optional[bool],
        scan_run_id: Optional[int] = None,
    ) -> DecisionResult:
        tuning = self._tuning
        technical = context.technical_result
        price = context.latest_price
        direction = _direction_of(investment_decision.recommendation)

        atr_value = None
        atr_pct = None
        support_resistance = None
        if technical is not None:
            atr_value = technical.indicators["atr_14"].latest()
            support_resistance = technical.support_resistance
            if atr_value is not None and price is not None and price > 0:
                atr_pct = atr_value / price

        volume_sma_latest = None
        if technical is not None and "volume_sma_20" in technical.indicators:
            volume_sma_latest = technical.indicators["volume_sma_20"].latest()
        average_traded_value = (
            price * volume_sma_latest if (price is not None and volume_sma_latest is not None) else None
        )

        trend = scoring.trend_score(technical, price)
        momentum = scoring.momentum_score(technical)
        volume = scoring.volume_score(technical)
        liquidity = scoring.liquidity_score(average_traded_value, get_min_average_traded_value())
        volatility = scoring.volatility_score(atr_pct, tuning)
        risk_reward = scoring.risk_reward_score(investment_decision.risk_reward_ratio, get_min_risk_reward_ratio())
        market_context = scoring.market_context_score(market_is_open, sector is not None)

        has_technical = technical is not None
        has_fundamental = context.fundamental_result is not None
        now = datetime.now(timezone.utc)
        data_age_hours: Optional[float] = None
        if quote_timestamp is not None:
            ts = quote_timestamp if quote_timestamp.tzinfo is not None else quote_timestamp.replace(tzinfo=timezone.utc)
            data_age_hours = (now - ts).total_seconds() / 3600.0
        max_age_hours = get_max_data_age_hours()
        data_quality = scoring.data_quality_score(
            has_technical, has_fundamental, is_synthetic, data_age_hours, max_age_hours, tuning
        )

        sub = {
            "trend_score": trend,
            "momentum_score": momentum,
            "volume_score": volume,
            "liquidity_score": liquidity,
            "volatility_score": volatility,
            "risk_reward_score": risk_reward,
            "market_context_score": market_context,
            "data_quality_score": data_quality,
        }
        available_sub_score_count = sum(1 for v in sub.values() if v is not None)
        opportunity_quality = scoring.opportunity_quality_score(sub, tuning)
        risk_score = scoring.risk_score_from_level(investment_decision.risk_level.value, volatility)

        entry_low, entry_high, entry_basis = structure.compute_entry_zone(
            price, atr_pct, direction,
            investment_decision.stop_loss, investment_decision.target_price,
            support_resistance, tuning,
        )
        missed_entry = structure.price_has_missed_entry_zone(price, entry_high, direction)
        target_2, target_3, target_2_basis, target_3_basis = structure.compute_extended_targets(
            price, investment_decision.target_price, atr_value, direction, support_resistance, tuning
        )
        holding_min_days, holding_max_days, holding_label = structure.compute_holding_period(
            investment_decision.time_horizon, tuning
        )

        confidence = investment_decision.confidence
        warnings: list = []
        if market_is_open is False:
            confidence = min(confidence, tuning.market_closed_confidence_cap)
            warnings.append("السوق مغلق حاليًا -- التحليل مبني على بيانات آخر جلسة مكتملة.")
        if not has_fundamental:
            confidence = min(confidence, tuning.missing_fundamentals_confidence_cap)
        if liquidity is not None and liquidity < 50.0:
            confidence = min(confidence, tuning.thin_liquidity_confidence_cap)
            warnings.append("سيولة التداول في هذا السهم محدودة نسبيًا مقارنة بالحد الأدنى المعتمد.")
        conflict_note = scoring.conflicting_indicators(trend, momentum)
        if conflict_note:
            confidence = min(confidence, tuning.conflicting_indicators_confidence_cap)
            warnings.append(conflict_note)
        if investment_decision.entry_quality is EntryQuality.POOR:
            confidence = min(confidence, tuning.near_resistance_confidence_cap)
        if missed_entry:
            confidence = min(confidence, tuning.missed_entry_confidence_cap)
        confidence = round(max(0.0, min(100.0, confidence)), 1)

        gate_inputs = GateInputs(
            has_technical=has_technical,
            recommendation=investment_decision.recommendation,
            direction=direction,
            is_synthetic=is_synthetic,
            data_age_hours=data_age_hours,
            max_age_hours=max_age_hours,
            price=price,
            entry_zone_low=entry_low,
            entry_zone_high=entry_high,
            stop_loss=investment_decision.stop_loss,
            target_1=investment_decision.target_price,
            risk_reward_ratio=investment_decision.risk_reward_ratio,
            min_risk_reward_ratio=get_min_risk_reward_ratio(),
            average_traded_value=average_traded_value,
            min_average_traded_value=get_min_average_traded_value(),
            atr_pct=atr_pct,
            excessive_volatility_pct=tuning.volatility_excessive_pct,
            market_status_known=market_status not in ("UNKNOWN", ""),
            available_sub_score_count=available_sub_score_count,
            fundamentals_available=has_fundamental,
            news_available=any(
                b.category.lower().startswith("news") and b.available for b in investment_decision.breakdown
            ),
            entry_quality=investment_decision.entry_quality,
            price_missed_entry_zone=missed_entry,
        )
        evaluation = evaluate_decision(gate_inputs, tuning)
        warnings.extend(evaluation.warnings)

        is_stale = data_age_hours is not None and data_age_hours > max_age_hours
        if is_synthetic is True:
            freshness_status = DataFreshnessStatus.UNKNOWN
        elif data_age_hours is None:
            freshness_status = DataFreshnessStatus.UNKNOWN
        elif is_stale:
            freshness_status = DataFreshnessStatus.STALE if market_is_open else DataFreshnessStatus.LAST_SESSION
        else:
            freshness_status = DataFreshnessStatus.LIVE

        positive_reasons = [
            s.description for s in investment_decision.signals if s.direction == SignalDirection.BULLISH
        ][:_MAX_REASONS]
        negative_reasons = [
            s.description for s in investment_decision.signals if s.direction == SignalDirection.BEARISH
        ][:_MAX_REASONS]
        if not positive_reasons and not negative_reasons:
            # No per-signal evidence available (e.g. a module ran with
            # zero specific observations) -- fall back to the
            # already-produced plain-language reasons rather than
            # showing an empty, unexplained decision.
            positive_reasons = list(investment_decision.reasons[:_MAX_REASONS])

        invalidation_conditions = self._build_invalidation(
            evaluation.decision, direction, entry_low, entry_high,
            investment_decision.stop_loss, investment_decision.target_price,
        )

        decision_result = DecisionResult(
            symbol=context.symbol,
            company_name_ar=company_name_ar,
            company_name_en=company_name_en,
            sector_ar=sector_ar,
            decision=evaluation.decision,
            decision_label_ar=DECISION_LABELS_AR[evaluation.decision],
            confidence_score=confidence,
            opportunity_quality_score=opportunity_quality,
            risk_score=risk_score,
            data_quality_score=round(data_quality, 1),
            data_freshness_status=freshness_status,
            current_price=price,
            entry_zone_low=entry_low,
            entry_zone_high=entry_high,
            stop_loss=investment_decision.stop_loss,
            target_1=investment_decision.target_price,
            target_2=target_2,
            target_3=target_3,
            expected_return_target_1=investment_decision.expected_return_pct,
            expected_return_target_2=self._pct_return(price, target_2),
            downside_to_stop=self._pct_return(price, investment_decision.stop_loss),
            risk_reward_target_1=investment_decision.risk_reward_ratio,
            risk_reward_target_2=self._risk_reward(price, investment_decision.stop_loss, target_2),
            expected_holding_period_min_days=holding_min_days,
            expected_holding_period_max_days=holding_max_days,
            expected_holding_period_label_ar=holding_label,
            horizon_type=investment_decision.time_horizon.value,
            market_status=market_status,
            decision_timestamp=now,
            invalidation_conditions=invalidation_conditions,
            positive_reasons=positive_reasons,
            negative_reasons=negative_reasons,
            warnings=warnings,
            recommendation_basis=(
                "دمج مرجّح وموثّق لعناصر الاتجاه والزخم والحجم والسيولة والتقلب والعائد إلى المخاطرة "
                "وسياق السوق وجودة البيانات، مبني بالكامل على مؤشرات فنية حقيقية محسوبة مسبقًا "
                f"(أساس وقف الخسارة: {investment_decision.stop_loss_basis}، "
                f"أساس الهدف الأول: {investment_decision.target_price_basis}، "
                f"أساس الهدف الثاني: {target_2_basis}، أساس الهدف الثالث: {target_3_basis}، "
                f"أساس نطاق الدخول: {entry_basis})."
            ),
            analysis_version=DECISION_V2_ENGINE_VERSION,
            data_source=data_source,
            scan_run_id=scan_run_id,
            sub_scores=SubScores(
                trend_score=trend,
                momentum_score=momentum,
                volume_score=volume,
                liquidity_score=liquidity,
                volatility_score=volatility,
                risk_reward_score=risk_reward,
                market_context_score=market_context,
                data_quality_score=round(data_quality, 1),
            ),
            gates=evaluation.gates,
        )
        return decision_result

    @staticmethod
    def _pct_return(price: Optional[float], target: Optional[float]) -> Optional[float]:
        if price is None or target is None or price <= 0:
            return None
        return round((target - price) / price * 100.0, 2)

    @staticmethod
    def _risk_reward(price: Optional[float], stop: Optional[float], target: Optional[float]) -> Optional[float]:
        if price is None or stop is None or target is None:
            return None
        risk_distance = abs(price - stop)
        if risk_distance == 0:
            return None
        return round(abs(target - price) / risk_distance, 2)

    @staticmethod
    def _build_invalidation(
        decision: Decision,
        direction: int,
        entry_low: Optional[float],
        entry_high: Optional[float],
        stop_loss: Optional[float],
        target_1: Optional[float],
    ) -> list:
        if decision not in (Decision.STRONG_BUY_CANDIDATE, Decision.BUY_CANDIDATE, Decision.WAIT_FOR_ENTRY, Decision.WATCH):
            return []
        conditions = []
        if stop_loss is not None:
            conditions.append(f"إغلاق السعر دون {stop_loss:.2f} يُبطل الفرصة ويستدعي إعادة التقييم.")
        if direction > 0 and entry_high is not None:
            conditions.append(f"تجاوز السعر {entry_high:.2f} دون اختراق حقيقي مؤكد يجعل الدخول مطاردة للسعر لا يُنصح بها.")
        if target_1 is not None:
            conditions.append("تغيّر جوهري في الاتجاه الفني (مثل كسر الاتجاه الصاعد) قبل بلوغ الهدف الأول يُضعف الفرضية.")
        return conditions
