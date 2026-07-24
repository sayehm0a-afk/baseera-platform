"""Integration tests for CompositeIntelligenceEngine, using real
TechnicalAnalysisEngine (M2.2) and FundamentalAnalysisEngine (M2.3)
output -- proving the full, real fusion pipeline works end-to-end, not
just against fakes (see factors/test_*.py for the fake-based unit
tests of each factor's own logic).
"""

from datetime import date, datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.analysis.composite.composite_intelligence_engine import CompositeIntelligenceEngine
from src.analysis.composite.registry import (
    DEFAULT_COMPOSITE_REGISTRY,
    CompositeFactorRegistry,
    CompositeFactorSpec,
)
from src.analysis.composite.types import (
    Agreement,
    CompositeCategory,
    CompositeFactorOutput,
    DataCompleteness,
    build_envelope,
)
from src.analysis.core.contracts import AnalysisEngineResult, AnalysisOutput
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.types import FundamentalFacts
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine

EXPECTED_DEFAULT_FACTOR_NAMES = {
    "data_quality_summary",
    "trend_fundamental_alignment",
    "valuation_momentum_context",
}


def _make_uptrend_ohlcv(n=60):
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 100 + np.arange(n, dtype="float64") * 1.5
    df = pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(n, 100000.0),
        },
        index=index,
    )
    df.index.name = "timestamp"
    return df


def _make_downtrend_ohlcv(n=40):
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    close = 300 - np.arange(n, dtype="float64") * 2.0
    df = pd.DataFrame(
        {
            "open": close + 0.2,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "volume": np.full(n, 100000.0),
        },
        index=index,
    )
    df.index.name = "timestamp"
    return df


def _facts(revenue=1000.0, eps=0.3, period_end=date(2024, 12, 31)):
    return FundamentalFacts(
        stock_id=1,
        period_type="annual",
        fiscal_period_end=period_end,
        revenue=revenue,
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
        eps=eps,
        dividend_per_share=0.1,
    )


def _envelopes_from_real_engines(ohlcv_df, facts, prior_facts, market_price, now, fundamental_as_of=None):
    tech_result = TechnicalAnalysisEngine().analyze(ohlcv_df)
    fund_result = FundamentalAnalysisEngine().analyze(facts, prior_facts=prior_facts, market_price=market_price)

    return {
        "technical_analysis": build_envelope("technical_analysis", tech_result, as_of=now, now=now),
        "fundamental_analysis": build_envelope(
            "fundamental_analysis", fund_result, as_of=fundamental_as_of or now, now=now
        ),
    }


def test_composite_engine_fuses_real_technical_and_fundamental_results():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    envelopes = _envelopes_from_real_engines(
        _make_uptrend_ohlcv(),
        _facts(revenue=1000.0),
        _facts(revenue=800.0, period_end=date(2023, 12, 31)),
        market_price=15.0,
        now=now,
    )

    result = CompositeIntelligenceEngine().analyze(envelopes)

    assert isinstance(result, AnalysisEngineResult)
    for factor in result.factors.values():
        assert isinstance(factor, AnalysisOutput)
    assert set(result.factors.keys()) == EXPECTED_DEFAULT_FACTOR_NAMES


def test_strong_uptrend_and_positive_growth_agree_bullish():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    envelopes = _envelopes_from_real_engines(
        _make_uptrend_ohlcv(),
        _facts(revenue=1000.0),
        _facts(revenue=800.0, period_end=date(2023, 12, 31)),
        market_price=15.0,
        now=now,
    )

    result = CompositeIntelligenceEngine().analyze(envelopes)
    alignment = result.get("trend_fundamental_alignment")

    assert alignment.value == pytest.approx(1.0)
    assert alignment.agreement == Agreement.AGREE
    assert alignment.completeness == DataCompleteness.COMPLETE


def test_strong_downtrend_with_positive_growth_disagrees():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    envelopes = _envelopes_from_real_engines(
        _make_downtrend_ohlcv(),
        _facts(revenue=1000.0),
        _facts(revenue=800.0, period_end=date(2023, 12, 31)),
        market_price=15.0,
        now=now,
    )

    result = CompositeIntelligenceEngine().analyze(envelopes)
    alignment = result.get("trend_fundamental_alignment")

    assert alignment.value == pytest.approx(0.0)
    assert alignment.agreement == Agreement.DISAGREE


def test_data_quality_summary_reflects_mixed_freshness():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    envelopes = _envelopes_from_real_engines(
        _make_uptrend_ohlcv(),
        _facts(revenue=1000.0),
        _facts(revenue=800.0, period_end=date(2023, 12, 31)),
        market_price=15.0,
        now=now,
        fundamental_as_of=now - timedelta(days=10),  # AGING under the default policy, not FRESH
    )

    result = CompositeIntelligenceEngine().analyze(envelopes)
    quality = result.get("data_quality_summary")

    assert quality.value == pytest.approx(0.5)
    assert quality.completeness == DataCompleteness.COMPLETE


def test_valuation_momentum_context_resolves_with_real_engines():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    envelopes = _envelopes_from_real_engines(
        _make_uptrend_ohlcv(),
        _facts(revenue=1000.0),
        _facts(revenue=800.0, period_end=date(2023, 12, 31)),
        market_price=15.0,
        now=now,
    )

    result = CompositeIntelligenceEngine().analyze(envelopes)
    context = result.get("valuation_momentum_context")

    assert context.completeness == DataCompleteness.COMPLETE
    assert 0.0 <= context.value <= 1.0
    assert "fundamental_analysis.price_to_earnings" in context.explanation


def test_latest_snapshot_has_one_entry_per_factor():
    now = datetime(2026, 3, 1, tzinfo=timezone.utc)
    envelopes = _envelopes_from_real_engines(
        _make_uptrend_ohlcv(),
        _facts(revenue=1000.0),
        _facts(revenue=800.0, period_end=date(2023, 12, 31)),
        market_price=15.0,
        now=now,
    )

    snapshot = CompositeIntelligenceEngine().analyze(envelopes).latest_snapshot()

    assert set(snapshot.keys()) == EXPECTED_DEFAULT_FACTOR_NAMES


def test_get_raises_key_error_for_unknown_factor():
    result = CompositeIntelligenceEngine().analyze({})
    with pytest.raises(KeyError):
        result.get("does_not_exist")


def test_engine_handles_empty_envelopes_without_raising():
    result = CompositeIntelligenceEngine().analyze({})

    assert set(result.factors.keys()) == EXPECTED_DEFAULT_FACTOR_NAMES
    for factor in result.factors.values():
        assert factor.value is None
        assert factor.completeness == DataCompleteness.INSUFFICIENT


# ---------------------------------------------------------------------------
# Extension point: a registry-driven, forward-looking consumer should be
# able to add a brand-new composite factor without CompositeIntelligenceEngine
# or any existing factor changing at all.
# ---------------------------------------------------------------------------


def test_engine_works_with_a_custom_registry_extension():
    registry = CompositeFactorRegistry()
    registry.register(
        CompositeFactorSpec(
            "future_news_placeholder",
            CompositeCategory.CONTEXT,
            ["news_intelligence"],
            lambda envelopes: CompositeFactorOutput(
                name="future_news_placeholder",
                category=CompositeCategory.CONTEXT,
                value=42.0,
                completeness=DataCompleteness.COMPLETE,
                agreement=None,
                contributing_engines=list(envelopes.keys()),
                explanation={},
            ),
        )
    )

    engine = CompositeIntelligenceEngine(registry=registry)
    result = engine.analyze({})

    assert set(result.factors.keys()) == {"future_news_placeholder"}
    assert result.get("future_news_placeholder").latest() == 42.0


def test_engine_default_registry_is_unaffected_by_custom_registries():
    before = {spec.name for spec in DEFAULT_COMPOSITE_REGISTRY.all_specs()}

    custom = CompositeFactorRegistry()
    custom.register(
        CompositeFactorSpec(
            "temp",
            CompositeCategory.CONTEXT,
            [],
            lambda envelopes: CompositeFactorOutput(
                name="temp",
                category=CompositeCategory.CONTEXT,
                value=1.0,
                completeness=DataCompleteness.COMPLETE,
                agreement=None,
                contributing_engines=[],
                explanation={},
            ),
        )
    )

    after = {spec.name for spec in DEFAULT_COMPOSITE_REGISTRY.all_specs()}
    assert before == after
    assert "temp" not in after


def test_default_registry_has_exactly_the_m24_factor_set():
    names = {spec.name for spec in DEFAULT_COMPOSITE_REGISTRY.all_specs()}
    assert names == EXPECTED_DEFAULT_FACTOR_NAMES
