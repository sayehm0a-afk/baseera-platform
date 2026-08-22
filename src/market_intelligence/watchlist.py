"""WatchlistEngine: turns one scan's `SymbolScanOutcome`s into the nine
requested watchlists.

Declarative, same discipline as `ranking.py`: every category is one
`_WatchlistRule` (predicate, reason, sort key) applied by a single
shared builder -- no category has its own hand-written filter/sort/
entry-building copy. Every rule reads only already-computed fields
(RSI/ADX/Bollinger from `TechnicalAnalysisEngine`, dividend yield from
`FundamentalAnalysisEngine`, recommendation/risk/time-horizon from
`AIDecisionEngine`) -- no indicator or ratio is computed here.

Watchlists are computed on read, not persisted -- the same reasoning
`ranking.py`'s module docstring and
domain/models/symbol_intelligence_record.py give for rankings applies
identically here.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional

from src.analysis.decision.types import RiskLevel, TimeHorizon
from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.config import (
    get_dividend_yield_threshold,
    get_momentum_adx_threshold,
    get_overbought_rsi_threshold,
    get_oversold_rsi_threshold,
    get_watchlist_max_size,
)
from src.market_intelligence.publication_gate import is_publishable
from src.market_intelligence.types import SymbolScanOutcome, WatchlistCategory, WatchlistEntry, WatchlistResult

_BUY_LIKE = {Recommendation.BUY, Recommendation.STRONG_BUY}
_SELL_LIKE = {Recommendation.SELL, Recommendation.STRONG_SELL}
_LOW_MEDIUM_RISK = {RiskLevel.LOW, RiskLevel.MEDIUM}
_HIGH_RISK = {RiskLevel.HIGH, RiskLevel.VERY_HIGH}

RISK_LEVEL_LABELS_AR = {
    RiskLevel.LOW: "منخفضة",
    RiskLevel.MEDIUM: "متوسطة",
    RiskLevel.HIGH: "عالية",
    RiskLevel.VERY_HIGH: "عالية جداً",
}


def _successful(outcome: SymbolScanOutcome) -> bool:
    """See ranking.py's `_successful` -- same real-evidence defect
    (symbol 2210, latest_price=0.0, no technical leg) and same fix:
    every watchlist is price- or indicator-derived, so a symbol with
    no valid price must never appear in any of them."""
    return (
        outcome.success
        and outcome.report is not None
        and outcome.latest_price is not None
        and outcome.latest_price > 0
    )


@dataclass(frozen=True)
class _WatchlistRule:
    # See ranking.py's `_FilterSortRule.predicate` for why every
    # predicate takes `calibrated_confidences` (symbol -> calibrated
    # 0-1 success probability) even when it doesn't use it -- a single
    # uniform signature the shared build() loop can call the same way.
    predicate: Callable[[SymbolScanOutcome, Dict[str, float]], bool]
    reason_fn: Callable[[SymbolScanOutcome], str]
    key_fn: Callable[[SymbolScanOutcome], float]
    reverse: bool


def _momentum_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return (
        _successful(o)
        and o.recommendation in (_BUY_LIKE | _SELL_LIKE)
        and o.adx is not None
        and o.adx >= get_momentum_adx_threshold()
    )


def _investment_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return (
        _successful(o)
        and o.recommendation in _BUY_LIKE
        and o.time_horizon is TimeHorizon.LONG_TERM
        and o.risk_level in _LOW_MEDIUM_RISK
        and is_publishable(o, cc.get(o.symbol))
    )


def _swing_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return (
        _successful(o) and o.recommendation in _BUY_LIKE and o.time_horizon is TimeHorizon.SHORT_TERM
        and is_publishable(o, cc.get(o.symbol))
    )


def _high_risk_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return _successful(o) and o.risk_level in _HIGH_RISK


def _dividend_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return _successful(o) and o.dividend_yield is not None and o.dividend_yield >= get_dividend_yield_threshold()


def _recovery_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return (
        _successful(o)
        and o.recommendation in _BUY_LIKE
        and o.rsi is not None
        and o.rsi < get_oversold_rsi_threshold()
        and is_publishable(o, cc.get(o.symbol))
    )


def _breakout_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return (
        _successful(o)
        and o.latest_price is not None
        and o.bollinger_upper is not None
        and o.latest_price > o.bollinger_upper
        and o.adx is not None
        and o.adx >= get_momentum_adx_threshold()
    )


def _oversold_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return (
        _successful(o)
        and o.rsi is not None
        and o.rsi < get_oversold_rsi_threshold()
        and o.recommendation is not Recommendation.STRONG_SELL
    )


def _overbought_predicate(o: SymbolScanOutcome, cc: Dict[str, float]) -> bool:
    return _successful(o) and o.rsi is not None and o.rsi > get_overbought_rsi_threshold()


# Pre-launch safety fix (2026-08-22, Priority 2): every reason_fn below
# was raw English -- a direct, presentation-only translation (each
# string is a template over already-computed values, no new
# classification/decision logic) since `entry.reason` is the only
# consumer of this text on the consumer-facing Watchlist page.
_RULES: Dict[WatchlistCategory, _WatchlistRule] = {
    WatchlistCategory.MOMENTUM: _WatchlistRule(
        _momentum_predicate, lambda o: f"مؤشر الاتجاه المتوسط (ADX) عند {o.adx:.1f} يشير إلى اتجاه قوي وراسخ.",
        lambda o: o.adx, True,
    ),
    WatchlistCategory.INVESTMENT: _WatchlistRule(
        _investment_predicate,
        lambda o: "توصية شراء، أفق استثماري طويل الأجل، مخاطرة منخفضة/متوسطة -- مرشح لمركز استثماري أساسي.",
        lambda o: o.confidence, True,
    ),
    WatchlistCategory.SWING: _WatchlistRule(
        _swing_predicate, lambda o: "توصية شراء بأفق قصير الأجل -- مرشح لصفقة تكتيكية.",
        lambda o: o.confidence, True,
    ),
    WatchlistCategory.HIGH_RISK: _WatchlistRule(
        _high_risk_predicate, lambda o: f"مستوى المخاطرة المقيّم: {RISK_LEVEL_LABELS_AR.get(o.risk_level, o.risk_level.value)}.",
        lambda o: o.confidence, True,
    ),
    WatchlistCategory.DIVIDEND: _WatchlistRule(
        _dividend_predicate, lambda o: f"عائد التوزيعات عند {o.dividend_yield * 100:.2f}%.",
        lambda o: o.dividend_yield, True,
    ),
    WatchlistCategory.RECOVERY: _WatchlistRule(
        _recovery_predicate,
        lambda o: f"مؤشر القوة النسبية (RSI) عند {o.rsi:.1f} (تشبع بيعي) مع توصية شراء -- تعافٍ محتمل.",
        lambda o: o.rsi, False,
    ),
    WatchlistCategory.BREAKOUT_CANDIDATES: _WatchlistRule(
        _breakout_predicate,
        lambda o: f"السعر ({o.latest_price:.2f}) اخترق النطاق العلوي لبولينجر ({o.bollinger_upper:.2f}) مع ADX عند {o.adx:.1f}.",
        lambda o: o.adx, True,
    ),
    WatchlistCategory.OVERSOLD_OPPORTUNITIES: _WatchlistRule(
        _oversold_predicate, lambda o: f"مؤشر القوة النسبية (RSI) عند {o.rsi:.1f} -- منطقة تشبع بيعي.",
        lambda o: o.rsi, False,
    ),
    WatchlistCategory.OVERBOUGHT_WARNINGS: _WatchlistRule(
        _overbought_predicate, lambda o: f"مؤشر القوة النسبية (RSI) عند {o.rsi:.1f} -- منطقة تشبع شرائي.",
        lambda o: o.rsi, True,
    ),
}


class WatchlistEngine:
    def build(
        self,
        outcomes: List[SymbolScanOutcome],
        calibrated_confidences: Optional[Dict[str, float]] = None,
    ) -> Dict[WatchlistCategory, WatchlistResult]:
        """See ranking.py's `RankingEngine.rank()` docstring for what
        `calibrated_confidences` is and why it must come from the
        caller (src.api.routes.market, via src.ai_evolution.
        confidence_calibration.compute_calibrated_confidences)."""
        generated_at = datetime.now(timezone.utc)
        max_size = get_watchlist_max_size()
        calibrated_confidences = calibrated_confidences or {}
        results: Dict[WatchlistCategory, WatchlistResult] = {}

        for category, rule in _RULES.items():
            matching = [o for o in outcomes if rule.predicate(o, calibrated_confidences)]
            matching.sort(key=rule.key_fn, reverse=rule.reverse)
            entries = [
                WatchlistEntry(
                    symbol=o.symbol,
                    sector=o.sector,
                    recommendation=o.recommendation.value if o.recommendation else None,
                    confidence=o.confidence,
                    reason=rule.reason_fn(o),
                )
                for o in matching[:max_size]
            ]
            results[category] = WatchlistResult(category=category, entries=entries, generated_at=generated_at)

        return results
