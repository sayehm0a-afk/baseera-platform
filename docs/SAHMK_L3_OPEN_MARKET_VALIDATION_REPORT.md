# Basirah — L3 Open-Market Live Validation Report

**Status: real evidence gathered against the live Saudi Exchange (Tadawul)
during an actual open trading session. Not a full production sign-off** --
several concrete gaps are documented below, discovered specifically
*because* this run happened during live market hours (they did not surface
in the earlier, market-closed L2 runs).

## Run identification

| Field | Value |
|---|---|
| Branch | `feature/sahmk-live-verification` |
| Commit (evidence run) | `4a438caef25e0d23926b384e7e5f21915396426a` |
| Workflow | `.github/workflows/sahmk-live-pipeline-validation.yml` |
| Workflow run ID (primary, enriched output) | [`30433534477`](https://github.com/sayehm0a-afk/baseera-platform/actions/runs/30433534477) -- `conclusion: success` |
| Workflow run ID (corroborating, pre-enrichment) | [`30432936823`](https://github.com/sayehm0a-afk/baseera-platform/actions/runs/30432936823) -- `conclusion: success` |
| Start (AST) | 2026-07-29 10:56:37 (07:56:37 UTC) |
| End (AST) | 2026-07-29 10:59:41 (07:59:41 UTC) |
| Market status at dispatch | **OPEN** -- confirmed via `is_market_open()` against the real system clock before dispatching, and again inside the running job (`is_market_open() at soak start: True`, `Tadawul local now: 2026-07-29T10:58:37+03:00`) |
| Symbols | `2222` (Saudi Aramco), `2010` (SABIC), `1120` (Al Rajhi Bank), `7010` (STC), `1180` (Al Inma Bank) |

## Objective-by-objective verdict

| # | Objective | Verdict | Evidence |
|---|---|---|---|
| 1 | Market open confirmed via real trading-calendar logic + actual AST time | **VERIFIED** | `is_market_open()` returned `True` both locally before dispatch and inside the workflow, against the real system clock, matching Tadawul's published Sun-Thu 10:00-15:00 AST hours |
| 2 | Dispatch existing workflow against `feature/sahmk-live-verification` | **VERIFIED** | Run `30433534477`, `head_branch: feature/sahmk-live-verification`, `head_sha: 4a438ca...` |
| 3 | Live Market Mode enters active/open-market state | **VERIFIED** | `market_open_at_start: True`, `observed_open_after_ticks: True` |
| 4 | Ingestion + market-intelligence schedulers start automatically while open | **VERIFIED** | `inner_ingestion_was_running: True`, `inner_scan_was_running: True` -- both started by `LiveMarketModeScheduler` with no manual trigger |
| 5 | Real SAHMK data ingestion during the open session | **PARTIALLY VERIFIED** | Symbols/OHLCV/dividends real and confirmed (below); fundamentals genuinely failed (Known Gap, below); "current quote timestamp" and "current market price" were **not populated** this run for a newly-confirmed, real reason (see Finding A below) -- not fabricated, left `None` |
| 6 | Full market scan + AI decision pipeline | **VERIFIED** | `MarketScanRun 1: status=SUCCESS succeeded=5 skipped=0 failed=0 duration=54.7s`, real `AnalystEngine -> AIDecisionEngine` execution |
| 7 | Capture every real recommendation with the full requested field set | **PARTIALLY VERIFIED** | See recommendation table below -- most fields real and captured; `company name` and `market_price_at_evaluation` are real but **empty/placeholder** for a confirmed, documented reason (Findings A and B) |
| 8 | Ranked opportunity outputs | **PARTIALLY VERIFIED** | 6 of 8 lists built from real data below; 2 (strongest-fundamental, best-medium/long-term) are honestly empty because the underlying data doesn't exist this run (fundamentals failed; no MEDIUM/LONG_TERM recommendation was generated) |
| 9 | Database persistence (stored, no duplicates, correct timestamps, provider=live, tracking rows created) | **PARTIALLY VERIFIED** | All of these hold **within the workflow run** (see integrity checks below); "records remain available after the workflow completes" is **NOT VERIFIED** -- see Finding C (ephemeral CI database) |
| 10 | Live Market Mode: active while open, schedulers running, cadence respected, no duplicate concurrent schedulers, no leaks, health endpoint reports real state | **VERIFIED** (soak-window scope) | `inner_schedulers_stopped_cleanly: True`, `no_leaked_tasks: True` (task count 1 before and after); "cadence respected" verified only within the single 60s soak window (one scheduled cycle observed, not multiple cycles over hours) |
| 11 | Frontend verification against the real live backend | **NOT VERIFIED** | See Finding D -- confirmed structurally infeasible from this sandbox, not attempted with synthetic substitutes |
| 12 | Post-close: Live Market Mode stops/idles, schedulers stop safely, recommendations persist, no data deleted | **PARTIALLY VERIFIED** | The "stays idle when closed" behavior was verified in a **separate, earlier run** (`30359750520`, 2026-07-28, dispatched after that day's close). This run (today) did not run long enough to observe today's own open-to-close transition -- doing so would require a multi-hour-running job, not attempted |
| 13 | Every item marked VERIFIED / PARTIALLY VERIFIED / FAILED / NOT VERIFIED with direct evidence, nothing claimed without it | **Applied throughout this report** | -- |
| 14 | On failure: stop that path, find root cause, no synthetic substitution | **Applied** | See Findings A, B, D below -- each is a real root cause, not worked around |
| 15 | Final evidence-based report | **This document** | -- |
| 16 | Update docs, commit, push to `feature/sahmk-live-verification`, no merge to `main` | **Done** | See commit referenced in this file's own history |

## Complete recommendation table (real, from the live 10:58 AST scan)

All 5 symbols scored successfully. Both the manual scan (Step 5b/6) and the
automatically-triggered Live Market Mode scan (Step 9b, ~1 minute later,
same ingested data) produced identical decisions -- expected, since no new
OHLCV was ingested between the two scans and the quote leg returned no data
either time (Finding A).

| DB ID | Symbol | Recommendation | Confidence | Total Score | Technical Score | Fundamental Score | Target | Stop | Risk | Time Horizon | Position Size |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | 1120 | SELL | 49.0% | 28.9 | 0.00 | *(none)* | 62.80 | 66.07 | MEDIUM | SHORT_TERM | MODERATE |
| 2 | 1180 | BUY | 67.0% | 61.0 | 72.00 | *(none)* | 39.76 | 38.31 | MEDIUM | SHORT_TERM | STANDARD |
| 3 | 2010 | HOLD | 73.0% | 46.1 | 46.00 | *(none)* | 51.71 | 53.37 | MEDIUM | SHORT_TERM | NONE |
| 4 | 2222 | HOLD | 67.0% | 52.1 | 66.00 | *(none)* | 26.51 | 26.12 | MEDIUM | SHORT_TERM | NONE |
| 5 | 7010 | SELL | 55.0% | 28.9 | 0.00 | *(none)* | 43.52 | 44.08 | MEDIUM | SHORT_TERM | MODERATE |
| 6-10 | *(same 5 symbols)* | *(identical)* | | | | | | | | | *auto-generated by Live Market Mode, ids 6-10* |

Every row: `engine_version=1.0.0`, `source=live_scan`, `evaluated_at` a real
UTC timestamp between 07:57:43 and 07:58:42 on 2026-07-29. `company name`
and `market_price_at_evaluation` are omitted from this table -- see
Findings A and B.

Technical reasoning (real, per symbol, not templated) -- one example each:
- **1120** (SELL): "MACD line (-0.591) is below its signal line (-0.552)
  with a negative histogram -- bearish momentum." / "Supertrend is in a
  bearish state (price below the trend line)."
- **1180** (BUY): "MACD line (0.043) is above its signal line (-0.158)
  with a positive histogram -- bullish momentum." / "Stochastic %K=84.2 is
  overbought (>=80), a bearish reversal signal."
- **2010** (HOLD): "MACD line (-0.651) is above its signal line (-0.802)
  with a positive histogram -- bullish momentum."
- **2222** (HOLD): "MACD line (-0.043) is above its signal line (-0.047)
  with a positive histogram -- bullish momentum." / "Supertrend is in a
  bullish state (price above the trend line)."
- **7010** (SELL): "MACD line (-0.175) is below its signal line (-0.120)
  with a negative histogram -- bearish momentum." / "Supertrend is in a
  bearish state (price below the trend line)."

## Ranked opportunity lists (from the 5 distinct recommendations above)

- **Top buy opportunities**: `1180` (BUY, 67.0% confidence, score 61.0) --
  the only BUY this scan.
- **Top sell/avoid opportunities**: `7010` (SELL, 55.0% confidence) then
  `1120` (SELL, 49.0% confidence) -- both score 28.9.
- **Stocks to watch**: `2010` (HOLD, 73.0% confidence -- highest of any
  symbol this scan) and `2222` (HOLD, 67.0% confidence, technical score
  66.0).
- **Highest-confidence recommendations**: `2010` (73.0%) > `1180` (67.0%)
  = `2222` (67.0%) > `7010` (55.0%) > `1120` (49.0%).
- **Strongest technical opportunities**: `1180` (72.0) > `2222` (66.0) >
  `2010` (46.0) > `1120` = `7010` (0.0).
- **Strongest fundamental opportunities**: **NOT VERIFIED -- no data.**
  `ingest_fundamentals` failed for all 5 symbols this run (Known Gap #2,
  below); every `fundamental_score` is `None`. Not fabricated.
- **Best short-term trading opportunities**: all 5 recommendations came
  back `SHORT_TERM` this scan; `1180` (BUY, 67.0%) is the standout
  actionable one.
- **Best medium/long-term investment opportunities**: **empty -- no
  MEDIUM_TERM or LONG_TERM recommendation was generated this run.** Not
  fabricated with a placeholder entry.

## Database verification

Two full integrity passes ran this workflow -- once after the manual scan
(5 rows), once after the Live Market Mode soak added 5 more (10 rows):

| Check | After manual scan | After soak (full set) |
|---|---|---|
| Total snapshots | 5 | 10 |
| No duplicates ((symbol, evaluated_at) distinct) | True | True |
| NULL critical fields | 0 | 0 |
| Orphaned stock FK | 0 | 0 |
| PENDING outcome rows | 35 (5 x 7 horizons) | 70 (10 x 7 horizons) |
| Expected PENDING outcome rows | 35 | 70 |
| **INTEGRITY CHECK** | **PASSED** | **PASSED** |

"Provider is SAHMK/live": confirmed at the source, not inferred --
`Market data provider selected: 'sahmk'` / `Fundamental data provider
selected: 'sahmk'`, both from the hard gate that aborts the entire run
rather than proceeding on a silent `DevMarketDataProvider` fallback.

"Records remain available after the workflow completes": **NOT
VERIFIED** -- see Finding C.

## Live Market Mode verification

| Signal | Value |
|---|---|
| `market_open_at_start` | `True` |
| `observed_open_after_ticks` | `True` |
| `inner_ingestion_was_running` | `True` |
| `inner_scan_was_running` | `True` |
| New snapshots from the automatic scan | 5 (ids 6-10, full detail captured, matches the manual scan's 5) |
| `inner_schedulers_stopped_cleanly` | `True` |
| Task count before soak / after stop | 1 / 1 -- `no_leaked_tasks: True` |
| Post-soak integrity (full 10-row set) | PASSED |

This is the first real evidence of `LiveMarketModeScheduler` autonomously
starting its inner `IngestionScheduler` and `IntervalMarketIntelligenceScheduler`
against the live system clock during an actual Tadawul session -- not a
unit test with an injected clock (see `tests/unit/market_intelligence/test_live_market_mode.py`
for those), a real run.

## Frontend verification -- NOT VERIFIED

Not attempted with synthetic data, per instruction. Root cause: this
sandbox's egress policy (see `docs/SAHMK_INTEGRATION.md`, L1 sections)
blocks `app.sahmk.sa`, and this session additionally confirmed:

- Raw TCP to PostgreSQL's default port (5432) is blocked at the network
  layer for any external host (`timeout 5 bash -c "echo > /dev/tcp/1.1.1.1/5432"`
  -> blocked), independent of the HTTPS proxy allowlist.
- HTTPS to any non-allowlisted host (tested: `google.com`, `neon.tech`) is
  rejected with `403` at the sandbox's proxy, identically to `app.sahmk.sa`.

There is therefore no path in this sandbox to point a locally-run frontend
+ backend at data this workflow generated: the CI job's PostgreSQL is an
ephemeral service container (destroyed at job end, see Finding C below),
and no persistent, externally-reachable database this sandbox could connect
to is provisioned or reachable. Frontend validation against real data would
require either running the frontend build/serve/Playwright steps *inside*
GitHub Actions (a new, larger workflow, not attempted here) or provisioning
a persistent database this sandbox can actually reach (also not attempted --
would need real infrastructure/credentials this session does not have).

## Findings discovered specifically by this open-market run

### Finding A -- "current market price" / "current quote timestamp" are `None` during live trading hours

`market_price_at_evaluation` was `None` on every row this run, both the
manual and the automatic scan. Root cause traced precisely (not guessed):

`SahmkMarketDataProvider.get_stock_data()` (`src/market_data/providers/sahmk_market_data_provider.py:86-101`)
deliberately sources "current price" from **today's completed daily bar**
via `/historical/{symbol}/` ("not `/quote/`, which has no open/high/low
fields" -- its own docstring), calling
`SahmkMarketDataService.get_daily_bar(symbol)` which defaults to
`target_day = today` and **raises** `SahmkResponseValidationError` if no
bar exists yet for that exact date
(`src/market_data/sahmk/service.py:154-164`). Mid-session, before the
trading day settles, SAHMK's historical endpoint has not yet published
today's bar -- so this call fails every time during live hours, is caught
by `context_builder.py`'s `except (SahmkError, CircuitBreakerOpenError)`,
and `latest_price`/`market_price_at_evaluation` stay `None`. This is a
genuine architecture gap, not a schema-name bug like the earlier ones:
the pipeline's live-price leg is structurally unable to return a price
while the market is open, only after close once the day's bar settles.
The dedicated `/quote/` endpoint (which does carry a real intraday price,
already confirmed live -- "200 OK, real price 26.56 SAR" in the L1
connectivity run) is not used by this code path at all.

**Not fixed in this session** (would mean changing `get_stock_data()`'s
data source, real business logic, out of scope for a validation run).
Documented as a new Known Gap below.

### Finding B -- company display names are placeholders, not real SAHMK company names

Every recommendation printed a name like "Stock 1120" rather than the real
company name (e.g. Al Rajhi Bank). Root cause: `sync_symbols()`
(`src/market_data/ingestion/ingest_symbols.py:47-104`), when called with
`discover_all=False` (this validation script's mode, to avoid pulling the
entire Tadawul+Nomu directory just to validate 5 symbols), looks for a
`get_company_profile` method on the provider it's given
(`getattr(provider, "get_company_profile", None)`) to enrich a newly
created `Stock` row's name. **`SahmkMarketDataProvider` does not implement
`get_company_profile`** -- confirmed by grep, no such method exists on that
class or on the `IMarketDataProvider` interface it implements. The
capability exists one layer down, on `SahmkMarketDataService.get_company_profile()`
(already confirmed live-working, "200 OK" in the L1 run), but it is never
surfaced through the adapter `sync_symbols` actually calls. So the
enrichment branch silently never fires, and every newly-created Stock row
keeps its placeholder name from `get_or_create_stock`.

**Not fixed in this session** (same reasoning as Finding A).

### Finding C -- database persistence is confirmed only within a single workflow run

The CI job's PostgreSQL is a `postgres:16` **service container**, created
fresh for each workflow run and destroyed when the job ends (visible in
this run's own logs -- container init, then `docker rm --force` in the
cleanup steps). Every integrity check in this report is real and passed,
but only proves correctness *during* the run. There is no persistent
database in this validation path, so "records remain available after the
workflow completes" cannot be verified as stated and is explicitly marked
NOT VERIFIED above, not silently assumed.

### Finding D -- frontend validation is structurally blocked, not attempted with a workaround

See the Frontend Verification section above.

## Known Gaps -- updated

In addition to the gaps already tracked in `docs/SAHMK_INTEGRATION.md`
(Pro-tier `get_events` unconfirmed; `/financials/` nested field names
confirmed broken for all 5 symbols tested; `adjusted_close`/`turnover` not
modeled; Starter-tier rate limits not fully characterized; Live Market
Mode's open-market auto-trigger -- now resolved, see above):

6. **New**: `get_stock_data()`'s live-price leg (`SahmkMarketDataProvider`)
   only succeeds once today's daily bar settles -- structurally returns no
   price during an open Tadawul session. The already-confirmed-live
   `/quote/` endpoint is not used for this purpose.
7. **New**: `SahmkMarketDataProvider` has no `get_company_profile` method,
   so `sync_symbols(discover_all=False)`'s name/sector enrichment never
   fires for SAHMK; newly-created Stock rows keep placeholder names unless
   `discover_all=True` (which also pulls the entire symbol directory, a
   much larger operation not exercised in this validation).

## Final verdict

**Basirah is not "fully validated against the live Saudi market" in the
complete sense requested.** What is now real, evidence-backed, and
verified:

- Live SAHMK authentication, ingestion, and the full AI decision pipeline
  run correctly against real market data, during a real open trading
  session, producing genuinely differentiated, non-fabricated
  recommendations with full referential/uniqueness database integrity.
- Live Market Mode correctly and automatically activates its ingestion and
  scan schedulers the moment the real market is open, with no leaks and a
  clean stop -- the specific gap the previous (market-closed) validation
  run could not close.

What remains genuinely open, each for a concrete, now-documented reason
rather than an assumption:
- Live intraday price and quote timestamp are not currently captured by
  this pipeline (Finding A).
- Company display names are placeholders (Finding B).
- Persistence beyond a single CI run is unverified (Finding C).
- Frontend validation is untested and structurally blocked in this
  sandbox (Finding D).
- The same-session open-to-close Live Market Mode transition has not been
  observed continuously (only each half separately, on different runs).

None of these were worked around with synthetic data, mocks, or
fabricated values -- each is either `None`/absent in the real captured
evidence, or explicitly marked NOT VERIFIED above.
