"""Verifies main.py's own module-level side effects -- importing it is
the real production startup path, and this test proves that path
actually populates src.analysis.core.registry.DEFAULT_ENGINE_REGISTRY,
not just tests that happen to import bootstrap.py directly.
"""

import main  # noqa: F401 -- import side effect is exactly what's under test

from src.analysis.composite.composite_intelligence_engine import CompositeIntelligenceEngine
from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY
from src.analysis.experts.council_engine import CouncilEngine
from src.analysis.experts.registry import DEFAULT_EXPERT_REGISTRY
from src.analysis.experts.types import Council
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine


def test_importing_main_populates_the_engine_registry():
    names = {spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs()}
    assert names == {
        "technical_analysis",
        "fundamental_analysis",
        "composite_analysis",
        "technical_council",
    }


def test_registry_engine_factories_are_usable_after_importing_main():
    assert isinstance(DEFAULT_ENGINE_REGISTRY.get("technical_analysis").engine_factory(), TechnicalAnalysisEngine)
    assert isinstance(
        DEFAULT_ENGINE_REGISTRY.get("fundamental_analysis").engine_factory(), FundamentalAnalysisEngine
    )
    assert isinstance(
        DEFAULT_ENGINE_REGISTRY.get("composite_analysis").engine_factory(), CompositeIntelligenceEngine
    )
    technical_council = DEFAULT_ENGINE_REGISTRY.get("technical_council").engine_factory()
    assert isinstance(technical_council, CouncilEngine)


def test_importing_main_populates_the_expert_registry():
    # The registry-reachability guard BEIF Section 8 requires -- proving
    # DEFAULT_EXPERT_REGISTRY is non-empty via the real production import
    # path (main.py), not just via a test that happens to import
    # src.analysis.experts.technical directly first.
    expert_ids = {spec.expert_id for spec in DEFAULT_EXPERT_REGISTRY.all_specs()}
    assert {
        "technical.trend",
        "technical.momentum",
        "technical.volatility",
        "technical.volume",
        "technical.candlestick",
    }.issubset(expert_ids)
    assert DEFAULT_EXPERT_REGISTRY.get("technical.trend").council is Council.TECHNICAL
    assert DEFAULT_EXPERT_REGISTRY.get("technical.momentum").council is Council.TECHNICAL
    assert DEFAULT_EXPERT_REGISTRY.get("technical.volatility").council is Council.TECHNICAL
    assert DEFAULT_EXPERT_REGISTRY.get("technical.volume").council is Council.TECHNICAL
    assert DEFAULT_EXPERT_REGISTRY.get("technical.candlestick").council is Council.TECHNICAL


def test_main_boots_expected_routes():
    # As of FastAPI 0.139.2, app.include_router() (used by M2.12's new
    # routers) registers a lazily-resolved _IncludedRouter wrapper in
    # app.routes, not a flat APIRoute per endpoint -- len(app.routes) no
    # longer counts real endpoints once any router is included (it did
    # when every route in this file was a bare @app.get(...), which is
    # why this test previously asserted a raw len(app.routes) == 11).
    # app.openapi()["paths"] always fully resolves every router
    # (included or not), so it is used here instead as the robust,
    # FastAPI-internals-proof way to count real endpoints.
    paths = set(main.app.openapi()["paths"].keys())
    assert paths == {
        "/health/live",
        "/health/ready",
        "/metrics",
        "/stats",
        "/api/tasks",
        "/api/tasks/{task_id}",
        "/api/agents/{agent_id}",
        "/api/v1/analysis/{symbol}/technical",
        "/api/v1/analysis/{symbol}/fundamental",
        "/api/v1/analysis/{symbol}/composite",
        "/api/v1/analysis/{symbol}/councils/technical",
        "/api/v1/stocks",
        "/api/v1/stocks/{symbol}",
        "/api/v1/market-data/{symbol}/ohlcv",
        "/auth/login",
        "/auth/refresh",
    }
