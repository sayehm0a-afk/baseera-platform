"""The unified output contract every analysis engine's result must
satisfy.

These are structural (`typing.Protocol`), not base classes to inherit
from -- deliberately. A structural contract lets M2.2's already-merged
`IndicatorOutput`/`TechnicalAnalysisResult` (src/analysis/types.py,
src/analysis/technical_analysis_engine.py) satisfy this contract with
zero changes to that code: they already have the right shape. Any
future engine's result type only needs to match the same shape, not
inherit from anything defined here or import any other engine's
module. This is what keeps Technical Analysis and Fundamental Analysis
(and every future engine) completely independent of one another while
still being uniformly consumable by a future Composite Analysis
Engine, Signal Engine, Confidence Scoring layer, Explainable AI layer,
or AI Decision Layer.

`category` is intentionally typed `Any`: each engine owns its own
category taxonomy (IndicatorCategory, RatioCategory, and whatever a
future News/Macro/Smart-Money engine defines) rather than sharing one
closed enum here -- a shared closed enum of "every analysis category
that will ever exist" would have to be edited every time a new engine
is added, which is the Open/Closed violation this contract exists to
avoid.
"""

from typing import Any, Dict, Protocol, runtime_checkable


@runtime_checkable
class AnalysisOutput(Protocol):
    """One named signal/ratio/value produced by any analysis engine."""

    name: str
    category: Any
    value: Any

    def latest(self) -> Any:
        """The current scalar/summary value(s) -- what a downstream
        consumer (Composite/Signal/Confidence/Decision layer) wants,
        not necessarily the full history behind it."""
        ...


@runtime_checkable
class AnalysisEngineResult(Protocol):
    """The aggregate result of running one analysis engine once.

    A future Composite Analysis Engine can hold a
    `Dict[str, AnalysisEngineResult]` (one per engine that ran) and
    call `.latest_snapshot()` on each without importing any concrete
    engine's result type.
    """

    def get(self, name: str) -> Any:
        """Look up one named output by its engine-specific name."""
        ...

    def latest_snapshot(self) -> Dict[str, Any]:
        """Every output's current value(s), keyed by name."""
        ...
