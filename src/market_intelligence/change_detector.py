"""ChangeDetector: diffs the current scan's `SymbolScanOutcome`s
against the previous scan's persisted `SymbolIntelligenceRecord` rows.

Reads `previous_records` (keyed by symbol) rather than re-running
anything -- the previous scan's numbers are already durable
(SymbolIntelligenceRecord is this layer's single source of truth, see
that model's docstring), so a diff is a pure comparison, never a
second analysis pass over historical data.
"""

from datetime import datetime, timezone
from typing import Dict, List, Optional

from src.domain.models import SymbolIntelligenceRecord
from src.market_intelligence.config import (
    get_confidence_change_threshold,
    get_score_change_threshold,
    get_target_price_change_threshold_pct,
)
from src.market_intelligence.types import ChangeDetectionResult, ChangeEvent, ChangeType, SymbolScanOutcome


def _successful(outcome: SymbolScanOutcome) -> bool:
    return outcome.success and outcome.report is not None


class ChangeDetector:
    def detect(
        self,
        current_outcomes: List[SymbolScanOutcome],
        previous_records: Dict[str, SymbolIntelligenceRecord],
        previous_scan_run_id: Optional[int],
    ) -> ChangeDetectionResult:
        detected_at = datetime.now(timezone.utc)
        current_successful = {o.symbol: o for o in current_outcomes if _successful(o)}

        events: List[ChangeEvent] = []
        for symbol, outcome in current_successful.items():
            previous = previous_records.get(symbol)
            if previous is None:
                continue
            events.extend(self._diff_one(symbol, outcome, previous, detected_at))

        new_symbols = sorted(set(current_successful) - set(previous_records))
        removed_symbols = sorted(set(previous_records) - set(current_successful))

        return ChangeDetectionResult(
            events=events,
            new_symbols=new_symbols,
            removed_symbols=removed_symbols,
            previous_scan_run_id=previous_scan_run_id,
        )

    @staticmethod
    def _diff_one(
        symbol: str,
        outcome: SymbolScanOutcome,
        previous: SymbolIntelligenceRecord,
        detected_at: datetime,
    ) -> List[ChangeEvent]:
        events: List[ChangeEvent] = []

        new_recommendation = outcome.recommendation.value if outcome.recommendation else None
        previous_recommendation = previous.recommendation.value if previous.recommendation else None
        if new_recommendation != previous_recommendation:
            events.append(
                ChangeEvent(
                    symbol=symbol, change_type=ChangeType.RECOMMENDATION_CHANGE,
                    previous_value=previous_recommendation, new_value=new_recommendation,
                    delta=None, detected_at=detected_at,
                )
            )

        confidence_delta = _delta(outcome.confidence, previous.confidence)
        if confidence_delta is not None and abs(confidence_delta) >= get_confidence_change_threshold():
            events.append(
                ChangeEvent(
                    symbol=symbol, change_type=ChangeType.CONFIDENCE_CHANGE,
                    previous_value=_fmt(previous.confidence), new_value=_fmt(outcome.confidence),
                    delta=confidence_delta, detected_at=detected_at,
                )
            )

        score_delta = _delta(outcome.final_score, previous.final_score)
        if score_delta is not None and abs(score_delta) >= get_score_change_threshold():
            events.append(
                ChangeEvent(
                    symbol=symbol, change_type=ChangeType.SCORE_CHANGE,
                    previous_value=_fmt(previous.final_score), new_value=_fmt(outcome.final_score),
                    delta=score_delta, detected_at=detected_at,
                )
            )

        target_delta = _delta(outcome.target_price, previous.target_price)
        previous_target = float(previous.target_price) if previous.target_price is not None else None
        if target_delta is not None and previous_target not in (None, 0) and abs(target_delta / previous_target) * 100.0 >= get_target_price_change_threshold_pct():
            events.append(
                ChangeEvent(
                    symbol=symbol, change_type=ChangeType.TARGET_PRICE_CHANGE,
                    previous_value=_fmt(previous.target_price), new_value=_fmt(outcome.target_price),
                    delta=target_delta, detected_at=detected_at,
                )
            )

        new_risk = outcome.risk_level.value if outcome.risk_level else None
        if new_risk != previous.risk_level:
            events.append(
                ChangeEvent(
                    symbol=symbol, change_type=ChangeType.RISK_CHANGE,
                    previous_value=previous.risk_level, new_value=new_risk,
                    delta=None, detected_at=detected_at,
                )
            )

        technical_delta = _delta(outcome.technical_score, previous.technical_score)
        if technical_delta is not None and abs(technical_delta) >= get_score_change_threshold():
            events.append(
                ChangeEvent(
                    symbol=symbol, change_type=ChangeType.TECHNICAL_CHANGE,
                    previous_value=_fmt(previous.technical_score), new_value=_fmt(outcome.technical_score),
                    delta=technical_delta, detected_at=detected_at,
                )
            )

        fundamental_delta = _delta(outcome.fundamental_score, previous.fundamental_score)
        if fundamental_delta is not None and abs(fundamental_delta) >= get_score_change_threshold():
            events.append(
                ChangeEvent(
                    symbol=symbol, change_type=ChangeType.FUNDAMENTAL_CHANGE,
                    previous_value=_fmt(previous.fundamental_score), new_value=_fmt(outcome.fundamental_score),
                    delta=fundamental_delta, detected_at=detected_at,
                )
            )

        return events


def _delta(new_value, previous_value) -> Optional[float]:
    if new_value is None or previous_value is None:
        return None
    return round(float(new_value) - float(previous_value), 4)


def _fmt(value) -> Optional[str]:
    return None if value is None else str(float(value))
