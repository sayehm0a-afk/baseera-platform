"""TechnicalAnalysisEngine: the single entry point for computing every
M2.2 indicator against one OHLCV DataFrame.

This is deliberately not just a collection of indicator calls -- it is
built as the permanent foundation for everything the approved M2
blueprint's later layers (Composite Indicator Engine, Signal Engine,
Confidence Scoring, Explainable Signals, an AI Decision Layer, and any
future indicator family such as Smart Money/ICT/Wyckoff-style
indicators) will need: a uniform `indicators: Dict[str, IndicatorOutput]`
map that those layers can consume without importing a specific
indicator module or knowing the concrete indicator set in advance, plus
`.latest_snapshot()` for exactly the flat "current value of everything"
shape a decision layer wants. Adding a new indicator to the platform
means adding one IndicatorSpec to src/analysis/registry.py -- nothing
in this file changes.
"""

from dataclasses import dataclass, field
from typing import Any, Dict

import pandas as pd

from src.analysis.registry import DEFAULT_REGISTRY, IndicatorRegistry
from src.analysis.types import (
    REQUIRED_OHLCV_COLUMNS,
    BollingerBandsResult,
    IndicatorMap,
    IndicatorOutput,
    MACDResult,
    SuperTrendResult,
)


@dataclass(frozen=True)
class TechnicalAnalysisResult:
    """The result of running every registered indicator against one
    OHLCV DataFrame.

    `indicators` is the extension point: any consumer that iterates it
    (or calls `.latest_snapshot()`) works correctly regardless of which
    indicators are registered, today or in the future. The named
    properties below are a convenience layer for code that does know
    the concrete M2.2 indicator set -- they simply read from the same
    `indicators` dict, so there is exactly one source of truth.
    """

    indicators: IndicatorMap = field(default_factory=dict)

    def get(self, name: str) -> IndicatorOutput:
        return self.indicators[name]

    def latest_snapshot(self) -> Dict[str, Any]:
        """Every indicator's most recent value, keyed by name -- the
        shape a future Signal Engine / Confidence Scoring / AI Decision
        Layer consumes as input."""
        return {name: output.latest() for name, output in self.indicators.items()}

    @property
    def sma_20(self) -> pd.Series:
        return self.indicators["sma_20"].value

    @property
    def ema_20(self) -> pd.Series:
        return self.indicators["ema_20"].value

    @property
    def adx_14(self) -> pd.Series:
        return self.indicators["adx_14"].value

    @property
    def supertrend(self) -> SuperTrendResult:
        return self.indicators["supertrend"].value

    @property
    def rsi_14(self) -> pd.Series:
        return self.indicators["rsi_14"].value

    @property
    def macd(self) -> MACDResult:
        return self.indicators["macd"].value

    @property
    def bollinger(self) -> BollingerBandsResult:
        return self.indicators["bollinger"].value

    @property
    def atr_14(self) -> pd.Series:
        return self.indicators["atr_14"].value

    @property
    def obv(self) -> pd.Series:
        return self.indicators["obv"].value

    @property
    def volume_sma_20(self) -> pd.Series:
        return self.indicators["volume_sma_20"].value

    @property
    def patterns(self):
        return self.indicators["candlestick_patterns"].value


class TechnicalAnalysisEngine:
    """Runs every indicator in a registry (default: the full M2.2 set)
    against one OHLCV DataFrame."""

    def __init__(self, registry: IndicatorRegistry = DEFAULT_REGISTRY):
        self._registry = registry

    def analyze(self, df: pd.DataFrame) -> TechnicalAnalysisResult:
        self._validate(df)

        computed: IndicatorMap = {}
        for spec in self._registry.all_specs():
            value = spec.compute(df)
            computed[spec.name] = IndicatorOutput(name=spec.name, category=spec.category, value=value)

        return TechnicalAnalysisResult(indicators=computed)

    @staticmethod
    def _validate(df: pd.DataFrame) -> None:
        missing = [col for col in REQUIRED_OHLCV_COLUMNS if col not in df.columns]
        if missing:
            raise ValueError(f"DataFrame is missing required column(s): {missing}")
        # MACD (slow=26, signal=9) is the longest warm-up requirement
        # among the default registry's indicators.
        minimum_rows = 35
        if len(df) < minimum_rows:
            raise ValueError(
                f"need at least {minimum_rows} rows for the full default indicator "
                f"set, got {len(df)}"
            )
