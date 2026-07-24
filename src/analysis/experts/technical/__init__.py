"""Technical Council's experts, self-registering into
src.analysis.experts.registry.DEFAULT_EXPERT_REGISTRY.

Imported here (not just defined in their own modules) so that
importing this package -- which src/analysis/experts/bootstrap.py does
-- is enough to trigger every Technical Council expert's
self-registration. Mirrors src/analysis/composite/factors/__init__.py's
identical pattern for the same reason: without this, whether
DEFAULT_EXPERT_REGISTRY is actually populated depends entirely on
which other modules happened to be imported first -- exactly the
dormant-registry bug class M2.4.1 found and fixed twice already
(DEFAULT_ENGINE_REGISTRY's missing bootstrap.py import in main.py, and
DEFAULT_COMPOSITE_REGISTRY's missing factors/__init__.py), applied
here from the start rather than retrofitted later.
"""

from src.analysis.experts.technical import momentum_expert, trend_expert

__all__ = ["trend_expert", "momentum_expert"]
