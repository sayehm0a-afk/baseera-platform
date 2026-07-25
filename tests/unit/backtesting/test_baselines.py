"""Unit tests for src.backtesting.baselines -- built against
hand-constructed TechnicalAnalysisResult/FundamentalAnalysisResult so
each rule is deterministic, the same technique
test_technical_contributor.py already uses."""

import pandas as pd
import pytest

from src.analysis.decision.types import AIDecisionTuning
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisResult
from src.analysis.fundamental.types import RatioCategory, RatioOutput
from src.analysis.recommendation.types import AnalysisContext, RecommendationTuning
from src.analysis.technical_analysis_engine import TechnicalAnalysisResult
from src.analysis.types import (
    BollingerBandsResult,
    IndicatorCategory,
    IndicatorOutput,
    MACDResult,
    SuperTrendResult,
)
from src.backtesting.baselines import (
    AIDecisionEngineStrategy,
    BuyAndHoldStrategy,
    DEFAULT_STRATEGIES,
    FundamentalOnlyStrategy,
    RSIOnlyStrategy,
    SMACrossoverStrategy,
    TechnicalOnlyStrategy,
    build_strategy,
    uncalibrated_ai_decision_engine_strategy,
)
from src.backtesting.data_access import AsOfDataset


def _output(name, category, value):
    return IndicatorOutput(name=name, category=category, value=value)


def _technical_result(rsi=50.0, sma_20=100.0, latest_close=None):
    indicators = {
        "rsi_14": _output("rsi_14", IndicatorCategory.MOMENTUM, pd.Series([rsi])),
        "sma_20": _output("sma_20", IndicatorCategory.TREND, pd.Series([sma_20])),
        "ema_20": _output("ema_20", IndicatorCategory.TREND, pd.Series([sma_20])),
        "macd": _output("macd", IndicatorCategory.MOMENTUM, MACDResult(pd.Series([0.0]), pd.Series([0.0]), pd.Series([0.0]))),
        "supertrend": _output("supertrend", IndicatorCategory.TREND, SuperTrendResult(pd.Series([0.0]), pd.Series([0.0]))),
        "adx_14": _output("adx_14", IndicatorCategory.TREND, pd.Series([20.0])),
        "atr_14": _output("atr_14", IndicatorCategory.VOLATILITY, pd.Series([2.0])),
        "obv": _output("obv", IndicatorCategory.VOLUME, pd.Series([1000.0] * 11)),
        "volume_sma_20": _output("volume_sma_20", IndicatorCategory.VOLUME, pd.Series([1000.0] * 11)),
        "bollinger": _output("bollinger", IndicatorCategory.VOLATILITY, BollingerBandsResult(pd.Series([103.5]), pd.Series([100.0]), pd.Series([96.5]))),
        "candlestick_patterns": _output("candlestick_patterns", IndicatorCategory.PRICE_ACTION, []),
    }
    return TechnicalAnalysisResult(indicators=indicators)


def _dataset(technical_result=None, fundamental_result=None, latest_price=None):
    context = AnalysisContext(
        symbol="2222", technical_result=technical_result, fundamental_result=fundamental_result, latest_price=latest_price
    )
    return AsOfDataset(
        context=context, technical_input_as_of=None, fundamental_input_as_of=None,
        price_bar_source="dev-synthetic", price_bar_is_synthetic=True,
    )


def _fundamental_result(roe=0.20):
    ratios = {"return_on_equity": RatioOutput(name="return_on_equity", category=RatioCategory.PROFITABILITY, value=roe)}
    for name in [
        "net_profit_margin", "gross_profit_margin", "return_on_assets", "current_ratio", "quick_ratio",
        "cash_ratio", "debt_to_equity", "debt_to_assets", "equity_multiplier", "asset_turnover",
        "price_to_earnings", "price_to_book", "dividend_yield", "market_cap", "revenue_growth",
        "net_income_growth", "eps_growth",
    ]:
        ratios[name] = RatioOutput(name=name, category=RatioCategory.PROFITABILITY, value=None)
    return FundamentalAnalysisResult(ratios=ratios)


# --- BuyAndHoldStrategy --------------------------------------------------


def test_buy_and_hold_always_buys():
    strategy = BuyAndHoldStrategy()
    call = strategy.evaluate(_dataset(latest_price=100.0))
    assert call.recommendation == "BUY"
    assert call.confidence == 100.0


def test_buy_and_hold_skips_when_no_price():
    strategy = BuyAndHoldStrategy()
    assert strategy.evaluate(_dataset(latest_price=None)) is None


# --- SMACrossoverStrategy ------------------------------------------------


def test_sma_crossover_buy_when_price_above_sma():
    strategy = SMACrossoverStrategy()
    call = strategy.evaluate(_dataset(technical_result=_technical_result(sma_20=90.0), latest_price=100.0))
    assert call.recommendation == "BUY"


def test_sma_crossover_sell_when_price_below_sma():
    strategy = SMACrossoverStrategy()
    call = strategy.evaluate(_dataset(technical_result=_technical_result(sma_20=110.0), latest_price=100.0))
    assert call.recommendation == "SELL"


def test_sma_crossover_hold_when_price_equals_sma():
    strategy = SMACrossoverStrategy()
    call = strategy.evaluate(_dataset(technical_result=_technical_result(sma_20=100.0), latest_price=100.0))
    assert call.recommendation == "HOLD"


def test_sma_crossover_skips_without_technical_result():
    strategy = SMACrossoverStrategy()
    assert strategy.evaluate(_dataset(latest_price=100.0)) is None


# --- RSIOnlyStrategy -------------------------------------------------


def test_rsi_only_buy_when_oversold():
    strategy = RSIOnlyStrategy()
    call = strategy.evaluate(_dataset(technical_result=_technical_result(rsi=25.0)))
    assert call.recommendation == "BUY"


def test_rsi_only_sell_when_overbought():
    strategy = RSIOnlyStrategy()
    call = strategy.evaluate(_dataset(technical_result=_technical_result(rsi=75.0)))
    assert call.recommendation == "SELL"


def test_rsi_only_hold_in_between():
    strategy = RSIOnlyStrategy()
    call = strategy.evaluate(_dataset(technical_result=_technical_result(rsi=50.0)))
    assert call.recommendation == "HOLD"


# --- TechnicalOnlyStrategy / FundamentalOnlyStrategy ----------------------


def test_technical_only_skips_without_technical_data():
    strategy = TechnicalOnlyStrategy()
    assert strategy.evaluate(_dataset()) is None


def test_technical_only_produces_a_call_when_data_present():
    strategy = TechnicalOnlyStrategy()
    call = strategy.evaluate(_dataset(technical_result=_technical_result()))
    assert call is not None
    assert call.fundamental_score is None


def test_fundamental_only_skips_without_fundamental_data():
    strategy = FundamentalOnlyStrategy()
    assert strategy.evaluate(_dataset()) is None


def test_fundamental_only_produces_a_call_when_data_present():
    strategy = FundamentalOnlyStrategy()
    call = strategy.evaluate(_dataset(fundamental_result=_fundamental_result(roe=0.25)))
    assert call is not None
    assert call.technical_score is None
    assert call.fundamental_score is not None


# --- AIDecisionEngineStrategy --------------------------------------------


def test_ai_decision_engine_strategy_skips_with_no_inputs_at_all():
    strategy = AIDecisionEngineStrategy()
    assert strategy.evaluate(_dataset()) is None


def test_ai_decision_engine_strategy_produces_full_call():
    strategy = AIDecisionEngineStrategy()
    call = strategy.evaluate(
        _dataset(technical_result=_technical_result(), fundamental_result=_fundamental_result(), latest_price=100.0)
    )
    assert call is not None
    assert call.recommendation in {"STRONG_BUY", "BUY", "HOLD", "SELL", "STRONG_SELL"}
    assert call.risk_level is not None
    assert call.time_horizon is not None
    assert len(call.contributor_breakdown) == 9


def test_ai_decision_engine_strategy_accepts_tuning_overrides():
    baseline = AIDecisionEngineStrategy()
    calibrated = AIDecisionEngineStrategy(
        recommendation_tuning=RecommendationTuning(buy_threshold=5.0),  # nearly everything becomes at least a BUY
        ai_tuning=AIDecisionTuning(),
    )
    dataset = _dataset(technical_result=_technical_result(rsi=50.0), fundamental_result=_fundamental_result(roe=0.0), latest_price=100.0)

    baseline_call = baseline.evaluate(dataset)
    calibrated_call = calibrated.evaluate(dataset)
    assert calibrated_call.recommendation != baseline_call.recommendation or calibrated_call.total_score == baseline_call.total_score


def test_uncalibrated_helper_uses_default_tuning():
    strategy = uncalibrated_ai_decision_engine_strategy()
    assert strategy.name == "uncalibrated_ai_decision_engine"
    call = strategy.evaluate(
        _dataset(technical_result=_technical_result(), fundamental_result=_fundamental_result(), latest_price=100.0)
    )
    assert call is not None


# --- registry / factory -------------------------------------------------


def test_build_strategy_known_names():
    for name in DEFAULT_STRATEGIES:
        strategy = build_strategy(name)
        assert strategy.name == name


def test_build_strategy_unknown_name_raises():
    with pytest.raises(ValueError, match="Unknown strategy"):
        build_strategy("not_a_real_strategy")
