"""indicator_signals: standalone, backtesting-only directional/risk
reads for each of the platform's individually-named indicators --
Fibonacci, Support/Resistance, VWAP, Volume Profile, RSI, MACD, ADX,
EMA, SMA, Bollinger, ATR.

Deliberately NOT a reuse of the live scoring contributors' internal
`_score_*` functions (TechnicalScoreContributor,
PriceStructureScoreContributor, ValueAreaScoreContributor,
RiskScoreContributor) -- this module exists so
`indicator_attribution.py` can measure each indicator's OWN standalone
predictive power in isolation, the same "one indicator, one opinion,
no blending" idea `src.backtesting.baselines`'s RSIOnlyStrategy/
SMACrossoverStrategy already establish for two of these eleven; this
module extends that exact pattern to the other nine, plus
Fibonacci/Support-Resistance/VWAP/Volume Profile. Reading a live
contributor's scoring function directly would only show how an
indicator performs already blended with everything else in that
contributor's score -- not what the indicator alone is worth. Where a
threshold below matches a live contributor's own convention, it is
cited in a comment; nothing here changes production behavior.

Two shapes of claim, both real and disclosed, never fabricated:
  - Nine indicators (Fibonacci, Support/Resistance, VWAP, Volume
    Profile, RSI, MACD, EMA, SMA, and ADX paired with the concurrent
    price trend) make a genuine directional claim (BULLISH/BEARISH/
    NEUTRAL), each with a 0-100 `magnitude` proxy for "how strong is
    this specific reading" -- consumed by indicator_attribution.py's
    win-rate/precision/recall/confidence-accuracy report.
  - Two indicators (ATR, Bollinger Band width) are volatility/risk
    measures in this codebase's own live scoring (see
    RiskScoreContributor) -- they make no directional claim at all, so
    forcing one here would misrepresent what they actually predict in
    production. Their `direction` is always "NEUTRAL"; their real
    signal is `magnitude`, which for these two specifically holds the
    raw volatility ratio (ATR/price, or Bollinger band width/price),
    not a 0-100 confidence proxy -- consumed by
    indicator_attribution.py's dedicated volatility-bucket report.
"""

from dataclasses import dataclass
from typing import Callable, Dict, Optional

from src.analysis.decision.contributors._series_utils import latest_value
from src.backtesting.data_access import AsOfDataset

# Matches PriceStructureScoreContributor/ValueAreaScoreContributor's own
# "near a level" thresholds -- see those modules for the live usage.
_PROXIMITY_THRESHOLD = 0.015
_VWAP_DEVIATION_THRESHOLD = 0.01
_POC_DEVIATION_THRESHOLD = 0.02

# Matches TechnicalScoreContributor's own ADX confidence gate.
_ADX_TRENDING_THRESHOLD = 25.0
_ADX_TREND_LOOKBACK = 10

# Matches RiskScoreContributor's own ATR-ratio / Bollinger-width-ratio bands.
_ATR_HIGH_RATIO = 0.03
_ATR_LOW_RATIO = 0.012
_BOLLINGER_WIDE_RATIO = 0.10
_BOLLINGER_NARROW_RATIO = 0.04

DIRECTIONAL_INDICATORS = (
    "fibonacci", "support_resistance", "vwap", "volume_profile",
    "rsi", "macd", "adx", "ema", "sma",
)
RISK_INDICATORS = ("atr", "bollinger")
ALL_INDICATORS = DIRECTIONAL_INDICATORS + RISK_INDICATORS


@dataclass(frozen=True)
class IndicatorCall:
    """One indicator's standalone opinion for one symbol, one
    evaluation date. See module docstring for the `magnitude`
    contract, which differs between the nine directional indicators
    and the two risk/volatility ones."""

    indicator: str
    direction: str  # "BULLISH" | "BEARISH" | "NEUTRAL"
    magnitude: Optional[float] = None


def _clip100(value: float) -> float:
    return max(0.0, min(100.0, value))


def _price(dataset: AsOfDataset) -> Optional[float]:
    return dataset.context.latest_price


def _technical(dataset: AsOfDataset):
    return dataset.context.technical_result


def _read_rsi(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    """Mirrors TechnicalScoreContributor._score_rsi's own four-band
    convention: <=30/>=70 are oversold/overbought *reversal* reads
    (the call is the opposite of the recent extreme), the mild >50/<50
    bands are trend-following reads."""
    result = _technical(dataset)
    if result is None:
        return None
    rsi = latest_value(result.rsi_14)
    if rsi is None:
        return None
    if rsi <= 30:
        return IndicatorCall("rsi", "BULLISH", magnitude=_clip100((30.0 - rsi) * 2.0 + 50.0))
    if rsi >= 70:
        return IndicatorCall("rsi", "BEARISH", magnitude=_clip100((rsi - 70.0) * 2.0 + 50.0))
    if rsi == 50:
        return IndicatorCall("rsi", "NEUTRAL", magnitude=0.0)
    direction = "BULLISH" if rsi > 50 else "BEARISH"
    return IndicatorCall("rsi", direction, magnitude=_clip100(abs(rsi - 50.0) * 2.0))


def _read_macd(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    result = _technical(dataset)
    if result is None:
        return None
    histogram = latest_value(result.macd.histogram)
    macd_line = latest_value(result.macd.macd_line)
    signal_line = latest_value(result.macd.signal_line)
    if histogram is None or macd_line is None or signal_line is None:
        return None

    atr = latest_value(result.atr_14)
    magnitude = _clip100(abs(histogram) / atr * 100.0) if atr else 60.0

    if histogram > 0 and macd_line > signal_line:
        return IndicatorCall("macd", "BULLISH", magnitude=magnitude)
    if histogram < 0 and macd_line < signal_line:
        return IndicatorCall("macd", "BEARISH", magnitude=magnitude)
    return IndicatorCall("macd", "NEUTRAL", magnitude=0.0)


def _read_ema(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    result = _technical(dataset)
    price = _price(dataset)
    if result is None or price is None:
        return None
    ema = latest_value(result.ema_20)
    if ema is None or ema == 0:
        return None
    deviation_pct = (price - ema) / ema * 100.0
    if deviation_pct == 0:
        return IndicatorCall("ema", "NEUTRAL", magnitude=0.0)
    direction = "BULLISH" if deviation_pct > 0 else "BEARISH"
    return IndicatorCall("ema", direction, magnitude=_clip100(abs(deviation_pct) * 20.0))


def _read_sma(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    result = _technical(dataset)
    price = _price(dataset)
    if result is None or price is None:
        return None
    sma = latest_value(result.sma_20)
    if sma is None or sma == 0:
        return None
    deviation_pct = (price - sma) / sma * 100.0
    if deviation_pct == 0:
        return IndicatorCall("sma", "NEUTRAL", magnitude=0.0)
    direction = "BULLISH" if deviation_pct > 0 else "BEARISH"
    return IndicatorCall("sma", direction, magnitude=_clip100(abs(deviation_pct) * 20.0))


def _read_adx(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    """ADX itself measures trend *strength*, not direction (see
    RiskScoreContributor/TechnicalScoreContributor -- neither ever
    treats it as directional). Its real, testable claim is "a strong
    trend reading predicts the concurrent price trend continuing," so
    this pairs a >=25 ADX reading with the sign of the recent price
    move over the same lookback TechnicalScoreContributor's own
    trend-comparison helpers use elsewhere. A weak (<25) reading makes
    no confident directional claim at all."""
    result = _technical(dataset)
    if result is None:
        return None
    adx = latest_value(result.adx_14)
    if adx is None or adx < _ADX_TRENDING_THRESHOLD:
        return IndicatorCall("adx", "NEUTRAL", magnitude=0.0) if adx is not None else None

    df = dataset.price_bars_df
    if df is None or "close" not in df.columns or len(df) <= _ADX_TREND_LOOKBACK:
        return None
    current = float(df["close"].iloc[-1])
    prior = float(df["close"].iloc[-1 - _ADX_TREND_LOOKBACK])
    if current == prior:
        return IndicatorCall("adx", "NEUTRAL", magnitude=_clip100(adx))
    direction = "BULLISH" if current > prior else "BEARISH"
    return IndicatorCall("adx", direction, magnitude=_clip100(adx))


def _read_fibonacci(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    result = _technical(dataset)
    price = _price(dataset)
    if result is None or price is None or price <= 0:
        return None
    fib = result.fibonacci_retracement
    if not fib.levels:
        return None

    nearest_name, nearest_price = min(fib.levels.items(), key=lambda kv: abs(kv[1] - price))
    proximity = abs(price - nearest_price) / price
    if proximity > _PROXIMITY_THRESHOLD:
        return IndicatorCall("fibonacci", "NEUTRAL", magnitude=0.0)

    magnitude = _clip100(100.0 * (1.0 - proximity / _PROXIMITY_THRESHOLD))
    direction = "BULLISH" if fib.is_uptrend else "BEARISH"
    return IndicatorCall("fibonacci", direction, magnitude=magnitude)


def _read_support_resistance(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    result = _technical(dataset)
    price = _price(dataset)
    if result is None or price is None or price <= 0:
        return None
    levels = result.support_resistance
    if not levels.support and not levels.resistance:
        return None

    above = [r for r in levels.resistance if r > price]
    below = [s for s in levels.support if s < price]

    if levels.resistance and not above:
        return IndicatorCall("support_resistance", "BULLISH", magnitude=90.0)  # breakout above every resistance
    if levels.support and not below:
        return IndicatorCall("support_resistance", "BEARISH", magnitude=90.0)  # breakdown below every support

    if below:
        proximity = (price - max(below)) / price
        if proximity <= _PROXIMITY_THRESHOLD:
            return IndicatorCall(
                "support_resistance", "BULLISH", magnitude=_clip100(100.0 * (1.0 - proximity / _PROXIMITY_THRESHOLD))
            )
    if above:
        proximity = (min(above) - price) / price
        if proximity <= _PROXIMITY_THRESHOLD:
            return IndicatorCall(
                "support_resistance", "BEARISH", magnitude=_clip100(100.0 * (1.0 - proximity / _PROXIMITY_THRESHOLD))
            )

    return IndicatorCall("support_resistance", "NEUTRAL", magnitude=0.0)


def _read_vwap(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    result = _technical(dataset)
    price = _price(dataset)
    if result is None or price is None:
        return None
    vwap = latest_value(result.vwap_20)
    if vwap is None or vwap <= 0:
        return None
    deviation = (price - vwap) / vwap
    if abs(deviation) < _VWAP_DEVIATION_THRESHOLD:
        return IndicatorCall("vwap", "NEUTRAL", magnitude=0.0)
    direction = "BULLISH" if deviation > 0 else "BEARISH"
    return IndicatorCall("vwap", direction, magnitude=_clip100(abs(deviation) * 1000.0))


def _read_volume_profile(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    result = _technical(dataset)
    price = _price(dataset)
    if result is None or price is None:
        return None
    profile = result.volume_profile
    if profile.point_of_control <= 0:
        return None
    deviation = (price - profile.point_of_control) / profile.point_of_control
    if abs(deviation) < _POC_DEVIATION_THRESHOLD:
        return IndicatorCall("volume_profile", "NEUTRAL", magnitude=0.0)
    direction = "BULLISH" if deviation > 0 else "BEARISH"
    return IndicatorCall("volume_profile", direction, magnitude=_clip100(abs(deviation) * 1000.0))


def _read_atr(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    """Non-directional (see module docstring) -- `magnitude` here is
    the raw ATR/price ratio, not a 0-100 confidence proxy."""
    result = _technical(dataset)
    price = _price(dataset)
    if result is None or price is None or price == 0:
        return None
    atr = latest_value(result.atr_14)
    if atr is None:
        return None
    return IndicatorCall("atr", "NEUTRAL", magnitude=atr / price)


def _read_bollinger(dataset: AsOfDataset) -> Optional[IndicatorCall]:
    """Non-directional (see module docstring) -- `magnitude` here is
    the raw Bollinger Band width/price ratio, not a 0-100 confidence
    proxy."""
    result = _technical(dataset)
    upper = latest_value(result.bollinger.upper) if result is not None else None
    lower = latest_value(result.bollinger.lower) if result is not None else None
    middle = latest_value(result.bollinger.middle) if result is not None else None
    if upper is None or lower is None or middle is None or middle == 0:
        return None
    return IndicatorCall("bollinger", "NEUTRAL", magnitude=(upper - lower) / middle)


_READERS: Dict[str, Callable[[AsOfDataset], Optional[IndicatorCall]]] = {
    "fibonacci": _read_fibonacci,
    "support_resistance": _read_support_resistance,
    "vwap": _read_vwap,
    "volume_profile": _read_volume_profile,
    "rsi": _read_rsi,
    "macd": _read_macd,
    "adx": _read_adx,
    "ema": _read_ema,
    "sma": _read_sma,
    "atr": _read_atr,
    "bollinger": _read_bollinger,
}


def read_indicator(indicator: str, dataset: AsOfDataset) -> Optional[IndicatorCall]:
    if indicator not in _READERS:
        raise KeyError(f"Unknown indicator {indicator!r}. Known indicators: {sorted(_READERS)}")
    return _READERS[indicator](dataset)


def read_all_indicators(dataset: AsOfDataset) -> Dict[str, IndicatorCall]:
    """Every indicator that could be computed for this dataset, keyed
    by name -- indicators with insufficient input data are simply
    absent, never a fabricated NEUTRAL/zero reading standing in for
    missing data."""
    readings = {}
    for name, reader in _READERS.items():
        call = reader(dataset)
        if call is not None:
            readings[name] = call
    return readings
