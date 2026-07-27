# SAHMK (sahmk.sa) Integration

Status: **provider implemented for every Starter-tier endpoint this
integration needs; live verification is blocked inside this sandbox's
network policy, but has been confirmed for real via
`.github/workflows/sahmk-live-verification.yml` on a GitHub-hosted
runner** (see "Live verification outside this sandbox" below) --
quotes, market summary, company profile/directory, financials,
dividends, and historical bars have all returned real 200 responses,
and the two field-name bugs that discovery surfaced have been fixed.

## Key rotation & plan upgrade

The account was upgraded from Free to Starter and `SAHMK_API_KEY` was
rotated (old key revoked, new key generated) after the first version of
this integration was built. Every claim in the previous revision of
this document about a specific real response (`403 PLAN_LIMIT` on
`/market/summary/` and `/historical/`) was observed against the **old,
now-revoked** Free-tier key and is **no longer applicable** -- it is not
repeated here as current fact. This revision reflects only the new key.

## Live verification attempt (this session)

`bool(os.getenv("SAHMK_API_KEY"))` confirmed the new key is present.
Every live call in this session goes through `SahmkClient`, which
(since the previous revision) always constructs its `aiohttp.ClientSession`
with `trust_env=True` so it honors this environment's `HTTPS_PROXY` --
the same policy `curl` observes, never bypassed.

Both `curl -H "X-API-Key: $SAHMK_API_KEY" https://app.sahmk.sa/api/v1/...`
and a call through the real `SahmkClient`/`SahmkMarketDataProvider` code
path were attempted (read-only `GET /market/summary/`). Both were
rejected identically, **before reaching sahmk.sa at all**:

```
curl:   exit 56, HTTP_STATUS:000
proxy status: {"kind": "connect_rejected",
               "detail": "gateway answered 403 to CONNECT (policy denial or upstream failure)",
               "host": "app.sahmk.sa:443"}
client: aiohttp.client_exceptions.ClientHttpProxyError:
               403, message='Forbidden', url='http://127.0.0.1:<local-proxy-port>'
```

The `403` comes from the **local egress proxy's own CONNECT response**
(the URL in the error is the proxy's own `127.0.0.1` address, not
sahmk.sa) -- this is this sandbox's organization-level network policy
declining to let any process reach `app.sahmk.sa`, not a response from
SAHMK, and not related to the key, the plan, or this code. Per this
environment's own documented policy ("never retry or route around a
403/407 from the proxy -- report it instead"), no further live attempt
was made.

**Consequence: none of tasks 2-5 of the "verify Starter-plan access"
request (authenticate live, confirm Quote/Historical/Market Summary/
Company Fundamentals/Dividends/Corporate Actions individually) could be
completed with a real HTTP response in this session.** This is a
network-policy fact about this sandbox, not a statement about the
SAHMK account or this code. `src/market_data/provider_factory.py` and
`fundamental_provider_factory.py` already handle exactly this condition
by design: `get_market_data_provider()`/`get_fundamental_data_provider()`
probe connectivity and fall back to the synthetic `Dev*Provider`
whenever SAHMK is unreachable, which is what actually happened here,
automatically, with no manual flag. **The moment this same code runs
somewhere with real network access to `sahmk.sa`, that probe will
succeed or fail on its own merits and the endpoint table below will
resolve itself** -- nothing else needs to change.

## Base URL & authentication

- **Base URL:** `https://app.sahmk.sa/api/v1` (`SAHMK_BASE_URL`,
  overridable, defaults to this public value -- not a secret).
- **Authentication:** every request carries an `X-API-Key` header
  (`SAHMK_API_KEY`, read from the environment, never hardcoded, never
  logged, never committed). There is no token-exchange endpoint -- the
  key itself is the credential on every call.

## Symbol format

Tadawul's 4-digit numeric code (e.g. `"1120"`, `"2222"`) -- the same
format already used throughout this codebase. Validated locally
(`src/market_data/validators/symbol_validator.py`) before any request is
sent, so a malformed symbol never costs a network call.

## Endpoint-by-endpoint status

Per the user's explicit request to document exactly which endpoints
work and which don't. "Implemented" means `SahmkClient` has a wrapper
method, `SahmkMarketDataService`/the provider adapters parse and
validate its response, and it has unit test coverage against mocked
responses. "Live-verified" means a real 2xx response was actually
observed in this environment -- which, per above, was not possible this
session for any endpoint.

| Basirah need | SAHMK endpoint | Plan (per SDK docs) | Implemented | Live-verified (2026-07-27) |
|---|---|---|---|---|
| Live quote | `GET /quote/{symbol}/` | Free | Yes (`get_quote`, `get_latest_quote`) | **Yes -- 200 OK, real price 26.56 SAR** |
| Historical OHLCV / today's bar | `GET /historical/{symbol}/` | Starter+ | Yes (`get_historical`, `get_stock_data`, `get_daily_bar`) | **Yes -- 200 OK, 118 real daily bars, full schema confirmed** |
| Market summary (index snapshot) | `GET /market/summary/?index=...` | Free | Yes (`get_market_summary`, `get_index_data`); also the `authenticate()`/`health_check()` probe call | **Yes -- 200 OK** |
| Company fundamentals (financial statements) | `GET /financials/{symbol}/` | Starter+ | Yes (`get_financials`, `SahmkFundamentalDataProvider.get_fundamentals`) | **Yes -- 200 OK (top-level envelope only; nested field names still unverified, see Known gaps)** |
| Dividends | `GET /dividends/{symbol}/` | Starter+ | Yes (`get_dividends`, folded into `get_fundamentals`'s `dividend_per_share`) | **Yes -- 200 OK** |
| Company profile | `GET /company/{symbol}/` | Free+ | Yes (`get_company_profile`) | **Yes -- 200 OK** |
| Corporate actions | *(no distinct endpoint documented)* | -- | Not implemented | N/A |
| "Market news" / stock events | `GET /events/` | **Pro+** | Yes (`get_events`, `get_market_news`) | Not yet exercised live -- plan access still unconfirmed |
| Batch quotes | `GET /quotes/?symbols=...` | Starter+ | Not implemented | N/A |
| Gainers/losers/volume/value/sectors | `GET /market/{gainers,losers,volume,value,sectors}/` | Free | Not implemented | N/A |
| Market depth (order book) | `GET /market/depth/{symbol}/` | Entitled | Not implemented | N/A |
| Analytics ratios / comparison | `GET /analytics/{ratios,compare}/` | Starter+ | Not implemented | N/A |
| Symbol discovery (company directory) | `GET /companies/` | Free | Yes (`get_companies`, `SahmkMarketDataService.get_company_directory`) | **Yes -- 200 OK, paginated** |
| WebSocket streams | `stream()`, `stream_depth()` | Pro+ | Not implemented (not supported through this environment's proxy in general -- WebSocket upgrades are explicitly unsupported) | N/A |

**"Corporate Actions"**: no source consulted (SAHMK's own developer
site was HTTP 403 to fetch directly; its SDK's GitHub README/PyPI page
were used instead) documents a distinct corporate-actions/splits/
announcements endpoint. `/dividends/{symbol}/` is the closest and only
Starter-tier match and is what this integration treats "corporate
actions" as, for now -- disclosed as an inference, not a confirmed
mapping.

## Retry / rate-limit / circuit-breaker behavior

- `429` and any `5xx` are retried (3 attempts, `0.5s → 1s → 2s`
  backoff), honoring a `429` response's `Retry-After` header.
  Exhausting retries raises `SahmkRateLimitError` / `SahmkRequestError`
  respectively.
- Network-level failures (DNS, connection refused/reset, an egress
  policy block -- exactly what this session observed) are **not**
  retried -- they surface immediately as `SahmkRequestError`, since
  SAHMK's own documented retry guidance covers 429/5xx specifically,
  not generic connectivity failure.
- Every retried call is wrapped in Basirah's existing `CircuitBreaker`
  (`src/core/runtime/reliability_layer/circuit_breaker.py`, reused
  unchanged) so a sustained outage stops hammering the upstream once
  the failure threshold trips.

## Error handling

- `401` → `SahmkAuthenticationError` (non-retryable). **UNVERIFIED**:
  no source states the exact REST status code for an invalid key.
- `403` with body `PLAN_LIMIT` → `SahmkEntitlementError`
  (non-retryable) -- confirmed shape from SDK docs; not re-confirmed
  live against the new Starter key this session (see above).
- `429` → retried, see above; `SahmkRateLimitError` if exhausted.
- Any other non-2xx → `SahmkRequestError`, with the raw response body
  attached -- never silently swallowed.
- A 200 response missing a field this integration requires →
  `SahmkResponseValidationError` -- never fabricated. `/financials/`'s
  exact field names are UNVERIFIED (no source enumerates them), so
  `SahmkMarketDataService.get_financials()` tries several plausible
  key names per field before giving up, and always keeps the untouched
  raw response alongside the parsed one.

## Automatic live/synthetic selection

Two parallel, identically-designed selectors, one per provider family:

- `src/market_data/provider_factory.get_market_data_provider()` →
  `IMarketDataProvider` (quotes/OHLCV/index/news).
- `src/market_data/fundamental_provider_factory.get_fundamental_data_provider()`
  → `IFundamentalDataProvider` (financials/dividends).

Both follow the same policy:

1. `MARKET_DATA_PROVIDER=dev` forces the synthetic `Dev*Provider`
   regardless of credentials.
2. Otherwise, if `SAHMK_API_KEY` is not configured, the synthetic
   provider is used (no live call is ever attempted without a key).
3. Otherwise, the SAHMK provider's `authenticate()` is probed with a
   short timeout (`SAHMK_PROBE_TIMEOUT_SECONDS`, default 5s). Reachable
   + accepted (including valid-but-plan-limited) → the live provider.
   Any connectivity failure, auth rejection, or timeout → the synthetic
   provider, logged clearly -- exactly what happened in this session.
4. Selection is cached (`MARKET_DATA_PROVIDER_CACHE_SECONDS`, default
   60s) so a tight loop doesn't re-probe on every call.

`GET /market-data/status` (main.py) reports both selections' current
provider and health at runtime, without ever exposing the key.

This means the exact same deployment automatically uses synthetic data
in this network-restricted sandbox today, and automatically switches to
live SAHMK data the moment it runs somewhere with real network access
to `sahmk.sa` -- no code change and no manual flag required.

## Live verification outside this sandbox

`.github/workflows/sahmk-live-verification.yml` (manual `workflow_dispatch`
only) runs on a GitHub-hosted runner, which has no egress restriction
to `app.sahmk.sa` -- the exact blocker described above. It now runs
three scripts in sequence against symbol `2222` (Saudi Aramco):

1. `scripts/verify_sahmk_live.py` -- four layers: DNS/TLS reachability,
   a raw direct HTTP call, a call through the real
   `SahmkClient`/`SahmkMarketDataService` (no mocking), and a real
   historical-data fetch through the real `TechnicalAnalysisEngine` and
   `RecommendationEngine`, ending in one of 8 named diagnoses (see
   `scripts/sahmk_live_diagnosis.py`).
2. `scripts/verify_sahmk_endpoint_coverage.py` -- a full sweep of every
   remaining `SahmkClient` method (market summary, company profile,
   company directory, financials, dividends) plus a rate-limit probe.
3. `scripts/verify_sahmk_historical_deep_dive.py` -- a byte-level
   schema/type/chronology/timezone audit of the raw `/historical/`
   response, bypassing `SahmkMarketDataService` entirely, plus live
   SMA/RSI/MACD computed directly from the raw closes.

**This has now actually been run** (workflow runs `30302024204` and
`30303216761`, both `conclusion: success`). Confirmed live results as
of 2026-07-27:

- Authentication, DNS/TLS, and every endpoint below returned real 200
  responses with the current key -- no 401/403 seen anywhere.
- Real quote fields: `ask, ask_size, bid, bid_size, change,
  change_percent, high, is_delayed, liquidity, low, name, name_en,
  open, previous_close, price, symbol, updated_at, value, volume`.
  **The quote timestamp field is `updated_at`, not `timestamp`** --
  `SahmkMarketDataService.get_latest_quote` read the wrong key until
  this was fixed (see Known gaps history below).
- Real `/historical/{symbol}/` top-level fields: `count, data, from,
  interval, is_final, is_intraday, latest_bar_at, partial, source,
  symbol, to`. **The bar array is under `data`, not `bars`.** Each bar
  has exactly `open, high, low, close, volume, date, adjusted_close,
  turnover` -- `date` is an ISO8601 **date-only** string (`"2026-01-28"`,
  no time component), ascending oldest-to-newest, every field present
  on all 118 bars returned for a 180-day range. `SahmkMarketDataService
  .get_historical_bars` read the wrong top-level key (`bars`) and the
  wrong per-bar key (`timestamp` instead of `date`) until fixed -- see
  below.
- `get_market_summary` top-level fields include a real `timestamp` key
  (unlike the quote endpoint) -- `get_index_snapshot`'s existing
  `data.get("timestamp")` was already correct and needed no change.
- 5 rapid sequential `get_quote` calls: no throttling observed.
- `get_events` (Pro-tier) has not yet been exercised live.

**Fixed as of this revision** (`src/market_data/sahmk/service.py`):
`get_latest_quote` now reads `updated_at`; `get_historical_bars` now
reads the top-level `data` key and each bar's `date` key. Both were
verified against the real API response shown above, not guessed.

## Known gaps -- still open

1. `get_events` (Pro-tier) -- plan/entitlement access not yet confirmed
   live.
2. Exact `/financials/{symbol}/` **nested** field names (inside
   `balance_sheets`/`cash_flows`/`income_statements`) -- the top-level
   envelope is confirmed live, but `get_financials()`'s defensive
   multi-name parsing per line-item has not been checked against the
   real nested structure the way `/historical/` and `/quote/` now have
   been.
3. `adjusted_close` and `turnover`, present on every real historical
   bar, are not currently modeled by `SahmkHistoricalBar` -- confirmed
   available, not yet consumed.
4. Full per-plan-tier rate-limit numbers for Starter -- 5 rapid calls
   showed no throttling, but the real ceiling is still unconfirmed.
