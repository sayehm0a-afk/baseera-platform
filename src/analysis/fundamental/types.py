"""Shared types for the fundamental analysis engine.

Mirrors the shape of src/analysis/types.py (M2.2) deliberately, but
does not import from it and is not imported by it -- both packages
depend only on src/analysis/core/'s structural contract, kept
completely independent of one another per explicit architectural
instruction.
"""

from dataclasses import dataclass
from datetime import date
from enum import Enum
from typing import Any, Dict, Optional


class RatioCategory(str, Enum):
    """Classification of a fundamental ratio, for downstream consumers
    that want to group or filter (e.g. "run only liquidity ratios")."""

    PROFITABILITY = "profitability"
    LIQUIDITY = "liquidity"
    LEVERAGE = "leverage"
    EFFICIENCY = "efficiency"
    VALUATION = "valuation"
    GROWTH = "growth"


@dataclass(frozen=True)
class FundamentalFacts:
    """Pure, DB-agnostic mirror of one FundamentalSnapshot row.

    fundamental_loader.py is the only module that converts an ORM row
    into this shape (Decimal -> float, same precision-boundary
    reasoning as src/analysis/ohlcv_loader.py's Decimal -> float64
    conversion for PriceBar) -- every ratio function downstream takes
    only this dataclass, never a database session or an ORM object.
    """

    stock_id: int
    period_type: str  # "annual" | "quarterly" -- plain str, not the domain model's enum
    fiscal_period_end: date

    revenue: float
    gross_profit: Optional[float]
    net_income: float
    total_assets: float
    total_liabilities: float
    total_equity: float
    current_assets: float
    current_liabilities: float
    inventory: Optional[float]
    cash_and_equivalents: Optional[float]
    total_debt: Optional[float]
    shares_outstanding: int
    eps: float
    dividend_per_share: float


@dataclass(frozen=True)
class RatioOutput:
    """Uniform wrapper around one computed ratio's result.

    Satisfies src.analysis.core.contracts.AnalysisOutput structurally
    (name, category, value, .latest()) without importing that module --
    a future Composite Analysis Engine can treat this identically to
    src.analysis.types.IndicatorOutput without either package knowing
    the other exists.

    `value` is `None`, never an exception, whenever the ratio is
    undefined for the given input (division by zero, a missing prior
    period for a growth ratio, no market price for a valuation ratio)
    -- unlike OHLCV bars, real-world financial statements are commonly
    incomplete, and a missing ratio is a normal, expected outcome, not
    an error condition.
    """

    name: str
    category: RatioCategory
    value: Optional[float]

    def latest(self) -> Any:
        # Ratios are already a single current value, not a time series
        # to reduce -- .latest() exists purely for structural
        # conformance with the shared AnalysisOutput contract.
        return self.value


RatioMap = Dict[str, RatioOutput]
