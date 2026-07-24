"""Cross-engine conformance tests.

Proof that M2.2's TechnicalAnalysisEngine (imported here read-only,
completely unmodified since it was merged) and M2.3's
FundamentalAnalysisEngine both satisfy the shared AnalysisOutput/
AnalysisEngineResult contract in src.analysis.core.contracts, without
either engine importing the other or depending on anything beyond
src.analysis.core. This is the direct evidence for the architectural
directive that both engines be "completely independent" while still
being "uniformly consumable" by a future Composite Analysis Engine.
"""

from datetime import date

import numpy as np
import pandas as pd

from src.analysis.core.contracts import AnalysisEngineResult, AnalysisOutput
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.types import FundamentalFacts
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine


def _make_ohlcv(n=60, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1, n))
    high = close + np.abs(rng.normal(0, 1, n))
    low = close - np.abs(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(10000, 100000, n).astype(float)
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def _facts():
    return FundamentalFacts(
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


def test_technical_analysis_result_satisfies_the_unified_contract():
    result = TechnicalAnalysisEngine().analyze(_make_ohlcv())

    assert isinstance(result, AnalysisEngineResult)
    for output in result.indicators.values():
        assert isinstance(output, AnalysisOutput)


def test_fundamental_analysis_result_satisfies_the_unified_contract():
    result = FundamentalAnalysisEngine().analyze(_facts())

    assert isinstance(result, AnalysisEngineResult)
    for output in result.ratios.values():
        assert isinstance(output, AnalysisOutput)


def test_both_engine_results_expose_an_identical_generic_shape():
    # A future Composite Analysis Engine can call get()/latest_snapshot()
    # on either result without knowing, or caring, which engine
    # produced it.
    technical_result = TechnicalAnalysisEngine().analyze(_make_ohlcv())
    fundamental_result = FundamentalAnalysisEngine().analyze(_facts())

    for result in (technical_result, fundamental_result):
        snapshot = result.latest_snapshot()
        assert isinstance(snapshot, dict)
        assert len(snapshot) > 0
        # get() on any name present in the snapshot must not raise.
        for name in snapshot:
            result.get(name)
