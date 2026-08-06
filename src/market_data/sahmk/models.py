"""Typed, provider-agnostic shapes for parsed SAHMK API responses.

SahmkClient returns raw dicts (the wire shape); SahmkMarketDataService
parses those dicts into the dataclasses below. Keeping the two separate
means a field-name change on SAHMK's side is fixed in one place
(service.py's parsing), not scattered across every caller.
"""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass(frozen=True)
class SahmkQuote:
    """A live price quote from GET /quote/{symbol}/.

    `bid`/`ask` are real fields on SAHMK's raw quote response (see
    docs/SAHMK_INTEGRATION.md's verified field list) that were
    previously parsed but discarded -- now carried through so the
    publication gate layer can compute a real bid/ask spread instead
    of having no spread signal at all."""

    symbol: str
    price: float
    change: Optional[float]
    change_percent: Optional[float]
    volume: Optional[int]
    timestamp: datetime
    bid: Optional[float] = None
    ask: Optional[float] = None


@dataclass(frozen=True)
class SahmkHistoricalBar:
    """One OHLCV bar from GET /historical/{symbol}/."""

    symbol: str
    open: float
    high: float
    low: float
    close: float
    volume: int
    timestamp: datetime


@dataclass(frozen=True)
class SahmkMarketSummary:
    """An index snapshot from GET /market/summary/."""

    index: str
    value: float
    change: Optional[float]
    change_percent: Optional[float]
    timestamp: Optional[datetime]


@dataclass(frozen=True)
class SahmkEvent:
    """One AI-generated stock event from GET /events/."""

    symbol: Optional[str]
    headline: str
    timestamp: Optional[datetime]
    raw: dict


@dataclass(frozen=True)
class SahmkCompanyProfile:
    """Company profile from GET /company/{symbol}/.

    `industry` and `exchange` are UNVERIFIED field names (same
    discipline as SahmkFinancials/get_company_directory): several
    plausible keys are tried, and either can legitimately be None if
    SAHMK's response doesn't carry that granularity for a given
    symbol -- `raw` is kept so a caller can always inspect exactly
    what SAHMK actually returned.

    `name_ar` is likewise UNVERIFIED and legitimately None: it is only
    ever set from a real Arabic-name field or Arabic-script text SAHMK
    itself returned (see service.py's _extract_name_ar), never
    fabricated -- a symbol whose response carries no Arabic text
    anywhere stays None rather than being guessed at."""

    symbol: str
    name: Optional[str]
    name_ar: Optional[str]
    sector: Optional[str]
    industry: Optional[str]
    exchange: Optional[str]
    raw: dict


@dataclass(frozen=True)
class SahmkFinancials:
    """A financial-statement snapshot from GET /financials/{symbol}/.

    Field names on the wire are UNVERIFIED (see docs/SAHMK_INTEGRATION.md)
    -- every field below is read defensively (several plausible key
    names tried, `None` if none match) rather than assumed present.
    `raw` always carries the untouched response so nothing SAHMK sends
    is silently dropped even if this dataclass doesn't yet have a field
    for it.
    """

    symbol: str
    period_type: str
    fiscal_period_end: Optional[str]
    revenue: Optional[float]
    gross_profit: Optional[float]
    net_income: Optional[float]
    total_assets: Optional[float]
    total_liabilities: Optional[float]
    total_equity: Optional[float]
    current_assets: Optional[float]
    current_liabilities: Optional[float]
    inventory: Optional[float]
    cash_and_equivalents: Optional[float]
    total_debt: Optional[float]
    shares_outstanding: Optional[int]
    eps: Optional[float]
    raw: dict


@dataclass(frozen=True)
class SahmkDividend:
    """One dividend record from GET /dividends/{symbol}/."""

    symbol: str
    dividend_per_share: float
    ex_date: Optional[str]
    payment_date: Optional[str]
    raw: dict
