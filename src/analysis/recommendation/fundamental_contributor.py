"""FundamentalScoreContributor: turns one FundamentalAnalysisEngine
result into a 0-100 bullishness score, a confidence, and the signals
behind it.

Reads exclusively from `FundamentalAnalysisResult`'s named ratio
properties (never recomputes a ratio, never touches FundamentalFacts
directly) -- a pure consumer of M2.3's already-computed output. Eight
ratios across profitability, liquidity, leverage, valuation, and
growth drive the score; any ratio that is `None` (a normal, disclosed
outcome for real-world financial statements -- see RatioOutput's own
docstring) is simply skipped, lowering this module's confidence rather
than raising an error.
"""

from typing import List, Optional, Tuple

from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisResult
from src.analysis.recommendation.types import AnalysisContext, ScoreContribution, Signal, SignalDirection

_CORE_SIGNAL_SLOTS = 8


def _bucket(
    value: float,
    high: float,
    low: float,
    high_points: float,
    mid_points: float,
    low_points: float,
    name: str,
    high_desc: str,
    mid_desc: str,
    low_desc: str,
) -> Tuple[float, Signal]:
    """A ratio is "good" above `high`, "bad" below `low`, and neutral
    in between -- the shape shared by every ratio scored below."""
    if value >= high:
        return high_points, Signal(
            name=name, description=high_desc, direction=SignalDirection.BULLISH,
            source="fundamental", impact=high_points,
        )
    if value <= low:
        return low_points, Signal(
            name=name, description=low_desc, direction=SignalDirection.BEARISH,
            source="fundamental", impact=low_points,
        )
    return mid_points, Signal(
        name=name, description=mid_desc, direction=SignalDirection.NEUTRAL,
        source="fundamental", impact=mid_points,
    )


def _score_roe(roe: float) -> Tuple[float, Signal]:
    return _bucket(
        roe, high=0.15, low=0.05, high_points=10.0, mid_points=3.0, low_points=-8.0,
        name="return_on_equity",
        high_desc=f"Return on Equity ({roe:.1%}) is strong (>=15%).",
        mid_desc=f"Return on Equity ({roe:.1%}) is moderate.",
        low_desc=f"Return on Equity ({roe:.1%}) is weak (<=5%).",
    )


def _score_net_margin(margin: float) -> Tuple[float, Signal]:
    return _bucket(
        margin, high=0.10, low=0.0, high_points=6.0, mid_points=2.0, low_points=-8.0,
        name="net_profit_margin",
        high_desc=f"Net profit margin ({margin:.1%}) is healthy (>=10%).",
        mid_desc=f"Net profit margin ({margin:.1%}) is positive but thin.",
        low_desc=f"Net profit margin ({margin:.1%}) is zero or negative.",
    )


def _score_current_ratio(ratio: float) -> Tuple[float, Signal]:
    return _bucket(
        ratio, high=1.5, low=1.0, high_points=5.0, mid_points=1.0, low_points=-6.0,
        name="current_ratio",
        high_desc=f"Current ratio ({ratio:.2f}) shows healthy short-term liquidity (>=1.5).",
        mid_desc=f"Current ratio ({ratio:.2f}) is adequate.",
        low_desc=f"Current ratio ({ratio:.2f}) is below 1.0 -- possible liquidity risk.",
    )


def _score_debt_to_equity(ratio: float) -> Tuple[float, Signal]:
    # Lower is better for leverage, so the bucket direction is inverted
    # relative to the ratios above: "good" is a *low* value.
    if ratio <= 1.0:
        return 5.0, Signal(
            name="debt_to_equity",
            description=f"Debt-to-equity ({ratio:.2f}) is conservative (<=1.0).",
            direction=SignalDirection.BULLISH, source="fundamental", impact=5.0,
        )
    if ratio >= 2.0:
        return -8.0, Signal(
            name="debt_to_equity",
            description=f"Debt-to-equity ({ratio:.2f}) is high (>=2.0) -- elevated leverage risk.",
            direction=SignalDirection.BEARISH, source="fundamental", impact=-8.0,
        )
    return -1.0, Signal(
        name="debt_to_equity",
        description=f"Debt-to-equity ({ratio:.2f}) is moderate.",
        direction=SignalDirection.NEUTRAL, source="fundamental", impact=-1.0,
    )


def _score_pe(pe: float) -> Optional[Tuple[float, Signal]]:
    if pe <= 0:
        return None  # a loss-making P/E is not meaningful, not "bad"
    if pe < 15:
        return 6.0, Signal(
            name="price_to_earnings",
            description=f"P/E ({pe:.1f}) is attractively low (<15).",
            direction=SignalDirection.BULLISH, source="fundamental", impact=6.0,
        )
    if pe > 25:
        return -6.0, Signal(
            name="price_to_earnings",
            description=f"P/E ({pe:.1f}) is rich (>25).",
            direction=SignalDirection.BEARISH, source="fundamental", impact=-6.0,
        )
    return 0.0, Signal(
        name="price_to_earnings",
        description=f"P/E ({pe:.1f}) is in a moderate range.",
        direction=SignalDirection.NEUTRAL, source="fundamental", impact=0.0,
    )


def _score_pb(pb: float) -> Optional[Tuple[float, Signal]]:
    if pb <= 0:
        return None
    if pb < 1.5:
        return 4.0, Signal(
            name="price_to_book",
            description=f"P/B ({pb:.2f}) is attractively low (<1.5).",
            direction=SignalDirection.BULLISH, source="fundamental", impact=4.0,
        )
    if pb > 3.0:
        return -5.0, Signal(
            name="price_to_book",
            description=f"P/B ({pb:.2f}) is rich (>3.0).",
            direction=SignalDirection.BEARISH, source="fundamental", impact=-5.0,
        )
    return 0.0, Signal(
        name="price_to_book",
        description=f"P/B ({pb:.2f}) is in a moderate range.",
        direction=SignalDirection.NEUTRAL, source="fundamental", impact=0.0,
    )


def _score_revenue_growth(growth: float) -> Tuple[float, Signal]:
    return _bucket(
        growth, high=0.10, low=0.0, high_points=6.0, mid_points=2.0, low_points=-6.0,
        name="revenue_growth",
        high_desc=f"Revenue growth ({growth:.1%}) is strong (>=10%).",
        mid_desc=f"Revenue growth ({growth:.1%}) is positive but modest.",
        low_desc=f"Revenue declined ({growth:.1%}) year-over-year.",
    )


def _score_eps_growth(growth: float) -> Tuple[float, Signal]:
    return _bucket(
        growth, high=0.10, low=0.0, high_points=6.0, mid_points=2.0, low_points=-6.0,
        name="eps_growth",
        high_desc=f"EPS growth ({growth:.1%}) is strong (>=10%).",
        mid_desc=f"EPS growth ({growth:.1%}) is positive but modest.",
        low_desc=f"EPS declined ({growth:.1%}) year-over-year.",
    )


class FundamentalScoreContributor:
    """The fundamental-analysis leg of the Recommendation & Confidence
    Engine. `default_weight` and everything else about this class can
    be tuned or replaced without RecommendationEngine changing."""

    name = "fundamental"

    def __init__(self, weight: float = 0.5):
        self.default_weight = weight

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        result: Optional[FundamentalAnalysisResult] = context.fundamental_result
        if result is None:
            return ScoreContribution(
                source=self.name,
                score=None,
                weight=0.0,
                confidence=0.0,
                signals=[],
                notes="No fundamental analysis result was available for this symbol.",
            )

        points = 0.0
        signals: List[Signal] = []
        computed = 0

        for value, scorer in (
            (result.return_on_equity, _score_roe),
            (result.net_profit_margin, _score_net_margin),
            (result.current_ratio, _score_current_ratio),
            (result.debt_to_equity, _score_debt_to_equity),
            (result.revenue_growth, _score_revenue_growth),
            (result.eps_growth, _score_eps_growth),
        ):
            if value is None:
                continue
            computed += 1
            pts, sig = scorer(value)
            points += pts
            signals.append(sig)

        for value, scorer in (
            (result.price_to_earnings, _score_pe),
            (result.price_to_book, _score_pb),
        ):
            if value is None:
                continue
            outcome = scorer(value)
            if outcome is None:
                continue
            computed += 1
            pts, sig = outcome
            points += pts
            signals.append(sig)

        score = max(0.0, min(100.0, 50.0 + points))
        confidence = round(100.0 * (computed / _CORE_SIGNAL_SLOTS), 1)

        return ScoreContribution(
            source=self.name,
            score=round(score, 1),
            weight=self.default_weight,
            confidence=confidence,
            signals=signals,
        )
