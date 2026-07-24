"""The composition root: the one module in this codebase that imports
TechnicalAnalysisEngine (M2.2), FundamentalAnalysisEngine (M2.3), and
CompositeIntelligenceEngine (M2.4), and registers them into the shared
DEFAULT_ENGINE_REGISTRY.

Importing this module is what makes DEFAULT_ENGINE_REGISTRY non-empty
in production code -- no engine self-registers, and
src/analysis/core/registry.py itself imports none of them. This is a
standard composition-root pattern, not an Open/Closed violation: the
engine classes and the registry class never change when a future
engine (News Intelligence, Market Intelligence, Sector Intelligence,
Macro Analysis, Smart Money/ICT, Wyckoff, ...) is added -- only this
one file gains one new import and one new .register() call, exactly
the same shape src/analysis/registry.py's build_default_registry()
already uses for listing all of M2.2's indicators.

Nothing about TechnicalAnalysisEngine, FundamentalAnalysisEngine, or
CompositeIntelligenceEngine was modified to make this possible -- each
is imported here read-only, exactly as it was already merged.
CompositeResult (M2.4) satisfies AnalysisEngineResult structurally the
same way TechnicalAnalysisResult/FundamentalAnalysisResult do, so
registering CompositeIntelligenceEngine here is exactly as valid a
catalog entry as either of the other two -- proof that the extension
point holds recursively, not just for the two engines it was designed
against first.
"""

from src.analysis.composite.composite_intelligence_engine import CompositeIntelligenceEngine
from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY, EngineSpec
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine


def register_default_engines() -> None:
    """Idempotent: safe to call more than once (e.g. from multiple test
    modules) -- registration is skipped for names already present."""
    existing = {spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs()}

    if "technical_analysis" not in existing:
        DEFAULT_ENGINE_REGISTRY.register(
            EngineSpec(
                name="technical_analysis",
                description="Price-action/indicator analysis over OHLCV bars (M2.2).",
                engine_factory=TechnicalAnalysisEngine,
            )
        )

    if "fundamental_analysis" not in existing:
        DEFAULT_ENGINE_REGISTRY.register(
            EngineSpec(
                name="fundamental_analysis",
                description="Financial-statement ratio analysis (M2.3).",
                engine_factory=FundamentalAnalysisEngine,
            )
        )

    if "composite_analysis" not in existing:
        DEFAULT_ENGINE_REGISTRY.register(
            EngineSpec(
                name="composite_analysis",
                description=(
                    "Cross-engine agreement/context/data-quality fusion over other "
                    "engines' already-computed results (M2.4)."
                ),
                engine_factory=CompositeIntelligenceEngine,
            )
        )


register_default_engines()
