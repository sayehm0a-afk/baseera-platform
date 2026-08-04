"""SahmkFundamentalDataProvider: the real, live IFundamentalDataProvider
implementation, backed by SAHMK's Starter-tier /financials/{symbol}/ and
/dividends/{symbol}/ endpoints.

Adapts src.market_data.sahmk.service.SahmkMarketDataService to
IFundamentalDataProvider's existing Dict[str, Any]-shaped contract,
unchanged, so ingest_fundamentals.py works identically against this
provider as it does against DevFundamentalDataProvider -- only the data
stops being synthetic. Returned dict mirrors DevFundamentalDataProvider's
shape exactly (same keys), with `source="sahmk"` and `is_synthetic=False`.

SAHMK's exact /financials/ field names are UNVERIFIED (see
docs/SAHMK_INTEGRATION.md) -- SahmkMarketDataService.get_financials()
already reads several plausible key names defensively. This class adds
one more layer of discipline on top: if a field ingest_fundamentals.py's
_upsert_fundamental_snapshot() *requires* (not optional) is still
missing after that defensive parse, this raises
SahmkResponseValidationError rather than passing a dict with a missing
key downstream to fail with a less legible KeyError.
"""

import logging
from typing import Any, Dict, List, Optional

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreakerOpenError
from src.market_data.providers.fundamental_data_provider import (
    FundamentalDataProviderFactory,
    IFundamentalDataProvider,
    ProviderHealth,
)
from src.market_data.sahmk.client import SahmkClient
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkConfigurationError,
    SahmkEntitlementError,
    SahmkError,
    SahmkResponseValidationError,
)
from src.market_data.sahmk.service import SahmkMarketDataService

logger = logging.getLogger(__name__)

# current_assets/current_liabilities/shares_outstanding/eps are
# deliberately NOT required: a real, live capture of SAHMK's
# /financials/{symbol}/ response (3 symbols, workflow run 30436660246)
# confirmed they are never present anywhere in it -- see
# docs/SAHMK_INTEGRATION.md. FundamentalSnapshot stores them as
# nullable and every ratio that needs one already degrades to None
# rather than raising (src/analysis/fundamental/ratios/).
_REQUIRED_FIELDS = [
    "revenue",
    "net_income",
    "total_assets",
    "total_liabilities",
    "total_equity",
]


class SahmkFundamentalDataProvider(IFundamentalDataProvider):
    """Live fundamental data provider backed by the SAHMK API."""

    is_synthetic = False

    def __init__(self, api_endpoint: Optional[str] = None, api_key: Optional[str] = None, **kwargs):
        self._service = SahmkMarketDataService(
            client=SahmkClient(api_key=api_key, base_url=api_endpoint)
        )
        self.authenticated = False

    @property
    def has_credentials(self) -> bool:
        return self._service.has_credentials

    async def authenticate(self) -> bool:
        """Same cheapest-confirmed-call check as SahmkMarketDataProvider
        (GET /market/summary/) -- financials/dividends are Starter+ and
        cost real quota, so authentication does not call them."""
        if not self._service.has_credentials:
            logger.warning(
                "SahmkFundamentalDataProvider.authenticate(): SAHMK_API_KEY is not configured."
            )
            self.authenticated = False
            return False

        try:
            await self._service.get_index_snapshot("TASI")
            self.authenticated = True
        except SahmkEntitlementError:
            self.authenticated = True
        except (SahmkAuthenticationError, SahmkConfigurationError) as exc:
            logger.error("SAHMK authentication failed: %s", exc)
            self.authenticated = False
        except (SahmkError, CircuitBreakerOpenError) as exc:
            logger.error("SAHMK authentication check could not complete: %s", exc)
            self.authenticated = False

        return self.authenticated

    async def get_fundamentals(self, symbol: str, period_type: str = "annual") -> Dict[str, Any]:
        financials = await self._service.get_financials(symbol, period_type=period_type)
        missing = [f for f in _REQUIRED_FIELDS if getattr(financials, f) is None]
        if financials.fiscal_period_end is None:
            missing.append("fiscal_period_end")
        if missing:
            raise SahmkResponseValidationError(
                f"SAHMK /financials/{symbol}/ response is missing required field(s) "
                f"{missing} (after trying every known alternate field name) -- see "
                f"docs/SAHMK_INTEGRATION.md for what is verified about this endpoint.",
                body=financials.raw,
            )

        dividend_per_share = await self._service.get_latest_dividend_per_share(symbol)

        return {
            "symbol": symbol,
            "period_type": financials.period_type,
            "fiscal_period_end": financials.fiscal_period_end,
            "revenue": financials.revenue,
            "gross_profit": financials.gross_profit,
            "net_income": financials.net_income,
            "total_assets": financials.total_assets,
            "total_liabilities": financials.total_liabilities,
            "total_equity": financials.total_equity,
            "current_assets": financials.current_assets,
            "current_liabilities": financials.current_liabilities,
            "inventory": financials.inventory,
            "cash_and_equivalents": financials.cash_and_equivalents,
            "total_debt": financials.total_debt,
            "shares_outstanding": financials.shares_outstanding,
            "eps": financials.eps,
            "dividend_per_share": dividend_per_share if dividend_per_share is not None else 0,
            "source": "sahmk",
            "is_synthetic": False,
        }

    async def get_dividends(self, symbol: str) -> List[Dict[str, Any]]:
        """Not part of IFundamentalDataProvider -- exposed for callers
        that want full dividend history, not just the most recent
        per-share figure get_fundamentals() folds in."""
        dividends = await self._service.get_dividends(symbol)
        return [
            {
                "symbol": d.symbol,
                "dividend_per_share": d.dividend_per_share,
                "ex_date": d.ex_date,
                "payment_date": d.payment_date,
                "source": "sahmk",
                "is_synthetic": False,
            }
            for d in dividends
        ]

    async def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """Not part of IFundamentalDataProvider -- exposed for callers
        that want company reference data (name/sector)."""
        profile = await self._service.get_company_profile(symbol)
        return {
            "symbol": profile.symbol,
            "name": profile.name,
            "sector": profile.sector,
            "industry": profile.industry,
            "exchange": profile.exchange,
            "source": "sahmk",
            "is_synthetic": False,
        }

    async def health_check(self) -> ProviderHealth:
        if not self._service.has_credentials:
            return ProviderHealth.UNHEALTHY
        try:
            healthy = await self._service.check_health()
        except CircuitBreakerOpenError:
            return ProviderHealth.UNHEALTHY
        return ProviderHealth.HEALTHY if healthy else ProviderHealth.UNHEALTHY

    async def disconnect(self) -> None:
        await self._service.close()
        self.authenticated = False


FundamentalDataProviderFactory.register("sahmk", SahmkFundamentalDataProvider)
