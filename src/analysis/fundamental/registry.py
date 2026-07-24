"""The fundamental ratio registry: the extension point future
intelligence layers use to discover every fundamental ratio, without
modifying any existing ratio.

Every ratio function under src/analysis/fundamental/ratios/ stays a
plain, isolated pure function -- it has zero awareness that a registry
exists. This mirrors src/analysis/registry.py's (M2.2) pattern exactly,
but is a completely separate registry: neither package imports the
other, both only depend on src/analysis/fundamental/types.py (this
package) or src/analysis/types.py (the technical package) respectively.

Every RatioSpec.compute has the same three-argument signature --
(facts, prior, price) -- even for ratios that only need one of them
(e.g. profitability ratios ignore prior and price entirely). This is
the same uniform-invocation choice src/analysis/registry.py made for
IndicatorSpec.compute (every indicator takes the full OHLCV DataFrame
even though most only touch one column): a single call site
(FundamentalAnalysisEngine.analyze()) can invoke every ratio
identically, with each ratio's own module deciding which arguments it
actually needs.

Adding a future ratio -- including one a future Composite Analysis
Engine or Signal Engine needs -- means writing one pure function plus
one new RatioSpec here. FundamentalAnalysisEngine.analyze() and every
existing ratio are unaffected.
"""

from dataclasses import dataclass
from typing import Callable, List, Optional

from src.analysis.fundamental.ratios.efficiency import asset_turnover
from src.analysis.fundamental.ratios.growth import eps_growth, net_income_growth, revenue_growth
from src.analysis.fundamental.ratios.leverage import (
    debt_to_assets,
    debt_to_equity,
    equity_multiplier,
)
from src.analysis.fundamental.ratios.liquidity import cash_ratio, current_ratio, quick_ratio
from src.analysis.fundamental.ratios.profitability import (
    gross_profit_margin,
    net_profit_margin,
    return_on_assets,
    return_on_equity,
)
from src.analysis.fundamental.ratios.valuation import (
    dividend_yield,
    market_cap,
    price_to_book,
    price_to_earnings,
)
from src.analysis.fundamental.types import FundamentalFacts, RatioCategory

RatioComputeFn = Callable[[FundamentalFacts, Optional[FundamentalFacts], Optional[float]], Optional[float]]


@dataclass(frozen=True)
class RatioSpec:
    name: str
    category: RatioCategory
    compute: RatioComputeFn


class RatioRegistry:
    """A named collection of RatioSpecs. FundamentalAnalysisEngine
    iterates one of these; it never hardcodes ratio names."""

    def __init__(self) -> None:
        self._specs: List[RatioSpec] = []

    def register(self, spec: RatioSpec) -> None:
        if any(existing.name == spec.name for existing in self._specs):
            raise ValueError(f"A ratio named {spec.name!r} is already registered")
        self._specs.append(spec)

    def all_specs(self) -> List[RatioSpec]:
        return list(self._specs)


def build_default_registry() -> RatioRegistry:
    """The M2.3 ratio set."""
    registry = RatioRegistry()

    registry.register(
        RatioSpec(
            "net_profit_margin",
            RatioCategory.PROFITABILITY,
            lambda facts, prior, price: net_profit_margin(facts),
        )
    )
    registry.register(
        RatioSpec(
            "gross_profit_margin",
            RatioCategory.PROFITABILITY,
            lambda facts, prior, price: gross_profit_margin(facts),
        )
    )
    registry.register(
        RatioSpec(
            "return_on_equity",
            RatioCategory.PROFITABILITY,
            lambda facts, prior, price: return_on_equity(facts),
        )
    )
    registry.register(
        RatioSpec(
            "return_on_assets",
            RatioCategory.PROFITABILITY,
            lambda facts, prior, price: return_on_assets(facts),
        )
    )

    registry.register(
        RatioSpec("current_ratio", RatioCategory.LIQUIDITY, lambda facts, prior, price: current_ratio(facts))
    )
    registry.register(
        RatioSpec("quick_ratio", RatioCategory.LIQUIDITY, lambda facts, prior, price: quick_ratio(facts))
    )
    registry.register(
        RatioSpec("cash_ratio", RatioCategory.LIQUIDITY, lambda facts, prior, price: cash_ratio(facts))
    )

    registry.register(
        RatioSpec(
            "debt_to_equity", RatioCategory.LEVERAGE, lambda facts, prior, price: debt_to_equity(facts)
        )
    )
    registry.register(
        RatioSpec(
            "debt_to_assets", RatioCategory.LEVERAGE, lambda facts, prior, price: debt_to_assets(facts)
        )
    )
    registry.register(
        RatioSpec(
            "equity_multiplier",
            RatioCategory.LEVERAGE,
            lambda facts, prior, price: equity_multiplier(facts),
        )
    )

    registry.register(
        RatioSpec(
            "asset_turnover", RatioCategory.EFFICIENCY, lambda facts, prior, price: asset_turnover(facts)
        )
    )

    registry.register(
        RatioSpec(
            "price_to_earnings",
            RatioCategory.VALUATION,
            lambda facts, prior, price: price_to_earnings(facts, price),
        )
    )
    registry.register(
        RatioSpec(
            "price_to_book",
            RatioCategory.VALUATION,
            lambda facts, prior, price: price_to_book(facts, price),
        )
    )
    registry.register(
        RatioSpec(
            "dividend_yield",
            RatioCategory.VALUATION,
            lambda facts, prior, price: dividend_yield(facts, price),
        )
    )
    registry.register(
        RatioSpec(
            "market_cap", RatioCategory.VALUATION, lambda facts, prior, price: market_cap(facts, price)
        )
    )

    registry.register(
        RatioSpec(
            "revenue_growth",
            RatioCategory.GROWTH,
            lambda facts, prior, price: revenue_growth(facts, prior),
        )
    )
    registry.register(
        RatioSpec(
            "net_income_growth",
            RatioCategory.GROWTH,
            lambda facts, prior, price: net_income_growth(facts, prior),
        )
    )
    registry.register(
        RatioSpec("eps_growth", RatioCategory.GROWTH, lambda facts, prior, price: eps_growth(facts, prior))
    )

    return registry


DEFAULT_RATIO_REGISTRY = build_default_registry()
