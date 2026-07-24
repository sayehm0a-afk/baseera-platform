"""FundamentalAnalysisEngine: the single entry point for computing
every M2.3 ratio against one company's financial-statement facts.

Deliberately independent of TechnicalAnalysisEngine (M2.2) -- neither
imports the other, both satisfy src.analysis.core.contracts'
AnalysisOutput/AnalysisEngineResult structurally, and both are
registered into src.analysis.core.registry.DEFAULT_ENGINE_REGISTRY by
src/analysis/core/bootstrap.py, the one module that knows about both.
That is what lets a future Composite Analysis Engine consume outputs
from both engines without either engine or this facade changing.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional

from src.analysis.fundamental.registry import DEFAULT_RATIO_REGISTRY, RatioRegistry
from src.analysis.fundamental.types import FundamentalFacts, RatioMap, RatioOutput


@dataclass(frozen=True)
class FundamentalAnalysisResult:
    """The result of running every registered ratio against one
    FundamentalFacts snapshot (plus an optional prior period and market
    price).

    `ratios` is the extension point: any consumer that iterates it (or
    calls `.latest_snapshot()`) works correctly regardless of which
    ratios are registered, today or in the future. The named
    properties below are a convenience layer for code that does know
    the concrete M2.3 ratio set -- they simply read from the same
    `ratios` dict, so there is exactly one source of truth.
    """

    ratios: RatioMap = field(default_factory=dict)

    def get(self, name: str) -> RatioOutput:
        return self.ratios[name]

    def latest_snapshot(self) -> Dict[str, Any]:
        """Every ratio's current value, keyed by name -- the shape a
        future Signal Engine / Confidence Scoring / AI Decision Layer
        consumes as input."""
        return {name: output.latest() for name, output in self.ratios.items()}

    @property
    def net_profit_margin(self) -> Optional[float]:
        return self.ratios["net_profit_margin"].value

    @property
    def gross_profit_margin(self) -> Optional[float]:
        return self.ratios["gross_profit_margin"].value

    @property
    def return_on_equity(self) -> Optional[float]:
        return self.ratios["return_on_equity"].value

    @property
    def return_on_assets(self) -> Optional[float]:
        return self.ratios["return_on_assets"].value

    @property
    def current_ratio(self) -> Optional[float]:
        return self.ratios["current_ratio"].value

    @property
    def quick_ratio(self) -> Optional[float]:
        return self.ratios["quick_ratio"].value

    @property
    def cash_ratio(self) -> Optional[float]:
        return self.ratios["cash_ratio"].value

    @property
    def debt_to_equity(self) -> Optional[float]:
        return self.ratios["debt_to_equity"].value

    @property
    def debt_to_assets(self) -> Optional[float]:
        return self.ratios["debt_to_assets"].value

    @property
    def equity_multiplier(self) -> Optional[float]:
        return self.ratios["equity_multiplier"].value

    @property
    def asset_turnover(self) -> Optional[float]:
        return self.ratios["asset_turnover"].value

    @property
    def price_to_earnings(self) -> Optional[float]:
        return self.ratios["price_to_earnings"].value

    @property
    def price_to_book(self) -> Optional[float]:
        return self.ratios["price_to_book"].value

    @property
    def dividend_yield(self) -> Optional[float]:
        return self.ratios["dividend_yield"].value

    @property
    def market_cap(self) -> Optional[float]:
        return self.ratios["market_cap"].value

    @property
    def revenue_growth(self) -> Optional[float]:
        return self.ratios["revenue_growth"].value

    @property
    def net_income_growth(self) -> Optional[float]:
        return self.ratios["net_income_growth"].value

    @property
    def eps_growth(self) -> Optional[float]:
        return self.ratios["eps_growth"].value


class FundamentalAnalysisEngine:
    """Runs every ratio in a registry (default: the full M2.3 set)
    against one FundamentalFacts snapshot."""

    def __init__(self, registry: RatioRegistry = DEFAULT_RATIO_REGISTRY):
        self._registry = registry

    def analyze(
        self,
        facts: FundamentalFacts,
        prior_facts: Optional[FundamentalFacts] = None,
        market_price: Optional[float] = None,
    ) -> FundamentalAnalysisResult:
        computed: RatioMap = {}
        for spec in self._registry.all_specs():
            value = spec.compute(facts, prior_facts, market_price)
            computed[spec.name] = RatioOutput(name=spec.name, category=spec.category, value=value)

        return FundamentalAnalysisResult(ratios=computed)
