"""Unit tests for WatchlistEngine."""

from src.analysis.decision.types import RiskLevel, TimeHorizon
from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.watchlist import WatchlistEngine
from src.market_intelligence.types import WatchlistCategory
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


def test_all_nine_categories_are_always_present():
    watchlists = WatchlistEngine().build([make_outcome(symbol="A")])
    assert set(watchlists.keys()) == set(WatchlistCategory)
    assert len(WatchlistCategory) == 9


def test_high_risk_watchlist_includes_high_and_very_high_risk():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", risk_level=RiskLevel.HIGH)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", risk_level=RiskLevel.VERY_HIGH)),
        make_outcome(symbol="C", decision=make_decision(symbol="C", risk_level=RiskLevel.LOW)),
    ]
    result = WatchlistEngine().build(outcomes)[WatchlistCategory.HIGH_RISK]
    assert {e.symbol for e in result.entries} == {"A", "B"}


def test_dividend_watchlist_requires_yield_above_threshold(monkeypatch):
    monkeypatch.setenv("MARKET_DIVIDEND_YIELD_THRESHOLD", "0.03")
    outcomes = [
        make_outcome(symbol="A", fundamental_snapshot={"dividend_yield": 0.05}),
        make_outcome(symbol="B", fundamental_snapshot={"dividend_yield": 0.01}),
    ]
    result = WatchlistEngine().build(outcomes)[WatchlistCategory.DIVIDEND]
    assert [e.symbol for e in result.entries] == ["A"]
    assert "5.00%" in result.entries[0].reason


def test_oversold_and_overbought_from_rsi(monkeypatch):
    monkeypatch.setenv("MARKET_OVERSOLD_RSI_THRESHOLD", "30")
    monkeypatch.setenv("MARKET_OVERBOUGHT_RSI_THRESHOLD", "70")
    outcomes = [
        make_outcome(symbol="A", technical_snapshot={"rsi_14": 20.0}),
        make_outcome(symbol="B", technical_snapshot={"rsi_14": 80.0}),
        make_outcome(symbol="C", technical_snapshot={"rsi_14": 50.0}),
    ]
    watchlists = WatchlistEngine().build(outcomes)
    assert [e.symbol for e in watchlists[WatchlistCategory.OVERSOLD_OPPORTUNITIES].entries] == ["A"]
    assert [e.symbol for e in watchlists[WatchlistCategory.OVERBOUGHT_WARNINGS].entries] == ["B"]


def test_oversold_excludes_a_confirmed_strong_sell():
    outcomes = [make_outcome(symbol="A", technical_snapshot={"rsi_14": 15.0}, decision=make_decision(symbol="A", recommendation=Recommendation.STRONG_SELL))]
    result = WatchlistEngine().build(outcomes)[WatchlistCategory.OVERSOLD_OPPORTUNITIES]
    assert result.entries == []


def test_recovery_requires_buy_and_low_rsi():
    outcomes = [
        make_outcome(symbol="A", technical_snapshot={"rsi_14": 25.0}, decision=make_decision(symbol="A", recommendation=Recommendation.BUY)),
        make_outcome(symbol="B", technical_snapshot={"rsi_14": 25.0}, decision=make_decision(symbol="B", recommendation=Recommendation.HOLD)),
    ]
    result = WatchlistEngine().build(outcomes)[WatchlistCategory.RECOVERY]
    assert [e.symbol for e in result.entries] == ["A"]


def test_breakout_candidates_requires_price_above_bollinger_upper_and_adx():
    outcomes = [
        make_outcome(symbol="A", latest_price=110.0, technical_snapshot={"adx_14": 30.0, "bollinger": {"upper": 100.0}}),
        make_outcome(symbol="B", latest_price=90.0, technical_snapshot={"adx_14": 30.0, "bollinger": {"upper": 100.0}}),
    ]
    result = WatchlistEngine().build(outcomes)[WatchlistCategory.BREAKOUT_CANDIDATES]
    assert [e.symbol for e in result.entries] == ["A"]


def test_investment_watchlist_requires_long_term_buy_and_low_medium_risk():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.BUY, time_horizon=TimeHorizon.LONG_TERM, risk_level=RiskLevel.LOW)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", recommendation=Recommendation.BUY, time_horizon=TimeHorizon.LONG_TERM, risk_level=RiskLevel.VERY_HIGH)),
    ]
    result = WatchlistEngine().build(outcomes)[WatchlistCategory.INVESTMENT]
    assert [e.symbol for e in result.entries] == ["A"]


def test_watchlist_max_size_is_respected(monkeypatch):
    monkeypatch.setenv("MARKET_WATCHLIST_MAX_SIZE", "1")
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", risk_level=RiskLevel.HIGH)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", risk_level=RiskLevel.HIGH)),
    ]
    result = WatchlistEngine().build(outcomes)[WatchlistCategory.HIGH_RISK]
    assert len(result.entries) == 1
