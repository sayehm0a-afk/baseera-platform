"""Integration tests for FundamentalAnalysisEngine/FundamentalAnalysisResult
and the ratio-level registry they are built on.
"""

from datetime import date

import pytest

from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.registry import DEFAULT_RATIO_REGISTRY, RatioRegistry, RatioSpec
from src.analysis.fundamental.types import FundamentalFacts, RatioCategory, RatioOutput

EXPECTED_DEFAULT_RATIO_NAMES = {
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
}


def _facts(**overrides) -> FundamentalFacts:
    defaults = dict(
        stock_id=1,
        period_type="annual",
        fiscal_period_end=date(2024, 12, 31),
        revenue=1000.0,
        gross_profit=400.0,
        net_income=150.0,
        total_assets=3000.0,
        total_liabilities=1200.0,
        total_equity=1800.0,
        current_assets=700.0,
        current_liabilities=400.0,
        inventory=100.0,
        cash_and_equivalents=200.0,
        total_debt=500.0,
        shares_outstanding=500,
        eps=0.3,
        dividend_per_share=0.1,
    )
    defaults.update(overrides)
    return FundamentalFacts(**defaults)


def _prior() -> FundamentalFacts:
    return _facts(fiscal_period_end=date(2023, 12, 31), revenue=800.0, net_income=100.0, eps=0.2)


def test_analyze_computes_every_default_ratio_with_prior_and_price():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(_facts(), prior_facts=_prior(), market_price=15.0)

    assert set(result.ratios.keys()) == EXPECTED_DEFAULT_RATIO_NAMES
    for name, output in result.ratios.items():
        assert isinstance(output, RatioOutput)
        assert output.name == name
        # With a full prior period and price supplied, every ratio for
        # this well-formed facts fixture should resolve to a real value.
        assert output.value is not None


def test_analyze_without_prior_or_price_leaves_those_categories_none():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(_facts())

    assert result.price_to_earnings is None
    assert result.market_cap is None
    assert result.revenue_growth is None
    assert result.eps_growth is None
    # Ratios that need neither prior nor price still resolve.
    assert result.net_profit_margin == pytest.approx(0.15)
    assert result.current_ratio == pytest.approx(1.75)


def test_analyze_typed_properties_match_ratios_dict():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(_facts(), prior_facts=_prior(), market_price=15.0)

    assert result.net_profit_margin == result.ratios["net_profit_margin"].value
    assert result.price_to_earnings == result.ratios["price_to_earnings"].value
    assert result.revenue_growth == result.ratios["revenue_growth"].value


def test_latest_snapshot_has_one_entry_per_ratio():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(_facts(), prior_facts=_prior(), market_price=15.0)

    snapshot = result.latest_snapshot()

    assert set(snapshot.keys()) == EXPECTED_DEFAULT_RATIO_NAMES
    assert snapshot["net_profit_margin"] == pytest.approx(0.15)


def test_get_raises_key_error_for_unknown_ratio():
    engine = FundamentalAnalysisEngine()
    result = engine.analyze(_facts())

    with pytest.raises(KeyError):
        result.get("does_not_exist")


# ---------------------------------------------------------------------------
# Extension point: a registry-driven, forward-looking consumer should be
# able to add a brand-new ratio without FundamentalAnalysisEngine or any
# existing ratio changing at all.
# ---------------------------------------------------------------------------


def test_engine_works_with_a_custom_registry_extension():
    registry = RatioRegistry()
    registry.register(
        RatioSpec(
            "future_smart_money_placeholder",
            RatioCategory.PROFITABILITY,
            lambda facts, prior, price: 42.0,
        )
    )

    engine = FundamentalAnalysisEngine(registry=registry)
    result = engine.analyze(_facts())

    assert set(result.ratios.keys()) == {"future_smart_money_placeholder"}
    assert result.get("future_smart_money_placeholder").latest() == 42.0


def test_engine_default_registry_is_unaffected_by_custom_registries():
    before = {spec.name for spec in DEFAULT_RATIO_REGISTRY.all_specs()}

    custom = RatioRegistry()
    custom.register(
        RatioSpec("temp", RatioCategory.PROFITABILITY, lambda facts, prior, price: 1.0)
    )

    after = {spec.name for spec in DEFAULT_RATIO_REGISTRY.all_specs()}
    assert before == after
    assert "temp" not in after


def test_default_registry_has_exactly_the_m23_ratio_set():
    names = {spec.name for spec in DEFAULT_RATIO_REGISTRY.all_specs()}
    assert names == EXPECTED_DEFAULT_RATIO_NAMES
