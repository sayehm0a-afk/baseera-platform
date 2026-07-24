# SAHMK (sahmk.sa) Integration

Status: **provider implemented, not yet verified against a live account**
(no API key has been used against a real endpoint as of this document).

This file records exactly what was verified from SAHMK's official sources
before any endpoint was implemented, and exactly what was **not**
confirmed and is therefore treated as best-effort/unverified in the code
until tested with a real key (Phase 7).

## Sources consulted (read-only, public)

- `https://github.com/sahmk-sa/sahmk-python` — SAHMK's own official
  Python SDK repository (README, CHANGELOG). This is the primary source
  for everything below.
- `https://pypi.org/project/sahmk/` — the published package page for the
  same SDK.
- `https://www.sahmk.sa/en/developers/docs` and
  `https://www.sahmk.sa/en/developers/tutorials/...` — SAHMK's own hosted
  docs site. **Both returned HTTP 403** when fetched (bot-protection or
  requires an authenticated sahmk.sa session) — not accessible from this
  environment. Nothing from these pages is used below; if you have an
  authenticated session, please paste or forward their content so any
  gaps below can be closed with a verified source rather than inference.

No endpoint, field name, or header in this document — or in
`src/market_data/providers/sahmk_market_data_provider.py` — was guessed.
Anything not confirmed by the sources above is explicitly marked
**UNVERIFIED** and the code treats it defensively (see "Known gaps"
below), never as an assumption baked into request-building logic.

## Base URL & authentication

- **Base URL:** `https://app.sahmk.sa/api/v1`
- **Authentication:** every request carries an `X-API-Key` header. There
  is **no token-exchange step** (no `/auth/token`-style endpoint) — the
  key itself is the credential on every call. This is a real
  architectural difference from the placeholder provider built in M2.13
  (which guessed a Bearer-token exchange flow modeled on
  `SaudiMarketDataProvider`) — that guess is now replaced.

## Symbol / identifier format

The API accepts three identifier forms:
- Numeric Tadawul symbol: `"2222"` (this is what Basirah's `Stock.symbol`
  column stores, and the only form this integration sends)
- Arabic company name: `"أرامكو السعودية"`
- English alias: `"Aramco"`

Basirah's `symbol_validator.py` (M2.13) already validates the 4-digit
numeric Tadawul format; that validation is kept as-is and applied before
every SAHMK call — the name/alias resolution path exists in SAHMK's API
but is not used by this integration, since Basirah's domain model only
ever stores numeric symbols.

## Endpoints used by this integration

| Basirah need | SAHMK endpoint | Plan requirement |
|---|---|---|
| Latest "bar" (`get_stock_data`) | `GET /historical/{symbol}/?interval=1d&from=<today>&to=<today>`, last bar of the result | **Starter+** (see note below — deliberately *not* `/quote/`) |
| Historical OHLCV (`get_historical_ohlcv`) | `GET /historical/{symbol}/?interval=1d&from=...&to=...` | Starter+ |
| Latest real-time quote (`get_latest_quote`, new — not part of `IMarketDataProvider`) | `GET /quote/{symbol}/` | Free |
| Market index snapshot (`get_index_data`) | `GET /market/summary/?index=TASI\|NOMU\|NOMUC` | Free |
| Provider health check | `GET /market/summary/` (cheapest confirmed endpoint; reused, not a dedicated `/health` route — SAHMK does not document one) | Free |
| "Market news" (`get_market_news`) | `GET /events/` ("AI-generated stock events" — the closest verified endpoint; SAHMK does **not** document a general news/headlines endpoint, so nothing else was invented for this) | **Pro+** — will return a plan-limit error on Free/Starter accounts, surfaced as-is, not silently swallowed |

**Why `get_stock_data` uses `/historical/` and not `/quote/`:** `IMarketDataProvider.get_stock_data()`'s
existing, unchanged contract (kept exactly as designed, per instruction)
must return a full OHLCV bar — `open`/`high`/`low`/`close`/`volume`/
`timestamp` — because `ingest_ohlcv.py`'s `_upsert_price_bar` requires
every one of those keys. SAHMK's confirmed `/quote/{symbol}/` response
only documents `price`/`change`/`change_percent`/`volume`/`value` — no
open/high/low. Fabricating `open=high=low=price` would be presenting
invented data as real, which is explicitly forbidden. So `get_stock_data`
calls `/historical/{symbol}/` for "today" instead, which *does* document
real OHLCV fields — honest, at the cost of requiring a Starter+ plan
instead of Free for this specific call. `/quote/{symbol}/` is still used,
via the new `get_latest_quote()` method, for callers that only need a
live price and are fine with the `MarketQuote` shape instead of a bar.

Endpoints documented by SAHMK but **not used** by this integration (out
of scope for M2.x's current data model, listed here so nothing is
accidentally duplicated later): `GET /quotes/` (batch quotes),
`GET /market/gainers/|/losers/|/volume/|/value/|/sectors/`,
`GET /market/depth/{symbol}/` (order book), `GET /companies/` (symbol
discovery), `GET /company/{symbol}/` (company profile), `GET
/financials/{symbol}/`, `GET /analytics/ratios/{symbol}/`, `GET
/analytics/compare/`, `GET /dividends/{symbol}/`, and the Pro+ WebSocket
streams (`stream()`, `stream_depth()`). These map naturally onto
`StockProfile`/`FinancialStatement`/`MarketIndex` in the provider
abstraction and are candidates for a later milestone, not this one.

## Historical data parameters

- `interval`: one of `1d`, `1w`, `1m`, `30m`, `60m` — **plan-gated**
  (Free: none; Starter: `1d`/`1w`/`1m`; Pro/Business: intraday
  intervals too, per the SDK docs). Basirah requests `1d` only, matching
  the existing `Timeframe.ONE_DAY` domain model — no other timeframe is
  requested.
- `from` / `to`: date range bounds. **UNVERIFIED**: the exact wire format
  (`YYYY-MM-DD` vs. full ISO-8601 datetime) is not stated in either
  source. This integration sends `date().isoformat()` (`YYYY-MM-DD`),
  the most common convention for a daily-bar endpoint and consistent
  with `interval=1d`; this must be confirmed against a real response in
  Phase 7 and corrected here if wrong.

## Retry / rate-limit behavior (confirmed)

- Transient failures — HTTP `429` and any `5xx` — are retried, default
  3 attempts, with backoff delays of `0.5s → 1s → 2s`.
- A `429` response with a `Retry-After` header uses that server-specified
  wait time instead of the computed backoff.
- `retries=3` / `backoff_factor=0.5` are the official SDK's own defaults
  — this integration's `tenacity` retry policy is configured to match
  them exactly (`wait_exponential(multiplier=0.5, max=2)`,
  `stop_after_attempt(3)`), reusing Basirah's existing `CircuitBreaker`
  (`src/core/runtime/reliability_layer/circuit_breaker.py`) around the
  whole retried call, unchanged from M2.13's design.

## Error handling (confirmed + gaps)

Confirmed from the SDK's own WebSocket close-code documentation
(REST-side status codes are **not** separately enumerated in either
source, so the mapping below is the most defensible reading, not a
guess of undocumented behavior):
- Authentication failure → non-retryable (WebSocket close code `4401`;
  REST is assumed to be the standard `401`, since no REST-specific code
  is documented — treated as **UNVERIFIED**, see "Known gaps").
- Entitlement / plan / inactive / unverified account → non-retryable
  (WebSocket close code `4403`; REST is documented explicitly as
  **`403` with body `PLAN_LIMIT`** — this one *is* confirmed for REST).
- `429` → retried per the policy above, respecting `Retry-After`.
- Any other non-2xx → surfaced as a normalized provider error with the
  response body attached (never silently swallowed, never retried
  beyond the documented 429/5xx cases).

## Rate limits / plan quotas

**UNVERIFIED at the exact-number level.** Public search results
mention "100 free requests per day" for the free tier, and the SDK's
`SahmkRateLimitError` carries `retry_after`/`rate_limit` metadata at
runtime, but neither source states the full table of daily-quota /
per-minute-burst numbers for every plan tier. Basirah's caching
(`TTLCache`, M2.13) is deliberately conservative as a result — see
"Known gaps" for what needs verifying once a real key is available.

## Known gaps — to verify in Phase 7 (real, limited testing), never guessed here

1. Exact `from`/`to` date wire format for `/historical/{symbol}/`.
2. Full daily/per-minute rate-limit numbers per plan tier.
3. REST (non-WebSocket) HTTP status code for an invalid/expired API key
   — assumed `401`, not confirmed.
4. Full response field list for `/historical/{symbol}/`,
   `/market/summary/`, and `/events/` (only the fields referenced above
   were confirmed via the SDK docs; the provider's response mapping
   only reads fields it has confirmed names for, and passes the rest of
   the payload through unmodified rather than dropping or renaming
   anything it doesn't recognize).

## Example requests (no real key — placeholder only)

```
GET https://app.sahmk.sa/api/v1/quote/2222/
X-API-Key: <SAHMK_API_KEY>

GET https://app.sahmk.sa/api/v1/historical/2222/?interval=1d&from=2024-01-01&to=2024-01-31
X-API-Key: <SAHMK_API_KEY>

GET https://app.sahmk.sa/api/v1/market/summary/?index=TASI
X-API-Key: <SAHMK_API_KEY>
```

## Notes on future expansion

`StockProfile`, `FinancialStatement`, and `MarketIndex` unified models
already exist in the provider-abstraction layer (see
`src/market_data/models.py`) precisely so that `/company/{symbol}/`,
`/financials/{symbol}/`, `/dividends/{symbol}/`, and the batch/gainers/
losers/sectors endpoints can be added later without another redesign —
each is a new method on `SahmkMarketDataProvider` returning one of the
already-defined unified models, not a new abstraction.
