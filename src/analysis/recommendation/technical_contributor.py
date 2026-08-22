"""TechnicalScoreContributor: turns one TechnicalAnalysisEngine result
into a 0-100 bullishness score, a confidence, and the signals behind
it.

Reads exclusively from `TechnicalAnalysisResult` (never recomputes an
indicator, never touches a DataFrame) -- it is a pure consumer of
M2.2's already-computed output, exactly like the existing `/technical`
route's `result.latest_snapshot()` call. Six core, always-computable
indicators (RSI, MACD, Supertrend, EMA-vs-SMA momentum, OBV trend,
volume trend) drive the score; ADX (trend strength, not direction)
only adjusts confidence; candlestick patterns add a capped score
contribution; Bollinger Band *width trend* (widening/narrowing over
the last 10 sessions) is reported as an informational, zero-impact
signal here specifically.

This is deliberately not the only place Bollinger Bands are read: a
different measurement of the same indicator -- the band's *width
ratio* relative to price, a point-in-time reading rather than a
trend -- is scored with real point impact by
`src.analysis.decision.contributors.risk_contributor.RiskScoreContributor`,
which does reach `InvestmentDecision.risk_level` and `final_score`
(see that module's own docstring). Phase 3's audit flagged this as a
potential documentation discrepancy between the two files; it is not
a functional bug -- the two contributors score two genuinely
different aspects of Bollinger Bands, each internally consistent and
already documented on its own side -- but this cross-reference is
added so nobody reading this file alone concludes Bollinger Bands
have zero score impact anywhere in the platform.
"""

from typing import List, Optional, Tuple

from src.analysis.recommendation.types import (
    AnalysisContext,
    ScoreContribution,
    Signal,
    SignalDirection,
)
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult

_CORE_SIGNAL_SLOTS = 7
_PATTERN_POINTS_PER_MATCH = 6.0
_PATTERN_POINTS_CAP = 12.0


def _score_stochastic(stochastic_latest: dict) -> Optional[Tuple[float, Signal]]:
    percent_k = stochastic_latest.get("percent_k") if stochastic_latest else None
    if percent_k is None:
        return None

    # Smaller point weights than RSI's -- Stochastic is highly correlated
    # with RSI (both are bounded momentum oscillators), so it must not
    # duplicate RSI's full weight in the blended score.
    if percent_k <= 20:
        return 10.0, Signal(
            name="stochastic",
            description=f"Stochastic %K={percent_k:.1f} is oversold (<=20), a bullish reversal signal.",
            direction=SignalDirection.BULLISH,
            source="technical",
            impact=10.0,
        )
    if percent_k >= 80:
        return -10.0, Signal(
            name="stochastic",
            description=f"Stochastic %K={percent_k:.1f} is overbought (>=80), a bearish reversal signal.",
            direction=SignalDirection.BEARISH,
            source="technical",
            impact=-10.0,
        )
    if percent_k > 50:
        return 4.0, Signal(
            name="stochastic",
            description=f"Stochastic %K={percent_k:.1f} is above 50, indicating bullish momentum.",
            direction=SignalDirection.BULLISH,
            source="technical",
            impact=4.0,
        )
    if percent_k < 50:
        return -4.0, Signal(
            name="stochastic",
            description=f"Stochastic %K={percent_k:.1f} is below 50, indicating bearish momentum.",
            direction=SignalDirection.BEARISH,
            source="technical",
            impact=-4.0,
        )
    return 0.0, Signal(
        name="stochastic",
        description="Stochastic %K=50.0 is exactly neutral.",
        direction=SignalDirection.NEUTRAL,
        source="technical",
        impact=0.0,
    )


def _score_rsi(rsi: float) -> Tuple[float, Signal]:
    if rsi <= 30:
        return 15.0, Signal(
            name="rsi_14",
            description=f"RSI(14)={rsi:.1f} is oversold (<=30), a bullish reversal signal.",
            direction=SignalDirection.BULLISH,
            source="technical",
            impact=15.0,
        )
    if rsi >= 70:
        return -15.0, Signal(
            name="rsi_14",
            description=f"RSI(14)={rsi:.1f} is overbought (>=70), a bearish reversal signal.",
            direction=SignalDirection.BEARISH,
            source="technical",
            impact=-15.0,
        )
    if rsi > 50:
        return 6.0, Signal(
            name="rsi_14",
            description=f"RSI(14)={rsi:.1f} is above 50, indicating bullish momentum.",
            direction=SignalDirection.BULLISH,
            source="technical",
            impact=6.0,
        )
    if rsi < 50:
        return -6.0, Signal(
            name="rsi_14",
            description=f"RSI(14)={rsi:.1f} is below 50, indicating bearish momentum.",
            direction=SignalDirection.BEARISH,
            source="technical",
            impact=-6.0,
        )
    return 0.0, Signal(
        name="rsi_14",
        description="RSI(14)=50.0 is exactly neutral.",
        direction=SignalDirection.NEUTRAL,
        source="technical",
        impact=0.0,
    )


def _score_macd(macd_latest: dict) -> Optional[Tuple[float, Signal]]:
    macd_line = macd_latest.get("macd_line")
    signal_line = macd_latest.get("signal_line")
    histogram = macd_latest.get("histogram")
    if macd_line is None or signal_line is None or histogram is None:
        return None

    if histogram > 0 and macd_line > signal_line:
        return 12.0, Signal(
            name="macd",
            description=(
                f"MACD line ({macd_line:.3f}) is above its signal line "
                f"({signal_line:.3f}) with a positive histogram -- bullish momentum."
            ),
            direction=SignalDirection.BULLISH,
            source="technical",
            impact=12.0,
        )
    if histogram < 0 and macd_line < signal_line:
        return -12.0, Signal(
            name="macd",
            description=(
                f"MACD line ({macd_line:.3f}) is below its signal line "
                f"({signal_line:.3f}) with a negative histogram -- bearish momentum."
            ),
            direction=SignalDirection.BEARISH,
            source="technical",
            impact=-12.0,
        )
    return 0.0, Signal(
        name="macd",
        description="MACD line and signal line are converging/crossing -- mixed momentum.",
        direction=SignalDirection.NEUTRAL,
        source="technical",
        impact=0.0,
    )


def _score_supertrend(supertrend_latest: dict) -> Optional[Tuple[float, Signal]]:
    direction = supertrend_latest.get("direction")
    if direction is None:
        return None
    if direction > 0:
        return 10.0, Signal(
            name="supertrend",
            description="Supertrend is in a bullish state (price above the trend line).",
            direction=SignalDirection.BULLISH,
            source="technical",
            impact=10.0,
        )
    if direction < 0:
        return -10.0, Signal(
            name="supertrend",
            description="Supertrend is in a bearish state (price below the trend line).",
            direction=SignalDirection.BEARISH,
            source="technical",
            impact=-10.0,
        )
    return 0.0, Signal(
        name="supertrend",
        description="Supertrend direction is flat.",
        direction=SignalDirection.NEUTRAL,
        source="technical",
        impact=0.0,
    )


def _score_ema_vs_sma(ema_20: Optional[float], sma_20: Optional[float]) -> Optional[Tuple[float, Signal]]:
    if ema_20 is None or sma_20 is None:
        return None
    if ema_20 > sma_20:
        return 8.0, Signal(
            name="ema_vs_sma",
            description=(
                f"EMA(20)={ema_20:.2f} is above SMA(20)={sma_20:.2f} -- recent price "
                "action is pulling the short-term average up."
            ),
            direction=SignalDirection.BULLISH,
            source="technical",
            impact=8.0,
        )
    if ema_20 < sma_20:
        return -8.0, Signal(
            name="ema_vs_sma",
            description=(
                f"EMA(20)={ema_20:.2f} is below SMA(20)={sma_20:.2f} -- recent price "
                "action is pulling the short-term average down."
            ),
            direction=SignalDirection.BEARISH,
            source="technical",
            impact=-8.0,
        )
    return 0.0, Signal(
        name="ema_vs_sma",
        description="EMA(20) and SMA(20) are equal.",
        direction=SignalDirection.NEUTRAL,
        source="technical",
        impact=0.0,
    )


def _series_trend_points(series, lookback: int, up_points: float, down_points: float):
    """Compares a series' latest non-null value against the value
    `lookback` non-null observations earlier. Returns None if there
    aren't enough non-null observations to compare."""
    non_null = series.dropna()
    if len(non_null) < 2:
        return None
    idx = min(lookback, len(non_null) - 1)
    current = non_null.iloc[-1]
    prior = non_null.iloc[-1 - idx]
    if current > prior:
        return up_points, SignalDirection.BULLISH, current, prior
    if current < prior:
        return down_points, SignalDirection.BEARISH, current, prior
    return 0.0, SignalDirection.NEUTRAL, current, prior


def _score_obv(result: TechnicalAnalysisResult) -> Optional[Tuple[float, Signal]]:
    outcome = _series_trend_points(result.obv, lookback=10, up_points=6.0, down_points=-6.0)
    if outcome is None:
        return None
    points, direction, current, prior = outcome
    verb = "rising (accumulation)" if points > 0 else "falling (distribution)" if points < 0 else "flat"
    return points, Signal(
        name="obv",
        description=f"On-Balance Volume is {verb} ({prior:.0f} -> {current:.0f}).",
        direction=direction,
        source="technical",
        impact=points,
    )


def _score_volume_trend(result: TechnicalAnalysisResult) -> Optional[Tuple[float, Signal]]:
    outcome = _series_trend_points(result.volume_sma_20, lookback=5, up_points=4.0, down_points=-4.0)
    if outcome is None:
        return None
    points, direction, current, prior = outcome
    verb = "increasing" if points > 0 else "decreasing" if points < 0 else "flat"
    return points, Signal(
        name="volume_sma_20",
        description=f"20-period average volume is {verb} ({prior:.0f} -> {current:.0f}).",
        direction=direction,
        source="technical",
        impact=points,
    )


def _score_patterns(result: TechnicalAnalysisResult) -> Tuple[float, List[Signal]]:
    matches = result.patterns
    if not matches:
        return 0.0, []
    latest_timestamp = max(match.timestamp for match in matches)
    latest_matches = [m for m in matches if m.timestamp == latest_timestamp]

    points = 0.0
    signals: List[Signal] = []
    for match in latest_matches:
        raw = _PATTERN_POINTS_PER_MATCH if match.bullish else -_PATTERN_POINTS_PER_MATCH
        capped = max(-_PATTERN_POINTS_CAP - points, min(_PATTERN_POINTS_CAP - points, raw))
        points += capped
        signals.append(
            Signal(
                name=f"pattern:{match.pattern_name}",
                description=(
                    f"Candlestick pattern '{match.pattern_name}' detected "
                    f"({'bullish' if match.bullish else 'bearish'})."
                ),
                direction=SignalDirection.BULLISH if match.bullish else SignalDirection.BEARISH,
                source="technical",
                impact=capped,
            )
        )
    return points, signals


def _bollinger_width_signal(result: TechnicalAnalysisResult) -> Optional[Signal]:
    """Always NEUTRAL, never added to `points` below -- purely
    informational (see this module's docstring for where Bollinger
    Band width *does* carry real score impact, in a different
    contributor)."""
    bollinger = result.bollinger
    upper = bollinger.upper.dropna()
    lower = bollinger.lower.dropna()
    middle = bollinger.middle.dropna()
    if len(upper) < 11 or len(lower) < 11 or len(middle) < 11:
        return None
    if middle.iloc[-1] == 0 or middle.iloc[-11] == 0:
        return None

    width_now = (upper.iloc[-1] - lower.iloc[-1]) / middle.iloc[-1]
    width_prior = (upper.iloc[-11] - lower.iloc[-11]) / middle.iloc[-11]
    if width_prior == 0:
        return None

    change = (width_now - width_prior) / width_prior
    if change >= 0.2:
        description = "Bollinger Bands are widening -- volatility is rising."
    elif change <= -0.2:
        description = "Bollinger Bands are narrowing (a squeeze) -- a breakout may be building."
    else:
        return None

    return Signal(
        name="bollinger_width",
        description=description,
        direction=SignalDirection.NEUTRAL,
        source="technical",
        impact=0.0,
    )


class TechnicalScoreContributor:
    """The technical-analysis leg of the Recommendation & Confidence
    Engine. `default_weight` and everything else about this class can
    be tuned or replaced without RecommendationEngine changing."""

    name = "technical"

    def __init__(self, weight: float = 0.5):
        self.default_weight = weight

    def contribute(self, context: AnalysisContext) -> ScoreContribution:
        result = context.technical_result
        if result is None:
            return ScoreContribution(
                source=self.name,
                score=None,
                weight=0.0,
                confidence=0.0,
                signals=[],
                notes="No technical analysis result was available for this symbol.",
            )

        points = 0.0
        signals: List[Signal] = []
        computed = 0

        rsi = result.indicators["rsi_14"].latest()
        if rsi is not None:
            computed += 1
            pts, sig = _score_rsi(rsi)
            points += pts
            signals.append(sig)

        macd_outcome = _score_macd(result.indicators["macd"].latest())
        if macd_outcome is not None:
            computed += 1
            pts, sig = macd_outcome
            points += pts
            signals.append(sig)

        stochastic_outcome = _score_stochastic(result.indicators["stochastic_14_3_3"].latest())
        if stochastic_outcome is not None:
            computed += 1
            pts, sig = stochastic_outcome
            points += pts
            signals.append(sig)

        supertrend_outcome = _score_supertrend(result.indicators["supertrend"].latest())
        if supertrend_outcome is not None:
            computed += 1
            pts, sig = supertrend_outcome
            points += pts
            signals.append(sig)

        ema_sma_outcome = _score_ema_vs_sma(
            result.indicators["ema_20"].latest(), result.indicators["sma_20"].latest()
        )
        if ema_sma_outcome is not None:
            computed += 1
            pts, sig = ema_sma_outcome
            points += pts
            signals.append(sig)

        obv_outcome = _score_obv(result)
        if obv_outcome is not None:
            computed += 1
            pts, sig = obv_outcome
            points += pts
            signals.append(sig)

        volume_outcome = _score_volume_trend(result)
        if volume_outcome is not None:
            computed += 1
            pts, sig = volume_outcome
            points += pts
            signals.append(sig)

        pattern_points, pattern_signals = _score_patterns(result)
        points += pattern_points
        signals.extend(pattern_signals)

        bollinger_signal = _bollinger_width_signal(result)
        if bollinger_signal is not None:
            signals.append(bollinger_signal)

        score = max(0.0, min(100.0, 50.0 + points))

        confidence = 100.0 * (computed / _CORE_SIGNAL_SLOTS)
        adx = result.indicators["adx_14"].latest()
        if adx is not None:
            if adx >= 25:
                confidence = min(100.0, confidence + 5.0)
            elif adx < 15:
                confidence = max(0.0, confidence - 5.0)

        return ScoreContribution(
            source=self.name,
            score=round(score, 1),
            weight=self.default_weight,
            confidence=round(confidence, 1),
            signals=signals,
        )
