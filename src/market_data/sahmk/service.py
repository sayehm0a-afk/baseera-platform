"""Business-level service over SahmkClient.

Where SahmkClient returns raw response dicts, SahmkMarketDataService
validates required fields, parses them into the typed dataclasses in
models.py, and caches results (src.market_data.caching.TTLCache) so
repeated calls for the same symbol/index within a short window don't
re-hit a metered, rate-limited vendor.

Cache TTLs: quotes and index snapshots change continuously during
trading hours, so they get a short TTL; a past trading day's bar never
changes once the day has closed, so historical bars get a long one.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qs, urlparse

from src.market_data.caching.ttl_cache import TTLCache
from src.market_data.sahmk.client import SahmkClient
from src.market_data.sahmk.exceptions import SahmkResponseValidationError
from src.market_data.sahmk.models import (
    SahmkCompanyProfile,
    SahmkDividend,
    SahmkEvent,
    SahmkFinancials,
    SahmkHistoricalBar,
    SahmkMarketSummary,
    SahmkQuote,
)

logger = logging.getLogger(__name__)

QUOTE_CACHE_TTL_SECONDS = 15.0
MARKET_SUMMARY_CACHE_TTL_SECONDS = 15.0
HISTORICAL_CACHE_TTL_SECONDS = 3600.0
EVENTS_CACHE_TTL_SECONDS = 300.0
COMPANY_PROFILE_CACHE_TTL_SECONDS = 86400.0  # a company's profile rarely changes
COMPANY_DIRECTORY_CACHE_TTL_SECONDS = 86400.0  # the symbol universe rarely changes
FINANCIALS_CACHE_TTL_SECONDS = 3600.0
DIVIDENDS_CACHE_TTL_SECONDS = 3600.0

# Bounds how many /companies/ pages get_company_directory() will ever
# follow, regardless of what a `count`/`total` field claims -- a
# misread or malicious total must never turn into an unbounded loop.
# 50 pages is generous headroom over any plausible page size for a
# market with a low-hundreds to low-thousands total listing count.
_MAX_DIRECTORY_PAGES = 50

# Page size requested on every /companies/ call. Real evidence
# (2026-08-08, direct probe of production SAHMK credentials): a bare
# `?limit=500` call returned exactly 500 results with no truncation or
# error, while the endpoint's own `total` field read 517 -- so this
# fetches the entire real directory in 2 requests instead of the
# default page size of 100 (~6 requests). If a future response ever
# returns fewer items than requested, the loop below still advances by
# however many items it actually got back, never by this requested
# size, so a silently smaller server-side max is still handled
# correctly and this is not a hardcoded assumption about the true
# total.
_DIRECTORY_PAGE_LIMIT = 500

# Field names tried, in order, when looking for a company's sector in
# a /companies/ directory entry -- UNVERIFIED, see get_company_directory's
# docstring. Includes both flat-string and Arabic-labeled candidates;
# a nested {"sector": {"name": ...}}-shaped value is handled separately
# by _extract_sector(), since _first_present() only reads flat values.
_SECTOR_KEY_CANDIDATES = [
    "sector", "sector_name", "sectorName", "gics_sector", "sector_ar", "sector_en",
]


def _extract_sector(item: Dict[str, Any]) -> Optional[str]:
    """Tries every flat sector key candidate, then falls back to a
    nested {"sector": {"name" | "name_en" | "sector_name": ...}} shape,
    a common pattern for APIs that model sector as an object rather
    than a bare string. Returns None (never guesses) if nothing
    matches either shape."""
    flat = _first_present(item, _SECTOR_KEY_CANDIDATES)
    if isinstance(flat, str):
        return flat
    nested = item.get("sector")
    if isinstance(nested, dict):
        return _first_present(nested, ["name", "name_en", "sector_name", "title"])
    return None


# Field names tried, in order, when looking for a company's Arabic name
# in a /companies/ or /company/{symbol}/ entry -- UNVERIFIED, same
# discipline as _SECTOR_KEY_CANDIDATES.
_NAME_AR_KEY_CANDIDATES = ["name_ar", "nameAr", "company_name_ar", "arabic_name", "name_arabic"]

# Unicode ranges covering Arabic script (main block, supplement, and
# presentation forms) -- used only to recognize Arabic text SAHMK
# itself already sent under an unlabeled "name" key, never to
# translate or invent one.
_ARABIC_SCRIPT_RANGES = (
    (0x0600, 0x06FF),
    (0x0750, 0x077F),
    (0xFB50, 0xFDFF),
    (0xFE70, 0xFEFF),
)


def _contains_arabic_script(value: Optional[str]) -> bool:
    if not value:
        return False
    return any(
        any(lo <= ord(ch) <= hi for lo, hi in _ARABIC_SCRIPT_RANGES) for ch in value
    )


def _extract_name_ar(item: Dict[str, Any]) -> Optional[str]:
    """Tries every flat Arabic-name key candidate first (mirrors
    _extract_sector's discipline). If none matched, and one of the
    English-name candidates ("name"/"company_name"/"name_en") happens
    to actually carry Arabic script -- a real, observed SAHMK
    inconsistency where the per-symbol profile endpoint has returned
    the Arabic company name under the same key the bulk directory uses
    for the Latin name (see docs/phase9_market_intelligence/
    DATA_QUALITY_REPORT.md) -- that text is used as the Arabic name
    rather than left null. Never fabricates: only ever returns text
    SAHMK itself actually sent."""
    flat = _first_present(item, _NAME_AR_KEY_CANDIDATES)
    if isinstance(flat, str) and flat.strip():
        return flat
    for key in ("name", "company_name", "name_en"):
        value = item.get(key)
        if isinstance(value, str) and _contains_arabic_script(value):
            return value
    return None


@dataclass
class _DirectoryDiagnostics:
    """Real, evidence-based record of what the last get_company_directory()
    call actually observed -- read by callers (e.g. the market-intelligence
    scan script) that need to report a genuine universe verdict rather
    than assuming 'however many came back is the whole market'."""

    pages_fetched: int
    total_fetched: int
    pagination_signal: Optional[str]
    reported_total: Optional[int]
    universe_verdict: str
    first_page_keys: List[str] = field(default_factory=list)
    first_item_keys: List[str] = field(default_factory=list)
    sector_populated_count: int = 0
    name_ar_populated_count: int = 0


def _classify_universe(
    pagination_signal: Optional[str], reported_total: Optional[int], fetched: int
) -> str:
    """FULL_UNIVERSE_VERIFIED requires an actual reconciliation: a
    reported total existed AND every record it claimed was fetched.
    PARTIAL_UNIVERSE_VERIFIED covers every other case where at least
    some real evidence of scope exists (a total was reported but not
    fully reconciled, or pagination was followed at all).
    UNIVERSE_NOT_VERIFIED is the honest default when the response
    carried no signal whatsoever about whether more data exists beyond
    what a single call happened to return -- this was every prior run's
    silent, unstated case before this fix."""
    if reported_total is not None and fetched >= reported_total > 0:
        return "FULL_UNIVERSE_VERIFIED"
    if reported_total is not None or pagination_signal is not None:
        return "PARTIAL_UNIVERSE_VERIFIED"
    return "UNIVERSE_NOT_VERIFIED"


def _first_present(data, keys: List[str]) -> Any:
    """Returns the value of the first key in `keys` present (and
    non-None) in `data`, or None. Used for fields whose exact wire name
    is UNVERIFIED (see docs/SAHMK_INTEGRATION.md) -- several plausible
    names are tried rather than assuming one.

    `data` may be a single dict, or a list of dicts to search in
    order (first dict wins) -- get_financials() uses the list form to
    check a per-statement dict first, falling back to the top-level
    response, without needing a second helper."""
    dicts = data if isinstance(data, list) else [data]
    for d in dicts:
        for key in keys:
            if key in d and d[key] is not None:
                return d[key]
    return None


def _first_matching_statement(items: Optional[List[Dict[str, Any]]], period_type: str) -> Dict[str, Any]:
    """Picks the entry in a /financials/ statement array (e.g.
    `income_statements`) whose own `statement_period` matches what was
    requested, most-recent `report_date` first per SAHMK's confirmed
    ordering; falls back to the first entry if none match, or `{}` if
    the array is missing/empty -- never raises, since a missing
    statement array is a normal degraded state (see
    SahmkFundamentalDataProvider, which decides what's actually
    required)."""
    if not items:
        return {}
    for item in items:
        if item.get("statement_period") == period_type:
            return item
    return items[0]


def _parse_timestamp(value: Any) -> Optional[datetime]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value)
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        logger.warning("Could not parse SAHMK timestamp %r; leaving unset.", value)
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed


def _require_fields(data: Dict[str, Any], fields: List[str], context: str) -> None:
    missing = [f for f in fields if f not in data or data[f] is None]
    if missing:
        raise SahmkResponseValidationError(
            f"SAHMK {context} response is missing required field(s): {missing}", body=data
        )


class SahmkMarketDataService:
    """Typed, cached, business-level access to SAHMK market data."""

    def __init__(self, client: Optional[SahmkClient] = None, cache: Optional[TTLCache] = None):
        self._client = client or SahmkClient()
        self._cache = cache if cache is not None else TTLCache()
        # Populated by get_company_directory() -- None until that method
        # has actually run at least once. See _DirectoryDiagnostics.
        self.last_directory_diagnostics: Optional[_DirectoryDiagnostics] = None

    @property
    def has_credentials(self) -> bool:
        return self._client.has_credentials

    async def close(self) -> None:
        await self._client.close()

    async def __aenter__(self) -> "SahmkMarketDataService":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    # ------------------------------------------------------------------

    async def get_latest_quote(self, symbol: str) -> SahmkQuote:
        async def _compute() -> SahmkQuote:
            data = await self._client.get_quote(symbol)
            _require_fields(data, ["price"], "quote")
            return SahmkQuote(
                symbol=symbol,
                price=float(data["price"]),
                change=_optional_float(data.get("change")),
                change_percent=_optional_float(data.get("change_percent")),
                volume=_optional_int(data.get("volume")),
                timestamp=_parse_timestamp(data.get("updated_at")) or datetime.now(timezone.utc),
                bid=_optional_float(data.get("bid")),
                ask=_optional_float(data.get("ask")),
            )

        return await self._cache.get_or_compute(
            ("quote", symbol), _compute, ttl_seconds=QUOTE_CACHE_TTL_SECONDS
        )

    async def get_historical_bars(
        self,
        symbol: str,
        date_from: date,
        date_to: date,
        interval: str = "1d",
    ) -> List[SahmkHistoricalBar]:
        async def _compute() -> List[SahmkHistoricalBar]:
            data = await self._client.get_historical(
                symbol, interval=interval, date_from=date_from, date_to=date_to
            )
            bars = data.get("data", [])
            result: List[SahmkHistoricalBar] = []
            for bar in bars:
                _require_fields(
                    bar, ["open", "high", "low", "close", "volume", "date"], "historical bar"
                )
                result.append(
                    SahmkHistoricalBar(
                        symbol=symbol,
                        open=float(bar["open"]),
                        high=float(bar["high"]),
                        low=float(bar["low"]),
                        close=float(bar["close"]),
                        volume=int(bar["volume"]),
                        timestamp=_parse_timestamp(bar["date"]),
                    )
                )
            return result

        cache_key = ("historical", symbol, date_from.isoformat(), date_to.isoformat(), interval)
        return await self._cache.get_or_compute(
            cache_key, _compute, ttl_seconds=HISTORICAL_CACHE_TTL_SECONDS
        )

    async def get_daily_bar(self, symbol: str, on: Optional[date] = None) -> SahmkHistoricalBar:
        """Most recent daily OHLCV bar for `symbol` as of `on` (default:
        today). Raises SahmkResponseValidationError if no bar is
        available for the requested day (e.g. a non-trading day)."""
        target_day = on or datetime.now(timezone.utc).date()
        bars = await self.get_historical_bars(symbol, target_day, target_day, interval="1d")
        if not bars:
            raise SahmkResponseValidationError(
                f"SAHMK returned no historical bar for '{symbol}' on {target_day.isoformat()}."
            )
        return bars[-1]

    async def get_index_snapshot(self, index: str = "TASI") -> SahmkMarketSummary:
        async def _compute() -> SahmkMarketSummary:
            data = await self._client.get_market_summary(index=index)
            _require_fields(data, ["index_value"], "market summary")
            return SahmkMarketSummary(
                index=index,
                value=float(data["index_value"]),
                change=_optional_float(data.get("index_change")),
                change_percent=_optional_float(data.get("index_change_percent")),
                timestamp=_parse_timestamp(data.get("timestamp")),
            )

        return await self._cache.get_or_compute(
            ("summary", index), _compute, ttl_seconds=MARKET_SUMMARY_CACHE_TTL_SECONDS
        )

    async def get_recent_events(self, limit: int = 10) -> List[SahmkEvent]:
        async def _compute() -> List[SahmkEvent]:
            data = await self._client.get_events(limit=limit)
            items = data.get("events", data.get("results", []))
            return [
                SahmkEvent(
                    symbol=item.get("symbol"),
                    headline=item.get("headline") or item.get("title") or "",
                    timestamp=_parse_timestamp(item.get("timestamp")),
                    raw=item,
                )
                for item in items
            ]

        return await self._cache.get_or_compute(
            ("events", limit), _compute, ttl_seconds=EVENTS_CACHE_TTL_SECONDS
        )

    async def get_company_profile(self, symbol: str) -> SahmkCompanyProfile:
        async def _compute() -> SahmkCompanyProfile:
            data = await self._client.get_company_profile(symbol)
            return SahmkCompanyProfile(
                symbol=symbol,
                name=_first_present(data, ["name", "company_name", "name_en"]),
                name_ar=_extract_name_ar(data),
                sector=_first_present(data, ["sector", "sector_name"]),
                industry=_first_present(data, ["industry", "industry_name", "sub_sector", "subsector"]),
                exchange=_first_present(data, ["exchange", "market", "exchange_name"]),
                raw=data,
            )

        return await self._cache.get_or_compute(
            ("company_profile", symbol), _compute, ttl_seconds=COMPANY_PROFILE_CACHE_TTL_SECONDS
        )

    async def get_company_directory(self) -> List[SahmkCompanyProfile]:
        """The full Tadawul+Nomu symbol directory from GET /companies/.

        CONFIRMED live (2026-08-08, direct probe against production
        SAHMK credentials, bypassing this client): the envelope's
        top-level keys are `count`, `limit`, `offset`, `results`,
        `total` -- `count` is this PAGE's own size (defaults to 100),
        `total` is the true grand total (observed: 517 unfiltered, 126
        for `?market=NOMU`). A prior version of this method read
        `count` before `total` when looking for the grand total, so it
        silently treated the page size as the whole universe and
        stopped after one call -- this is exactly why two earlier
        full-universe runs both returned precisely 100 companies. Both
        `limit` (confirmed: `?limit=500` returns 500 real results in
        one call, not truncated) and `offset` (confirmed:
        `?offset=100&limit=100` succeeds) are real, working pagination
        parameters, not guessed.

        This method paginates via `limit`/`offset` using the server's
        own reported `total`, bounded to `_MAX_DIRECTORY_PAGES`
        iterations so a misread or adversarial total can never spin
        forever. A `next` URL, if the server ever sends one (not
        observed in practice), is still followed as an alternative
        signal. If no pagination signal is present at all, behavior is
        unchanged from before this fix: one call, whatever it returns
        is the universe. Either way, the outcome is recorded in
        `self.last_directory_diagnostics` (see `_DirectoryDiagnostics`)
        with an explicit universe verdict -- FULL_UNIVERSE_VERIFIED is
        only ever set when a reported total was actually reconciled
        against what was fetched, never assumed."""

        async def _compute() -> List[SahmkCompanyProfile]:
            result: List[SahmkCompanyProfile] = []
            seen_symbols: set = set()
            page_params: Optional[Dict[str, Any]] = None
            offset = 0
            pages_fetched = 0
            reported_total: Optional[int] = None
            pagination_signal: Optional[str] = None
            first_page_keys: List[str] = []
            first_item_keys: List[str] = []

            while pages_fetched < _MAX_DIRECTORY_PAGES:
                if page_params is not None:
                    request_params: Dict[str, Any] = dict(page_params)
                else:
                    request_params = {"limit": _DIRECTORY_PAGE_LIMIT}
                    if offset:
                        request_params["offset"] = offset

                data = await self._client.get_companies(params=request_params)
                pages_fetched += 1
                if pages_fetched == 1 and isinstance(data, dict):
                    first_page_keys = sorted(data.keys())

                items = data.get("companies", data.get("results", data.get("data", [])))
                if not isinstance(items, list):
                    items = []
                if pages_fetched == 1 and items and isinstance(items[0], dict):
                    first_item_keys = sorted(items[0].keys())

                new_this_page = 0
                for item in items:
                    symbol = _first_present(item, ["symbol", "ticker"])
                    if symbol is None:
                        continue
                    symbol = str(symbol)
                    if symbol in seen_symbols:
                        continue
                    seen_symbols.add(symbol)
                    new_this_page += 1
                    result.append(
                        SahmkCompanyProfile(
                            symbol=symbol,
                            name=_first_present(item, ["name", "company_name", "name_en"]),
                            name_ar=_extract_name_ar(item),
                            sector=_extract_sector(item),
                            industry=_first_present(
                                item, ["industry", "industry_name", "sub_sector", "subsector"]
                            ),
                            exchange=_first_present(item, ["exchange", "market", "exchange_name"]),
                            raw=item,
                        )
                    )

                # `total` (the true grand total) is checked before `count`
                # (this page's own size) -- see the docstring above for the
                # real-evidence reason this order matters.
                page_total = _first_present(
                    data, ["total", "count", "total_count", "totalCount", "total_results"]
                )
                if page_total is not None:
                    reported_total = int(page_total)

                next_url = data.get("next") if isinstance(data, dict) else None
                if next_url:
                    pagination_signal = "next_url"
                    parsed = urlparse(str(next_url))
                    page_params = {k: v[0] for k, v in parse_qs(parsed.query).items()}
                    if not page_params:
                        # A `next` value with no parseable query string can't
                        # be followed via the params-only client method --
                        # stop rather than guess at a raw-URL fetch.
                        break
                    continue

                page_params = None
                offset += len(items)
                if reported_total is not None and offset < reported_total and new_this_page > 0:
                    pagination_signal = pagination_signal or "count_total"
                    continue

                break

            verdict = _classify_universe(
                pagination_signal=pagination_signal,
                reported_total=int(reported_total) if reported_total is not None else None,
                fetched=len(result),
            )
            sector_populated = sum(1 for c in result if c.sector)
            name_ar_populated = sum(1 for c in result if c.name_ar)
            diagnostics = _DirectoryDiagnostics(
                pages_fetched=pages_fetched,
                total_fetched=len(result),
                pagination_signal=pagination_signal,
                reported_total=int(reported_total) if reported_total is not None else None,
                universe_verdict=verdict,
                first_page_keys=first_page_keys,
                first_item_keys=first_item_keys,
                sector_populated_count=sector_populated,
                name_ar_populated_count=name_ar_populated,
            )
            self.last_directory_diagnostics = diagnostics
            logger.info(
                "SAHMK company directory: %d page(s), %d unique companies, "
                "pagination_signal=%s, reported_total=%s, universe_verdict=%s, "
                "sector_populated=%d/%d, name_ar_populated=%d/%d, "
                "first_page_keys=%s, first_item_keys=%s",
                pages_fetched, len(result), pagination_signal, reported_total, verdict,
                sector_populated, len(result), name_ar_populated, len(result),
                first_page_keys, first_item_keys,
            )
            if result and sector_populated == 0:
                logger.warning(
                    "SAHMK company directory: sector field unresolved for all %d companies -- "
                    "raw first item's top-level keys were %s. None of the tried sector key "
                    "names (%s) matched; sector-dependent analysis will be NOT_EVALUATED "
                    "until the real field name is confirmed from this log line.",
                    len(result), first_item_keys, _SECTOR_KEY_CANDIDATES,
                )
            if result and name_ar_populated == 0:
                logger.warning(
                    "SAHMK company directory: name_ar unresolved for all %d companies -- "
                    "raw first item's top-level keys were %s. Neither the tried Arabic-name "
                    "key names (%s) nor Arabic script in the name/company_name/name_en fields "
                    "matched; Arabic company names will stay NULL (frontend falls back to "
                    "name_en) until a real Arabic-name field is confirmed from this log line.",
                    len(result), first_item_keys, _NAME_AR_KEY_CANDIDATES,
                )
            return result

        return await self._cache.get_or_compute(
            "company_directory", _compute, ttl_seconds=COMPANY_DIRECTORY_CACHE_TTL_SECONDS
        )

    async def get_financials(self, symbol: str, period_type: str = "annual") -> SahmkFinancials:
        """Parses GET /financials/{symbol}/.

        CONFIRMED live (workflow run 30436660246, 3 real symbols): the
        response is NOT a flat object -- figures are split across three
        per-period statement arrays (`income_statements`,
        `balance_sheets`, `cash_flows`), each entry carrying its own
        `report_date`/`statement_period`, most-recent period first.
        Also confirmed: `current_assets`, `current_liabilities`,
        `shares_outstanding`, and `eps` are not present ANYWHERE in
        this response, for any symbol tested -- not misnamed, genuinely
        absent from this endpoint's data (see docs/SAHMK_INTEGRATION.md)
        -- so those come back as `None` rather than being guessed at.

        A flat top-level shape is still tried as a fallback (via
        _first_present) in case a different symbol/tier ever returns
        one; `raw` always carries the untouched response either way.
        """

        async def _compute() -> SahmkFinancials:
            data = await self._client.get_financials(symbol, period_type=period_type)
            income = _first_matching_statement(data.get("income_statements"), period_type)
            balance = _first_matching_statement(data.get("balance_sheets"), period_type)

            return SahmkFinancials(
                symbol=symbol,
                period_type=period_type,
                fiscal_period_end=_first_present(
                    [income, balance, data], ["report_date", "fiscal_period_end", "period_end", "date"]
                ),
                revenue=_optional_float(_first_present([income, data], ["total_revenue", "revenue"])),
                gross_profit=_optional_float(_first_present([income, data], ["gross_profit"])),
                net_income=_optional_float(_first_present([income, data], ["net_income", "net_profit"])),
                total_assets=_optional_float(_first_present([balance, data], ["total_assets"])),
                total_liabilities=_optional_float(_first_present([balance, data], ["total_liabilities"])),
                total_equity=_optional_float(
                    _first_present([balance, data], ["stockholders_equity", "total_equity", "shareholders_equity"])
                ),
                current_assets=_optional_float(_first_present([balance, data], ["current_assets"])),
                current_liabilities=_optional_float(_first_present([balance, data], ["current_liabilities"])),
                inventory=_optional_float(_first_present([balance, data], ["inventory"])),
                cash_and_equivalents=_optional_float(
                    _first_present([balance, data], ["cash_and_equivalents", "cash"])
                ),
                total_debt=_optional_float(_first_present([balance, data], ["total_debt"])),
                shares_outstanding=_optional_int(
                    _first_present([balance, income, data], ["shares_outstanding", "shares"])
                ),
                eps=_optional_float(_first_present([income, data], ["eps", "earnings_per_share"])),
                raw=data,
            )

        cache_key = ("financials", symbol, period_type)
        return await self._cache.get_or_compute(
            cache_key, _compute, ttl_seconds=FINANCIALS_CACHE_TTL_SECONDS
        )

    async def get_dividends(self, symbol: str) -> List[SahmkDividend]:
        async def _compute() -> List[SahmkDividend]:
            data = await self._client.get_dividends(symbol)
            items = data.get("dividends", data.get("results", []))
            result: List[SahmkDividend] = []
            for item in items:
                per_share = _first_present(item, ["dividend_per_share", "amount", "value"])
                if per_share is None:
                    continue
                result.append(
                    SahmkDividend(
                        symbol=symbol,
                        dividend_per_share=float(per_share),
                        ex_date=_first_present(item, ["ex_date", "ex_dividend_date"]),
                        payment_date=_first_present(item, ["payment_date", "pay_date"]),
                        raw=item,
                    )
                )
            return result

        return await self._cache.get_or_compute(
            ("dividends", symbol), _compute, ttl_seconds=DIVIDENDS_CACHE_TTL_SECONDS
        )

    async def get_latest_dividend_per_share(self, symbol: str) -> Optional[float]:
        """Most recent dividend_per_share, or None if SAHMK reports no
        dividend history for `symbol` -- a stock never having paid a
        dividend is a valid, expected state, not an error."""
        dividends = await self.get_dividends(symbol)
        return dividends[0].dividend_per_share if dividends else None

    async def check_health(self) -> bool:
        """Cheapest confirmed call (GET /market/summary/) used to verify
        the configured key is accepted and the host is reachable.
        Returns False for any failure rather than raising -- callers
        that need the specific failure reason should call
        get_index_snapshot() directly instead."""
        try:
            await self.get_index_snapshot("TASI")
            return True
        except Exception as exc:  # noqa: BLE001 -- deliberate: this is a boolean health probe
            logger.info("SAHMK health check failed: %s", exc)
            return False


def _optional_float(value: Any) -> Optional[float]:
    return float(value) if value is not None else None


def _optional_int(value: Any) -> Optional[int]:
    return int(value) if value is not None else None
