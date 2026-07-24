"""Provider-agnostic market data models.

Every concrete IMarketDataProvider (Dev/Saudi/Sahmk) parses its own raw
response shape into these dataclasses before handing data further into
the pipeline. This is the seam that lets Basirah change data vendors
later without redesigning anything downstream: the analysis engines,
ingestion jobs, and API layer depend on these types (or, for the two
existing IMarketDataProvider methods that predate this file --
get_stock_data/get_historical_ohlcv -- on the plain dict shape those
methods already return), never on a specific vendor's field names.

Frozen dataclasses, not Pydantic models: this package has no existing
Pydantic dependency at the provider layer (Pydantic is an API-layer
concern, see src/api/schemas/), and these types are internal data
carriers, not request/response validation boundaries themselves --
`SahmkResponseValidationError` (raised by the Sahmk provider before a
dataclass is even constructed) is the actual validation step.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class MarketQuote:
    """A single point-in-time quote for one symbol."""

    symbol: str
    price: float
    change: float
    change_percent: float
    volume: float
    timestamp: datetime
    name_en: Optional[str] = None
    name_ar: Optional[str] = None
    value: Optional[float] = None
    source: str = "unknown"
    is_synthetic: bool = False


@dataclass(frozen=True)
class HistoricalCandle:
    """One OHLCV bar. Field names mirror the dict shape
    IMarketDataProvider.get_historical_ohlcv already returns (see that
    method's own docstring) so converting between the two is a direct
    field-for-field mapping, never a redesign."""

    symbol: str
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    source: str = "unknown"
    is_synthetic: bool = False


@dataclass(frozen=True)
class MarketIndex:
    """A market-level index snapshot (e.g. TASI, NOMU)."""

    index_name: str
    value: float
    change: float
    change_percent: float
    timestamp: datetime
    is_delayed: Optional[bool] = None
    source: str = "unknown"
    is_synthetic: bool = False


@dataclass(frozen=True)
class StockProfile:
    """Company reference data. Not populated by any provider yet (no
    /company/{symbol}/-equivalent call is wired in this milestone) --
    defined now so a later milestone that adds one returns this type,
    not a fifth ad-hoc dict shape."""

    symbol: str
    name_en: str
    name_ar: Optional[str] = None
    sector: Optional[str] = None
    market: Optional[str] = None  # "TASI" | "NOMU" | "NOMUC"
    source: str = "unknown"


@dataclass(frozen=True)
class FinancialStatement:
    """One reporting period's financial statement figures. Not
    populated by any provider yet -- defined for the same forward-
    compatibility reason as StockProfile."""

    symbol: str
    period_label: str
    revenue: Optional[float] = None
    net_income: Optional[float] = None
    total_assets: Optional[float] = None
    total_liabilities: Optional[float] = None
    total_equity: Optional[float] = None
    eps: Optional[float] = None
    source: str = "unknown"


@dataclass(frozen=True)
class StockSummary:
    """A quote paired with whatever profile data is available -- the
    shape a "stock detail" API response naturally wants. `profile` is
    None until a provider actually implements company-profile lookups."""

    quote: MarketQuote
    profile: Optional[StockProfile] = None


@dataclass(frozen=True)
class TechnicalIndicator:
    """One named technical indicator reading, shaped to be trivially
    constructible from the existing AnalysisOutput-conforming indicator
    results (src/analysis/core/contracts.py) -- this is a carrier type
    for feeding indicator values into the future Recommendation Engine
    (see src/analysis/intelligence/contracts/), not a replacement for
    the existing IndicatorOutput/AnalysisOutput contracts."""

    name: str
    category: str
    value: object


@dataclass(frozen=True)
class RecommendationInput:
    """Everything a future Recommendation Engine needs as input for one
    symbol, gathered from already-existing engines/providers -- defined
    now purely as a typed carrier so src/analysis/intelligence/contracts's
    IRecommendationEngine.recommend() has a concrete parameter type to
    declare. No recommendation logic is implemented against this type in
    this milestone (see docs/architecture/current-status.md's M2.9
    section: no unverified/unbacked financial recommendation is ever
    produced from placeholder logic)."""

    symbol: str
    quote: Optional[MarketQuote] = None
    profile: Optional[StockProfile] = None
    technical_indicators: list = field(default_factory=list)
    fundamental_ratios: list = field(default_factory=list)
    as_of: Optional[datetime] = None
