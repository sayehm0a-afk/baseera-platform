"""Full-pipeline integration test: data ingestion -> real database ->
loaders -> Technical Engine -> Fundamental Engine -> Composite Engine,
as one continuous test.

Scope item 2 of the approved M2.4.1 Foundation Hardening milestone.
Every unit test elsewhere in the suite exercises one stage in
isolation (ingestion against a DB, a loader against pre-seeded rows,
an engine against an in-memory DataFrame/facts object). Nothing,
before this file, proved the full chain -- ingest via the real
ingest_ohlcv/ingest_fundamentals functions, persisted to a real
(SQLite) database, read back via the real ohlcv_loader/
fundamental_loader, fed into the real TechnicalAnalysisEngine and
FundamentalAnalysisEngine, and fused by the real
CompositeIntelligenceEngine -- works end to end without a break
anywhere in that boundary (e.g. a column-name mismatch or a Decimal/
float conversion issue that only a full round trip would catch).

Uses SQLite (not Postgres) for the same reason every other DB-backed
unit test in this repo does: fast, isolated, no external service
dependency -- consistent with the existing test fixture pattern used
throughout tests/unit/domain/, tests/unit/market_data/, and
tests/unit/analysis/.

======================================================================
VERIFIED DEFECT (found and fixed at M2.10): dormant DEFAULT_EXPERT_REGISTRY
======================================================================

Root cause: Stage 7 below (added at M2.7) calls
`CouncilEngine(council=Council.TECHNICAL).analyze(...)`, which reads
`DEFAULT_EXPERT_REGISTRY` (src/analysis/experts/registry.py).
That registry is only populated as an *import-time side effect* of
importing `src.analysis.experts.technical` (each expert module
self-registers when its parent package is imported -- see that
package's own __init__.py docstring). This file itself never imported
that package, or `src.analysis.experts.bootstrap` (the actual
production composition root main.py imports) -- it only imported the
`CouncilEngine`/`Council` *types*, which do not trigger the
registration side effect. `CompositeIntelligenceEngine`, by contrast,
imports its own factors package directly inside its own module
(src/analysis/composite/composite_intelligence_engine.py), making
Stage 6 self-sufficient wherever it is imported; `CouncilEngine` is
deliberately council-agnostic (it must support Fundamental/Saudi/Risk/
Intelligence-Learning councils too, per BEIF Section 6), so it cannot
safely import one specific council's expert package itself -- wiring
a specific council to the registry is `bootstrap.py`'s job by design,
not `CouncilEngine`'s. That correct separation is exactly what made
this dependency easy to omit at a call site.

Why it remained hidden: Stage 7's own assertions are directly
sensitive to this (an empty registry produces an empty CouncilResult,
which its own `assert set(council_result.experts.keys()) == {...}`
line already catches) -- but only when this file is executed in
genuine isolation. Every session before this fix ran it either as
part of the full suite or alongside other Technical Council test
files, and `tests/unit/test_main_boot.py` (which imports `main`,
which imports `src.analysis.experts.bootstrap`) reliably ran early
enough in test collection to populate the shared registry singleton
first -- masking the missing dependency completely. Verified directly
before this fix, in a fresh interpreter with no other test module
involved: `python -c "import tests.integration.test_full_pipeline; ..."`
showed `DEFAULT_EXPERT_REGISTRY` with zero registered specs.

Exact correction: `import src.analysis.experts.bootstrap` added below,
not `import src.analysis.experts.technical` directly -- bootstrap.py
is the real production composition root (the same module main.py
itself imports), and importing it exercises strictly more of the real
reachability path: it populates both `DEFAULT_EXPERT_REGISTRY` (via
its own `import src.analysis.experts.technical`) and
`DEFAULT_ENGINE_REGISTRY`'s `"technical_council"` entry (via its own
`register_default_councils()` call) -- confirmed directly: importing
`.technical` alone left `DEFAULT_ENGINE_REGISTRY` empty in a fresh
interpreter; importing `.bootstrap` populated both registries
correctly.

Isolation verification performed: `pytest
tests/integration/test_full_pipeline.py -v` run alone (passes);
`python -c "import tests.integration.test_full_pipeline; ..."` run in
a genuinely fresh interpreter, asserting >=4 registered expert specs
(passes); every other expert-layer test file in the repository run
individually, alone, to confirm none of them share this same latent
defect (all pass alone).

Regression protection added:
tests/integration/test_registry_reachability_regression.py -- a
dedicated, subprocess-based test (a truly fresh Python interpreter,
not just "this file run alone via pytest") that would fail
immediately, with a clear, specific message, if this file's bootstrap
import were ever accidentally removed again. See that file's own
docstring for why a subprocess, not just an in-process isolated pytest
run, is the correct regression-guard mechanism.

The same dormant-registry bug class M2.4.1 found and fixed twice
already (`DEFAULT_ENGINE_REGISTRY`'s missing bootstrap.py import in
main.py; `DEFAULT_COMPOSITE_REGISTRY`'s missing factors/__init__.py),
present a third time, here, since M2.7 added Stage 7 -- caught only
because M2.10's own validation discipline required running this file
in true isolation for the first time since M2.7.
"""

from datetime import date, datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

import src.analysis.experts.bootstrap  # noqa: F401 -- import side effect required, see module docstring
from src.analysis.composite.composite_intelligence_engine import CompositeIntelligenceEngine
from src.analysis.composite.types import Agreement, DataCompleteness, build_envelope
from src.analysis.core.contracts import AnalysisEngineResult, AnalysisOutput
from src.analysis.experts.council_engine import CouncilEngine
from src.analysis.experts.types import Council, ExpertDirection
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.fundamental_loader import load_fundamental_snapshots
from src.analysis.ohlcv_loader import load_price_bars
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine
from src.core.db.database import Base
from src.domain.models import PeriodType, Stock, Timeframe
from src.market_data.ingestion.ingest_fundamentals import ingest_fundamentals
from src.market_data.ingestion.ingest_ohlcv import ingest_ohlcv

SYMBOL = "1111"
BAR_COUNT = 40


class _SequentialMarketDataProvider:
    """A minimal IMarketDataProvider-shaped fake that replays one
    pre-built OHLCV bar per get_stock_data() call -- lets a real,
    unmodified ingest_ohlcv() build up multi-day history one call at a
    time, exactly as the real production call pattern would (one
    ingestion run per trading day), instead of hand-inserting rows.
    """

    def __init__(self, bars):
        self._bars = list(bars)
        self._index = 0

    async def authenticate(self):
        return True

    async def get_stock_data(self, symbol):
        bar = self._bars[self._index]
        self._index += 1
        return bar

    async def disconnect(self):
        return None


class _SequentialFundamentalDataProvider:
    """Same idea as _SequentialMarketDataProvider, for get_fundamentals()."""

    def __init__(self, snapshots):
        self._snapshots = list(snapshots)
        self._index = 0

    async def authenticate(self):
        return True

    async def get_fundamentals(self, symbol, period_type="annual"):
        snapshot = self._snapshots[self._index]
        self._index += 1
        return snapshot

    async def disconnect(self):
        return None


def _make_ohlcv_bars(n):
    bars = []
    start = date(2024, 1, 1)
    for i in range(n):
        close = 100.0 + i * 1.5  # steady uptrend, same shape used elsewhere to guarantee a bullish SuperTrend
        bars.append(
            {
                "symbol": SYMBOL,
                "open": close - 0.2,
                "high": close + 0.5,
                "low": close - 0.5,
                "close": close,
                "volume": 100_000 + i * 100,
                "timestamp": datetime.combine(
                    start + timedelta(days=i), datetime.min.time(), tzinfo=timezone.utc
                ).isoformat(),
                "source": "dev-synthetic",
                "is_synthetic": True,
            }
        )
    return bars


def _make_fundamental_snapshots():
    prior = {
        "symbol": SYMBOL,
        "period_type": "annual",
        "fiscal_period_end": date(2023, 12, 31).isoformat(),
        "revenue": 800_000_000,
        "gross_profit": 320_000_000,
        "net_income": 100_000_000,
        "total_assets": 2_800_000_000,
        "total_liabilities": 1_200_000_000,
        "total_equity": 1_600_000_000,
        "current_assets": 650_000_000,
        "current_liabilities": 380_000_000,
        "inventory": 90_000_000,
        "cash_and_equivalents": 180_000_000,
        "total_debt": 480_000_000,
        "shares_outstanding": 500_000_000,
        "eps": 0.20,
        "dividend_per_share": 0.08,
        "source": "dev-synthetic",
        "is_synthetic": True,
    }
    current = {
        "symbol": SYMBOL,
        "period_type": "annual",
        "fiscal_period_end": date(2024, 12, 31).isoformat(),
        "revenue": 1_000_000_000,
        "gross_profit": 400_000_000,
        "net_income": 150_000_000,
        "total_assets": 3_000_000_000,
        "total_liabilities": 1_200_000_000,
        "total_equity": 1_800_000_000,
        "current_assets": 700_000_000,
        "current_liabilities": 400_000_000,
        "inventory": 100_000_000,
        "cash_and_equivalents": 200_000_000,
        "total_debt": 500_000_000,
        "shares_outstanding": 500_000_000,
        "eps": 0.30,
        "dividend_per_share": 0.10,
        "source": "dev-synthetic",
        "is_synthetic": True,
    }
    # ingest_fundamentals upserts by (stock_id, period_type, fiscal_period_end),
    # so ingesting prior before current is what makes both survive as two
    # distinct rows rather than one overwriting the other.
    return [prior, current]


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_full_pipeline_ingestion_through_composite_fusion(session_factory):
    # --- Stage 1: ingestion (real ingest_ohlcv/ingest_fundamentals, real upsert/dedup logic) ---
    market_provider = _SequentialMarketDataProvider(_make_ohlcv_bars(BAR_COUNT))
    for _ in range(BAR_COUNT):
        result = await ingest_ohlcv([SYMBOL], market_provider, session_factory)
        assert result.success is True

    fundamental_provider = _SequentialFundamentalDataProvider(_make_fundamental_snapshots())
    for _ in range(2):
        result = await ingest_fundamentals([SYMBOL], fundamental_provider, session_factory, period_type="annual")
        assert result.success is True

    # --- Stage 2: real database (row-level sanity check before moving on) ---
    session = session_factory()
    stock = session.query(Stock).filter_by(symbol=SYMBOL).one()
    assert stock.name_en == f"Stock {SYMBOL}"

    # --- Stage 3: loaders (real ohlcv_loader/fundamental_loader) ---
    price_df = load_price_bars(session, stock.id, Timeframe.ONE_DAY)
    assert len(price_df) == BAR_COUNT

    fundamental_facts = load_fundamental_snapshots(session, stock.id, PeriodType.ANNUAL, limit=2)
    assert len(fundamental_facts) == 2
    assert fundamental_facts[0].fiscal_period_end == date(2024, 12, 31)  # most recent first
    assert fundamental_facts[1].fiscal_period_end == date(2023, 12, 31)
    session.close()

    # --- Stage 4: Technical Engine (real, on the real loaded DataFrame) ---
    technical_result = TechnicalAnalysisEngine().analyze(price_df)
    assert isinstance(technical_result, AnalysisEngineResult)
    for output in technical_result.indicators.values():
        assert isinstance(output, AnalysisOutput)
    # Steady, sustained uptrend -> SuperTrend should have settled bullish by the last bar.
    assert technical_result.supertrend.direction.dropna().iloc[-1] == 1.0

    # --- Stage 5: Fundamental Engine (real, on the real loaded facts) ---
    latest_price = float(price_df["close"].iloc[-1])
    fundamental_result = FundamentalAnalysisEngine().analyze(
        fundamental_facts[0], prior_facts=fundamental_facts[1], market_price=latest_price
    )
    assert isinstance(fundamental_result, AnalysisEngineResult)
    for output in fundamental_result.ratios.values():
        assert isinstance(output, AnalysisOutput)
    # revenue grew 800M -> 1000M = +25%, computed from real ingested/loaded data end to end.
    assert fundamental_result.revenue_growth == pytest.approx(0.25)

    # --- Stage 6: Composite Engine (real, fusing both real engine results) ---
    now = datetime(2026, 1, 1, tzinfo=timezone.utc)
    envelopes = {
        "technical_analysis": build_envelope("technical_analysis", technical_result, as_of=now, now=now),
        "fundamental_analysis": build_envelope("fundamental_analysis", fundamental_result, as_of=now, now=now),
    }
    composite_result = CompositeIntelligenceEngine().analyze(envelopes)

    assert isinstance(composite_result, AnalysisEngineResult)
    assert set(composite_result.factors.keys()) == {
        "data_quality_summary",
        "trend_fundamental_alignment",
        "valuation_momentum_context",
    }

    alignment = composite_result.get("trend_fundamental_alignment")
    assert alignment.completeness == DataCompleteness.COMPLETE
    # Bullish trend (direction=+1) + positive revenue growth (+25%) -> agree bullish,
    # the same real chain the M2.4 integration test exercises, but now the inputs
    # came from real ingestion + real persistence + real loading, not fabricated
    # in-memory DataFrames/facts.
    assert alignment.value == pytest.approx(1.0)
    assert alignment.agreement == Agreement.AGREE

    quality = composite_result.get("data_quality_summary")
    assert quality.completeness == DataCompleteness.COMPLETE
    assert quality.value == pytest.approx(1.0)  # both envelopes fresh (same `now`)

    # --- Stage 7: Technical Council / Trend + Momentum + Volatility Expert (real, on
    # the real technical_analysis envelope already built above) -- BEIF's "one more
    # hop" extension, M2.7 (Trend), M2.8 (Momentum), M2.9 (Volatility). ---
    # All three experts ship EXPERIMENTAL (no shadow-mode history yet, per BEIF
    # Section 15), so CouncilEngine.analyze() must be asked for every status
    # explicitly to see them -- exactly the promotion-gate behavior that status is
    # supposed to enforce.
    technical_council = CouncilEngine(council=Council.TECHNICAL)
    council_result = technical_council.analyze(SYMBOL, envelopes, include_all_statuses=True)

    assert isinstance(council_result, AnalysisEngineResult)
    assert set(council_result.experts.keys()) == {
        "technical.trend",
        "technical.momentum",
        "technical.volatility",
        "technical.volume",
    }

    trend = council_result.get("technical.trend")
    assert isinstance(trend, AnalysisOutput)
    # Steady, sustained uptrend (same 40-bar series Stage 4 already confirmed a
    # bullish SuperTrend on): EMA-20 above SMA-20, SuperTrend bullish -> full
    # directional agreement, real ADX strength scaling the magnitude.
    assert trend.direction == ExpertDirection.BULLISH
    assert trend.normalized_score > 0.0
    assert trend.conflicts == ()
    assert trend.completeness == DataCompleteness.COMPLETE
    assert trend.symbol == SYMBOL

    momentum = council_result.get("technical.momentum")
    assert isinstance(momentum, AnalysisOutput)
    # A monotonic 40-bar uptrend with no down days pushes RSI-14 strongly
    # positive and keeps MACD's histogram above zero -> bullish agreement,
    # on real, non-mocked indicator output.
    assert momentum.direction == ExpertDirection.BULLISH
    assert momentum.normalized_score > 0.0
    assert momentum.completeness == DataCompleteness.COMPLETE
    assert momentum.symbol == SYMBOL

    volatility = council_result.get("technical.volatility")
    assert isinstance(volatility, AnalysisOutput)
    # Non-directional by design (Architectural Decision 1) -- direction is
    # always NEUTRAL regardless of how much real intensity the real
    # Bollinger/ATR computation over this series reports.
    assert volatility.direction == ExpertDirection.NEUTRAL
    assert volatility.normalized_score is not None
    assert 0.0 <= volatility.normalized_score <= 1.0
    assert volatility.conflicts == ()

    volume = council_result.get("technical.volume")
    assert isinstance(volume, AnalysisOutput)
    # Every one of the 40 synthetic bars closes strictly higher than the
    # last (close = 100 + i*1.5, never flat, never down) -> OBV's own
    # construction makes it strictly increasing every bar, on real,
    # non-mocked indicator output -> unambiguous 20-bar bullish trend.
    assert volume.direction == ExpertDirection.BULLISH
    assert volume.normalized_score > 0.0
    assert volume.completeness == DataCompleteness.COMPLETE
    assert volume.conflicts == ()
    assert volume.symbol == SYMBOL
    assert volatility.completeness == DataCompleteness.COMPLETE
    assert volatility.symbol == SYMBOL
