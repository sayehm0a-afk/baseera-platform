"""Composite factors, self-registering into
src.analysis.composite.registry.DEFAULT_COMPOSITE_REGISTRY.

Imported here (not just defined in their own modules) so that
importing this package -- which src/analysis/composite/
composite_intelligence_engine.py now does -- is enough to trigger
every factor's self-registration. Mirrors src/domain/models/__init__.py's
identical pattern for the same reason: without this, whether
DEFAULT_COMPOSITE_REGISTRY is actually populated depends entirely on
which other modules happened to be imported first (e.g. by test
collection order), which is exactly the kind of hidden reachability
gap M2.4.1 exists to close -- the same bug class as
DEFAULT_ENGINE_REGISTRY's missing bootstrap.py import, just one layer
down, in the composite-factor-level registry instead of the
engine-level one.
"""

from src.analysis.composite.factors import data_quality, trend_fundamental_alignment, valuation_momentum_context

__all__ = ["data_quality", "trend_fundamental_alignment", "valuation_momentum_context"]
