"""Unit tests for fundamental_summary.py -- real M2.3 ratios only,
never fabricated."""

from src.analysis.decision_v2.fundamental_summary import build_fundamental_summary
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisResult
from src.analysis.fundamental.types import RatioCategory, RatioOutput


_ALL_RATIO_NAMES = (
    "revenue_growth", "net_income_growth", "net_profit_margin", "gross_profit_margin",
    "return_on_equity", "debt_to_equity", "price_to_earnings", "price_to_book",
    "dividend_yield", "eps_growth",
)


def _result(**overrides):
    """Builds a FundamentalAnalysisResult with every ratio key present
    (defaulting to None) -- matches FundamentalAnalysisEngine.analyze()'s
    real invariant that every registered ratio is always inserted, only
    `.value` may be None."""
    values = {name: None for name in _ALL_RATIO_NAMES}
    values.update(overrides)
    ratios = {
        name: RatioOutput(name=name, category=RatioCategory.PROFITABILITY, value=value)
        for name, value in values.items()
    }
    return FundamentalAnalysisResult(ratios=ratios)


class TestBuildFundamentalSummary:
    def test_none_result_returns_all_none_and_a_not_available_sentence(self):
        summary, overview = build_fundamental_summary(None)
        assert all(v is None for v in summary.values())
        assert set(summary.keys()) == {
            "revenue_growth", "profit_growth", "net_profit_margin", "gross_profit_margin",
            "return_on_equity", "debt_to_equity", "price_to_earnings", "price_to_book",
            "dividend_yield", "eps_growth",
        }
        assert "غير متوفرة" in overview

    def test_real_ratios_are_read_verbatim_never_recomputed(self):
        result = _result(
            revenue_growth=0.12, net_income_growth=0.08, net_profit_margin=0.15,
            gross_profit_margin=0.40, return_on_equity=0.18, debt_to_equity=0.5,
            price_to_earnings=14.2, price_to_book=2.1, dividend_yield=0.03, eps_growth=0.10,
        )
        summary, overview = build_fundamental_summary(result)
        assert summary["revenue_growth"] == 0.12
        assert summary["profit_growth"] == 0.08
        assert summary["net_profit_margin"] == 0.15
        assert summary["return_on_equity"] == 0.18
        assert summary["price_to_earnings"] == 14.2
        assert overview != ""

    def test_missing_ratio_stays_none_never_fabricated(self):
        # FundamentalAnalysisEngine.analyze() always inserts every
        # registered ratio (value=None when uncomputable from real
        # financials, e.g. no prior period for a growth ratio) -- this
        # matches that real shape rather than omitting keys outright.
        result = _result(net_profit_margin=0.1)
        summary, _ = build_fundamental_summary(result)
        assert summary["revenue_growth"] is None
        assert summary["profit_growth"] is None
        assert summary["net_profit_margin"] == 0.1

    def test_revenue_trend_wording_reflects_direction(self):
        up, _ = build_fundamental_summary(_result(revenue_growth=0.10, net_income_growth=0.0))
        down, _ = build_fundamental_summary(_result(revenue_growth=-0.10, net_income_growth=0.0))
        flat, _ = build_fundamental_summary(_result(revenue_growth=0.01, net_income_growth=0.0))
        _, up_overview = build_fundamental_summary(_result(revenue_growth=0.10, net_income_growth=0.0))
        _, down_overview = build_fundamental_summary(_result(revenue_growth=-0.10, net_income_growth=0.0))
        _, flat_overview = build_fundamental_summary(_result(revenue_growth=0.01, net_income_growth=0.0))
        assert "تصاعدي" in up_overview
        assert "تراجعي" in down_overview
        assert "مستقر" in flat_overview
        assert up["revenue_growth"] == 0.10
        assert down["revenue_growth"] == -0.10
        assert flat["revenue_growth"] == 0.01
