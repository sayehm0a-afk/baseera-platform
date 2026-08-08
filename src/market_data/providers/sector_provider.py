"""Sector-classification provider interface.

SAHMK's `/companies/` directory has no `sector` field of any name for
403 of 408 currently active Saudi equities (confirmed via
GET /api/v1/admin/market-intelligence/universe-diagnostics against the
live production API, 2026-08-08) -- this is a genuine provider-side
data gap, not a Basirah defect. `src.domain.sector_labels` is only an
English->Arabic *label translation* table for the 20 real Tadawul GICS
sector names already seen on the wire for the 5 stocks SAHMK does
supply a sector for; it is not a symbol->sector data source and cannot
be used to fabricate sectors for the other 403.

This module defines the seam a real authoritative source would plug
into -- e.g. Tadawul's own published sector classification, a licensed
market-data vendor, or a maintained static mapping built from Tadawul's
official sector listings -- without inventing one now. `NullSectorProvider`
is the only implementation shipped: it always returns None, honestly
reporting "no source configured" rather than guessing. Wiring a real
provider is a follow-up task once credentials/access to an authoritative
source exist; see `get_sector_classification_provider()`'s docstring for
exactly what's required.
"""

import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class SectorClassification:
    symbol: str
    sector: str
    source: str


class ISectorClassificationProvider(ABC):
    """A source of sector classifications for Saudi-listed symbols.

    Every implementation must return None for a symbol it has no real
    data for -- never guess, infer from name/industry heuristics, or
    fall back to a placeholder. `source` on a real result must name the
    authoritative source (e.g. "tadawul_official"), so it is auditable
    and never confusable with a Basirah-invented value.
    """

    @abstractmethod
    async def get_sector(self, symbol: str) -> Optional[SectorClassification]:
        raise NotImplementedError

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """False for a provider with no real backing source (e.g.
        NullSectorProvider) -- lets callers/diagnostics distinguish "we
        checked and there's genuinely no sector" from "no sector source
        has ever been wired up," so a coverage report can say which is
        true instead of collapsing both into the same null."""
        raise NotImplementedError


class NullSectorProvider(ISectorClassificationProvider):
    """The only provider currently shipped. Always returns None --
    explicit, honest "not configured," never a fabricated sector."""

    async def get_sector(self, symbol: str) -> Optional[SectorClassification]:
        return None

    @property
    def is_configured(self) -> bool:
        return False


def get_sector_classification_provider() -> ISectorClassificationProvider:
    """Selects a sector-classification provider by the
    SECTOR_CLASSIFICATION_PROVIDER environment variable. Only "null"
    (the default) is implemented today -- this always returns
    NullSectorProvider() regardless of the env var's value, and is
    intentionally not silently treated as a config error, since no real
    provider exists yet to select.

    To wire up a real authoritative source, add a new
    ISectorClassificationProvider implementation here (e.g.
    "tadawul_official") backed by whatever real credential/endpoint that
    source requires, and branch on SECTOR_CLASSIFICATION_PROVIDER to
    select it -- this function is the single place that decision is
    made, so every caller (ingestion, /coverage diagnostics, ranking)
    picks it up automatically without any other code change."""
    provider_name = os.getenv("SECTOR_CLASSIFICATION_PROVIDER", "null").strip().lower()
    if provider_name not in ("", "null"):
        import logging

        logging.getLogger(__name__).warning(
            "SECTOR_CLASSIFICATION_PROVIDER=%r requested but no real sector-classification "
            "provider is implemented yet -- falling back to NullSectorProvider (always None, "
            "never fabricated). See src.market_data.providers.sector_provider's module "
            "docstring for what implementing a real one requires.",
            provider_name,
        )
    return NullSectorProvider()
