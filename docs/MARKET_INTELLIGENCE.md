# Autonomous Market Intelligence Layer

This document describes the Autonomous Market Intelligence Layer
milestone: how it continuously discovers opportunities across the
entire tracked symbol universe without a user selecting a stock, its
architecture, its REST API, its scheduler, and — explicitly — what has
and has not been verified.

No claim in this document should be read as "production ready," "fully
complete," or "profitable." This document does not use those phrases as
characterizations of the platform, and none of the numbers/rankings/
alerts this layer can produce should be read as a claim about live
market performance — see "What was live-verified vs. mock-tested"
below.

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  REST layer (src/api/routes/market.py)                            │
│  POST /scan creates a MarketScanRun row + schedules a               │
│  BackgroundTask; every GET reads already-persisted state.           │
└──────────────────────┬────────────────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ src/market_intelligence/services/scan_job_runner.run_market_scan_job │
│ (same shape as backtesting/job_runner.py: retry a transient DB      │
│  failure, never let an exception escape, always record the outcome) │
└──────────────────────┬────────────────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ src/market_intelligence/market_engine.MarketIntelligenceEngine       │
│  1. SymbolSelector.select()      -- every active, price-eligible     │
│                                      Stock row                        │
│  2. MarketScanner.scan()          -- per symbol, reused pipeline      │
│  3. SectorAnalyzer.analyze()      -- vs. the previous scan's          │
│                                      persisted sector averages        │
│  4. ChangeDetector.detect()       -- vs. the previous scan's          │
│                                      persisted SymbolIntelligenceRecords │
│  5. AlertEngine.generate()        -- Alert objects only                │
│  6. MarketIntelligenceRepository  -- persists every result             │
└──────────────────────┬────────────────────────────────────────────┘
                        │ per symbol, reused, unmodified:
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ src.analysis.context_builder.build_analysis_context()               │
│  -> AnalystEngine.analyze()                                          │
│     -> AIDecisionEngine.decide()                                     │
│        -> RecommendationEngine.generate()                            │
│           -> TechnicalAnalysisEngine / FundamentalAnalysisEngine     │
└──────────────────────────────────────────────────────────────────┘
```

Every read route (`/summary`, `/rankings`, `/watchlists`, `/sectors`,
`/changes`, `/alerts`) reconstructs `SymbolScanOutcome`s from the
persisted `SymbolIntelligenceRecord` rows for a given scan (via
`src.market_intelligence.read_model.outcome_from_record`) and hands
them to the *exact same* `RankingEngine`/`WatchlistEngine`/
`MarketSnapshotBuilder` the scan itself used — no ranking, watchlist,
or sentiment rule is duplicated between the write path and the read
path.

### What is reused unmodified

`TechnicalAnalysisEngine`, `FundamentalAnalysisEngine`,
`RecommendationEngine`, `AIDecisionEngine`, and `AnalystEngine` are
called exactly as `/analyst-report` already calls them, once per
symbol. No score, target price, confidence value, or narrative is
computed anywhere in `src/market_intelligence/`.

One refactor, not a duplication, was necessary to make this possible:
`src/api/routes/stocks.py`'s private `_build_analysis_context` (shared
by `/recommendation`, `/decision`, `/analyst-report`) was extracted,
unchanged in behavior, into the public
`src.analysis.context_builder.build_analysis_context()` — `stocks.py`
now calls that shared function, and so does
`src.market_intelligence.scanner.MarketScanner`. This was verified to
be a pure, behavior-preserving move: every existing `/recommendation`,
`/decision`, and `/analyst-report` test still passes unchanged.

## 2. The eleven modules

| Module | File | Responsibility |
|---|---|---|
| `SymbolSelector` | `symbol_selector.py` | Resolves "every listed Saudi stock" to a concrete symbol list from already-ingested `Stock`/`PriceBar` rows. |
| `MarketScanner` | `scanner.py` | Runs the reused pipeline per symbol with bounded concurrency and per-symbol retry. |
| `RankingEngine` | `ranking.py` | The 17 requested ranking categories, via declarative filter/sort rules over `SymbolScanOutcome`. |
| `WatchlistEngine` | `watchlist.py` | The 9 requested watchlists, via declarative predicate rules. |
| `SectorAnalyzer` | `sector_analysis.py` | Per-sector aggregates, strongest/weakest, momentum, rotation, breadth. |
| `ChangeDetector` | `change_detector.py` | Diffs one scan against the previous one's persisted records. |
| `AlertEngine` | `alert_engine.py` | Produces `Alert` objects only -- no notification/delivery mechanism. |
| `MarketSnapshotBuilder` | `market_snapshot.py` | Market-wide sentiment: bull/bear ratio, average confidence/recommendation, strongest/weakest sectors. |
| `MarketIntelligenceScheduler` | `scheduler.py` | Replaceable recurring-scan abstraction (`IMarketIntelligenceScheduler` interface, one concrete `IntervalMarketIntelligenceScheduler`). |
| `MarketIntelligenceEngine` | `market_engine.py` | Top-level orchestrator tying every module above together. |
| `MarketIntelligenceRepository` | `repositories/market_intelligence_repository.py` | The only module that reads/writes this layer's domain tables. |

`types.py` holds every shared dataclass/enum; `config.py` holds every
env-var-configurable threshold/limit; `ordinals.py` holds the
`Recommendation`/`RiskLevel` orderings `ranking.py` and `alert_engine.py`
both need, defined once; `read_model.py` reconstructs a
`SymbolScanOutcome` from a persisted row for the read routes;
`services/scan_job_runner.py` runs one scan to completion in the
background.

## 3. Rankings, watchlists, and sectors: what is persisted vs. computed on read

**Persisted** (durable, one row per scan): `MarketScanRun` (scan
history), `SymbolIntelligenceRecord` (one row per symbol per scan —
the market snapshot granular data and this layer's single source of
truth), `SectorIntelligenceSummary` (needed for momentum's t-1
comparison), `MarketAlert`, `MarketChangeEvent`.

**Computed on read, never persisted as their own tables**: the 17
rankings and 9 watchlists. They carry zero information beyond what
`SymbolIntelligenceRecord` already stores — persisting them separately
would only be a stale-prone cache of the same data, not a second
source of truth. This is a deliberate architecture choice, not an
omission: it keeps exactly one place (`SymbolIntelligenceRecord`)
that can ever disagree with what a ranking or watchlist actually
contains.

## 4. Change detection and alerts

`ChangeDetector.detect()` compares the current scan's outcomes against
the previous scan's persisted `SymbolIntelligenceRecord` rows and
produces `ChangeEvent`s for: `RECOMMENDATION_CHANGE`,
`CONFIDENCE_CHANGE`, `SCORE_CHANGE`, `TARGET_PRICE_CHANGE`,
`RISK_CHANGE`, `TECHNICAL_CHANGE`, `FUNDAMENTAL_CHANGE` — each gated by
a configurable minimum-delta threshold so routine noise isn't reported
as a change.

`AlertEngine.generate()` reads those events (plus sector summaries) and
produces `Alert` objects for: `NEW_STRONG_BUY`,
`RECOMMENDATION_UPGRADED`/`DOWNGRADED`, `CONFIDENCE_ABOVE_THRESHOLD`,
`TARGET_REACHED`, `RISK_SPIKE` (risk worsening *and* a paired
confidence drop — a risk-level change alone can be routine),
`SECTOR_ROTATION`. **Generation only** — there is no notification or
delivery mechanism (email, push, webhook, SMS) anywhere in this
codebase. Building one is explicitly out of scope for this milestone.

## 5. REST API

All under `/api/v1/market`:

| Method | Path | Purpose |
|---|---|---|
| POST | `/scan` | Creates a `MarketScanRun` and schedules it as a background task; never scans inline. |
| GET | `/scan/{run_id}` | Poll a scan's status/progress. |
| GET | `/summary` | Market-wide sentiment snapshot for the latest (or a specific `run_id`) scan. |
| GET | `/rankings` | All 17 ranking lists (optional `category` filter). |
| GET | `/top-buy` | Convenience wrapper for the `TOP_BUY` ranking. |
| GET | `/top-strong-buy` | Convenience wrapper for the `TOP_STRONG_BUY` ranking. |
| GET | `/watchlists` | All 9 watchlists (optional `category` filter). |
| GET | `/sectors` | Per-sector summaries for a scan. |
| GET | `/changes` | Paginated change-event log (optional `run_id` filter). |
| GET | `/alerts` | Paginated alert log (optional `severity`/`alert_type` filters). |

Every read route defaults to the latest *successful* `MarketScanRun`
when `run_id` is omitted, and returns 404 `no_market_scan_data` if none
exists yet — the same "legitimate not-yet state, not a server failure"
discipline `/recommendation`/`/decision` already apply to insufficient
per-symbol data, applied here to "no scan has ever completed."

## 6. Scheduler

`IntervalMarketIntelligenceScheduler` mirrors
`src.market_data.ingestion.scheduler.IngestionScheduler`'s design: one
`asyncio.Task`, "run then sleep(interval)," so a slow scan can never
overlap itself. Supported intervals: every minute, every 5 minutes,
hourly, daily, weekly (`MARKET_INTELLIGENCE_SCAN_INTERVAL`). **Disabled
by default** (`MARKET_INTELLIGENCE_SCHEDULER_ENABLED=false`) — an
unattended, recurring full-market scan is real workload an operator
must opt into, the same secure-by-default posture
`INGESTION_SCHEDULER_ENABLED` already uses. "The scheduler must be
replaceable": any future implementation only needs to satisfy the
three-member `IMarketIntelligenceScheduler` protocol (`start`, `stop`,
`is_running`) to be a drop-in replacement in `main.py`'s startup/
shutdown wiring.

## 7. Known limitations (disclosed)

- **No real parallel scanning is exercised.** `MarketScanner` is
  architected for it (a bounded `asyncio.Semaphore`, each concurrent
  task opening its own DB session), but `MARKET_SCAN_BATCH_SIZE`
  defaults to 1 (sequential) and no test in this milestone runs it
  above 1 against a real multi-connection DB pool.
- **`new_symbols`/`removed_symbols` are not persisted separately from
  the change-event log.** A GET route reading a past scan's rankings
  therefore reconstructs `NEW_OPPORTUNITIES` from `RECOMMENDATION_CHANGE`
  events alone (a symbol upgraded into BUY/STRONG_BUY territory) — it
  cannot also see "a brand-new symbol first appeared already rated
  BUY," which only the original scan's own in-memory `ChangeDetectionResult`
  knew. A small, disclosed gap between the live-scan path and the
  read-a-past-scan path.
- **`REMOVED_OPPORTUNITIES` means "a symbol's recommendation dropped
  out of BUY/STRONG_BUY territory,"** not "a symbol vanished from the
  universe" — a deliberate interpretation, since a full-market scan's
  universe rarely changes scan-to-scan and the recommendation-based
  reading is the more useful product signal.
- **No corporate-action price adjustment, no true portfolio/position-
  sizing model** — the same disclosed gaps `docs/BACKTESTING_AND_
  CALIBRATION.md` already documents for the engines this layer reuses,
  inherited unchanged.
- **Sector breadth/momentum/rotation are per-scan aggregates only**,
  not a TASI-index-relative measure (no broad-market index history is
  ingested — `MarketSnapshot`, this codebase's TASI-index model,
  remains unpopulated, same as before this milestone).
- **The suggested `src/market_intelligence/schemas/` subpackage was
  intentionally not created.** REST schemas live in
  `src/api/schemas/market_intelligence.py`, matching the location of
  every other REST schema module in this codebase
  (`stocks.py`, `backtesting.py`) — a convention-adherence choice, not
  an omission.

## 8. What was live-verified vs. what was only mock/synthetic-tested

**Live-verified: nothing in this milestone.** As with every prior
milestone, this sandbox has no network access to SAHMK. Every test
(`tests/unit/market_intelligence/`, `tests/integration/api/
test_market_routes.py`) runs against hand-built fixtures or synthetic,
hand-seeded `PriceBar`/`FundamentalSnapshot` data in an in-memory
SQLite database via the Dev* providers. No ranking, watchlist, alert,
or sentiment value produced by any test in this milestone is a claim
about real market behavior — every example is illustrative of the
*mechanism* working correctly on invented data.

**What is real, tested code, regardless of data source:** every
ranking/watchlist rule, sector aggregation, change-detection diff,
alert-generation rule, the scan lifecycle (PENDING → RUNNING →
SUCCESS/FAILED, with retry on transient failure), the REST layer's
graceful defaults and 404 handling, the scheduler's start/stop
lifecycle, and the migration chain (verified via the existing
`tests/integration/test_migrations.py` upgrade/downgrade/re-upgrade
round trip, now covering the new tables too).

## 9. Tests

- **90 unit tests** under `tests/unit/market_intelligence/` (one file
  per module, hand-built fixtures via `_fixtures.py`, plus 12
  dedicated repository tests against real in-memory SQLite).
- **3 unit tests** for the extracted `build_analysis_context`
  (`tests/unit/analysis/test_context_builder.py`).
- **10 integration tests** under `tests/integration/api/
  test_market_routes.py` — real FastAPI routing, a real background-
  task scan (`POST /scan` → poll `/scan/{run_id}` → read every GET
  route), category filters, explicit `run_id` selection, 404s, and a
  credential-leak check.
- **1720 tests pass, 12 skipped, repo-wide** (up from 1617 at the end
  of the Autonomous AI Analyst Framework milestone). `flake8 src/
  tests/ main.py` is clean at 0 violations.

No claim in this document should be read as "production ready," "fully
complete," or "100% accurate" — none of those are accurate
characterizations, and this document does not use those phrases as
characterizations of the platform.
