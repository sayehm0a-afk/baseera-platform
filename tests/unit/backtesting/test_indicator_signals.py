"""Unit tests for src.backtesting.calibration.indicator_signals -- pure
functions, hand-built TechnicalAnalysisResult/AsOfDataset fixtures, no
database."""

import pandas as pd
import pytest

from src.analysis.recommendation.types import AnalysisContext
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import (
    BollingerBandsResult,
    FibonacciLevels,
    IndicatorCategory,
    IndicatorOutput,
    MACDResult,
    SupportResistanceLevels,
    VolumeProfileResult,
)
from src.backtesting.calibration.indicator_signals import (
    ALL_INDICATORS,
    DIRECTIONAL_INDICATORS,
    RISK_INDICATORS,
    read_all_indicators,
    read_indicator,
)
from src.backtesting.data_access import AsOfDataset


def _technical_result(
    rsi=50.0, macd_line=0.0, signal_line=0.0, histogram=0.0, adx=20.0, ema=100.0, sma=100.0,
    atr=2.0, bollinger_upper=105.0, bollinger_middle=100.0, bollinger_lower=95.0,
    support=None, resistance=None, fib_levels=None, is_uptrend=True, vwap=100.0,
    poc=100.0, bin_edges=None, bin_volumes=None,
):
    return TechnicalAnalysisResult(
        indicators={
            "rsi_14": IndicatorOutput(name="rsi_14", category=IndicatorCategory.MOMENTUM, value=pd.Series([rsi])),
            "macd": IndicatorOutput(
                name="macd", category=IndicatorCategory.MOMENTUM,
                value=MACDResult(
                    macd_line=pd.Series([macd_line]), signal_line=pd.Series([signal_line]),
                    histogram=pd.Series([histogram]),
                ),
            ),
            "adx_14": IndicatorOutput(name="adx_14", category=IndicatorCategory.TREND, value=pd.Series([adx])),
            "ema_20": IndicatorOutput(name="ema_20", category=IndicatorCategory.TREND, value=pd.Series([ema])),
            "sma_20": IndicatorOutput(name="sma_20", category=IndicatorCategory.TREND, value=pd.Series([sma])),
            "atr_14": IndicatorOutput(name="atr_14", category=IndicatorCategory.VOLATILITY, value=pd.Series([atr])),
            "bollinger": IndicatorOutput(
                name="bollinger", category=IndicatorCategory.VOLATILITY,
                value=BollingerBandsResult(
                    upper=pd.Series([bollinger_upper]), middle=pd.Series([bollinger_middle]),
                    lower=pd.Series([bollinger_lower]),
                ),
            ),
            "support_resistance": IndicatorOutput(
                name="support_resistance", category=IndicatorCategory.PRICE_ACTION,
                value=SupportResistanceLevels(support=support or [], resistance=resistance or []),
            ),
            "fibonacci_retracement": IndicatorOutput(
                name="fibonacci_retracement", category=IndicatorCategory.PRICE_ACTION,
                value=FibonacciLevels(
                    swing_high=110.0, swing_high_at=1, swing_low=90.0, swing_low_at=0,
                    is_uptrend=is_uptrend, levels=fib_levels or {},
                ),
            ),
            "vwap_20": IndicatorOutput(name="vwap_20", category=IndicatorCategory.VOLUME, value=pd.Series([vwap])),
            "volume_profile": IndicatorOutput(
                name="volume_profile", category=IndicatorCategory.VOLUME,
                value=VolumeProfileResult(
                    bin_edges=bin_edges or [95.0, 100.0, 105.0], bin_volumes=bin_volumes or [100.0, 100.0],
                    point_of_control=poc,
                ),
            ),
        }
    )


def _dataset(technical_result=None, price=100.0, price_bars_df=None):
    context = AnalysisContext(symbol="2222", technical_result=technical_result, latest_price=price)
    return AsOfDataset(
        context=context, technical_input_as_of=None, fundamental_input_as_of=None,
        price_bar_source=None, price_bar_is_synthetic=None, price_bars_df=price_bars_df,
    )


def _trend_df(closes):
    index = pd.date_range("2026-01-01", periods=len(closes), freq="D", tz="UTC")
    return pd.DataFrame({"close": closes}, index=index)


# --- registry / dispatch --------------------------------------------------


def test_all_indicators_covers_directional_and_risk():
    assert set(ALL_INDICATORS) == set(DIRECTIONAL_INDICATORS) | set(RISK_INDICATORS)
    assert len(ALL_INDICATORS) == 11


def test_read_indicator_rejects_unknown_name():
    with pytest.raises(KeyError):
        read_indicator("not_a_real_indicator", _dataset())


def test_read_all_indicators_omits_indicators_with_no_technical_result():
    assert read_all_indicators(_dataset(technical_result=None)) == {}


# --- RSI --------------------------------------------------------------


def test_rsi_oversold_is_bullish():
    call = read_indicator("rsi", _dataset(_technical_result(rsi=25.0)))
    assert call.direction == "BULLISH"
    assert call.magnitude > 0


def test_rsi_overbought_is_bearish():
    call = read_indicator("rsi", _dataset(_technical_result(rsi=80.0)))
    assert call.direction == "BEARISH"


def test_rsi_neutral_at_fifty():
    call = read_indicator("rsi", _dataset(_technical_result(rsi=50.0)))
    assert call.direction == "NEUTRAL"
    assert call.magnitude == 0.0


def test_rsi_missing_returns_none():
    result = _technical_result()
    result.indicators["rsi_14"] = IndicatorOutput(name="rsi_14", category=IndicatorCategory.MOMENTUM, value=pd.Series([None]))
    assert read_indicator("rsi", _dataset(result)) is None


# --- MACD ---------------------------------------------------------------


def test_macd_bullish_crossover():
    call = read_indicator("macd", _dataset(_technical_result(macd_line=0.5, signal_line=0.3, histogram=0.2, atr=1.0)))
    assert call.direction == "BULLISH"
    assert call.magnitude == pytest.approx(20.0)  # |0.2|/1.0*100


def test_macd_bearish_crossover():
    call = read_indicator("macd", _dataset(_technical_result(macd_line=-0.5, signal_line=-0.3, histogram=-0.2)))
    assert call.direction == "BEARISH"


def test_macd_neutral_when_mixed():
    call = read_indicator("macd", _dataset(_technical_result(macd_line=0.5, signal_line=0.3, histogram=-0.1)))
    assert call.direction == "NEUTRAL"


def test_macd_falls_back_to_fixed_magnitude_without_atr():
    call = read_indicator("macd", _dataset(_technical_result(macd_line=0.5, signal_line=0.3, histogram=0.2, atr=0.0)))
    assert call.magnitude == 60.0


# --- EMA / SMA ----------------------------------------------------------


def test_ema_price_above_is_bullish():
    call = read_indicator("ema", _dataset(_technical_result(ema=95.0), price=100.0))
    assert call.direction == "BULLISH"


def test_ema_price_below_is_bearish():
    call = read_indicator("ema", _dataset(_technical_result(ema=105.0), price=100.0))
    assert call.direction == "BEARISH"


def test_sma_price_above_is_bullish():
    call = read_indicator("sma", _dataset(_technical_result(sma=95.0), price=100.0))
    assert call.direction == "BULLISH"


def test_sma_price_equal_is_neutral():
    call = read_indicator("sma", _dataset(_technical_result(sma=100.0), price=100.0))
    assert call.direction == "NEUTRAL"


# --- ADX ------------------------------------------------------------------


def test_adx_weak_trend_is_neutral():
    call = read_indicator("adx", _dataset(_technical_result(adx=10.0), price_bars_df=_trend_df([100.0] * 15)))
    assert call.direction == "NEUTRAL"
    assert call.magnitude == 0.0


def test_adx_missing_returns_none():
    result = _technical_result()
    result.indicators["adx_14"] = IndicatorOutput(name="adx_14", category=IndicatorCategory.TREND, value=pd.Series([None]))
    assert read_indicator("adx", _dataset(result)) is None


def test_adx_strong_trend_pairs_with_rising_price():
    closes = [90.0 + i for i in range(15)]  # rising over the lookback
    call = read_indicator("adx", _dataset(_technical_result(adx=30.0), price_bars_df=_trend_df(closes)))
    assert call.direction == "BULLISH"
    assert call.magnitude == pytest.approx(30.0)


def test_adx_strong_trend_pairs_with_falling_price():
    closes = [90.0 - i for i in range(15)]
    call = read_indicator("adx", _dataset(_technical_result(adx=30.0), price_bars_df=_trend_df(closes)))
    assert call.direction == "BEARISH"


def test_adx_strong_trend_without_price_history_is_unknown():
    call = read_indicator("adx", _dataset(_technical_result(adx=30.0), price_bars_df=None))
    assert call is None


# --- Fibonacci -----------------------------------------------------------


def test_fibonacci_near_level_in_uptrend_is_bullish():
    result = _technical_result(fib_levels={"61.8": 99.7}, is_uptrend=True)
    call = read_indicator("fibonacci", _dataset(result, price=100.0))
    assert call.direction == "BULLISH"
    assert call.magnitude > 0


def test_fibonacci_near_level_in_downtrend_is_bearish():
    result = _technical_result(fib_levels={"61.8": 99.7}, is_uptrend=False)
    call = read_indicator("fibonacci", _dataset(result, price=100.0))
    assert call.direction == "BEARISH"


def test_fibonacci_far_from_any_level_is_neutral():
    result = _technical_result(fib_levels={"61.8": 50.0}, is_uptrend=True)
    call = read_indicator("fibonacci", _dataset(result, price=100.0))
    assert call.direction == "NEUTRAL"


def test_fibonacci_no_levels_returns_none():
    result = _technical_result(fib_levels={})
    assert read_indicator("fibonacci", _dataset(result, price=100.0)) is None


# --- Support / Resistance -------------------------------------------------


def test_support_resistance_near_support_is_bullish():
    result = _technical_result(support=[99.5], resistance=[])
    call = read_indicator("support_resistance", _dataset(result, price=100.0))
    assert call.direction == "BULLISH"


def test_support_resistance_near_resistance_is_bearish():
    result = _technical_result(support=[], resistance=[100.5])
    call = read_indicator("support_resistance", _dataset(result, price=100.0))
    assert call.direction == "BEARISH"


def test_support_resistance_breakout_above_all_resistance_is_bullish():
    result = _technical_result(resistance=[80.0, 85.0])
    call = read_indicator("support_resistance", _dataset(result, price=100.0))
    assert call.direction == "BULLISH"
    assert call.magnitude == 90.0


def test_support_resistance_breakdown_below_all_support_is_bearish():
    result = _technical_result(support=[120.0, 130.0])
    call = read_indicator("support_resistance", _dataset(result, price=100.0))
    assert call.direction == "BEARISH"


def test_support_resistance_no_levels_returns_none():
    result = _technical_result(support=[], resistance=[])
    assert read_indicator("support_resistance", _dataset(result, price=100.0)) is None


# --- VWAP / Volume Profile -------------------------------------------------


def test_vwap_above_is_bullish():
    result = _technical_result(vwap=95.0)
    call = read_indicator("vwap", _dataset(result, price=100.0))
    assert call.direction == "BULLISH"


def test_vwap_close_is_neutral():
    result = _technical_result(vwap=100.05)
    call = read_indicator("vwap", _dataset(result, price=100.0))
    assert call.direction == "NEUTRAL"


def test_volume_profile_above_poc_is_bullish():
    result = _technical_result(poc=95.0)
    call = read_indicator("volume_profile", _dataset(result, price=100.0))
    assert call.direction == "BULLISH"


def test_volume_profile_below_poc_is_bearish():
    result = _technical_result(poc=105.0)
    call = read_indicator("volume_profile", _dataset(result, price=100.0))
    assert call.direction == "BEARISH"


# --- ATR / Bollinger (risk, non-directional) -------------------------------


def test_atr_is_always_neutral_with_raw_ratio_magnitude():
    result = _technical_result(atr=3.0)
    call = read_indicator("atr", _dataset(result, price=100.0))
    assert call.direction == "NEUTRAL"
    assert call.magnitude == pytest.approx(0.03)


def test_bollinger_is_always_neutral_with_raw_ratio_magnitude():
    result = _technical_result(bollinger_upper=110.0, bollinger_middle=100.0, bollinger_lower=90.0)
    call = read_indicator("bollinger", _dataset(result, price=100.0))
    assert call.direction == "NEUTRAL"
    assert call.magnitude == pytest.approx(0.20)


# --- read_all_indicators ---------------------------------------------------


def test_read_all_indicators_returns_every_computable_indicator():
    result = _technical_result(support=[99.5], fib_levels={"61.8": 99.7}, vwap=95.0, poc=95.0)
    readings = read_all_indicators(_dataset(result, price=100.0, price_bars_df=_trend_df([90.0 + i for i in range(15)])))
    assert set(readings) == set(ALL_INDICATORS)
    assert readings["support_resistance"].direction == "BULLISH"
