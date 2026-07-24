"""The six extension points: one `typing.Protocol` per module named in
the current instruction (Live Market Scanner, Recommendation Engine,
Portfolio Analysis, Risk Engine, Alert System, AI Decision Layer).

Structural, not base classes to inherit from -- the same choice
`src.analysis.core.contracts` and
`src.core.autonomous_intelligence_layer.contracts.interfaces` already
make, for the same reason: a future concrete implementation only needs
the right shape, not an inheritance relationship with this module, and
can be checked with `isinstance(x, IRecommendationEngine)` (every
interface below is `@runtime_checkable`) without either side importing
the other.

None of these interfaces are implemented anywhere in this codebase. No
class in this repository currently satisfies any of them -- see
`tests/unit/analysis/intelligence/contracts/test_interfaces.py` for the
minimal, test-only fake classes proving each Protocol is actually
satisfiable, not vacuous, which must never be mistaken for real
implementations.
"""

from typing import Protocol, Tuple, Union, runtime_checkable

from src.analysis.intelligence.contracts.types import (
    AlertEvent,
    AlertRule,
    DecisionContext,
    DecisionOutput,
    PortfolioAnalysisResult,
    PortfolioPosition,
    RecommendationOutput,
    RiskAssessment,
    ScanCriteria,
    ScanMatch,
)
from src.market_data.models import RecommendationInput


@runtime_checkable
class IMarketScanner(Protocol):
    """Live Market Scanner's extension point: scans a universe of
    symbols against `ScanCriteria` and returns every match. What
    "scanning all Saudi stocks" costs in SAHMK API calls, and how that
    is budgeted, is explicitly a concrete implementation's concern --
    see integration.py for why this package does not decide it."""

    def scan(self, criteria: ScanCriteria) -> Tuple[ScanMatch, ...]:
        ...


@runtime_checkable
class IRecommendationEngine(Protocol):
    """Produces one `RecommendationOutput` for a symbol from already-
    computed Technical/Fundamental/Council/Composite results (received
    as a `src.market_data.models.RecommendationInput`, per
    integration.py) -- never raw provider data, never a guaranteed-
    profit claim (see `types.MANDATORY_DISCLAIMER_AR`/`_EN`)."""

    def recommend(self, input_data: RecommendationInput) -> RecommendationOutput:
        ...


@runtime_checkable
class IPortfolioAnalyzer(Protocol):
    """Analyzes a set of positions (concentration, aggregate exposure,
    aggregate risk) -- never trade execution, never a broker
    integration; purely an analysis of positions the caller already
    holds."""

    def analyze(self, positions: Tuple[PortfolioPosition, ...]) -> PortfolioAnalysisResult:
        ...


@runtime_checkable
class IRiskEngine(Protocol):
    """Produces a `RiskAssessment` for a symbol (or, with `symbol=None`
    in the returned assessment, a portfolio/market-level one). What
    "risk factors" are computed from -- volatility, liquidity,
    concentration, data quality -- is a concrete engine's own design,
    same discipline as every other interface in this package."""

    def assess(self, symbol_or_positions: Union[str, Tuple[PortfolioPosition, ...]]) -> RiskAssessment:
        ...


@runtime_checkable
class IAlertSystem(Protocol):
    """Evaluates a set of registered `AlertRule`s against current data
    and returns every `AlertEvent` that fired. Registration/storage of
    rules is a concrete implementation's own concern -- this interface
    only fixes the evaluate-and-report calling convention."""

    def register_rule(self, rule: AlertRule) -> None:
        ...

    def evaluate(self) -> Tuple[AlertEvent, ...]:
        ...


@runtime_checkable
class IAIDecisionLayer(Protocol):
    """The top-level fusion point: combines a `DecisionContext`
    (already-computed recommendation/risk/portfolio context) into one
    final `DecisionOutput`. Deliberately the *last* interface in this
    package's call chain, mirroring how `CompositeIntelligenceEngine`
    sits above Technical/Fundamental, not beside them -- this is not a
    seventh independent module, it is the fusion layer the other six
    feed into."""

    def decide(self, context: DecisionContext) -> DecisionOutput:
        ...
