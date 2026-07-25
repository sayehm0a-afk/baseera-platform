"""Unit tests for FundamentalScoreContributor.

Builds FundamentalAnalysisResult directly from hand-picked RatioOutput
values (rather than running FundamentalAnalysisEngine over
FundamentalFacts) so each bucket rule can be exercised deterministically
and in isolation, exactly like test_technical_contributor.py does for
the technical leg.
"""

from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisResult
from src.analysis.fundamental.types import RatioCategory, RatioOutput
from src.analysis.recommendation.fundamental_contributor import FundamentalScoreContributor
from src.analysis.recommendation.types import AnalysisContext, SignalDirection

_ALL_RATIO_NAMES = [
    "net_profit_margin",
    "gross_profit_margin",
    "return_on_equity",
    "return_on_assets",
    "current_ratio",
    "quick_ratio",
    "cash_ratio",
    "debt_to_equity",
    "debt_to_assets",
    "equity_multiplier",
    "asset_turnover",
    "price_to_earnings",
    "price_to_book",
    "dividend_yield",
    "market_cap",
    "revenue_growth",
    "net_income_growth",
    "eps_growth",
]


def _output(name, value):
    return RatioOutput(name=name, category=RatioCategory.PROFITABILITY, value=value)


def _result(**overrides):
    ratios = {name: _output(name, None) for name in _ALL_RATIO_NAMES}
    ratios.update({name: _output(name, value) for name, value in overrides.items()})
    return FundamentalAnalysisResult(ratios=ratios)


def _contribute(result):
    contributor = FundamentalScoreContributor()
    context = AnalysisContext(symbol="2222", fundamental_result=result)
    return contributor.contribute(context)


# --- unavailable -----------------------------------------------------------


def test_no_fundamental_result_is_reported_as_unavailable():
    contributor = FundamentalScoreContributor()
    context = AnalysisContext(symbol="2222", fundamental_result=None)

    contribution = contributor.contribute(context)

    assert contribution.source == "fundamental"
    assert contribution.score is None
    assert contribution.weight == 0.0
    assert contribution.confidence == 0.0
    assert "No fundamental analysis" in contribution.notes


def test_all_ratios_none_is_available_but_neutral_and_zero_confidence():
    """An engine result that exists but computed nothing (e.g. every
    ratio undefined for this company) is a different, more honest
    signal than "no data was ingested at all" -- it participates with
    a neutral score and confidence 0, not an outright unavailable."""
    contribution = _contribute(_result())
    assert contribution.score == 50.0
    assert contribution.confidence == 0.0
    assert contribution.weight == 0.5
    assert contribution.signals == []


# --- Return on Equity --------------------------------------------------


def test_roe_strong_is_bullish():
    contribution = _contribute(_result(return_on_equity=0.20))
    sig = next(s for s in contribution.signals if s.name == "return_on_equity")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 10.0


def test_roe_weak_is_bearish():
    contribution = _contribute(_result(return_on_equity=0.02))
    sig = next(s for s in contribution.signals if s.name == "return_on_equity")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


def test_roe_moderate_is_neutral():
    contribution = _contribute(_result(return_on_equity=0.10))
    sig = next(s for s in contribution.signals if s.name == "return_on_equity")
    assert sig.direction == SignalDirection.NEUTRAL
    assert sig.impact == 3.0


# --- Net profit margin ---------------------------------------------------


def test_net_margin_healthy_is_bullish():
    contribution = _contribute(_result(net_profit_margin=0.15))
    sig = next(s for s in contribution.signals if s.name == "net_profit_margin")
    assert sig.direction == SignalDirection.BULLISH


def test_net_margin_negative_is_bearish():
    contribution = _contribute(_result(net_profit_margin=-0.05))
    sig = next(s for s in contribution.signals if s.name == "net_profit_margin")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


# --- Current ratio -----------------------------------------------------


def test_current_ratio_below_one_is_bearish():
    contribution = _contribute(_result(current_ratio=0.8))
    sig = next(s for s in contribution.signals if s.name == "current_ratio")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -6.0


def test_current_ratio_healthy_is_bullish():
    contribution = _contribute(_result(current_ratio=2.0))
    sig = next(s for s in contribution.signals if s.name == "current_ratio")
    assert sig.direction == SignalDirection.BULLISH


# --- Debt to equity (inverted: low is good) -------------------------------


def test_low_debt_to_equity_is_bullish():
    contribution = _contribute(_result(debt_to_equity=0.4))
    sig = next(s for s in contribution.signals if s.name == "debt_to_equity")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 5.0


def test_high_debt_to_equity_is_bearish():
    contribution = _contribute(_result(debt_to_equity=2.5))
    sig = next(s for s in contribution.signals if s.name == "debt_to_equity")
    assert sig.direction == SignalDirection.BEARISH
    assert sig.impact == -8.0


# --- Valuation (P/E, P/B) -------------------------------------------------


def test_low_pe_is_bullish():
    contribution = _contribute(_result(price_to_earnings=10.0))
    sig = next(s for s in contribution.signals if s.name == "price_to_earnings")
    assert sig.direction == SignalDirection.BULLISH


def test_high_pe_is_bearish():
    contribution = _contribute(_result(price_to_earnings=40.0))
    sig = next(s for s in contribution.signals if s.name == "price_to_earnings")
    assert sig.direction == SignalDirection.BEARISH


def test_negative_pe_is_not_meaningful_and_skipped():
    contribution = _contribute(_result(price_to_earnings=-5.0))
    assert not any(s.name == "price_to_earnings" for s in contribution.signals)


def test_low_pb_is_bullish():
    contribution = _contribute(_result(price_to_book=1.0))
    sig = next(s for s in contribution.signals if s.name == "price_to_book")
    assert sig.direction == SignalDirection.BULLISH


def test_high_pb_is_bearish():
    contribution = _contribute(_result(price_to_book=5.0))
    sig = next(s for s in contribution.signals if s.name == "price_to_book")
    assert sig.direction == SignalDirection.BEARISH


# --- Growth ----------------------------------------------------------------


def test_strong_revenue_growth_is_bullish():
    contribution = _contribute(_result(revenue_growth=0.15))
    sig = next(s for s in contribution.signals if s.name == "revenue_growth")
    assert sig.direction == SignalDirection.BULLISH


def test_revenue_decline_is_bearish():
    contribution = _contribute(_result(revenue_growth=-0.05))
    sig = next(s for s in contribution.signals if s.name == "revenue_growth")
    assert sig.direction == SignalDirection.BEARISH


def test_eps_growth_scored_same_as_revenue_growth():
    contribution = _contribute(_result(eps_growth=0.20))
    sig = next(s for s in contribution.signals if s.name == "eps_growth")
    assert sig.direction == SignalDirection.BULLISH
    assert sig.impact == 6.0


# --- Aggregate behavior ----------------------------------------------------


def test_confidence_reflects_fraction_of_ratios_available():
    contribution = _contribute(
        _result(return_on_equity=0.20, net_profit_margin=0.15, current_ratio=2.0, debt_to_equity=0.4)
    )
    # 4 of the 8 core signal slots are populated.
    assert contribution.confidence == 50.0


def test_score_is_high_and_fully_confident_under_maximal_bullish_ratios():
    contribution = _contribute(
        _result(
            return_on_equity=0.30,
            net_profit_margin=0.25,
            current_ratio=3.0,
            debt_to_equity=0.1,
            price_to_earnings=8.0,
            price_to_book=0.5,
            revenue_growth=0.30,
            eps_growth=0.30,
        )
    )
    # 10 + 6 + 5 + 5 + 6 + 4 + 6 + 6 = 48 points above the 50-point neutral baseline.
    assert contribution.score == 98.0
    assert contribution.confidence == 100.0


def test_score_is_clamped_to_0_under_maximal_bearish_ratios():
    contribution = _contribute(
        _result(
            return_on_equity=0.0,
            net_profit_margin=-0.20,
            current_ratio=0.3,
            debt_to_equity=5.0,
            price_to_earnings=100.0,
            price_to_book=10.0,
            revenue_growth=-0.30,
            eps_growth=-0.30,
        )
    )
    assert contribution.score == 0.0


def test_default_weight_is_configurable():
    contributor = FundamentalScoreContributor(weight=0.3)
    context = AnalysisContext(symbol="2222", fundamental_result=_result())
    contribution = contributor.contribute(context)
    assert contribution.weight == 0.3
