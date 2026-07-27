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
  `config.py`, `calibration/parameters.py`, `calibration/engine.py`,
  `calibration/indicator_signals.py`, `calibration/indicator_attribution.py`,
  `calibration/statistical_calibration.py` (the last three: §5a/§5b).
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
| **precision / recall** | Standard binary-classification metrics: each directional call is a prediction, the sign of the realized forward return is ground truth. Bullish calls (predicting UP) and bearish calls (predicting DOWN) are independent classes, scored separately then macro-averaged — a BUY call is never penalized against the DOWN class it never claimed anything about. HOLD calls and zero/unknown forward returns are excluded from both. |
| **position sizing quality** | Buckets directional calls with a known outcome by their recorded `position_size` (NONE/SMALL/MODERATE/STANDARD/LARGE) and reports each bucket's win rate/average directional P&L, plus `monotonicity_score` — the Pearson correlation between the size ordinal and the bucket's average P&L. Close to +1 means larger sizes really do earn better outcomes (well-calibrated sizing); near 0 or negative means they don't. |

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

## 5a. Per-indicator attribution

Every prior milestone's metrics were computed at the *contributor*
level (technical, fundamental, momentum, ...) or at the *whole-engine*
level — no existing code measured a single named indicator's (RSI,
MACD, Fibonacci, ...) own standalone predictive quality in isolation.
`src/backtesting/calibration/indicator_signals.py` and
`indicator_attribution.py` close that gap for all eleven indicators
named in this milestone's requirements: **Fibonacci, Support/Resistance,
VWAP, Volume Profile, RSI, MACD, ADX, EMA, SMA, Bollinger Band width,
ATR.**

`indicator_signals.py` defines one standalone, backtesting-only pure
reader per indicator — deliberately **not** a reuse of the live
scoring contributors' internal `_score_*` functions, which would only
show how an indicator performs already blended with everything else in
that contributor's score. This is the same "one indicator, one
opinion" idea `src.backtesting.baselines`'s `RSIOnlyStrategy`/
`SMACrossoverStrategy` already established for two of these eleven,
extended here to the other nine. Two disclosed categories:

- **Nine directional indicators** (Fibonacci, Support/Resistance,
  VWAP, Volume Profile, RSI, MACD, EMA, SMA, ADX) make a genuine
  BULLISH/BEARISH/NEUTRAL claim, each with a bounded 0–100 `magnitude`
  ("how strong is this specific reading") used for the confidence-
  accuracy metric. **ADX** is a special case: it measures trend
  *strength*, not direction, in this codebase's own live scoring (see
  `TechnicalScoreContributor`/`RiskScoreContributor` — neither ever
  treats it as directional) — its real, testable claim is "a strong
  trend reading predicts the concurrent price trend continuing," so
  it's paired with the sign of the recent price move over the same
  10-bar lookback the rest of the codebase already uses for trend
  comparisons, disclosed explicitly as this module's own convention,
  not a fabricated ADX-is-directional claim.
- **Two risk/volatility indicators** (ATR, Bollinger Band width) make
  no directional claim at all in this codebase (see
  `RiskScoreContributor`) — forcing a win-rate framing on them would
  misrepresent what they actually predict. Their `direction` is always
  `NEUTRAL`; their real signal is the raw ATR/price or band-width/price
  ratio, consumed by a dedicated volatility-bucket report instead.

`indicator_attribution.run_indicator_attribution()` replays the same
anti-look-ahead (symbol, date) grid every other historical replay in
this engine walks (via the shared `data_access.collect_as_of_evaluations()`
— see below), reads all eleven indicators at each point, and scores:

- The nine directional indicators through the *exact same*
  `metrics.compute_all_metrics()` every other report in this engine
  uses (win rate, average/median forward return, drawdown, Sharpe/
  Sortino, precision/recall, calibration error/confidence accuracy) —
  computed completely independently per indicator, zero blending.
- ATR and Bollinger through a volatility-bucket report: each historical
  point is bucketed "low"/"moderate"/"high" using the *exact same*
  thresholds `RiskScoreContributor` already uses in production (ATR
  ratio 0.012/0.03, Bollinger width ratio 0.04/0.10), and each bucket
  reports its sample size, average forward return, and realized
  volatility (stdev of forward returns) — directly testing the claim
  "a low reading really does precede calmer forward price action."

### Shared grid-walk primitive

`data_access.collect_as_of_evaluations(session, symbols, start_date,
end_date, frequency_days, data_provenance_mode,
fundamental_reporting_lag_days)` extracts the (symbol, date) grid walk
+ safety checks (symbol exists, provenance matches, at least one input
available) that `BacktestingEngine.run()`, `run_indicator_attribution()`,
and `propose_statistical_weights()` (§5b) all need, into one shared,
independently-tested function — so all three historical replays always
mean the same thing by "which (symbol, date) points get evaluated."
`BacktestingEngine.run()` itself is left using its own established,
heavily-tested inline loop (its own extra machinery — snapshot
persistence, cancellation, regime classification, progress callbacks —
isn't needed by the other two callers) rather than being migrated onto
the new primitive; only its tiny `_evaluation_dates()` date-generation
helper now delegates to the shared `evaluation_dates()` to remove exact
duplication, with zero behavior change (regression-tested).

## 5b. Statistical weight calibration

`CalibrationEngine.propose_random_candidates()` (§4/§5) samples
candidate parameter values uniformly at random and lets `validate()`'s
same-period backtest comparison decide if one happens to be better —
useful, but not evidence-driven: nothing measures *why* a candidate's
weights should change before proposing them.
`src/backtesting/calibration/statistical_calibration.py` adds a
second, complementary path: it *measures* each of the eleven scoring
contributors' (technical, fundamental, momentum, volume, risk,
price_structure, value_area, news_sentiment, macro,
insider_transactions, sector_rotation) own standalone directional edge
over a training period — reusing the exact same "run
`RecommendationEngine` with only this one contributor at weight 1.0"
technique `TechnicalOnlyStrategy`/`FundamentalOnlyStrategy` already
use for two of them — and proposes a new weight **only where a
significance test says the evidence actually supports it**.

### The significance test

`significance_test(values, min_sample_size, significance_level)` is a
two-sided one-sample z-test of a contributor's directional P&L series
against zero (the null hypothesis: "this contributor has no real
edge"). No `scipy` dependency: `statistics.NormalDist` (Python 3.8+
stdlib) supplies the standard normal CDF this needs — the normal
approximation to the t-distribution, exact as sample size grows and
the conventional, textbook-standard approximation once
`n >= ~30`, which is exactly this module's own default
`DEFAULT_MIN_SAMPLE_SIZE`. A candidate is `significant` only when
**both** the p-value is below `significance_level` (default 0.05)
**and** the sample size meets the floor — a low p-value from a
handful of lucky calls is never treated as evidence on its own.

### The weight-proposal formula

For a significant contributor, `_propose_weight()` scales the old
weight by a bounded function of the t-statistic: `edge_scale =
clamp(t_statistic / 10, -0.5, 0.5)`, `new_weight = max(0.01, old_weight
* (1 + edge_scale))` — a disclosed, bounded heuristic (a t-statistic of
5+ already saturates the ±50% adjustment cap, so one extreme outlier
run can't dominate a single calibration pass), not fabricated
precision. Non-significant or insufficient-sample contributors keep
their **exact** existing weight — no renormalization drift, because
`RecommendationEngine.generate()` already self-normalizes by whatever
weights are actually present among available contributors (divides by
`sum(c.weight for c in available)`), so proposing a new weight for
only *some* contributors and leaving the rest at their engine defaults
is always mathematically correct, not an approximation.

### The report

`StatisticalCalibrationReport` (one `ContributorCalibrationEntry` per
contributor) is exactly the shape requirement 5 asked for: **old
weight, new weight, mean edge, t-statistic, p-value, sample size, and
an explicit `action`** (`"reweighted"` / `"unchanged_insufficient_evidence"`
/ `"unchanged_not_significant"`) — every contributor is listed, even
the four external-factor ones (news/macro/insider/sector-rotation)
that honestly report `sample_size=0` and `unchanged_insufficient_evidence`
every time, since `data_access.py`'s `AsOfDataset` has no real news/
macro/insider/sector feed wired in for them to score against — a
disclosed gap, not a silently fabricated result.

### Reusability (requirement 6)

`report.contributor_weights` (only the `"reweighted"` entries) is the
*exact* `config["contributor_weights"]` JSON shape
`calibration/parameters.py`'s `build_contributors()` already consumes
— handing it straight to the existing, unmodified
`CalibrationEngine.propose()` produces a normal `DRAFT`
`CalibrationConfig`, which then goes through the same
`validate()` → `activate()` → `rollback()` lifecycle every other
calibration candidate already uses (§5). `POST
/api/v1/calibrations/statistical-weights` (§6) can do this in one call
via `create_draft_calibration: true`. Because this is just a function
call over whatever date range and symbols are supplied, running it
again against a later date range once new market data has been
ingested produces a fresh, independently re-validated candidate — this
*is* the "continuously improve the model" reusability requirement,
with no new infrastructure beyond calling the same function again.

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
| `POST /api/v1/calibrations/indicator-attribution` | §5a — replays historical data and returns each of the eleven named indicators' standalone predictive-quality report. Runs synchronously, bounded the same way `/validate` is. |
| `POST /api/v1/calibrations/statistical-weights` | §5b — measures each contributor's standalone directional edge, statistically tests it, and returns a per-contributor old-weight/new-weight/confidence/significance/sample-size report. `create_draft_calibration: true` (plus a `validation_period_start`/`_end`) additionally creates a `DRAFT` `CalibrationConfig` from any reweighted contributors in the same call. |

`/validate`, `/indicator-attribution`, and `/statistical-weights` are
the three routes that don't defer to a background task — all three are
bounded by the same `BacktestCreateRequest`-style validators, so none
is ever a "large full-market backtest" by construction. A genuinely
asynchronous background path for any of them is a natural extension,
not built here.

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
- **Per-indicator `magnitude` scaling constants are disclosed
  heuristics, not backtested/calibrated** (§5a) — e.g. EMA/SMA/VWAP/
  Volume-Profile deviation-to-magnitude scaling factors, the RSI
  proportional magnitude formula. They only affect the confidence-
  accuracy metric's bucketing, never win rate/precision/recall/average
  return (those depend only on `direction`, which is not a scaled
  heuristic — it's the same threshold logic already used in
  production, or an explicitly disclosed convention for ADX).
- **The statistical weight-proposal formula's edge-to-weight scaling
  (§5b) is a disclosed, bounded heuristic** — a t-statistic-based
  ±50%-max adjustment, not a formally derived optimal weight. The
  significance *test* itself (a standard z-test/normal approximation)
  is not a heuristic; only the translation from "how significant" to
  "how much to change the weight" is.
- **The four external-factor contributors (news/macro/insider/sector-
  rotation) have zero backtestable sample size** (§5b) — no real news/
  macro/insider/sector-rotation feed is wired into
  `data_access.AsOfDataset`, so `propose_statistical_weights()` always
  reports them as `unchanged_insufficient_evidence`, honestly, rather
  than fabricating a result.

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

## 9. What remains before the News Intelligence phase

- Wiring an `ACTIVE` calibration into the live `/recommendation` and
  `/decision` routes.
- A genuine live-data backtest, once SAHMK network access and enough
  ingested history exist, to produce the first honest performance
  numbers this platform can actually stand behind (never claimed here).
- Corporate-action (split) price adjustment.
- A true portfolio/position-sizing model, if position-level metrics
  (rather than the current discrete equal-weighted trade sequence) are
  needed.
- An asynchronous `/calibrations/{version}/validate`,
  `/indicator-attribution`, or `/statistical-weights` path, if
  workloads grow beyond the current bounded-synchronous limits.
- A batch/universe-wide scheduled backtest job (reusing
  `src/market_data/ingestion/config.py`'s symbol-universe pattern), if
  recurring, unattended backtest runs are wanted.
- **Backtesting the per-indicator `magnitude` scaling constants and the
  statistical weight-proposal edge-to-weight formula themselves** (§5a/
  §5b) — both are disclosed heuristics today, not yet validated the way
  `AIDecisionTuning`'s ATR multiples are (§1).
- **Real news/macro/insider/sector-rotation data sources**, so the four
  external-factor contributors can finally be measured by
  `propose_statistical_weights()` instead of always reporting zero
  sample size (§5b).

This document is superseded by whatever the next milestone's own
status document says, once that work is code-verified.
