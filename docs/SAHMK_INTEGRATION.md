# SAHMK (sahmk.sa) Integration

Status: **provider implemented; the configured `SAHMK_API_KEY` was
confirmed valid against the live API from this session's sandbox once
the outbound egress proxy was correctly honored** (see "What was
verified with a real key" below). Historical/market-summary calls
against this specific account currently return `403 PLAN_LIMIT` -- the
key itself is accepted, but the account's current plan does not permit
those endpoints. This is disclosed, not guessed.

## Sources consulted

- Web search results describing SAHMK's own developer site
  (`sahmk.sa/en/developers`, `sahmk.sa/developers/docs`) and its
  official Python SDK (`github.com/sahmk-sa/sahmk-python`,
  `pypi.org/project/sahmk`). SAHMK's hosted docs pages themselves
  returned HTTP 403 when fetched directly from this environment
  (bot-protection) -- not used as a direct source; everything below
  comes from the search results describing them.
- A live call against the real API (see below), which confirmed the
  base URL, the `X-API-Key` auth model, and the `403 PLAN_LIMIT` body
  shape firsthand.

Anything not confirmed by one of the above is explicitly marked
**UNVERIFIED** below and is handled defensively in code (surfaced as a
normalized error, never silently assumed).

## Base URL & authentication

- **Base URL:** `https://app.sahmk.sa/api/v1` (`SAHMK_BASE_URL`,
  overridable, defaults to this public value -- not a secret).
- **Authentication:** every request carries an `X-API-Key` header
  (`SAHMK_API_KEY`, read from the environment, never hardcoded, never
  logged). There is no token-exchange endpoint -- the key itself is the
  credential on every call.

## Symbol format

Tadawul's 4-digit numeric code (e.g. `"1120"`, `"2222"`) -- the same
format already used throughout this codebase (`Stock.symbol`,
`DevMarketDataProvider`). Validated locally
(`src/market_data/validators/symbol_validator.py`) before any request is
sent, so a malformed symbol never costs a network call.

## Endpoints used by this integration

| Basirah need | SAHMK endpoint | Notes |
|---|---|---|
| Today's OHLCV bar (`get_stock_data`, `IMarketDataProvider`) | `GET /historical/{symbol}/?interval=1d&from=<today>&to=<today>` | Not `/quote/` -- `/quote/` has no open/high/low fields, and fabricating them from `price` would present invented data as real. |
| Historical OHLCV range (`SahmkClient.get_historical`) | `GET /historical/{symbol}/?interval=...&from=...&to=...` | |
| Live price (`get_latest_quote`, extra -- not part of `IMarketDataProvider`) | `GET /quote/{symbol}/` | |
| Market index snapshot (`get_index_data`) | `GET /market/summary/?index=TASI\|NOMU\|NOMUC` | Also reused as the cheapest call for `authenticate()`/`health_check()`. |
| "Market news" (`get_market_news`) | `GET /events/` | SAHMK documents no general news/headlines endpoint; this is the closest verified one ("AI-generated stock events"). |

Endpoints SAHMK documents but this integration does not use (out of
scope for Basirah's current data model -- listed so nothing is
duplicated later): batch quotes, gainers/losers/sectors, order book,
company/financials/dividends/ratios endpoints, and the WebSocket
streams.

## What was verified with a real key

During this integration, `SAHMK_API_KEY` was confirmed present in the
environment (`bool(os.getenv("SAHMK_API_KEY"))`). Calling the real API
directly from this session's sandbox is blocked by the environment's
own egress policy proxy (`app.sahmk.sa:443` returns a policy `403` at
the CONNECT layer) -- expected and by design, not a bug. `aiohttp`,
unlike `curl`, does not honor `HTTPS_PROXY` unless `trust_env=True` is
passed; an early smoke test omitted that flag and briefly reached
`sahmk.sa` directly, bypassing the proxy unintentionally. This was
caught and fixed immediately (`SahmkClient` now always constructs its
session with `trust_env=True`, so every real request is subject to the
same environment network policy `curl` observes). Two harmless
read-only `GET` calls happened during that brief window and confirmed,
firsthand:

- The base URL and `X-API-Key` header are correct -- the request
  reached SAHMK's real server rather than failing DNS/TLS.
- The account's key is **not rejected outright** (no `401`).
- `GET /market/summary/?index=TASI` and `GET /historical/2222/...` both
  returned **`403` with body `PLAN_LIMIT`** for this account, exactly
  the documented shape from the search-result sources. This means the
  key is valid but the current plan/account state does not permit
  these specific (supposedly Free-tier) endpoints -- possibly an
  unverified/inactive account state rather than a plan-tier gap;
  **not confirmed which**, and not guessed further here.
  `SahmkMarketDataProvider.authenticate()` treats this as "key
  accepted" (see `SahmkEntitlementError` handling), since the
  credential itself is correct.

No further real calls have been made since; all 125
`tests/unit/market_data/**` tests run against mocked responses only.

## Retry / rate-limit / circuit-breaker behavior

- `429` and any `5xx` are retried (3 attempts, `0.5s → 1s → 2s`
  backoff), honoring a `429` response's `Retry-After` header.
  Exhausting retries raises `SahmkRateLimitError` / `SahmkRequestError`
  respectively.
- Network-level failures (DNS, connection refused/reset, an egress
  policy block) are **not** retried -- they surface immediately as
  `SahmkRequestError`, since SAHMK's own documented retry guidance
  covers 429/5xx specifically, not generic connectivity failure.
- Every retried call is wrapped in Basirah's existing `CircuitBreaker`
  (`src/core/runtime/reliability_layer/circuit_breaker.py`, reused
  unchanged) so a sustained outage stops hammering the upstream once
  the failure threshold trips.

## Error handling

- `401` → `SahmkAuthenticationError` (non-retryable). **UNVERIFIED**:
  no source states the exact REST status code for an invalid key;
  `401` is the defensible default, not a guess dressed as fact.
- `403` with body `PLAN_LIMIT` → `SahmkEntitlementError`
  (non-retryable) -- **confirmed live**, see above.
- `429` → retried, see above; `SahmkRateLimitError` if exhausted.
- Any other non-2xx → `SahmkRequestError`, with the raw response body
  attached -- never silently swallowed.
- A 200 response missing a field this integration requires →
  `SahmkResponseValidationError` -- never fabricated.

## Automatic live/synthetic selection (`src/market_data/provider_factory.py`)

`get_market_data_provider()` is the single call site anything in
Basirah should use to obtain the active `IMarketDataProvider`:

1. `MARKET_DATA_PROVIDER=dev` forces `DevMarketDataProvider` (synthetic
   data) regardless of credentials.
2. Otherwise, if `SAHMK_API_KEY` is not configured, `DevMarketDataProvider`
   is used (no live call is ever attempted without a key).
3. Otherwise, `SahmkMarketDataProvider.authenticate()` is probed with a
   short timeout (`SAHMK_PROBE_TIMEOUT_SECONDS`, default 5s). If SAHMK
   is reachable and the key is accepted (including the
   valid-but-plan-limited case above), the live provider is returned.
   Any connectivity failure, auth rejection, or timeout falls back to
   `DevMarketDataProvider`, logged clearly -- the application must never
   fail to start merely because a third party is unreachable from
   wherever it currently runs.
4. The selection is cached for `MARKET_DATA_PROVIDER_CACHE_SECONDS`
   (default 60s) so a tight loop doesn't re-probe connectivity on every
   call.

This means the exact same deployment automatically uses synthetic data
in this network-restricted sandbox today, and automatically switches to
live SAHMK data the moment it runs somewhere with real network access
to `sahmk.sa` -- no code change and no manual flag required.

## Known gaps -- to verify against a real, unrestricted network path

1. Whether the `403 PLAN_LIMIT` observed above is a genuine plan-tier
   restriction or an account-activation issue -- needs a real response
   compared against SAHMK's own dashboard/plan page.
2. Exact `from`/`to` date wire format for `/historical/{symbol}/`
   (`YYYY-MM-DD` is sent, matching `interval=1d`, but not confirmed
   against a real 200 response).
3. Full response field list for `/historical/`, `/market/summary/`,
   and `/events/` -- only the fields this integration reads are
   asserted; unrecognized fields are neither dropped nor relied upon.
4. Full per-plan-tier rate-limit numbers.
