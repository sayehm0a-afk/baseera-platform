"""AlertEngine: turns one scan's outcomes, change events, and sector
summaries into `Alert` *objects* -- generation only. There is no
notification/delivery mechanism anywhere in this codebase (email,
push, webhook, SMS); wiring one up is explicitly out of scope for this
milestone (see docs/MARKET_INTELLIGENCE.md).
"""

from datetime import datetime, timezone
from typing import Dict, List

from src.market_intelligence.config import (
    get_alert_confidence_threshold,
    get_alert_risk_spike_confidence_drop,
    get_sector_rotation_momentum_threshold,
)
from src.market_intelligence.ordinals import recommendation_rank_of_value, risk_rank_of_value
from src.market_intelligence.types import (
    Alert,
    AlertSeverity,
    AlertType,
    ChangeDetectionResult,
    ChangeType,
    SectorSummary,
    SymbolScanOutcome,
)

_BUY_LIKE = {"BUY", "STRONG_BUY"}
_SELL_LIKE = {"SELL", "STRONG_SELL"}

# Pre-launch safety fix (2026-08-22, Priority 2): Arabic labels for the
# raw Recommendation/RiskLevel enum tokens this module embeds into
# generated alert text -- presentation only, does not change which
# alert fires or its severity/type classification.
_RECOMMENDATION_LABELS_AR = {
    "STRONG_BUY": "شراء قوي",
    "BUY": "شراء",
    "HOLD": "احتفاظ",
    "SELL": "بيع",
    "STRONG_SELL": "بيع قوي",
}

_RISK_LABELS_AR = {
    "LOW": "منخفضة",
    "MEDIUM": "متوسطة",
    "HIGH": "عالية",
    "VERY_HIGH": "عالية جداً",
}


def _recommendation_ar(value: str | None) -> str:
    if value is None:
        return "غير مصنّف"
    return _RECOMMENDATION_LABELS_AR.get(value, value)


def _risk_ar(value: str | None) -> str:
    if value is None:
        return "غير معروفة"
    return _RISK_LABELS_AR.get(value, value)


def _successful(outcome: SymbolScanOutcome) -> bool:
    return outcome.success and outcome.report is not None


class AlertEngine:
    def generate(
        self,
        outcomes: List[SymbolScanOutcome],
        change_result: ChangeDetectionResult,
        sector_summaries: List[SectorSummary],
    ) -> List[Alert]:
        generated_at = datetime.now(timezone.utc)
        by_symbol: Dict[str, SymbolScanOutcome] = {o.symbol: o for o in outcomes}

        alerts: List[Alert] = []
        alerts.extend(self._recommendation_alerts(change_result, generated_at))
        alerts.extend(self._confidence_alerts(outcomes, generated_at))
        alerts.extend(self._target_reached_alerts(outcomes, generated_at))
        alerts.extend(self._risk_spike_alerts(change_result, by_symbol, generated_at))
        alerts.extend(self._sector_rotation_alerts(sector_summaries, generated_at))
        return alerts

    @staticmethod
    def _recommendation_alerts(change_result: ChangeDetectionResult, generated_at: datetime) -> List[Alert]:
        alerts = []
        for event in change_result.events:
            if event.change_type is not ChangeType.RECOMMENDATION_CHANGE:
                continue
            new_rank = recommendation_rank_of_value(event.new_value)
            previous_rank = recommendation_rank_of_value(event.previous_value)

            if event.new_value == "STRONG_BUY" and event.previous_value != "STRONG_BUY":
                alerts.append(
                    Alert(
                        alert_type=AlertType.NEW_STRONG_BUY, severity=AlertSeverity.INFO,
                        symbol=event.symbol, sector=None,
                        message=f"{event.symbol} أصبح مصنّفاً {_recommendation_ar('STRONG_BUY')} (كان {_recommendation_ar(event.previous_value)}).",
                        generated_at=generated_at,
                    )
                )
            elif new_rank > previous_rank:
                alerts.append(
                    Alert(
                        alert_type=AlertType.RECOMMENDATION_UPGRADED, severity=AlertSeverity.INFO,
                        symbol=event.symbol, sector=None,
                        message=f"{event.symbol} تمت ترقيته من {_recommendation_ar(event.previous_value)} إلى {_recommendation_ar(event.new_value)}.",
                        generated_at=generated_at,
                    )
                )
            elif new_rank < previous_rank:
                alerts.append(
                    Alert(
                        alert_type=AlertType.RECOMMENDATION_DOWNGRADED, severity=AlertSeverity.WARNING,
                        symbol=event.symbol, sector=None,
                        message=f"{event.symbol} تم تخفيضه من {_recommendation_ar(event.previous_value)} إلى {_recommendation_ar(event.new_value)}.",
                        generated_at=generated_at,
                    )
                )
        return alerts

    @staticmethod
    def _confidence_alerts(outcomes: List[SymbolScanOutcome], generated_at: datetime) -> List[Alert]:
        threshold = get_alert_confidence_threshold()
        return [
            Alert(
                alert_type=AlertType.CONFIDENCE_ABOVE_THRESHOLD, severity=AlertSeverity.INFO,
                symbol=o.symbol, sector=o.sector,
                message=f"{o.symbol}: درجة الثقة عند {o.confidence:.1f}% (>= الحد الأدنى {threshold:.1f}%).",
                generated_at=generated_at,
            )
            for o in outcomes
            if _successful(o) and o.confidence is not None and o.confidence >= threshold
        ]

    @staticmethod
    def _target_reached_alerts(outcomes: List[SymbolScanOutcome], generated_at: datetime) -> List[Alert]:
        alerts = []
        for o in outcomes:
            if not _successful(o) or o.latest_price is None or o.target_price is None or o.recommendation is None:
                continue
            recommendation = o.recommendation.value
            reached = (
                (recommendation in _BUY_LIKE and o.latest_price >= o.target_price)
                or (recommendation in _SELL_LIKE and o.latest_price <= o.target_price)
            )
            if reached:
                alerts.append(
                    Alert(
                        alert_type=AlertType.TARGET_REACHED, severity=AlertSeverity.INFO,
                        symbol=o.symbol, sector=o.sector,
                        message=f"{o.symbol} بلغ سعره المستهدف {o.target_price:.2f} (آخر سعر: {o.latest_price:.2f}).",
                        generated_at=generated_at,
                    )
                )
        return alerts

    @staticmethod
    def _risk_spike_alerts(
        change_result: ChangeDetectionResult, by_symbol: Dict[str, SymbolScanOutcome], generated_at: datetime
    ) -> List[Alert]:
        confidence_deltas = {
            e.symbol: e.delta for e in change_result.events if e.change_type is ChangeType.CONFIDENCE_CHANGE
        }
        drop_threshold = get_alert_risk_spike_confidence_drop()

        alerts = []
        for event in change_result.events:
            if event.change_type is not ChangeType.RISK_CHANGE:
                continue
            if risk_rank_of_value(event.new_value) <= risk_rank_of_value(event.previous_value):
                continue
            confidence_delta = confidence_deltas.get(event.symbol)
            if confidence_delta is None or confidence_delta > -drop_threshold:
                continue
            outcome = by_symbol.get(event.symbol)
            severity = AlertSeverity.CRITICAL if confidence_delta <= -2 * drop_threshold else AlertSeverity.WARNING
            alerts.append(
                Alert(
                    alert_type=AlertType.RISK_SPIKE, severity=severity,
                    symbol=event.symbol, sector=outcome.sector if outcome else None,
                    message=(
                        f"ارتفعت مخاطرة {event.symbol} من {_risk_ar(event.previous_value)} إلى {_risk_ar(event.new_value)} "
                        f"مع انخفاض في درجة الثقة بمقدار {abs(confidence_delta):.1f} نقطة."
                    ),
                    generated_at=generated_at,
                )
            )
        return alerts

    @staticmethod
    def _sector_rotation_alerts(sector_summaries: List[SectorSummary], generated_at: datetime) -> List[Alert]:
        threshold = get_sector_rotation_momentum_threshold()
        alerts = []
        for summary in sector_summaries:
            if summary.momentum is None or abs(summary.momentum) < threshold:
                continue
            direction_ar = "إلى" if summary.momentum > 0 else "خارج"
            alerts.append(
                Alert(
                    alert_type=AlertType.SECTOR_ROTATION, severity=AlertSeverity.INFO,
                    symbol=None, sector=summary.sector,
                    message=f"يبدو أن هناك تدفقاً لرؤوس الأموال {direction_ar} قطاع {summary.sector} (الزخم {summary.momentum:+.1f}).",
                    generated_at=generated_at,
                )
            )
        return alerts
