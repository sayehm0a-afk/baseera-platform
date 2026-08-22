"""Decision Engine V2's eight documented sub-scores.

Every input here is a value `TechnicalAnalysisEngine`/`AIDecisionEngine`
already computed -- this module invents no indicator and reads no raw
OHLCV data of its own. Two disclosed, real limitations (not silently
worked around):

1. This codebase's indicator registry (src/analysis/registry.py) only
   registers SMA-20/EMA-20, not SMA-50/SMA-200 -- `trend_score` uses
   SMA-20/EMA-20 + SuperTrend direction + ADX strength instead of the
   longer moving averages Phase 1's brief mentions as an example.
2. Raw per-bar volume is not retained on `TechnicalAnalysisResult`
   (only the 20-period volume SMA and OBV are registered indicators)
   -- `volume_score` uses OBV's short-term trend as a real, but
   different, volume-confirmation proxy, not a "current vs. average
   volume" ratio.

Every sub-score is 0-100, 50 = neutral/unknown-but-assumed-average.
`None` means "genuinely not computable from available data," which the
engine (engine.py) turns into an honest data-quality warning rather
than a fabricated number.
"""

from typing import Optional

from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult


def _clamp(value: float, low: float = 0.0, high: float = 100.0) -> float:
    return max(low, min(high, value))


def _latest(series) -> Optional[float]:
    if series is None:
        return None
    non_null = series.dropna()
    if non_null.empty:
        return None
    return float(non_null.iloc[-1])


def trend_score(technical: Optional[TechnicalAnalysisResult], price: Optional[float]) -> Optional[float]:
    """Price position relative to SMA-20/EMA-20, SuperTrend direction,
    and ADX strength (which amplifies conviction in whichever direction
    the moving averages/SuperTrend already point, since ADX itself is
    directionless)."""
    if technical is None or price is None or price <= 0:
        return None

    score = 50.0
    sma20 = _latest(technical.sma_20)
    if sma20 is not None and sma20 > 0:
        score += 15.0 if price > sma20 else -15.0
    ema20 = _latest(technical.ema_20)
    if ema20 is not None and ema20 > 0:
        score += 10.0 if price > ema20 else -10.0

    try:
        supertrend_direction = _latest(technical.supertrend.direction)
    except (KeyError, AttributeError):
        supertrend_direction = None
    if supertrend_direction is not None:
        score += 15.0 if supertrend_direction > 0 else -15.0

    adx = _latest(technical.adx_14)
    if adx is not None and adx >= 25.0 and score != 50.0:
        strength_bonus = min(10.0, (adx - 25.0) * 0.4)
        score += strength_bonus if score > 50.0 else -strength_bonus

    return _clamp(score)


def momentum_score(technical: Optional[TechnicalAnalysisResult]) -> Optional[float]:
    """60% RSI-14 (already a 0-100 momentum reading), 40% MACD
    histogram sign (confirms whether momentum is accelerating or
    decelerating in the RSI's implied direction)."""
    if technical is None:
        return None
    rsi = _latest(technical.rsi_14)
    if rsi is None:
        return None

    macd_component = 50.0
    try:
        histogram = _latest(technical.macd.histogram)
    except (KeyError, AttributeError):
        histogram = None
    if histogram is not None:
        macd_component = 65.0 if histogram > 0 else 35.0 if histogram < 0 else 50.0

    return _clamp(rsi * 0.6 + macd_component * 0.4)


def volume_score(technical: Optional[TechnicalAnalysisResult]) -> Optional[float]:
    """OBV short-term trend (last 5 bars) as a volume-confirmation
    proxy -- see this module's docstring for why a current-vs-average
    raw-volume ratio isn't available."""
    if technical is None:
        return None
    try:
        obv = technical.obv.dropna()
    except (KeyError, AttributeError):
        return None
    if len(obv) < 5:
        return None
    recent = obv.iloc[-5:]
    delta = float(recent.iloc[-1] - recent.iloc[0])
    if delta == 0:
        return 50.0
    return 65.0 if delta > 0 else 35.0


def liquidity_score(average_traded_value: Optional[float], min_average_traded_value: float) -> Optional[float]:
    """Piecewise-linear against the configured minimum (same
    `get_min_average_traded_value()` the market-wide scanner's
    liquidity gate already uses): 0 at zero liquidity, 50 exactly at
    the minimum, 100 at 3x the minimum or beyond."""
    if average_traded_value is None or min_average_traded_value <= 0:
        return None
    ratio = average_traded_value / min_average_traded_value
    if ratio >= 3.0:
        return 100.0
    if ratio >= 1.0:
        return 50.0 + (ratio - 1.0) / 2.0 * 50.0
    return _clamp(50.0 * ratio)


def volatility_score(atr_pct: Optional[float], tuning: DecisionV2Tuning) -> Optional[float]:
    """A "sweet spot" band of ATR-as-percent-of-price scores highest
    (enough movement potential to realistically reach a target within
    the expected holding period); below it there's too little
    movement, above it the setup carries real gap/whipsaw risk."""
    if atr_pct is None or atr_pct < 0:
        return None
    low, high, excessive = (
        tuning.volatility_sweet_spot_low_pct,
        tuning.volatility_sweet_spot_high_pct,
        tuning.volatility_excessive_pct,
    )
    if low <= atr_pct <= high:
        return 85.0
    if atr_pct < low:
        return _clamp(85.0 * (atr_pct / low)) if low > 0 else 0.0
    if atr_pct <= excessive:
        span = excessive - high
        progress = (atr_pct - high) / span if span > 0 else 1.0
        return _clamp(85.0 - progress * 45.0)
    overshoot = atr_pct - excessive
    return _clamp(40.0 - overshoot * 300.0, low=5.0)


def risk_reward_score(risk_reward_ratio: Optional[float], min_ratio: float) -> Optional[float]:
    """Same shape as `liquidity_score`: 50 exactly at the configured
    minimum acceptable ratio, 100 at 3x the minimum or beyond."""
    if risk_reward_ratio is None or min_ratio <= 0:
        return None
    ratio_norm = risk_reward_ratio / min_ratio
    if ratio_norm >= 3.0:
        return 100.0
    if ratio_norm >= 1.0:
        return 50.0 + (ratio_norm - 1.0) / 2.0 * 50.0
    return _clamp(50.0 * ratio_norm)


def market_context_score(market_is_open: Optional[bool], sector_known: bool) -> float:
    """Real-time open-market data is worth more than a prior-session
    close for an actionable, time-sensitive entry decision -- this is
    not a claim about the underlying analysis being wrong when the
    market is closed, only that the price it's anchored to is a
    session or more old."""
    if market_is_open is True:
        base = 70.0
    elif market_is_open is False:
        base = 55.0
    else:
        base = 40.0
    if sector_known:
        base += 5.0
    return _clamp(base)


def data_quality_score(
    has_technical: bool,
    has_fundamental: bool,
    is_synthetic: Optional[bool],
    data_age_hours: Optional[float],
    max_age_hours: float,
    tuning: DecisionV2Tuning,
) -> float:
    score = 100.0
    if not has_technical:
        score -= 50.0
    if not has_fundamental:
        score -= tuning.missing_leg_penalty
    if is_synthetic is True:
        score = 0.0
    if data_age_hours is not None and data_age_hours > max_age_hours:
        score = min(score, tuning.stale_data_penalty_score)
    return _clamp(score)


_RISK_LEVEL_BASE = {"LOW": 90.0, "MEDIUM": 65.0, "HIGH": 35.0, "VERY_HIGH": 15.0}


def risk_score_from_level(risk_level_value: str, volatility: Optional[float]) -> float:
    """Blends the already-computed `RiskLevel` (never re-derived here)
    with the volatility sub-score above, so two symbols in the same
    RiskLevel band aren't presented as identically risky when their
    ATR-implied volatility clearly differs.

    Direction, stated explicitly because it is easy to misread: this is
    a SAFETY score, not a risk magnitude -- RiskLevel.LOW (the safest
    band) maps to ~90, RiskLevel.VERY_HIGH to ~15. Every real internal
    consumer already inverts it (`100 - risk_score`) before presenting
    it as "risk" in the intuitive higher-is-riskier sense --
    `personal_scan.py::_composite_score` and
    `portfolio_intelligence/portfolio_score.py` both do this for their
    own, unrelated risk_score fields. `ExecutiveDecisionCard.tsx`
    (Phase 3 area 3) now does the same for this one; do not remove that
    inversion or add a new raw display of this value without it.
    """
    base = _RISK_LEVEL_BASE.get(risk_level_value, 50.0)
    if volatility is None:
        return base
    return round(_clamp(base * 0.65 + volatility * 0.35), 1)


def opportunity_quality_score(sub: dict, tuning: DecisionV2Tuning) -> float:
    """Weighted blend of every available sub-score (weights sum to
    1.0, see DecisionV2Tuning); a `None` sub-score is excluded and the
    remaining weights are renormalized, exactly the same "coverage"
    principle RecommendationEngine already applies to missing
    contributor modules.

    Score-semantics decision (Phase 3 area 3, evidence-based): this
    score and `risk_score` above are deliberately kept OPTION B
    (display-only / informational), not wired into any publication
    gate or into `confidence_score` (OPTION A). Two reasons, both
    evidence-based rather than assumed:
    (1) gates.py already gates several of this blend's own inputs
    individually and more precisely -- trend_momentum_consistency,
    volume_quality, volatility_acceptable, liquidity, risk_reward --
    so an additional gate on the blended composite would silently
    double-penalize the same evidence a second time under a vaguer
    signal.
    (2) `confidence_score` is computed upstream by AIDecisionEngine and
    deliberately never mutated by decision_v2 (see engine.py's module
    docstring: "computes zero indicators of its own"); blending this
    score into it after the fact would break that invariant for a
    number that adds no evidence AIDecisionEngine didn't already see.
    Neither score is ever a probability of profit -- it is a composite
    of already-real sub-scores, presented for transparency alongside
    (not instead of) the gates that actually decided `decision`.
    """
    weights = {
        "trend_score": tuning.trend_weight,
        "momentum_score": tuning.momentum_weight,
        "volume_score": tuning.volume_weight,
        "liquidity_score": tuning.liquidity_weight,
        "volatility_score": tuning.volatility_weight,
        "risk_reward_score": tuning.risk_reward_weight,
        "market_context_score": tuning.market_context_weight,
        "data_quality_score": tuning.data_quality_weight,
    }
    total_weight = 0.0
    weighted_sum = 0.0
    for key, weight in weights.items():
        value = sub.get(key)
        if value is None:
            continue
        weighted_sum += value * weight
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return round(weighted_sum / total_weight, 1)


def conflicting_indicators(trend: Optional[float], momentum: Optional[float]) -> Optional[str]:
    """A real, checkable disagreement: the trend reads clearly bullish
    while momentum reads clearly bearish, or vice versa -- distinct
    from RecommendationEngine's own contributor-agreement heuristic
    (which operates on the five-to-nine contributor scores, not on
    these two specific technical sub-scores)."""
    if trend is None or momentum is None:
        return None
    if trend >= 60.0 and momentum <= 40.0:
        return "الاتجاه العام إيجابي لكن الزخم الحالي ضعيف أو سلبي -- إشارات متعارضة."
    if trend <= 40.0 and momentum >= 60.0:
        return "الزخم الحالي إيجابي لكن الاتجاه العام سلبي -- إشارات متعارضة."
    return None
