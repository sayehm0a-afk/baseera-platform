"""The indicator registry: the extension point future intelligence
layers use, so they never need to modify an existing indicator.

Every indicator function under src/analysis/{indicators,volume,
price_action}/ stays a plain, isolated pure function -- it has zero
awareness that a registry exists. This module is the only place that
knows the full set of indicators and how to invoke each one uniformly
(every IndicatorSpec.compute takes the full OHLCV DataFrame and returns
that indicator's raw value, even for single-series indicators like SMA,
which are otherwise generic over any Series, not tied to `close`).

Adding a new indicator -- including a future Smart Money/ICT/Wyckoff-
style one -- means writing one pure function plus one new IndicatorSpec
here. TechnicalAnalysisEngine.analyze() and every existing indicator
are unaffected.
"""

from dataclasses import dataclass
from typing import Callable, List

import pandas as pd

from src.analysis.indicators.momentum import macd, rsi
from src.analysis.indicators.trend import adx, ema, sma, supertrend
from src.analysis.indicators.volatility import atr, bollinger_bands
from src.analysis.price_action.candlestick_patterns import detect_patterns
from src.analysis.types import IndicatorCategory
from src.analysis.volume.volume_indicators import obv, volume_sma


@dataclass(frozen=True)
class IndicatorSpec:
    name: str
    category: IndicatorCategory
    compute: Callable[[pd.DataFrame], object]


class IndicatorRegistry:
    """A named collection of IndicatorSpecs. TechnicalAnalysisEngine
    iterates one of these; it never hardcodes indicator names."""

    def __init__(self) -> None:
        self._specs: List[IndicatorSpec] = []

    def register(self, spec: IndicatorSpec) -> None:
        if any(existing.name == spec.name for existing in self._specs):
            raise ValueError(f"An indicator named {spec.name!r} is already registered")
        self._specs.append(spec)

    def all_specs(self) -> List[IndicatorSpec]:
        return list(self._specs)


def build_default_registry() -> IndicatorRegistry:
    """The M2.2 indicator set. A future milestone that wants its own
    additional indicators (or a derived/composite registry that
    operates on TechnicalAnalysisResult rather than raw OHLCV) can
    build its own IndicatorRegistry the same way, or extend this one,
    without touching this function's existing entries."""
    registry = IndicatorRegistry()

    registry.register(
        IndicatorSpec("sma_20", IndicatorCategory.TREND, lambda df: sma(df["close"], 20))
    )
    registry.register(
        IndicatorSpec("ema_20", IndicatorCategory.TREND, lambda df: ema(df["close"], 20))
    )
    registry.register(IndicatorSpec("adx_14", IndicatorCategory.TREND, lambda df: adx(df, 14)))
    registry.register(
        IndicatorSpec("supertrend", IndicatorCategory.TREND, lambda df: supertrend(df, 10, 3.0))
    )

    registry.register(
        IndicatorSpec("rsi_14", IndicatorCategory.MOMENTUM, lambda df: rsi(df["close"], 14))
    )
    registry.register(
        IndicatorSpec("macd", IndicatorCategory.MOMENTUM, lambda df: macd(df["close"], 12, 26, 9))
    )

    registry.register(
        IndicatorSpec(
            "bollinger",
            IndicatorCategory.VOLATILITY,
            lambda df: bollinger_bands(df["close"], 20, 2.0),
        )
    )
    registry.register(
        IndicatorSpec("atr_14", IndicatorCategory.VOLATILITY, lambda df: atr(df, 14))
    )

    registry.register(IndicatorSpec("obv", IndicatorCategory.VOLUME, lambda df: obv(df)))
    registry.register(
        IndicatorSpec("volume_sma_20", IndicatorCategory.VOLUME, lambda df: volume_sma(df, 20))
    )

    registry.register(
        IndicatorSpec(
            "candlestick_patterns", IndicatorCategory.PRICE_ACTION, lambda df: detect_patterns(df)
        )
    )

    return registry


DEFAULT_REGISTRY = build_default_registry()
