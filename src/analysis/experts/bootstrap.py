"""The BEIF composition root: the one module that imports every
council package (today: technical) and registers a CouncilEngine per
council into src.analysis.core.registry.DEFAULT_ENGINE_REGISTRY.

Mirrors src.analysis.core.bootstrap's register_default_engines()
pattern exactly, as a separate, sibling composition root rather than a
modification to that module -- BEIF experts are a fourth, independent
registry (src.analysis.experts.registry.DEFAULT_EXPERT_REGISTRY,
distinct from IndicatorRegistry/RatioRegistry/CompositeFactorRegistry)
and this file's job is analogous but distinct: it populates
DEFAULT_EXPERT_REGISTRY (by importing src.analysis.experts.technical,
which self-registers Trend Expert) and then registers one
CouncilEngine per open council into DEFAULT_ENGINE_REGISTRY, so a
council's output is discoverable as a peer of "technical_analysis" /
"fundamental_analysis" / "composite_analysis", exactly as BEIF
Section 2 requires.

Importing this module (from main.py, alongside the existing
`import src.analysis.core.bootstrap`) is what makes both registries
non-empty in the real running application -- the same production-
reachability discipline M2.4.1 established after finding
DEFAULT_ENGINE_REGISTRY dormant in production twice.
"""

import src.analysis.experts.technical  # noqa: F401 -- import triggers Trend Expert self-registration
from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY, EngineSpec
from src.analysis.experts.council_engine import CouncilEngine
from src.analysis.experts.types import Council


def register_default_councils() -> None:
    """Idempotent: safe to call more than once (e.g. from multiple test
    modules) -- registration is skipped for names already present."""
    existing = {spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs()}

    if "technical_council" not in existing:
        DEFAULT_ENGINE_REGISTRY.register(
            EngineSpec(
                name="technical_council",
                description=(
                    "Expert-level interpretation over already-computed Technical "
                    "Analysis Engine output (BEIF, M2.7)."
                ),
                engine_factory=lambda: CouncilEngine(council=Council.TECHNICAL),
            )
        )


register_default_councils()
