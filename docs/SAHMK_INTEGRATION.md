# SAHMK (sahmk.sa) Integration

Status: **provider implemented for every Starter-tier endpoint this
integration needs; live verification is blocked inside this sandbox's
network policy, but has been confirmed for real via GitHub-hosted
runners** -- `.github/workflows/sahmk-live-verification.yml` (see
"Live verification outside this sandbox" below) confirmed quotes,
market summary, company profile/directory, historical bars, and
dividends with real 200 responses, and the two field-name bugs
discovery surfaced there have been fixed. `.github/workflows/sahmk-
live-pipeline-validation.yml` (see "L2: full production pipeline
validated live" below) then ran the entire production pipeline --
ingestion -> a real PostgreSQL database -> the AI decision engine ->
5 real, differentiated recommendations, all integrity-checked -- and
surfaced one remaining real defect: `/financials/{symbol}/`'s nested
field names don't match this integration's parsing for any of the 5
symbols tested (not yet fixed, see Known Gap #2). That same workflow
was then run **during an actual open Tadawul session** (2026-07-29) --
see `docs/SAHMK_L3_OPEN_MARKET_VALIDATION_REPORT.md` for the full,
16-objective evidence-based report. Live Market Mode was confirmed to
autonomously activate its schedulers and generate a second, automatic
batch of real recommendations with the market genuinely open, closing
the one gap the market-closed run couldn't -- but that same open
session also surfaced two new, real gaps (Known Gaps #6 and #7:
current price/quote timestamp not populated during trading hours;
company display names are placeholders), and confirmed frontend
validation is not achievable from this sandbox at all (no reachable
path to bridge CI-generated data to a locally-run frontend/backend).

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

## L2: full production pipeline validated live (2026-07-28)

`.github/workflows/sahmk-live-pipeline-validation.yml` (manual
`workflow_dispatch`, additive to the connectivity workflow above) runs
`scripts/verify_sahmk_live_pipeline.py`: real SAHMK ingestion -> a real
ephemeral PostgreSQL 16 service container -> the unmodified
`AnalystEngine`/`AIDecisionEngine` pipeline -> recommendation storage
-> a real-clock `LiveMarketModeScheduler` soak test. A hard gate
(`_require_live_providers`) aborts the run rather than silently
falling back to `DevMarketDataProvider` if SAHMK is unreachable even
from the runner -- this run passed that gate (`provider selected:
'sahmk'` for both market and fundamental providers).

**Run** `30359750520`, `conclusion: success`, symbols `2222, 2010,
1120, 7010, 1180`:

- `sync_symbols`: 5/5 succeeded.
- `ingest_historical_ohlcv`: 5/5 succeeded, 295 real daily bars
  upserted.
- `ingest_fundamentals`: **0/5 succeeded -- confirms Known Gap #2
  below as an actual live failure, not just an open question.** Every
  one of the 5 symbols returned the identical error: SAHMK's real
  `/financials/{symbol}/` response is missing every field
  `get_financials()` looks for (`revenue`, `net_income`,
  `total_assets`, `total_liabilities`, `total_equity`,
  `current_assets`, `current_liabilities`, `shares_outstanding`,
  `eps`, `fiscal_period_end`), under every alternate name this
  integration tries. The endpoint itself returns 200 (confirmed
  earlier), but the nested statement structure is not what this
  integration assumes -- not yet fixed, since diagnosing the real
  nested shape needs one more live capture of a raw, unparsed
  response, out of scope for this validation run's "verify, don't
  rewrite" mandate.
- `ingest_dividends`: 5/5 succeeded (0 rows -- no dividend records in
  range for these symbols currently, not an error).
- Market scan: `MarketScanRun` `SUCCESS`, 5/5 symbols scored, 0
  skipped, 0 failed, 52.6s.
- **5 real recommendations generated**, genuinely differentiated (not
  hardcoded): `1120` SELL 49.0% conf, `1180` BUY 67.0% conf, `2010`
  HOLD 81.0% conf, `2222` HOLD 61.0% conf, `7010` SELL 59.9% conf --
  each with real technical reasoning (real MACD line/signal values per
  symbol) and real target/stop prices.
- Database integrity: 5 snapshots, 0 duplicates, 0 null critical
  fields, 0 orphaned FKs, 35/35 expected PENDING outcome rows (5 x 7
  horizons) -- PASSED.
- Live Market Mode soak: dispatched at 15:39 Arabia Standard Time --
  after Tadawul's 15:00 close -- so `is_market_open()` correctly read
  `False` against the real clock and the inner ingestion/scan
  schedulers correctly stayed idle for the full 45s soak (0 new
  snapshots, clean stop, no leaked asyncio tasks). This confirms the
  closed-market branch is correct; the open-market "auto-triggers a
  real scan" branch still needs a run dispatched during an actual
  Tadawul session (Sun-Thu 10:00-15:00 AST) to observe directly --
  not yet done.

## Known gaps -- still open

1. `get_events` (Pro-tier) -- plan/entitlement access not yet confirmed
   live.
2. **Confirmed broken as of the L2 run above**: `/financials/{symbol}/`'s
   real nested field names don't match any name `get_financials()`
   tries -- every field, every symbol tested. The top-level envelope
   is fine; the line-item structure inside it needs a raw-response
   capture to diagnose and fix (not done in this validation run).
3. `adjusted_close` and `turnover`, present on every real historical
   bar, are not currently modeled by `SahmkHistoricalBar` -- confirmed
   available, not yet consumed.
4. Full per-plan-tier rate-limit numbers for Starter -- 5 rapid calls
   showed no throttling, but the real ceiling is still unconfirmed.
5. ~~Live Market Mode's "market just opened -> auto-scans" transition
   has not been observed against the real clock yet.~~ **Resolved
   2026-07-29**: observed and verified live during an actual open
   Tadawul session -- see `docs/SAHMK_L3_OPEN_MARKET_VALIDATION_REPORT.md`.
6. **New, confirmed 2026-07-29**: `SahmkMarketDataProvider.get_stock_data()`
   sources "current price" from today's completed daily bar
   (`/historical/`), which does not exist yet while the market is open --
   so `market_price_at_evaluation`/`latest_price` are `None` for every
   live scan run during trading hours. The already-confirmed-live
   `/quote/` endpoint (real intraday price, `updated_at`, bid/ask) is not
   used for this purpose. Not fixed -- see the L3 report for the exact
   code path.
7. **New, confirmed 2026-07-29**: `SahmkMarketDataProvider` has no
   `get_company_profile` method, so `sync_symbols(discover_all=False)`'s
   name/sector enrichment silently never fires for SAHMK -- newly
   ingested Stock rows keep their placeholder name (`"Stock {symbol}"`)
   instead of the real company name, even though
   `SahmkMarketDataService.get_company_profile()` one layer down is
   already confirmed live-working. Not fixed -- see the L3 report.
