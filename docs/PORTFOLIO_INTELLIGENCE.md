# Autonomous Portfolio Intelligence Layer

This document describes the Autonomous Portfolio Intelligence Layer
milestone: how Baseerah reasons about an entire investment portfolio
rather than isolated stocks, its architecture, its REST API, and —
explicitly — what has and has not been verified.

No claim in this document should be read as "production ready," "fully
complete," or "profitable." This document does not use those phrases as
characterizations of the platform, and none of the scores/allocations/
recommendations this layer can produce should be read as a claim about
real investment outcomes — see "What was live-verified vs. mock-tested"
below.

## 1. Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  REST layer (src/api/routes/portfolio.py)                         │
│  POST /analyze runs synchronously (no background job -- a          │
│  portfolio's holdings count is inherently small and bounded);      │
│  every GET reads the latest persisted PortfolioAnalysisSnapshot.   │
└──────────────────────┬────────────────────────────────────────────┘
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ src.portfolio_intelligence.portfolio_engine.PortfolioEngine        │
│  1. HoldingAnalyzer  -- per holding, reused pipeline (below)        │
│  2. AllocationEngine     -- weight/market value per holding + cash  │
│  3. ExposureEngine       -- dollar-weighted sector exposure         │
│  4. DiversificationEngine -- HHI-based concentration + score        │
│  5. RiskEngine            -- real correlation matrix, volatility,   │
│                               drawdown; beta architecture-ready      │
│  6. CashManager           -- target cash-reserve band               │
│  7. RebalanceEngine       -- per-holding action + new-buy            │
│                               opportunities (reuses Phase 7)         │
│  8. OptimizationEngine    -- prioritized recommendations             │
│  9. PortfolioScore        -- 0-100 health score                      │
│ 10. RecommendationBuilder -- pure assembly of the final feed         │
└──────────────────────┬────────────────────────────────────────────┘
                        │ per holding, reused, unmodified:
                        ▼
┌──────────────────────────────────────────────────────────────────┐
│ src.analysis.context_builder.build_analysis_context()               │
│  -> AnalystEngine.analyze()                                          │
│     -> AIDecisionEngine.decide()                                     │
│        -> RecommendationEngine.generate()                            │
│           -> TechnicalAnalysisEngine / FundamentalAnalysisEngine     │
└──────────────────────────────────────────────────────────────────┘
```

### What is reused unmodified

Every holding's analysis is exactly `AnalystEngine.analyze()` (itself
`AIDecisionEngine` -> `RecommendationEngine` ->
`TechnicalAnalysisEngine`/`FundamentalAnalysisEngine`, unmodified),
called once per held symbol via `HoldingAnalyzer` -- the same
`build_analysis_context()` extraction Phase 7 already introduced. No
score, target, or narrative is computed anywhere in
`src/portfolio_intelligence/`.

**New-buy opportunities reuse Phase 7 directly, not a re-implementation.**
`RebalanceEngine` reads the latest completed `MarketScanRun` (if one
exists) via `MarketIntelligenceRepository`, reconstructs
`SymbolScanOutcome`s via `market_intelligence.read_model.
outcome_from_record` (exactly as the market REST routes do), and hands
them to the *same* `RankingEngine` that powers `GET /api/v1/market/
top-buy` -- filtered to symbols not already held. When no market scan
has ever run, the list is honestly empty with a disclosed reason
(`"POST /api/v1/market/scan to enable new-buy-opportunity
suggestions."`), never fabricated.

`ExposureEngine`'s sector exposure is deliberately **not** a reuse of
`market_intelligence.sector_analysis.SectorAnalyzer` -- that engine
averages per-symbol scores equally across a market-wide scan (the
right basis for "how is the Energy sector performing market-wide");
a portfolio's sector *exposure* must be dollar-weighted ("how much of
this portfolio's money sits in Energy"). Reusing `SectorAnalyzer` here
would silently produce the wrong number, so this is a genuinely
different calculation, not a duplicate of Phase 7's sector logic.

## 2. The fourteen modules

| Module | File | Responsibility |
|---|---|---|
| `HoldingAnalyzer` / `PortfolioEngine` | `portfolio_engine.py` | Per-holding reuse of `AnalystEngine`; top-level orchestrator. |
| `AllocationEngine` | `allocation_engine.py` | Weight and market value per holding plus cash. |
| `ExposureEngine` | `exposure_engine.py` | Dollar-weighted sector exposure. |
| `DiversificationEngine` | `diversification_engine.py` | Herfindahl-Hirschman-Index concentration risk + diversification score. |
| `RiskEngine` | `risk_engine.py` | Real correlation matrix, volatility, drawdown; beta architecture-ready. |
| `CashManager` | `cash_manager.py` | Recommended cash-reserve band. |
| `PositionSizer` | `position_sizer.py` | Per-holding increase/reduce/exit/hold decision. |
| `RebalanceEngine` | `rebalance_engine.py` | Full rebalance plan + new-buy opportunities (reuses Phase 7). |
| `PortfolioScore` | `portfolio_score.py` | 0-100 health score, a disclosed weighted blend of four components. |
| `OptimizationEngine` | `optimization_engine.py` | Synthesizes prioritized, human-readable recommendations. |
| `RecommendationBuilder` | `recommendation_builder.py` | Pure assembly of the final recommendation feed. |
| `PortfolioRepository` | `repository.py` | The only module that reads/writes this layer's domain tables. |

`types.py` holds every shared dataclass/enum; `config.py` holds every
env-var-configurable threshold/weight.

## 3. Risk: what is real math vs. architecture-ready

**Real, computed from ingested data:**
- **Volatility**: per-holding annualized volatility from realized daily
  returns (`PriceBar` closes, via the existing `load_price_bars`
  loader), portfolio volatility via `w^T Σ w` (Σ built from the real
  correlation matrix and per-holding volatilities) -- standard Modern
  Portfolio Theory math, not a fabricated number.
- **Correlation matrix**: pairwise Pearson correlation of daily returns
  across held symbols, computed with `pandas.DataFrame.corr()`.
  Symbols with fewer than `PORTFOLIO_MIN_OVERLAPPING_DAYS` of return
  history are excluded and disclosed (`excluded_from_volatility`), never
  silently included with insufficient data.
- **Drawdown**: reconstructed from a weighted daily-return equity curve
  at the portfolio's *current* weights (a standard "as if constantly
  rebalanced to today's weights" retrospective estimate, not a live
  historical simulation of actual past weights — disclosed below).

**Architecture-ready, not wired to real data:** `compute_beta()`
implements the standard `cov(asset, market) / var(market)` formula and
is unit-tested with synthetic series proving it works correctly — but
this platform has never ingested any market/TASI index price history
(`MarketSnapshot`, the index-snapshot model, remains unpopulated, the
same disclosed gap Phases 6 and 7 already note), so `portfolio_beta`
is always `None` in production, with `beta_unavailable_reason`
explaining exactly why. This mirrors the `LLMAdapter`/`NullLLMAdapter`
pattern from Phase 6: the mechanism is built and proven, never
fabricated against data that does not exist.

## 4. REST API

All under `/api/v1/portfolio`:

| Method | Path | Purpose |
|---|---|---|
| POST | `/analyze` | Creates or re-analyzes a portfolio synchronously; returns the full analysis. |
| GET | `/{id}` | The latest persisted analysis for a portfolio. |
| GET | `/{id}/recommendations` | Rebalance actions, new-buy opportunities, cash recommendation, and prioritized optimization recommendations. |
| GET | `/{id}/risk` | Risk score, volatility, drawdown, correlation matrix, beta (architecture-ready). |
| GET | `/{id}/allocation` | Per-holding weight and market value plus cash. |
| GET | `/{id}/diversification` | HHI-based diversification score. |
| GET | `/{id}/rebalance` | Rebalance actions and new-buy opportunities only. |
| GET | `/{id}/health` | The 0-100 portfolio health score and its components. |

A deliberate, disclosed convention-adherence choice: the milestone spec
listed several GET routes without a portfolio ID in the path (e.g.
`GET /portfolio/risk`); every existing REST router in this codebase
(`/backtests/{run_id}/status`, `/calibrations/{version}/...`) scopes a
sub-resource route by the parent resource's ID in the path, so these
routes were built as `/portfolio/{id}/risk` etc. instead, for
consistency with the project's own established convention.

`POST /analyze` runs synchronously, unlike `POST /api/v1/market/scan`
(Phase 7): a portfolio's holdings count is bounded
(`PORTFOLIO_MAX_HOLDINGS`, default 50) and inherently small compared to
a full-market scan, so analyzing it is comparable in cost to a handful
of sequential `/analyst-report` calls -- well within normal HTTP
request latency. A background job would be unjustified complexity for
this workload size.

## 5. Known limitations (disclosed)

- **Portfolio beta is never computed against real market data** -- see
  §3. The formula is implemented and tested; no market index data
  source is wired up.
- **Drawdown assumes constant current-day weights applied
  retrospectively**, not the portfolio's actual historical weight
  drift (which this platform has no record of, since holdings are only
  ever analyzed as of "now") -- a standard simplification for this kind
  of estimate, but not a simulation of what the portfolio's owner
  actually experienced.
- **A pair of symbols with individually-sufficient but non-overlapping
  date ranges can still produce a low-confidence correlation cell**;
  any NaN correlation from insufficient pairwise overlap is treated as
  0 (uncorrelated) rather than left undefined, a conservative
  simplification disclosed here.
- **No user/ownership model exists** -- `Portfolio.name` is a plain,
  non-unique label, the same "reference data only" scope `Stock`
  itself has; there is no authentication or per-user portfolio
  isolation anywhere in this codebase yet.
- **New-buy opportunities depend on a completed market scan.** If none
  has ever run, `RebalanceEngine` returns an empty list with a
  disclosed reason rather than fabricating opportunities.
- **`PortfolioAnalysisSnapshot.analysis_json` intentionally omits each
  holding's full `AnalystReport` narrative** (investment summary,
  technical/fundamental reasoning prose, etc.) -- only the summary
  fields (`recommendation`, `confidence`, `risk_level`, `target_price`,
  ...) are persisted, the same discipline `SymbolIntelligenceRecord`
  already applies one milestone down. A caller that needs the full
  per-symbol narrative should call `GET /analyst-report/{symbol}`,
  which always re-runs `AnalystEngine` live.

## 6. What was live-verified vs. what was only mock/synthetic-tested

**Live-verified: nothing in this milestone.** As with every prior
milestone, this sandbox has no network access to SAHMK. Every test
(`tests/unit/portfolio_intelligence/`, `tests/integration/api/
test_portfolio_routes.py`) runs against hand-built fixtures or
synthetic, hand-seeded `PriceBar`/`FundamentalSnapshot` data in an
in-memory SQLite database via the Dev* providers. No allocation, risk,
diversification, health, or recommendation value produced by any test
in this milestone is a claim about real investment performance --
every example is illustrative of the *mechanism* working correctly on
invented data.

**What is real, tested code, regardless of data source:** the
Herfindahl-Hirschman-Index math, the correlation-matrix/volatility/
drawdown computation (genuine Modern Portfolio Theory formulas, not
placeholders), the position-sizing decision rules, the cash-band logic,
the health-score blend, the REST layer's graceful defaults and 404
handling, and the reuse of Phase 7's `RankingEngine` for new-buy
opportunities.

## 7. Tests

- **66 unit tests** under `tests/unit/portfolio_intelligence/` (one
  file per module, hand-built fixtures via `_fixtures.py`, plus 11
  dedicated repository tests against real in-memory SQLite).
- **17 integration tests** under `tests/integration/api/
  test_portfolio_routes.py` -- real FastAPI routing, a real synchronous
  portfolio analysis, every GET route, category-free sub-resource
  routes, 404s, a graceful-degradation case (a symbol with no ingested
  data), and a genuine cross-milestone reuse test (new-buy
  opportunities sourced from a real `POST /api/v1/market/scan`).
- **1803 tests pass, 12 skipped, repo-wide** (up from 1720 at the end
  of the Autonomous Market Intelligence Layer milestone). `flake8 src/
  tests/ main.py` is clean at 0 violations.

Two real bugs were caught and fixed during self-review before commit:
a `numpy.float64` leaking through `RiskEngine`'s portfolio-volatility
calculation into every downstream score (JSON/Pydantic-unsafe; fixed
by casting to a plain Python `float`), and
`PortfolioRepository.get_latest_analysis_snapshot()` ordering only by
the caller-supplied `generated_at` timestamp, which can legitimately
tie across two analyses run in close succession (fixed to order by
`id` instead, the same deterministic-tie-break convention
`MarketScanRun` queries already use).

No claim in this document should be read as "production ready," "fully
complete," or "100% accurate" — none of those are accurate
characterizations, and this document does not use those phrases as
characterizations of the platform.
