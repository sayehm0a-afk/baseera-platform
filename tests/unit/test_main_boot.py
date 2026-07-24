"""Verifies main.py's own module-level side effects -- importing it is
the real production startup path, and this test proves that path
actually populates src.analysis.core.registry.DEFAULT_ENGINE_REGISTRY,
not just tests that happen to import bootstrap.py directly.
"""

import main  # noqa: F401 -- import side effect is exactly what's under test

from src.analysis.composite.composite_intelligence_engine import CompositeIntelligenceEngine
from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine


def test_importing_main_populates_the_engine_registry():
    names = {spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs()}
    assert names == {"technical_analysis", "fundamental_analysis", "composite_analysis"}


def test_registry_engine_factories_are_usable_after_importing_main():
    assert isinstance(DEFAULT_ENGINE_REGISTRY.get("technical_analysis").engine_factory(), TechnicalAnalysisEngine)
    assert isinstance(
        DEFAULT_ENGINE_REGISTRY.get("fundamental_analysis").engine_factory(), FundamentalAnalysisEngine
    )
    assert isinstance(
        DEFAULT_ENGINE_REGISTRY.get("composite_analysis").engine_factory(), CompositeIntelligenceEngine
    )


def test_main_boots_11_routes():
    # Unchanged boot smoke test, now living alongside the registry check
    # so both are verified from the same real `import main`.
    assert len(main.app.routes) == 11
