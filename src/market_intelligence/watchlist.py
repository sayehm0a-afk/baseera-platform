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
from typing import Callable, Dict, List

from src.analysis.decision.types import RiskLevel, TimeHorizon
from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.config import (
    get_dividend_yield_threshold,
    get_momentum_adx_threshold,
    get_overbought_rsi_threshold,
    get_oversold_rsi_threshold,
    get_watchlist_max_size,
)
from src.market_intelligence.types import SymbolScanOutcome, WatchlistCategory, WatchlistEntry, WatchlistResult

_BUY_LIKE = {Recommendation.BUY, Recommendation.STRONG_BUY}
_SELL_LIKE = {Recommendation.SELL, Recommendation.STRONG_SELL}
_LOW_MEDIUM_RISK = {RiskLevel.LOW, RiskLevel.MEDIUM}
_HIGH_RISK = {RiskLevel.HIGH, RiskLevel.VERY_HIGH}


def _successful(outcome: SymbolScanOutcome) -> bool:
    return outcome.success and outcome.report is not None


@dataclass(frozen=True)
class _WatchlistRule:
    predicate: Callable[[SymbolScanOutcome], bool]
    reason_fn: Callable[[SymbolScanOutcome], str]
    key_fn: Callable[[SymbolScanOutcome], float]
    reverse: bool


def _momentum_predicate(o: SymbolScanOutcome) -> bool:
    return (
        _successful(o)
        and o.recommendation in (_BUY_LIKE | _SELL_LIKE)
        and o.adx is not None
        and o.adx >= get_momentum_adx_threshold()
    )


def _investment_predicate(o: SymbolScanOutcome) -> bool:
    return (
        _successful(o)
        and o.recommendation in _BUY_LIKE
        and o.time_horizon is TimeHorizon.LONG_TERM
        and o.risk_level in _LOW_MEDIUM_RISK
    )


def _swing_predicate(o: SymbolScanOutcome) -> bool:
    return _successful(o) and o.recommendation in _BUY_LIKE and o.time_horizon is TimeHorizon.SHORT_TERM


def _high_risk_predicate(o: SymbolScanOutcome) -> bool:
    return _successful(o) and o.risk_level in _HIGH_RISK


def _dividend_predicate(o: SymbolScanOutcome) -> bool:
    return _successful(o) and o.dividend_yield is not None and o.dividend_yield >= get_dividend_yield_threshold()


def _recovery_predicate(o: SymbolScanOutcome) -> bool:
    return (
        _successful(o)
        and o.recommendation in _BUY_LIKE
        and o.rsi is not None
        and o.rsi < get_oversold_rsi_threshold()
    )


def _breakout_predicate(o: SymbolScanOutcome) -> bool:
    return (
        _successful(o)
        and o.latest_price is not None
        and o.bollinger_upper is not None
        and o.latest_price > o.bollinger_upper
        and o.adx is not None
        and o.adx >= get_momentum_adx_threshold()
    )


def _oversold_predicate(o: SymbolScanOutcome) -> bool:
    return (
        _successful(o)
        and o.rsi is not None
        and o.rsi < get_oversold_rsi_threshold()
        and o.recommendation is not Recommendation.STRONG_SELL
    )


def _overbought_predicate(o: SymbolScanOutcome) -> bool:
    return _successful(o) and o.rsi is not None and o.rsi > get_overbought_rsi_threshold()


_RULES: Dict[WatchlistCategory, _WatchlistRule] = {
    WatchlistCategory.MOMENTUM: _WatchlistRule(
        _momentum_predicate, lambda o: f"ADX at {o.adx:.1f} indicates a strong, established trend.",
        lambda o: o.adx, True,
    ),
    WatchlistCategory.INVESTMENT: _WatchlistRule(
        _investment_predicate,
        lambda o: "Buy-rated, long-term horizon, low/medium risk -- a candidate for a core holding.",
        lambda o: o.confidence, True,
    ),
    WatchlistCategory.SWING: _WatchlistRule(
        _swing_predicate, lambda o: "Buy-rated with a short-term horizon -- a tactical trade candidate.",
        lambda o: o.confidence, True,
    ),
    WatchlistCategory.HIGH_RISK: _WatchlistRule(
        _high_risk_predicate, lambda o: f"Risk assessed as {o.risk_level.value.title()}.",
        lambda o: o.confidence, True,
    ),
    WatchlistCategory.DIVIDEND: _WatchlistRule(
        _dividend_predicate, lambda o: f"Dividend yield at {o.dividend_yield * 100:.2f}%.",
        lambda o: o.dividend_yield, True,
    ),
    WatchlistCategory.RECOVERY: _WatchlistRule(
        _recovery_predicate,
        lambda o: f"RSI at {o.rsi:.1f} (oversold) with a Buy rating -- a potential recovery.",
        lambda o: o.rsi, False,
    ),
    WatchlistCategory.BREAKOUT_CANDIDATES: _WatchlistRule(
        _breakout_predicate,
        lambda o: f"Price ({o.latest_price:.2f}) broke above the upper Bollinger Band ({o.bollinger_upper:.2f}) with ADX at {o.adx:.1f}.",
        lambda o: o.adx, True,
    ),
    WatchlistCategory.OVERSOLD_OPPORTUNITIES: _WatchlistRule(
        _oversold_predicate, lambda o: f"RSI at {o.rsi:.1f} -- oversold territory.",
        lambda o: o.rsi, False,
    ),
    WatchlistCategory.OVERBOUGHT_WARNINGS: _WatchlistRule(
        _overbought_predicate, lambda o: f"RSI at {o.rsi:.1f} -- overbought territory.",
        lambda o: o.rsi, True,
    ),
}


class WatchlistEngine:
    def build(self, outcomes: List[SymbolScanOutcome]) -> Dict[WatchlistCategory, WatchlistResult]:
        generated_at = datetime.now(timezone.utc)
        max_size = get_watchlist_max_size()
        results: Dict[WatchlistCategory, WatchlistResult] = {}

        for category, rule in _RULES.items():
            matching = [o for o in outcomes if rule.predicate(o)]
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
