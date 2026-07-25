# Backtesting & Calibration Engine

This document describes the Backtesting & Calibration Engine milestone:
how it evaluates Basirah's historical recommendations, how it prevents
look-ahead bias, how walk-forward validation and calibration work, its
REST API, its operational limits, and — explicitly — what has and has
not been verified.

No claim in this document should be read as "production ready," "fully
complete," "profitable," or "100% accurate." This document does not use
those phrases as characterizations of the platform, and none of the
numbers this engine can produce should be read as a claim about live
market performance — see "What was live-verified vs. mock-tested" below.

## 1. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  REST layer (src/api/routes/backtests.py, calibrations.py)      │
│  POST creates a row + schedules a FastAPI BackgroundTask;        │
│  every GET only reads already-persisted state.                  │
└───────────────┬───────────────────────────────┬─────────────────┘
                │                               │
                ▼                               ▼
┌───────────────────────────┐   ┌───────────────────────────────────┐
│ src/backtesting/job_runner │   │ src/backtesting/calibration/engine │
│ run_backtest_job()          │   │ propose/validate/activate/rollback │
└───────────────┬─────────────┘   └───────────────┬─────────────────┘
                │                                  │ (validate() runs
                ▼                                  │  two backtests)
┌─────────────────────────────────────────────────▼─────────────────┐
│ src/backtesting/engine.BacktestingEngine.run()                     │
│ for each symbol × evaluation date:                                 │
│   data_access.load_as_of_dataset()  -- anti-look-ahead read         │
│   strategy.evaluate(dataset)        -- baselines.py                │
│   data_access.load_forward_price_path() -- scores the outcome      │
│   regime.classify_market_regime()                                  │
│   -> RecommendationSnapshot row (upserted, idempotent)              │
└───────────────┬─────────────────────────────────────────────────────┘
                │ consumes, unmodified:
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ TechnicalAnalysisEngine · FundamentalAnalysisEngine ·              │
│ RecommendationEngine · AIDecisionEngine  (all pre-existing,        │
│ reused exactly as built in prior milestones)                       │
└─────────────────────────────────────────────────────────────────┘
                │ reads only already-ingested rows from:
                ▼
┌─────────────────────────────────────────────────────────────────┐
│ PriceBar · FundamentalSnapshot · Dividend · Stock  (via             │
│ ohlcv_loader.load_price_bars / fundamental_loader.load_fundamental_ │
│ snapshots, both already anti-look-ahead-capable)                    │
└─────────────────────────────────────────────────────────────────┘
```

All metrics computation (`src/backtesting/metrics.py`) is pure —
no database, no engine calls — so every formula is independently unit
tested against hand-built fixtures, not only through a full backtest run.

### What was reused unmodified

- `TechnicalAnalysisEngine`, `FundamentalAnalysisEngine`,
  `RecommendationEngine`, `AIDecisionEngine`, and all nine
  `ScoreContributor`s — not reimplemented, not forked. `BacktestingEngine`
  calls them exactly as the live `/recommendation` and `/decision` routes
  do.
- `ohlcv_loader.load_price_bars` (already accepted an `end` cutoff),
  `SahmkClient`/`DevMarketDataProvider`/`SahmkMarketDataProvider`,
  `IngestionScheduler`, the REST/error-envelope/dependency-injection
  conventions from `src/api/`, and the Alembic migration chain.

### What was newly built

- `src/backtesting/data_access.py`, `metrics.py`, `regime.py`,
  `baselines.py`, `engine.py`, `walk_forward.py`, `job_runner.py`,
  `config.py`, `calibration/parameters.py`, `calibration/engine.py`.
- Three new domain models: `RecommendationSnapshot`, `BacktestRun`,
  `CalibrationConfig` (migration `9d260aefc6a7`).
- `src/api/routes/backtests.py`, `src/api/routes/calibrations.py`,
  `src/api/schemas/backtesting.py`.
- Two small, additive extensions to already-shipped engines (see §2):
  `RecommendationTuning` and `AIDecisionTuning`.

### Small, additive extensions to already-shipped code

Two gaps blocked reliable backtesting and were fixed, both backward
compatible (default behavior unchanged for every existing caller):

1. **`PriceBar` had no `source`/`is_synthetic` columns.** Both market
   data providers already returned these per bar, but `upsert_price_bar`
   discarded them — meaning nothing could tell, per bar, whether it came
   from SAHMK or the synthetic dev provider. Fixed via migration
   `9d260aefc6a7` (adds the columns, conservative `is_synthetic=true`
   default for any bar written before this migration existed) and an
   `upsert_price_bar` update to persist them.
2. **`load_fundamental_snapshots` had no as-of-date cutoff.** It always
   returned the most recent snapshots regardless of date — a direct
   look-ahead vector if reused inside a backtest loop unmodified. Fixed
   with an additive, optional `as_of` parameter (default `None`,
   identical behavior to before).
3. **`RecommendationEngine`/`AIDecisionEngine` had every threshold, ATR
   multiple, and confidence-penalty parameter hardcoded as module
   constants.** Calibration (Phase 5) needs these to be genuinely
   tunable, not just theoretically pluggable. Both engines now accept an
   optional `tuning` object (`RecommendationTuning`, `AIDecisionTuning`)
   whose field defaults exactly reproduce the previously-hardcoded
   values — omitting `tuning=` is bit-for-bit identical to before this
   milestone (locked in by regression tests).

## 2. Anti-look-ahead controls

This is the single most safety-critical property of a backtester. Three
independent mechanisms enforce it:

1. **Backward-only data access.** `data_access.load_as_of_dataset(session,
   stock, as_of, fundamental_reporting_lag_days)` is the *only* function
   `BacktestingEngine` uses to build a decision's inputs:
   - Price bars: `ohlcv_loader.load_price_bars(..., end=as_of)` — bars
     strictly on or before the evaluation date, never later.
   - Fundamentals: `load_fundamental_snapshots(..., as_of=as_of -
     fundamental_reporting_lag_days)`. A `fiscal_period_end` is when a
     reporting period *ended*, not when a company's results became
     public — there is no filing/publication-date field in this schema
     (see §7, disclosed gaps) — so a configurable, conservative buffer
     (default 45 days) stands in for that missing field. This is an
     approximation, not exact filing-date accuracy, and is documented as
     such everywhere it's used.
   - Live price: never used. Every price a backtest sees comes from an
     already-ingested `PriceBar`, never a live provider call — this is
     also what makes a backtest fast and provider-rate-limit-free.
2. **Forward data only flows into outcome scoring, never into the
   decision.** `data_access.load_forward_price_path()` is the one
   function allowed to look forward — used exclusively to compute
   `forward_return_pct`/`hit_target`/`hit_stop_loss` *after* a decision
   was already made. This is not leakage: scoring what actually happened
   after a historical recommendation is backtesting's entire purpose, as
   long as that data never flows back into the decision itself. The two
   functions are structurally separate (different module functions,
   different tests) specifically so this boundary can't blur by
   accident.
3. **Regression tests that fail loudly on a leak.** `tests/unit/backtesting/test_data_access.py`
   asserts, for concrete dates: a bar exactly on the cutoff date is
   included, a bar one day after is not; a fundamental snapshot becomes
   visible exactly `fundamental_reporting_lag_days` after its period
   end, not before; a later fiscal period never appears when an earlier
   one is the correct "as of" answer.

### Synthetic/live separation

`bars_match_provenance()` checks every `PriceBar` in an evaluation's date
range against the run's declared `data_provenance_mode` (`SYNTHETIC` or
`LIVE`). A symbol/date whose bars don't match is **skipped and counted**
(`skipped.provenance_mismatch`), never silently blended in. A
`BacktestRun`'s `metrics` therefore never mix synthetic and live-derived
results — this is enforced per evaluation, not just documented.

## 3. Metrics (formulas)

All pure functions in `src/backtesting/metrics.py`; every one has unit
tests with hand-computed expected values.

| Metric | Definition |
|---|---|
| **direction accuracy** | Of BUY/STRONG_BUY/SELL/STRONG_SELL calls with a known forward return, the fraction whose sign matched the call's implied direction. HOLD makes no directional claim and is excluded. |
| **target-price hit rate** | Of calls with a target price set and a known outcome, the fraction touched within `target_price_horizon_days`. |
| **stop-loss hit rate** | Same, for the stop-loss level. |
| **forward return** | % price change from the evaluation price to the price `holding_horizon_days` later, net of the run's round-trip transaction cost/slippage assumption. |
| **win rate / loss rate** | Of directional (non-HOLD) calls, the fraction whose *directional* P&L (positive for a correct call in either direction) was positive / negative. |
| **profit factor** | sum(positive directional P&L) / abs(sum(negative directional P&L)). `None` (not infinite) when there are no losing calls or no calls at all — never a misleading "infinite edge." |
| **max drawdown** | Largest peak-to-trough decline of a *discrete trade-sequence* equity curve built by compounding each call's directional P&L in evaluation-date order, equal-weighted. **This is a simplification** — not a true position-sized portfolio simulation, since there is no portfolio model in this codebase. |
| **volatility** | Sample standard deviation of the directional P&L series. |
| **downside deviation** | Sample standard deviation of only the negative values in that series. |
| **Sharpe ratio** | mean(directional P&L − risk-free rate) / volatility. Non-annualized unless `periods_per_year` is supplied. |
| **Sortino ratio** | Same, divided by downside deviation instead of volatility. |
| **calibration error (ECE)** | Calls are bucketed by stated confidence (0–20, 20–40, …, 80–100); for each bucket, `|mean_confidence/100 − realized_accuracy|`, weighted by bucket size and summed. 0 = perfectly calibrated confidence; higher = systematically over/under-confident. |

Breakdowns (`full_report()`) group every metric above by recommendation
class, confidence bucket, risk level, time horizon, sector, symbol, and
market regime.

### Market regime — a disclosed simplification

There is no ingested TASI/market-index history in this codebase —
`MarketSnapshot` (the index-level model) exists but is never populated by
any ingestion job (confirmed during this milestone's architecture audit).
Rather than fabricate index data, `regime.classify_market_regime()`
classifies **per symbol**, from that symbol's own trailing 20-bar
volatility and trend, into `UPTREND` / `DOWNTREND` / `RANGE_BOUND` /
`HIGH_VOLATILITY`. This is a real, honestly-labeled, narrower signal than
a broad-market regime — treated as such everywhere it's used.

## 4. Walk-forward methodology

`src/backtesting/walk_forward.generate_walk_forward_windows()` is pure
date arithmetic (no database, no randomness) that:

1. Reserves the **last** `test_days` of the full date range as an
   untouched test period.
2. Splits everything before that into a sequence of (train, validation)
   windows — `mode="rolling"` (fixed-size training window sliding
   forward by `step_days`, default = `validation_days`) or
   `mode="expanding"` (training start date fixed, training end grows by
   absorbing each validation period after it's used).
3. Structurally guarantees no window's train or validation period ever
   overlaps the reserved test period, and that train always strictly
   precedes validation within a window.

`CalibrationEngine.validate()` is what actually *uses* a (train,
validation) pair: it runs the candidate configuration and the current
active configuration (or engine defaults, if none is active) through
`BacktestingEngine` over the **same** validation period, so "is this
better" is always a same-period, like-for-like comparison. The reserved
test period is never touched by anything in this milestone — evaluating
a final calibrated configuration against it is future work, done only
once a human decides calibration is complete (see §7).

Reproducibility: `CalibrationEngine.propose_random_candidates()` samples
candidate parameter values with a local `random.Random(seed)` instance
(never touching global `random` state) — the same seed always produces
the same candidates, verified by a regression test.

## 5. Calibration lifecycle

```
DRAFT --validate()--> VALIDATED --activate()--> ACTIVE --rollback()--> ROLLED_BACK
   |                      |                         |
   +--validate() fails--> REJECTED                  +--superseded by a newer activate()--> SUPERSEDED
```

- **`propose()`** only ever creates a `DRAFT` row — it never touches
  production behavior. The candidate is a JSON bag
  (`contributor_weights`, `recommendation_tuning`, `ai_tuning` — see
  `src/backtesting/calibration/parameters.py` for the exact shape) that
  `RecommendationTuning`/`AIDecisionTuning`/contributor weight overrides
  are built from.
- **`validate()`** runs the candidate and the current active
  configuration (or defaults) through `BacktestingEngine` over the
  identical validation period, and applies the anti-overfitting guard:
  a candidate is `VALIDATED` only if its `direction_accuracy` is not
  worse than the baseline's **and** its `max_drawdown` is not materially
  worse (more than a 0.05 regression) even if the primary metric
  improved. Otherwise it is `REJECTED`, with the specific reason
  recorded in `notes`. This directly implements "reject a candidate that
  improves one metric while materially worsening risk or drawdown" —
  not a general-purpose scoring formula, a specific, explainable guard.
- **`activate()`** requires `VALIDATED` status. At most one configuration
  is `ACTIVE` at a time — enforced in `CalibrationEngine`, not a database
  constraint (a partial unique index on status is backend-specific and
  the invariant is just as strong here, since activation only happens
  through this one code path). Activating a new version marks the
  previous `ACTIVE` one `SUPERSEDED`.
- **`rollback()`** deactivates whatever is `ACTIVE` (→ `ROLLED_BACK`)
  and, if a target version is given, reactivates that specific prior
  version (which must have been `VALIDATED`, `SUPERSEDED`, or
  `ROLLED_BACK` — never a `DRAFT` or `REJECTED` one).
- Nothing is ever silently overwritten: every transition is one explicit
  method call, one row update, one commit.

**Not done in this milestone (disclosed):** an `ACTIVE` calibration is
not wired into the *live* `/recommendation` and `/decision` routes —
those routes still always use engine defaults. This milestone builds and
proves the calibration lifecycle machinery; making production traffic
actually respect an active calibration is a natural, bounded follow-up,
not started here.

## 6. REST API

All routes follow `src/api/routes/stocks.py`'s conventions: `APIError`
subclasses → a consistent `{"error": {"code", "message"}}` envelope,
Pydantic request validation, plain `Depends(get_db)` sessions.

### Backtests

| Route | Notes |
|---|---|
| `POST /api/v1/backtests` | Creates a `PENDING` run and schedules it as a FastAPI `BackgroundTask` — never blocks on the backtest itself. Idempotent: an identical request (hashed from every config field) returns the existing run, 200, never a duplicate. Rejects (409) a large-scope (`>= BACKTEST_FULL_MARKET_SYMBOL_THRESHOLD` symbols) request while another large-scope run is `PENDING`/`RUNNING`. |
| `GET /api/v1/backtests/{run_id}` | Full run record. |
| `GET /api/v1/backtests/{run_id}/status` | Lightweight polling: status, progress, timing. |
| `POST /api/v1/backtests/{run_id}/cancel` | Cooperative cancellation — sets `cancel_requested`; the run checks it between evaluations. |
| `GET /api/v1/backtests/{run_id}/metrics` | The full `metrics.full_report()` output. |
| `GET /api/v1/backtests/{run_id}/trades` | Paginated `RecommendationSnapshot` rows (`limit`/`offset`, bounded by `BACKTEST_MAX_TRADES_PAGE_SIZE`). |
| `GET /api/v1/backtests/{run_id}/confidence-calibration` | Just the calibration-error/confidence-bucket slice of the metrics. |
| `GET /api/v1/backtests/{run_id}/comparison` | Finds other **already-completed** runs sharing the same symbols/date range/provenance but a different strategy, and returns them side by side. Never triggers a new backtest (it's a GET) — submit a baseline strategy run separately to populate the comparison. |

### Calibrations

| Route | Notes |
|---|---|
| `POST /api/v1/calibrations` | Creates a `DRAFT`. |
| `GET /api/v1/calibrations` | Lists all, newest first. |
| `GET /api/v1/calibrations/{version}` | One record. |
| `POST /api/v1/calibrations/{version}/validate` | Runs **synchronously** (see below), bounded by the same symbol-count/date-range limits as a backtest. |
| `POST /api/v1/calibrations/{version}/activate` | Requires `VALIDATED`. |
| `POST /api/v1/calibrations/{version}/rollback` | Rolls back to the `{version}` in the path. |

`/validate` is the one route that doesn't defer to a background task —
it is bounded by the same `BacktestCreateRequest`-style validators
(reused via `CalibrationValidateRequest`), so it is never a "large
full-market backtest" by construction. A genuinely asynchronous
validate-in-background is a natural extension, not built here.

### Operational limits (Phase 7/8)

- `BACKTEST_MAX_SYMBOLS` (default 50), `BACKTEST_MAX_RANGE_DAYS`
  (default 3650), `BACKTEST_FULL_MARKET_SYMBOL_THRESHOLD` (default 20),
  `BACKTEST_MAX_TRADES_PAGE_SIZE` (default 500) — all read at request
  time (`src/backtesting/config.py`), so they're independently
  test-overridable via env vars.
- **Idempotent execution**: identical `POST` requests return the same
  run; re-running the same `run_id` through the engine directly
  (`BacktestingEngine.run()`) upserts snapshots in place rather than
  duplicating them — the same discipline `PriceBar`/`FundamentalSnapshot`
  upserts already use.
- **Retry**: `job_runner.run_backtest_job()` retries the whole run only
  on a curated set of transient exceptions (`OperationalError`,
  `ConnectionError`, `TimeoutError`, `OSError`) with exponential
  backoff, mirroring `run_ingestion_job`'s established contract. A
  configuration/programming-bug exception (`ValueError`, an unknown
  strategy, a missing calibration version) is recorded as `FAILED`
  immediately, never retried. The job runner never raises — even a
  failure in its very first "mark RUNNING" write is caught and logged.
- **Rate-limit awareness**: `BacktestingEngine` never calls a live
  market-data provider — every price/fundamental input is
  already-ingested database data (`data_access.py`), so backtests place
  zero additional load on SAHMK's rate limits by construction, not by a
  separate throttling mechanism.
- **Structured logs without secrets**: this module logs run IDs,
  symbols, statuses, durations — never credentials. (No SAHMK data is
  even touched by a backtest, since it only reads the database.)
- **Progress/duration reporting**: `BacktestRun.progress_current/
  progress_total` update every 5 evaluations (throttled, not one commit
  per evaluation) plus always on completion; `duration_seconds` is
  recorded on every run.
- **Duplicate full-market job guard**: see the `POST /api/v1/backtests`
  row above.

## 7. Known limitations (disclosed)

- **No corporate-action price adjustment.** Only dividends are tracked
  (`Dividend` model); there is no split-adjustment ingestion. A backtest
  spanning an unadjusted split would see a price discontinuity as if it
  were a real move. Not built this milestone.
- **Fundamental "as of" is an approximation.** `fundamental_reporting_lag_days`
  is a configurable buffer standing in for a missing filing/publication-date
  field on `FundamentalSnapshot` — see §2.
- **Market regime is per-symbol, not broad-market**, because no TASI
  index history is ingested — see §3.
- **Max drawdown/volatility/Sharpe/Sortino are computed on a discrete,
  equal-weighted trade-sequence equity curve**, not a true position-sized
  portfolio simulation — there is no portfolio/position-sizing model in
  this codebase.
- **Calibration is not wired into live production routes** — see §5.
- **`/calibrations/{version}/validate` runs synchronously**, bounded by
  the same limits as a backtest, not a background job — see §6.
- **No data-quality scoring beyond `source`/`is_synthetic` labeling** —
  no granular per-bar confidence/quality metric exists.
- **"One decision per stock" is per-symbol**, not a batch/universe-wide
  execution endpoint (submit one run per symbol list, or one run with
  multiple symbols — a full-market run reuses the same mechanism, just
  bounded by `BACKTEST_MAX_SYMBOLS`).

## 8. What was live-verified vs. what was only mock/synthetic-tested

**Live-verified: nothing in this milestone.** This sandbox has no
network access to SAHMK (a standing constraint throughout this project,
not specific to this milestone). Every test in
`tests/unit/backtesting/` and `tests/integration/` (REST routes, the
migration chain, the end-to-end engine flow) runs against **synthetic,
deterministic, hand-seeded `PriceBar`/`FundamentalSnapshot` data** in an
in-memory SQLite database, or hand-built fixtures for pure functions
(`metrics.py`, `walk_forward.py`, `regime.py`). No metric value produced
by any test in this milestone is a claim about real market behavior,
real trading accuracy, or real profitability — every number shown
anywhere in this codebase's tests is illustrative of the *mechanism*
working correctly on invented data, never a performance claim.

**What is real, tested code, regardless of data source:** the anti-
look-ahead data-access boundary, the metrics formulas, the walk-forward
window splitter, the calibration state machine, the REST layer, the
idempotency/retry/cancellation logic. These are correctness properties
of the *code*, verified with deterministic fixtures — they do not depend
on whether the underlying price data is real or synthetic to be true.

## 9. What remains before the Autonomous AI Analyst phase

- Wiring an `ACTIVE` calibration into the live `/recommendation` and
  `/decision` routes.
- A genuine live-data backtest, once SAHMK network access and enough
  ingested history exist, to produce the first honest performance
  numbers this platform can actually stand behind (never claimed here).
- Corporate-action (split) price adjustment.
- A true portfolio/position-sizing model, if position-level metrics
  (rather than the current discrete equal-weighted trade sequence) are
  needed.
- An asynchronous `/calibrations/{version}/validate` path, if validation
  workloads grow beyond the current bounded-synchronous limits.
- A batch/universe-wide scheduled backtest job (reusing
  `src/market_data/ingestion/config.py`'s symbol-universe pattern), if
  recurring, unattended backtest runs are wanted.

This document is superseded by whatever the Autonomous AI Analyst
milestone's own status document says, once that work is code-verified.
