"""Reusable, low-level async HTTP client for the SAHMK (sahmk.sa) API.

Authentication: every request carries an `X-API-Key` header -- SAHMK
has no token-exchange endpoint, the key itself is the credential (see
docs/SAHMK_INTEGRATION.md). The key is read from the SAHMK_API_KEY
environment variable by default (src.market_data.config) and is never
hardcoded or logged.

Retry policy matches SAHMK's own documented defaults: 3 attempts,
0.5s/1s/2s exponential backoff on 429/5xx, honoring a 429's
Retry-After header. A CircuitBreaker wraps the retried call so a
sustained *infrastructure* outage (network failure, or 429/5xx that
survives every retry) stops hammering the upstream once the failure
threshold trips (src.core.runtime.reliability_layer.circuit_breaker,
reused unchanged) -- but a deterministic *business* response (401, 403
PLAN_LIMIT, any other non-2xx) never counts as a breaker failure. Those
are legitimate, expected answers from a reachable, healthy SAHMK to a
specific request (e.g. calling a Pro+ endpoint on a Starter plan is
*always* going to be 403, not a sign anything is down) -- counting them
would let three routine plan-limit responses on one endpoint block
completely unrelated, healthy calls on the same client for
`recovery_timeout` seconds. See `_BusinessError` below for how this is
enforced structurally, not just by convention.

This class only knows how to talk to the wire -- it returns raw
response dicts. src.market_data.sahmk.service.SahmkMarketDataService
is the layer that turns those into typed models and adds caching.
"""

import asyncio
import logging
import re
from datetime import date
from typing import Any, Dict, Optional

import aiohttp
from tenacity import retry, retry_if_exception_type, stop_after_attempt, wait_exponential

from src.core.runtime.reliability_layer.circuit_breaker import CircuitBreaker
from src.market_data import config as market_data_config
from src.market_data.sahmk.exceptions import (
    SahmkAuthenticationError,
    SahmkConfigurationError,
    SahmkDailyQuotaExhaustedError,
    SahmkEntitlementError,
    SahmkRateLimitError,
    SahmkRequestError,
)
from src.market_data.sahmk.rate_limiter import SahmkRateLimiter, get_default_rate_limiter
from src.market_data.sahmk.request_priority import get_current_priority
from src.market_data.validators.symbol_validator import validate_symbol_format

logger = logging.getLogger(__name__)

# Matches SAHMK's own real 429 wording, e.g. (production evidence,
# 2026-08-10): "Daily rate limit exceeded (5000 requests/day). Resets
# at midnight. Upgrade: https://www.sahmk.sa/developers/pricing
# Expected available in 54711 seconds." Deliberately evidence-based --
# no assumed reset timezone is hard-coded anywhere; the "Expected
# available in N seconds" figure IS the reset time, straight from
# SAHMK itself, whatever timezone its own "midnight" turns out to be.
_DAILY_QUOTA_PATTERN = re.compile(r"daily rate limit exceeded", re.IGNORECASE)
_EXPECTED_AVAILABLE_PATTERN = re.compile(r"expected available in\s+(\d+)\s+seconds", re.IGNORECASE)


def _extract_daily_quota_evidence(body: Any) -> Optional["_DailyQuotaEvidence"]:
    """Returns real evidence extracted from a 429 body if (and only if)
    it matches SAHMK's own daily-quota-exhaustion wording -- None for
    an ordinary short-lived rate limit (which should still be retried
    normally). `body` may be a parsed dict (the common case -- SAHMK
    returns JSON) or raw text (if the body wasn't valid JSON)."""
    text = body.get("detail") if isinstance(body, dict) else body
    if not isinstance(text, str) or not _DAILY_QUOTA_PATTERN.search(text):
        return None
    match = _EXPECTED_AVAILABLE_PATTERN.search(text)
    retry_after_seconds = float(match.group(1)) if match else None
    return _DailyQuotaEvidence(raw_message=text, retry_after_seconds=retry_after_seconds)


class _DailyQuotaEvidence:
    __slots__ = ("raw_message", "retry_after_seconds")

    def __init__(self, raw_message: str, retry_after_seconds: Optional[float]):
        self.raw_message = raw_message
        self.retry_after_seconds = retry_after_seconds


class _RetryableSahmkError(Exception):
    """Internal-only signal used to trigger tenacity's retry on 429/5xx.
    Never escapes SahmkClient -- _request() converts it to
    SahmkRateLimitError or SahmkRequestError once retries are exhausted.
    This is the only exception type that both tenacity's retry and the
    CircuitBreaker are ever allowed to see -- it is raised exclusively
    for conditions that are actually transient/infrastructure in
    nature (429, 5xx), never for a business response."""

    def __init__(self, message: str, *, kind: str, retry_after: Optional[float] = None):
        super().__init__(message)
        self.kind = kind  # "rate_limit" | "server_error" | "network_error"
        self.retry_after = retry_after


class _BusinessError:
    """Wraps a deterministic, non-transient business exception (401,
    403 PLAN_LIMIT, any other non-2xx) so it can be *returned* rather
    than *raised* from the function passed to CircuitBreaker.execute().

    CircuitBreaker.execute() (src.core.runtime.reliability_layer,
    shared with the rest of the codebase, deliberately not modified
    here) counts any *raised* exception from its wrapped call as a
    failure, with no way to distinguish exception types -- it wasn't
    designed to. Returning this sentinel instead of raising is what
    keeps a 401/403/other business response from ever being recorded
    as a circuit-breaker failure while still surfacing the exact same
    exception to the caller: _request() unwraps and raises `.exception`
    itself, outside of `execute()`'s try/except, once the (successful,
    as far as the breaker is concerned) call has returned."""

    def __init__(self, exception: Exception):
        self.exception = exception


class SahmkClient:
    """Talks to https://app.sahmk.sa/api/v1 (or SAHMK_BASE_URL)."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        timeout_seconds: float = 10.0,
        session: Optional[aiohttp.ClientSession] = None,
        circuit_breaker: Optional[CircuitBreaker] = None,
        rate_limiter: Optional[SahmkRateLimiter] = None,
    ):
        self._api_key = api_key if api_key is not None else market_data_config.get_sahmk_api_key()
        self._base_url = (base_url or market_data_config.get_sahmk_base_url()).rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._session = session
        self._owns_session = session is None
        self._circuit_breaker = circuit_breaker or CircuitBreaker(
            failure_threshold=3, recovery_timeout=30
        )
        # Shared, process-wide by default (see rate_limiter.py's module
        # docstring for why: SAHMK's quota is per API key, not per
        # client instance, and this class has more than one instance
        # per process -- market data and fundamentals each hold their
        # own). Only ever overridden explicitly, for tests.
        self._rate_limiter = rate_limiter or get_default_rate_limiter()

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

    async def __aenter__(self) -> "SahmkClient":
        await self._ensure_session()
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # ------------------------------------------------------------------
    # Core request machinery
    # ------------------------------------------------------------------

    async def _request(self, path: str, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        if not self._api_key:
            raise SahmkConfigurationError(
                "SAHMK_API_KEY is not configured -- cannot call the SAHMK API."
            )

        # Rate-limited once per logical request, deliberately outside
        # circuit_breaker.execute()'s scope below -- a daily-quota
        # refusal (SahmkRateLimitExceededError) says nothing about
        # whether SAHMK itself is reachable/healthy, so it must never
        # be counted as a breaker failure, the same reasoning
        # _BusinessError exists for. The per-minute wait only ever
        # sleeps, never raises, so it's safe either way -- checked here
        # for the same reason: one throttle point for the whole
        # request, not one per retry attempt (tenacity's own backoff
        # already spaces retries of one request out).
        #
        # priority comes from the current asyncio task's
        # request_priority contextvar, not a parameter here -- every
        # caller (ingestion jobs, diagnostics, live scans) shares this
        # same client/rate-limiter, so a contextvar is what lets the
        # limiter tell a background backfill's request apart from a
        # live Decision Engine scan's, without changing every method's
        # signature (see request_priority.py's module docstring).
        await self._rate_limiter.acquire(priority=get_current_priority())

        @retry(
            reraise=True,
            stop=stop_after_attempt(3),
            wait=wait_exponential(multiplier=0.5, min=0.5, max=2),
            retry=retry_if_exception_type(_RetryableSahmkError),
        )
        async def _do_request() -> Any:
            # Returns either the parsed dict (2xx) or a _BusinessError
            # sentinel (401/403/other non-2xx) -- never *raises* for a
            # business outcome, so CircuitBreaker.execute() below never
            # sees it as a failure. Only raises _RetryableSahmkError
            # (429/5xx, retried by tenacity above) or a network-level
            # SahmkRequestError (from _send) -- both genuinely transient,
            # both legitimate for the breaker to count.
            return await self._send(path, params)

        try:
            outcome = await self._circuit_breaker.execute(_do_request)
        except _RetryableSahmkError as exc:
            if exc.kind == "rate_limit":
                raise SahmkRateLimitError(str(exc), retry_after=exc.retry_after) from exc
            raise SahmkRequestError(str(exc)) from exc

        if isinstance(outcome, _BusinessError):
            # Raised here, outside circuit_breaker.execute()'s scope --
            # this is a real, surfaced error for the *caller*, but it is
            # deliberately never counted as a breaker failure.
            if isinstance(outcome.exception, SahmkDailyQuotaExhaustedError):
                # Records SAHMK's own real evidence so every other
                # acquire() call -- this process and every other
                # worker/deployment sharing the same persisted state --
                # stops hammering SAHMK for nonessential requests until
                # the reset time SAHMK itself reported, instead of each
                # discovering the same exhaustion independently via its
                # own wasted request.
                self._rate_limiter.record_upstream_daily_exhaustion(
                    retry_after_seconds=outcome.exception.retry_after_seconds,
                    raw_message=str(outcome.exception),
                )
            raise outcome.exception
        return outcome

    async def _send(self, path: str, params: Optional[Dict[str, Any]]) -> Any:
        session = await self._ensure_session()
        url = f"{self._base_url}{path}"
        headers = {"X-API-Key": self._api_key}

        try:
            async with session.get(
                url,
                params=params,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=self._timeout_seconds),
            ) as response:
                return await self._handle_response(response)
        except _RetryableSahmkError:
            raise
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            # A connection failure or request timeout is exactly as
            # transient as a 5xx -- both mean "SAHMK/the network was
            # unavailable for this attempt," and a real full-market
            # scan should not give up on a symbol after a single slow
            # response when a 500 in the same spot gets 3 tenacity
            # attempts. Raising _RetryableSahmkError here (instead of
            # SahmkRequestError directly) routes it through the same
            # retry_if_exception_type(_RetryableSahmkError) path as
            # server_error; _request()'s translation still turns an
            # exhausted retry into SahmkRequestError for the caller.
            raise _RetryableSahmkError(f"Network error calling SAHMK API: {exc}", kind="network_error") from exc

    async def _handle_response(self, response: aiohttp.ClientResponse) -> Any:
        status = response.status

        if status == 200:
            try:
                return await response.json()
            except (aiohttp.ContentTypeError, ValueError) as exc:
                # An unparseable 200 is not a clean business rejection --
                # it looks like something between SAHMK and here (a
                # captive portal, a broken intermediary) returned a
                # malformed response, which is exactly the class of
                # anomaly the circuit breaker exists to protect against.
                # Raised directly (not wrapped in _BusinessError), so it
                # is still counted.
                body_text = await response.text()
                raise SahmkRequestError(
                    f"SAHMK returned a non-JSON 200 response: {body_text[:200]!r}",
                    status_code=status,
                    body=body_text,
                ) from exc

        body = await self._read_body(response)

        if status == 401:
            return _BusinessError(
                SahmkAuthenticationError(
                    "SAHMK rejected the configured API key (401).", status_code=status, body=body
                )
            )
        if status == 403:
            return _BusinessError(
                SahmkEntitlementError(
                    "SAHMK plan does not permit this endpoint (403 PLAN_LIMIT).",
                    status_code=status,
                    body=body,
                )
            )
        if status == 429:
            daily_evidence = _extract_daily_quota_evidence(body)
            if daily_evidence is not None:
                # A real, deterministic "today's account-wide quota is
                # spent" answer -- not a transient infrastructure
                # blip. Returned as a _BusinessError (never raised
                # inside circuit_breaker.execute()'s scope, never seen
                # by tenacity's retry_if_exception_type(_RetryableSahmkError)
                # predicate above) for exactly the same reason 401/403
                # are: SAHMK is reachable and answered correctly, our
                # account is just out of budget for the day. Retrying
                # within a few seconds of backoff, or tripping the
                # breaker as if SAHMK itself were unhealthy, would
                # both be wrong.
                return _BusinessError(
                    SahmkDailyQuotaExhaustedError(
                        f"SAHMK daily quota exhausted (429): {daily_evidence.raw_message}",
                        status_code=status,
                        body=body,
                        retry_after_seconds=daily_evidence.retry_after_seconds,
                    )
                )
            raise _RetryableSahmkError(
                f"SAHMK rate limit hit (429): {body}",
                kind="rate_limit",
                retry_after=self._parse_retry_after(response),
            )
        if 500 <= status < 600:
            raise _RetryableSahmkError(f"SAHMK server error ({status}): {body}", kind="server_error")

        return _BusinessError(
            SahmkRequestError(
                f"SAHMK request failed with status {status}.", status_code=status, body=body
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
    # API wrappers -- one per SAHMK endpoint this integration uses.
    # See docs/SAHMK_INTEGRATION.md for the verified endpoint table.
    # ------------------------------------------------------------------

    async def get_quote(self, symbol: str) -> Dict[str, Any]:
        """GET /quote/{symbol}/ -- live price (Free tier)."""
        validate_symbol_format(symbol)
        return await self._request(f"/quote/{symbol}/")

    async def get_historical(
        self,
        symbol: str,
        *,
        interval: str = "1d",
        date_from: Optional[date] = None,
        date_to: Optional[date] = None,
    ) -> Dict[str, Any]:
        """GET /historical/{symbol}/ -- OHLCV bars (Starter+)."""
        validate_symbol_format(symbol)
        params: Dict[str, Any] = {"interval": interval}
        if date_from is not None:
            params["from"] = date_from.isoformat()
        if date_to is not None:
            params["to"] = date_to.isoformat()
        return await self._request(f"/historical/{symbol}/", params=params)

    async def get_market_summary(self, index: str = "TASI") -> Dict[str, Any]:
        """GET /market/summary/?index=... -- index snapshot (Free tier);
        also the cheapest confirmed call, reused for health/auth checks."""
        return await self._request("/market/summary/", params={"index": index})

    async def get_events(self, limit: int = 10) -> Dict[str, Any]:
        """GET /events/ -- AI-generated stock events (Pro+)."""
        return await self._request("/events/", params={"limit": limit})

    async def get_company_profile(self, symbol: str) -> Dict[str, Any]:
        """GET /company/{symbol}/ -- company profile (Free+)."""
        validate_symbol_format(symbol)
        return await self._request(f"/company/{symbol}/")

    async def get_financials(self, symbol: str, period_type: str = "annual") -> Dict[str, Any]:
        """GET /financials/{symbol}/ -- financial statements (Starter+).

        UNVERIFIED (docs/SAHMK_INTEGRATION.md): the exact query-parameter
        name/values for selecting annual vs. quarterly statements are not
        confirmed by any source consulted. `period_type` is sent as-is
        under a `period` parameter as the most defensible reading, not a
        confirmed contract -- SahmkFundamentalDataProvider treats
        whatever SAHMK actually returns as authoritative rather than
        assuming this parameter is honored.
        """
        validate_symbol_format(symbol)
        return await self._request(f"/financials/{symbol}/", params={"period": period_type})

    async def get_dividends(self, symbol: str) -> Dict[str, Any]:
        """GET /dividends/{symbol}/ -- dividend history and yield
        (Starter+). The closest SAHMK endpoint to "corporate actions" --
        no source consulted documents a separate corporate-actions/
        splits/announcements endpoint distinct from this one."""
        validate_symbol_format(symbol)
        return await self._request(f"/dividends/{symbol}/")

    async def get_companies(self, params: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """GET /companies/ -- company directory / symbol discovery
        (Free tier). Used for periodic symbol-universe sync
        (src.market_data.ingestion.ingest_symbols).

        `params` is UNVERIFIED pagination support: SAHMK's actual
        pagination convention (if any) for this endpoint has never been
        confirmed live (see docs/SAHMK_INTEGRATION.md) -- this sandbox's
        network policy blocks direct calls to app.sahmk.sa, so the real
        scheme can only be confirmed from a live run's logs, not from
        here. Passing no params reproduces the original single-call
        behavior exactly. SahmkMarketDataService.get_company_directory()
        is responsible for deciding what params (if any) to send on a
        follow-up page, based on what the first response's envelope
        actually contains."""
        return await self._request("/companies/", params=params)
