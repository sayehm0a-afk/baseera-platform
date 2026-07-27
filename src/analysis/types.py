"""Shared types for the technical analysis engine.

These types are the uniform boundary between individual indicator
functions (each an isolated pure function under src/analysis/indicators/,
src/analysis/volume/, src/analysis/price_action/) and everything that
consumes their output -- today, only TechnicalAnalysisEngine; in the
future, a Composite Indicator Engine, Signal Engine, Confidence Scoring
layer, Explainable Signals layer, AI Decision Layer, and further
indicator families (Smart Money/ICT/Wyckoff-style, or anything else)
without any of them needing to import a specific indicator module
directly or know its concrete return type in advance.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List

import pandas as pd

REQUIRED_OHLCV_COLUMNS = ("open", "high", "low", "close", "volume")


class IndicatorCategory(str, Enum):
    """Classification of an indicator, for downstream consumers that
    want to group or filter (e.g. "run only volume indicators")."""

    TREND = "trend"
    MOMENTUM = "momentum"
    VOLATILITY = "volatility"
    VOLUME = "volume"
    PRICE_ACTION = "price_action"


@dataclass(frozen=True)
class MACDResult:
    macd_line: pd.Series
    signal_line: pd.Series
    histogram: pd.Series


@dataclass(frozen=True)
class BollingerBandsResult:
    upper: pd.Series
    middle: pd.Series
    lower: pd.Series


@dataclass(frozen=True)
class SuperTrendResult:
    trend: pd.Series
    direction: pd.Series  # +1 (bullish) / -1 (bearish) per bar


@dataclass(frozen=True)
class PatternMatch:
    pattern_name: str
    timestamp: datetime
    bullish: bool


@dataclass(frozen=True)
class StochasticResult:
    percent_k: pd.Series
    percent_d: pd.Series


@dataclass(frozen=True)
class FibonacciLevels:
    """Retracement levels between one swing high and one swing low
    found within the analyzed window. `is_uptrend` records which
    extreme occurred first: True when the low preceded the high (the
    classic "retrace down from the high" case), False when the high
    preceded the low ("retrace up from the low")."""

    swing_high: float
    swing_high_at: Any
    swing_low: float
    swing_low_at: Any
    is_uptrend: bool
    levels: Dict[str, float]


@dataclass(frozen=True)
class VolumeProfileResult:
    """A daily-bar approximation of volume-at-price: each bar's entire
    volume is attributed to the price bucket containing that bar's
    typical price ((high+low+close)/3), not distributed across the
    bar's true intrabar range -- real volume-at-price needs tick data,
    which this platform does not have."""

    bin_edges: List[float]
    bin_volumes: List[float]
    point_of_control: float


@dataclass(frozen=True)
class SupportResistanceLevels:
    support: List[float]
    resistance: List[float]


def _latest_series_value(series: pd.Series) -> Any:
    non_null = series.dropna()
    if non_null.empty:
        return None
    return non_null.iloc[-1]


@dataclass(frozen=True)
class IndicatorOutput:
    """Uniform wrapper around any indicator's result.

    This is the actual extension point: a future consumer that has no
    compile-time knowledge of which indicators exist (a Composite
    Indicator Engine, Signal Engine, Confidence Scoring, Explainable
    Signals, an AI Decision Layer, or a future Smart Money/ICT/Wyckoff
    module) can iterate a Dict[str, IndicatorOutput] and call
    .latest() on each without special-casing the concrete type behind
    `value`.
    """

    name: str
    category: IndicatorCategory
    value: Any  # pd.Series | MACDResult | BollingerBandsResult | SuperTrendResult | StochasticResult | FibonacciLevels | VolumeProfileResult | SupportResistanceLevels | List[PatternMatch]

    def latest(self) -> Any:
        """The most recent scalar/summary value(s) -- what a decision
        layer wants, not the full history."""
        if isinstance(self.value, pd.Series):
            return _latest_series_value(self.value)
        if isinstance(self.value, MACDResult):
            return {
                "macd_line": _latest_series_value(self.value.macd_line),
                "signal_line": _latest_series_value(self.value.signal_line),
                "histogram": _latest_series_value(self.value.histogram),
            }
        if isinstance(self.value, BollingerBandsResult):
            return {
                "upper": _latest_series_value(self.value.upper),
                "middle": _latest_series_value(self.value.middle),
                "lower": _latest_series_value(self.value.lower),
            }
        if isinstance(self.value, SuperTrendResult):
            return {
                "trend": _latest_series_value(self.value.trend),
                "direction": _latest_series_value(self.value.direction),
            }
        if isinstance(self.value, StochasticResult):
            return {
                "percent_k": _latest_series_value(self.value.percent_k),
                "percent_d": _latest_series_value(self.value.percent_d),
            }
        if isinstance(self.value, FibonacciLevels):
            return {"is_uptrend": self.value.is_uptrend, "levels": self.value.levels}
        if isinstance(self.value, VolumeProfileResult):
            return {
                "point_of_control": self.value.point_of_control,
                "bin_volumes": self.value.bin_volumes,
            }
        if isinstance(self.value, SupportResistanceLevels):
            return {"support": self.value.support, "resistance": self.value.resistance}
        if isinstance(self.value, list):
            matches: List[PatternMatch] = self.value
            if not matches:
                return []
            latest_timestamp = max(match.timestamp for match in matches)
            return [m.pattern_name for m in matches if m.timestamp == latest_timestamp]
        raise TypeError(f"IndicatorOutput.latest() has no handling for type {type(self.value)!r}")


IndicatorMap = Dict[str, IndicatorOutput]
