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
    """A live price quote from GET /quote/{symbol}/."""

    symbol: str
    price: float
    change: Optional[float]
    change_percent: Optional[float]
    volume: Optional[int]
    timestamp: datetime


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
