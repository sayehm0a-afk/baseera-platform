"""Reusable, low-level async HTTP client for the Polygon.io REST API.

Authentication: every request carries an `Authorization: Bearer <key>`
header (Polygon's documented bearer-token auth convention). The key is
read from the POLYGON_API_KEY environment variable by default
(src.market_data.config) and is never hardcoded or logged.

Retry/circuit-breaker split mirrors src.market_data.sahmk.client
exactly: tenacity retries a genuinely transient failure (429, 5xx, or a
network-level error) up to 3 times with exponential backoff; a
deterministic business response (401, 403, any other non-2xx) is
returned as a `_BusinessError` sentinel instead of raised, so
CircuitBreaker.execute() -- which counts any *raised* exception as a
failure with no way to tell a business response from a real outage --
never mistakes "Polygon correctly rejected this request" for "Polygon
is down." See sahmk/client.py's module docstring and `_BusinessError`
for the full reasoning; not repeated here.

This class only knows how to talk to the wire -- it returns raw
response dicts. src.market_data.polygon.service.PolygonMarketDataService
is the layer that turns those into typed models and adds caching.
"""

import asyncio
import logging
from datetime import date
from typing import Any, Dict, List, Optional, Union
from urllib.parse import parse_qs, urlparse

import aiohttp
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreaker
from src.domain.models.stock import Market
from src.market_data import config as market_data_config
from src.market_data.polygon.exceptions import (
    PolygonAuthenticationError,
    PolygonConfigurationError,
    PolygonRateLimitError,
    PolygonRequestError,
)
from src.market_data.polygon.rate_limiter import PolygonRateLimiter, get_default_polygon_rate_limiter
from src.market_data.validators.symbol_validator import validate_symbol_format

logger = logging.getLogger(__name__)

# Bounds how many /v3/reference/tickers pages get_tickers() will ever
# follow via `next_url`, regardless of how many Polygon itself reports
# -- mirrors _MAX_DIRECTORY_PAGES in sahmk/service.py's
# get_company_directory(): a misread or adversarial cursor can never
# turn into an unbounded loop.
_MAX_TICKER_PAGES = 50


class _RetryableError(Exception):
    """Internal-only signal used to trigger tenacity's retry on 429/5xx.
    Never escapes PolygonClient -- _request() converts it to
    PolygonRateLimitError or PolygonRequestError once retries are
    exhausted. This is the only exception type that both tenacity's
    retry and the CircuitBreaker are ever allowed to see -- it is
    raised exclusively for conditions that are actually transient/
    infrastructure in nature (429, 5xx, network), never for a business
    response."""

    def __init__(self, message: str, *, kind: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.kind = kind  # "rate_limit" | "server_error" | "network_error"
        self.retry_after = retry_after


class _BusinessError:
    """Wraps a deterministic, non-transient business exception (401,
    403, any other non-2xx) so it can be *returned* rather than
    *raised* from the function passed to CircuitBreaker.execute() --
    mirrors sahmk/client.py's `_BusinessError` exactly. See that
    class's docstring for the full reasoning."""

    def __init__(self, exception: Exception):
        self.exception = exception


def _date_param(value: Union[str, date]) -> str:
    return value.isoformat() if isinstance(value, date) else str(value)


class PolygonClient:
    """Talks to https://api.polygon.io (or POLYGON_BASE_URL)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        session: Optional[aiohttp.ClientSession] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        rate_limiter: Optional[PolygonRateLimiter] = None,
    ):
        self._api_key = api_key if api_key is not None else market_data_config.get_polygon_api_key()
        self._base_url = (base_url or market_data_config.get_polygon_base_url()).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = session
        self._owns_session = session is None
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=3, recovery_timeout=30
        )
        # Shared, process-wide by default (see rate_limiter.py's module
        # docstring): Polygon's quota is per API key, not per client
        # instance. Only ever overridden explicitly, for tests.
        self._rate_limiter = rate_limiter or get_default_polygon_rate_limiter()

    @property
    def has_credentials(self) -> bool:
        return bool(self._api_key)

    async def _ensure_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            # trust_env=True: aiohttp does NOT read HTTP_PROXY/HTTPS_PROXY by
            # default (unlike curl/requests). This process's outbound network
            # is governed by an environment-provided egress proxy; omitting
            # trust_env here would silently dial out directly, bypassing that
            # policy instead of receiving its allow/deny decision.
            self._session = aiohttp.ClientSession(trust_env=True)
            self._owns_session = True
        return self._session

    async def close(self) -> None:
        if self._session is not None and self._owns_session and not self._session.closed:
            await self._session.close()

    async def __aenter__(self) -> "PolygonClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Core request machinery
    # ------------------------------------------------------------------

    async def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._api_key:
            raise PolygonConfigurationError(
                "POLYGON_API_KEY is not configured -- cannot call the Polygon.io API."
            )

        # Rate-limited once per logical request, deliberately outside
        # circuit_breaker.execute()'s scope below -- the per-minute wait
        # only ever sleeps, never raises, so this is safe either way;
        # kept here so one throttle point covers the whole request, not
        # one per retry attempt (tenacity's own backoff already spaces
        # retries of one request out).
        await self._rate_limiter.acquire()

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
            retry=retry_if_exception_type(_RetryableError),
        )
        async def _do_request() -> Any:
            # Returns either the parsed dict (2xx) or a _BusinessError
            # sentinel (401/403/other non-2xx) -- never *raises* for a
            # business outcome, so CircuitBreaker.execute() below never
            # sees it as a failure. Only raises _RetryableError (429/5xx,
            # retried by tenacity above) or a network-level error from
            # _send -- both genuinely transient, both legitimate for the
            # breaker to count.
            return await self._send(path, params)

        try:
            outcome = await self._circuit_breaker.execute(_do_request)
        except _RetryableError as exc:
            if exc.kind == "rate_limit":
                raise PolygonRateLimitError(str(exc), retry_after=exc.retry_after) from exc
            raise PolygonRequestError(str(exc)) from exc

        if isinstance(outcome, _BusinessError):
            # Raised here, outside circuit_breaker.execute()'s scope --
            # this is a real, surfaced error for the *caller*, but it is
            # deliberately never counted as a breaker failure.
            raise outcome.exception
        return outcome

    async def _send(self, path: str, params: Optional[Dict[str, Any]]) -> Any:
        session = await self._ensure_session()
        url = f"{self._base_url}{path}"
        headers = {"Authorization": f"Bearer {self._api_key}"}

        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout_seconds),
            ) as response:
                return await self._handle_response(response)
        except _RetryableError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            # A connection failure or request timeout is exactly as
            # transient as a 5xx -- raising _RetryableError here (instead
            # of PolygonRequestError directly) routes it through the same
            # retry_if_exception_type(_RetryableError) path as
            # server_error; _request()'s translation still turns an
            # exhausted retry into PolygonRequestError for the caller.
            raise _RetryableError(
                f"Network error calling Polygon API: {exc}", kind="network_error"
            ) from exc

    async def _handle_response(self, response: aiohttp.ClientResponse) -> Any:
        status = response.status

        if status == 200:
            try:
                return await response.json()
            except (aiohttp.ContentTypeError, ValueError) as exc:
                # An unparseable 200 is not a clean business rejection --
                # it looks like something between Polygon and here (a
                # captive portal, a broken intermediary) returned a
                # malformed response, exactly the class of anomaly the
                # circuit breaker exists to protect against. Raised
                # directly (not wrapped in _BusinessError), so it is
                # still counted.
                body_text = await response.text()
                raise PolygonRequestError(
                    f"Polygon returned a non-JSON 200 response: {body_text[:200]!r}",
                    status_code=status,
                    body=body_text,
                ) from exc

        body = await self._read_body(response)

        if status in (401, 403):
            return _BusinessError(
                PolygonAuthenticationError(
                    f"Polygon rejected the configured API key ({status}).",
                    status_code=status,
                    body=body,
                )
            )
        if status == 429:
            raise _RetryableError(
                f"Polygon rate limit hit (429): {body}",
                kind="rate_limit",
                retry_after=self._parse_retry_after(response),
            )
        if 500 <= status < 600:
            raise _RetryableError(f"Polygon server error ({status}): {body}", kind="server_error")

        return _BusinessError(
            PolygonRequestError(
                f"Polygon request failed with status {status}.", status_code=status, body=body
            )
        )

    @staticmethod
    async def _read_body(response: aiohttp.ClientResponse) -> Any:
        try:
            return await response.json()
        except (aiohttp.ContentTypeError, ValueError):
            return await response.text()

    @staticmethod
    def _parse_retry_after(response: aiohttp.ClientResponse) -> Optional[float]:
        raw = response.headers.get("Retry-After")
        if raw is None:
            return None
        try:
            return float(raw)
        except ValueError:
            return None

    # ------------------------------------------------------------------
    # API wrappers -- one per Polygon.io endpoint this integration uses.
    # ------------------------------------------------------------------

    async def get_previous_close(self, ticker: str) -> Dict[str, Any]:
        """GET /v2/aggs/ticker/{ticker}/prev -- the prior trading day's
        OHLCV aggregate bar."""
        validate_symbol_format(ticker, market=Market.US)
        return await self._request(f"/v2/aggs/ticker/{ticker}/prev")

    async def get_aggregates(
        self,
        ticker: str,
        multiplier: int,
        timespan: str,
        from_: Union[str, date],
        to: Union[str, date],
        adjusted: bool = True,
        sort: str = "asc",
        limit: int = 5000,
    ) -> Dict[str, Any]:
        """GET /v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/{from}/{to}
        -- custom-window OHLCV aggregate bars."""
        validate_symbol_format(ticker, market=Market.US)
        params: Dict[str, Any] = {"adjusted": str(adjusted).lower(), "sort": sort, "limit": limit}
        path = (
            f"/v2/aggs/ticker/{ticker}/range/{multiplier}/{timespan}/"
            f"{_date_param(from_)}/{_date_param(to)}"
        )
        return await self._request(path, params=params)

    async def get_ticker_details(self, ticker: str) -> Dict[str, Any]:
        """GET /v3/reference/tickers/{ticker} -- reference metadata for
        one ticker (name, market, exchange, market cap, ...)."""
        validate_symbol_format(ticker, market=Market.US)
        return await self._request(f"/v3/reference/tickers/{ticker}")

    async def get_tickers(
        self,
        market: str = "stocks",
        active: bool = True,
        params: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """GET /v3/reference/tickers -- ticker directory/discovery.

        Follows Polygon's own real, documented cursor-based `next_url`
        pagination until either no further page is reported or
        `_MAX_TICKER_PAGES` is reached -- the same bounded-pagination
        discipline SahmkMarketDataService.get_company_directory() uses
        for SAHMK's `/companies/` directory, so a misbehaving or
        adversarial cursor can never spin forever. Returns a single
        merged envelope (`{"results": [...], "count": ...}`) so callers
        never need to know pagination happened at all.
        """
        request_params: Dict[str, Any] = {"market": market, "active": str(active).lower()}
        if params:
            request_params.update(params)

        all_results: List[Any] = []
        pages_fetched = 0
        next_params: Optional[Dict[str, Any]] = request_params

        while next_params is not None and pages_fetched < _MAX_TICKER_PAGES:
            data = await self._request("/v3/reference/tickers", params=next_params)
            pages_fetched += 1
            results = data.get("results", [])
            if isinstance(results, list):
                all_results.extend(results)

            next_url = data.get("next_url")
            if not next_url:
                break
            parsed = urlparse(str(next_url))
            query_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
            if not query_params:
                # A `next_url` with no parseable query string can't be
                # followed via the params-only client method -- stop
                # rather than guess at a raw-URL fetch.
                break
            next_params = query_params

        return {"results": all_results, "count": len(all_results)}

    async def get_ticker_news(self, ticker: Optional[str] = None, limit: int = 10) -> Dict[str, Any]:
        """GET /v2/reference/news -- ticker-related news articles."""
        if ticker is not None:
            validate_symbol_format(ticker, market=Market.US)
        params: Dict[str, Any] = {"limit": limit}
        if ticker is not None:
            params["ticker"] = ticker
        return await self._request("/v2/reference/news", params=params)

    async def get_market_status(self) -> Dict[str, Any]:
        """GET /v1/marketstatus/now -- whether US markets are currently
        open, and per-exchange status."""
        return await self._request("/v1/marketstatus/now")
