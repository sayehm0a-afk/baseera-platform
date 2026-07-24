# Current Status — Authoritative

This is the only authoritative status document for the Basirah platform.
Where anything in `docs/archive/legacy-reports/` or elsewhere conflicts
with this document, this document is correct — it is derived from direct
code inspection and executed validation, not narrative claims. It
supersedes `docs/architecture/m0-build-status.md` for overall status (that
document remains as the detailed M0 evidence record) and is itself
superseded by whatever the next milestone's equivalent document says,
once code-verified.

As of M2.3 (branch `feature/m2.3-fundamental-analysis-engine`, based on
`main` at `078db462186a979ee77b69f5efc1e293f72bb719`, M2.2's merge
commit):

## Implemented

- **Build/CI infrastructure** (M0): clean `pip install`, editable package
  install, zero syntax errors, unified `src.core.*` import convention, lazy
  database initialization, a CI pipeline that actually gates merges.
- **Generic runtime/orchestration scaffolding**: task queue, execution
  engine, reliability layer (circuit breaker, retries, compensation),
  observability layer, Redis message bus — real, tested code, reachable
  from `main.py`. See `docs/architecture/runtime-ownership.md` for exactly
  which files are canonical vs. legacy-but-still-referenced.
- **LLM abstraction**: a real `OpenAILLMClient` wrapper — but not wired
  into any agent by default (`BaseAgent.llm_client` is `None` unless
  explicitly supplied).
- **`src/core/base_agent/base_agent.py`**: directly imported and
  instantiated by `main.py` at application startup (a sample `BaseAgent`
  is created and registered with the agent runtime) — this makes it
  **canonical, reachable runtime code**, not legacy/orphaned. It remains
  only a generic agent base with no domain logic (no LLM client attached
  by default, no stock-analysis or agent-specific behavior). Distinct
  from `multi_agent_system.SupervisorAgent`, which subclasses it but is
  itself not reachable from `main.py` (see "Partially implemented" below
  and `docs/architecture/runtime-ownership.md`).
- **FastAPI application shell**: `main.py` boots, exposes health/metrics/
  generic task-and-agent CRUD endpoints. No domain-specific routes exist.
- **Domain models and persistence** (M2.1): `Stock`, `PriceBar`,
  `MarketSnapshot` — the first real models ever registered against
  `src.core.db.database.Base`. One Alembic migration
  (`migrations/versions/0001_initial_domain_models.py`), verified
  upgrade→downgrade→upgrade against a real Postgres 16 instance, with
  server-side column defaults (not just ORM-side) so a non-ORM insert
  still satisfies every NOT NULL constraint. No `DecisionRecord` or
  other decision/signal-layer model yet — those depend on milestones
  this one doesn't cover.
- **OHLCV ingestion** (M2.1): `src/market_data/ingestion/ingest_ohlcv.py`
  fetches and upserts one day's bar per symbol via any
  `IMarketDataProvider`, isolating per-symbol failures. Not yet wired
  into `RealWorker`/`RealTaskQueue`/`main.py` — its signature is
  handler-compatible for a later milestone to register, but that wiring
  itself is out of M2.1's scope.
- **Technical Analysis Engine** (M2.2): `src/analysis/technical_analysis_engine.py`
  computes 11 indicators — SMA, EMA, ADX, SuperTrend (trend); RSI, MACD
  (momentum); Bollinger Bands, ATR (volatility); OBV, Volume SMA
  (volume); 5 candlestick patterns (Doji, Hammer, Shooting Star,
  Bullish/Bearish Engulfing) — against one OHLCV `DataFrame`, all
  implemented directly on `pandas`/`numpy` (no new dependency).
  `src/analysis/registry.py`'s `IndicatorRegistry`/`IndicatorSpec` is
  the extension point: a future indicator (including a Smart Money/ICT/
  Wyckoff-style one) is one pure function plus one registry entry, with
  no change to the engine or any existing indicator.
  `TechnicalAnalysisResult.latest_snapshot()` gives the flat "current
  value of everything" shape a future Signal Engine/Confidence Scoring/
  AI Decision Layer would consume. `ohlcv_loader.py` bridges `PriceBar`
  (M2.1) to this pure-computation layer and is the only module in
  `src/analysis/` that touches a database session. **Not included**:
  no persistence of computed indicator values (nothing is written back
  to the database), no API route exposes any of this yet, no
  support/resistance detection, no trend-strength beyond what ADX/
  SuperTrend already provide, and no signal generation or confidence
  scoring — those are later layers this milestone only prepared the
  extension point for. Depends entirely on `DevMarketDataProvider`'s
  synthetic data via `ohlcv_loader.py`; no real Tadawul vendor is
  contracted (unchanged from M2.1).
- **Fundamental Analysis Engine** (M2.3): `src/analysis/fundamental/
  fundamental_analysis_engine.py` computes 18 financial-statement
  ratios across 6 categories — net profit margin, gross profit margin,
  ROE, ROA (profitability); current ratio, quick ratio, cash ratio
  (liquidity); debt-to-equity, debt-to-assets, equity multiplier
  (leverage); asset turnover (efficiency); P/E, P/B, dividend yield,
  market cap (valuation — needs a market price); revenue growth, net
  income growth, EPS growth (growth — needs a prior period) — against
  one `FundamentalFacts` snapshot. New domain model
  `FundamentalSnapshot` (`src/domain/models/fundamental_snapshot.py`,
  migration `migrations/versions/a75a1f329294_...py`), a vendor-neutral
  `IFundamentalDataProvider` interface + `FundamentalDataProviderFactory`
  (no real vendor — interface only), `DevFundamentalDataProvider`
  (synthetic-only, same `source="dev-synthetic"`/`is_synthetic=True`
  labeling as `DevMarketDataProvider`), and `ingest_fundamentals`
  (mirrors `ingest_ohlcv`'s per-symbol failure isolation).
  `src/analysis/fundamental/registry.py`'s `RatioRegistry`/`RatioSpec`
  is this engine's own extension point, structurally independent of
  M2.2's `IndicatorRegistry` — neither package imports the other.
  Every ratio returns `None`, never raises, when its inputs are
  missing or a denominator is zero (financial statements are commonly
  incomplete, unlike OHLCV bars).
  **Cross-engine architecture**: a new `src/analysis/core/` package
  (`contracts.py`'s `AnalysisOutput`/`AnalysisEngineResult`
  `typing.Protocol`s, `registry.py`'s engine-level `EngineRegistry`,
  `bootstrap.py` as the one composition-root module that registers
  both `TechnicalAnalysisEngine` and `FundamentalAnalysisEngine`) is
  the shared, engine-agnostic contract every current and future
  analysis engine (News/Market/Sector Intelligence, Macro, Smart
  Money/ICT, Wyckoff, and beyond) will satisfy — proven directly by
  `tests/unit/analysis/core/test_contracts.py`, which verifies M2.2's
  `TechnicalAnalysisResult`/`IndicatorOutput` satisfy the contract
  **with zero changes to that M2.2 code** (the contract is structural,
  not inheritance-based). **Not included**: no persistence of computed
  ratios, no API route exposes any of this, no real financial-data
  vendor (interface-only, per explicit instruction), and no Composite
  Analysis Engine/Signal Engine/Confidence Scoring/AI Decision
  Layer/Multi-Agent Orchestrator yet — `core/` only prepares the
  extension point those will use. Depends entirely on
  `DevFundamentalDataProvider`'s synthetic data; no real fundamentals
  vendor is contracted.

## Partially implemented

- **`autonomous_intelligence_layer/` and `multi_agent_system/`**
  (~30 files under `src/core/`): real Python data structures for a
  Supervisor/Planner/Debate/Voting/Fusion/Knowledge-Graph pattern, each
  with passing unit tests — but not reachable from `main.py`'s actual
  startup path, and not connected to any real LLM call except
  `ReflectionEngine`. This is orchestration scaffolding for a future
  agent framework, not a working expert-agent system.
- **Market data**: two providers now exist behind `IMarketDataProvider`.
  `SaudiMarketDataProvider` (`src/market_data/providers/
  market_data_provider.py`, moved from `src/core/market_data/` in M1,
  logic unchanged) remains a generic HTTP client shell against a
  hypothetical API — zero real vendor behind it, never exercised against
  a real data source. `DevMarketDataProvider` (M2.1, `src/market_data/
  providers/dev_market_data_provider.py`) is new: a deterministic,
  synthetic-data-only provider explicitly **not** real market data,
  built because no Tadawul data vendor is contracted yet (see the
  approved M2 blueprint's risk assessment) — exercised end-to-end
  against a real Postgres instance via `ingest_ohlcv`, but every value
  it returns is fabricated and must never be mistaken for real trading
  data. Registered with `MarketDataProviderFactory` under the `"dev"`
  key.

## Not implemented

- **Composite Analysis Engine, Signal Engine, Confidence Scoring,
  Explainable AI Engine, AI Decision Layer, Multi-Agent Orchestrator**:
  none of these exist yet. M2.3's `src/analysis/core/` package
  (`AnalysisOutput`/`AnalysisEngineResult` contracts, `EngineRegistry`,
  `bootstrap.py`) was built specifically so these can be added later
  without modifying `TechnicalAnalysisEngine`, `FundamentalAnalysisEngine`,
  or any indicator/ratio inside either, but no such layer has been
  written.
- **News Intelligence Engine, Market Intelligence Engine, Sector
  Intelligence Engine, Macro Analysis Engine, Smart Money/ICT Engine,
  Wyckoff Engine**: none exist yet — only Technical (M2.2) and
  Fundamental (M2.3) analysis are implemented so far, each independent
  and each satisfying the same `src/analysis/core/` contract these
  future engines will also satisfy.
- **Support/resistance detection**: not implemented — distinct from the
  trend-strength/direction ADX and SuperTrend already provide.
- **Expert agent system** (the 15-agent organization described in the
  approved recovery plan: Chief Investment Intelligence, Market Regime,
  Technical Analysis, Price Action, Volume/Liquidity, Fundamental,
  News/Events, Macro/Sector, Risk Manager, Red-Team, Decision Fusion,
  Confidence Calibration, Explainability, Outcome/Learning, Governance):
  not started. `src/agents/base/` is empty scaffolding, distinct from the
  legacy `autonomous_intelligence_layer/`/`multi_agent_system/` code.
  Note: the "Fundamental" **agent** in this list is a distinct,
  not-yet-started concept from the "Fundamental Analysis Engine"
  implemented in M2.3 — M2.3 is pure ratio computation with no agent,
  LLM, or decision-making wrapper around it.
- **Decision pipeline, debate/fusion orchestration, learning loop**:
  `src/pipeline/` and `src/learning/` are empty scaffolding.
- **Frontend**: does not exist in any form. `frontend/` is empty
  scaffolding.
- **Authentication/authorization, rate limiting, audit logs**: not
  implemented on the API layer.
- **Prompt library**: `prompts/` is empty scaffolding (the old
  `الملقنات/` skeleton it replaces was equally empty — see
  `docs/architecture/m1-move-map.md`).

## Retained only as legacy reference (not evidence of status)

`docs/archive/legacy-reports/` — 42 documents that claimed 100%
completion, production readiness, final certification, or a fully
completed AI agent layer. Code-level inspection during the M0 audit and
this M1 restructuring found none of those claims supported by the actual
repository state at the time they were written or since. See that
directory's own `README.md`.

## Empty future subsystems (scaffolded, not implemented)

`src/market_data/{validators,schemas}/`, `src/agents/base/`,
`src/pipeline/`, `src/learning/`, `prompts/`, `frontend/`,
`tests/{financial_validation,operational}/` — created in M1 as
directory scaffolding only (`.gitkeep`/empty `__init__.py`), per the
canonical target architecture. None contain code. None are placeholder
implementations. (`src/domain/` and `migrations/versions/` are no
longer empty as of M2.1, and `src/analysis/*` is no longer empty as of
M2.2 — see "Implemented" above for each.)

## Verified test/build state (M2.3)

- Compile sweep: 0 syntax errors across `src/`, `tests/`, `main.py`.
- Boot smoke test: `import main` succeeds, 11 routes (unchanged since
  M2.1), no `PYTHONPATH` manipulation required.
- Full test suite: 892 passed / 12 skipped (Redis unavailable) / 0 failed
  without a live Redis; 904 passed / 0 skipped / 0 failed with one.
  904 total test functions in the repository (up from 807 at M2.2's
  close — 97 new tests for the M2.3 domain model, provider, ingestion
  job, ratios, loader, engine facade, and the new `src/analysis/core/`
  cross-engine contract; zero existing tests modified).
- flake8: **0** violations across `src/`, `tests/`, `main.py`, gated in
  CI at `FLAKE8_BASELINE: 0` since M2.0 (see "Completed: M2.0" below).
- Migration cycle (`alembic upgrade head` → `downgrade base revision` →
  `upgrade head`) verified against a real local Postgres 16 instance
  matching `database.py`'s default `DATABASE_URL` exactly, for the new
  `fundamental_snapshots` migration.

## Completed: M1.5 — Lint Debt Reduction

Closed the 1515 pre-existing flake8 violations recorded at M1's close
down to 0, in 9 atomic work packages (WP1–WP9, `[M1.5]`-prefixed commits
on `chore/m1.5-lint-debt-reduction`), each with its own before/after
count, full test suite run (with and without Redis), compile sweep, and
boot smoke test. Breakdown by rule code prior to this milestone is in
`docs/architecture/m0-build-status.md` §5 (kept as the historical
record; not updated in place). Two genuine latent bugs were found and
fixed along the way (both `F821` undefined-name `NameError`s from a
missing `import asyncio`, in `src/core/service_layer/service_layer.py`
and `src/core/autonomous_intelligence_layer/agent_runtime/agent_runtime.py`
— both in files classified "legacy but still referenced" in
`runtime-ownership.md`, unreachable from `main.py`, which is why the
bugs were never caught by any test).

**`.github/workflows/ci.yml`'s `FLAKE8_BASELINE` was deliberately left
at `1515`, not lowered, in this milestone** — an explicit scope decision
to keep M1.5 to source/test cleanup only, without touching CI
configuration. This means the CI gate is now a loose ceiling (it will
only fail if violations climb back above 1515, not if they climb above
0) until a follow-up milestone updates the baseline value and/or
replaces it with the dynamic, self-verifying ratchet mechanism
originally scoped as this milestone's "WP0" and deferred. Until then,
`flake8 src/ tests/ main.py --count` should read 0; any nonzero count
is new debt from work done after this milestone closed, not inherited
debt.

## Completed: M2.0 — Tighten CI Baseline

One-line change: `.github/workflows/ci.yml`'s `FLAKE8_BASELINE` lowered
from `1515` to `0`, matching the count M1.5 actually achieved. The
dynamic/self-verifying ratchet mechanism M1.5 deferred (its "WP0")
remains **not implemented** — this was a manual value change only. PR
#4, merge commit `4567c9fb7c0c509a098b84faaa26b10f4d90f281`.

## Completed: M2.1 — Data Foundation

First real domain models and database schema for the platform:
`Stock`, `PriceBar`, `MarketSnapshot`, one Alembic migration, an interim
market-data provider, and an OHLCV ingestion job — see "Implemented"
and "Partially implemented" above for what each of those actually is
and isn't. Five `[M2.1]`-prefixed commits on
`feature/m2-saudi-stock-analysis-engine`, PR #5.

Two real bugs were found and fixed during this milestone, not worked
around:
- The autogenerated migration's `downgrade()` dropped the `price_bars`
  table but not the Postgres `timeframe` ENUM type it created,
  independently, as a side effect of that table's column — a
  downgrade→upgrade cycle failed with "type already exists" until an
  explicit `sa.Enum(...).drop(...)` was added.
- `src/market_data/__init__.py` had imported from `.market_data_provider`
  (the file's pre-M1 location) since M1 moved it to
  `.providers.market_data_provider` and updated every other reference —
  except this one, which had zero real importers until M2.1's tests
  became the first actual import of the `src.market_data` package.

**No Tadawul (or any other) data vendor is contracted.** This is the
single largest gap remaining for the whole M2 effort — everything from
M2.2 onward can be built and tested against `DevMarketDataProvider`'s
synthetic data, but no real signal or decision output will be
meaningful until a real vendor is integrated. `DevMarketDataProvider`
is explicitly, permanently labeled as non-production in its own module
docstring, in every dict it returns (`source="dev-synthetic"`,
`is_synthetic=True`), and in `.env.example`'s comment next to
`TADAWUL_API_KEY` — it must never be mistaken for, or silently promoted
to, a real data source.

## Completed: M2.2 — Technical Analysis Engine

11 technical indicators plus a registry-based extension point and an
engine facade — see "Implemented" above for exactly what each is and
isn't. Nine `[M2.2]`-prefixed commits on
`feature/m2.2-technical-analysis-engine`, PR #6.

Before implementation began, one architectural enhancement was made to
the approved spec by explicit instruction: the engine must not become
just a collection of indicators, but the permanent foundation later
layers (Composite Indicator Engine, Signal Engine, Confidence Scoring,
Explainable Signals, AI Decision Layer, future Smart Money/ICT/Wyckoff
modules) build on, without any of them needing to modify an existing
indicator. `src/analysis/types.py`'s `IndicatorOutput` and
`src/analysis/registry.py`'s `IndicatorRegistry`/`IndicatorSpec` are
that extension point, verified directly in
`tests/unit/analysis/test_technical_analysis_engine.py`: a hand-built
custom registry with a placeholder "future indicator" runs through the
unmodified engine correctly, and building a custom registry never
mutates the shared default one.

Per the spec's own risk assessment ("indicator math has a subtle
off-by-one or window-edge bug" as the single highest-likelihood defect
class for this milestone), every indicator has hand-computed reference
values, and the most deeply recursive/stateful ones (EMA, ADX, RSI,
MACD) additionally have independent, freshly-written non-vectorized
loop implementations cross-checked against the production code —
plain compile success and one ad hoc smoke test were treated as
explicitly insufficient verification.

**Deliberately out of scope, same "no data vendor" gap as M2.1**: no
indicator values are persisted, no API route exposes any of this, and
every computation still runs on `DevMarketDataProvider`'s synthetic
data — no real Tadawul vendor is contracted. Support/resistance
detection, signal generation, and confidence scoring do not exist yet;
this milestone only prepared the extension point they will plug into.

## Completed: M2.3 — Fundamental Analysis Engine

18 financial-statement ratios across 6 categories, a vendor-neutral
fundamental data provider interface, a synthetic-only dev provider, an
ingestion job, a ratio-level extension point, an engine facade, and a
new cross-engine architectural layer — see "Implemented" above for
exactly what each is and isn't. Fifteen `[M2.3]`-prefixed commits on
`feature/m2.3-fundamental-analysis-engine`, PR #7.

Before implementation began, an architectural directive extended
M2.2's "build an extension point" instruction one level further: M2.3
is only the second of many future analysis pillars (News/Market/Sector
Intelligence, Macro, Smart Money/ICT, Wyckoff, Composite, Signal,
Confidence Scoring, Explainable AI, AI Decision Layer, Multi-Agent
Orchestrator), so nothing in it may assume only Technical and
Fundamental Analysis will ever exist, every output must be generic and
uniformly consumable, and Technical/Fundamental must stay completely
independent of each other. This produced `src/analysis/core/`:
`contracts.py`'s `AnalysisOutput`/`AnalysisEngineResult` are structural
`typing.Protocol`s, not base classes, so M2.2's already-merged
`IndicatorOutput`/`TechnicalAnalysisResult` satisfy them with **zero
changes to that M2.2 code** — proven directly by
`tests/unit/analysis/core/test_contracts.py`. `registry.py`'s
`EngineRegistry` catalogs engines by name without standardizing each
engine's `analyze()` call signature (OHLCV DataFrames and
financial-statement facts are genuinely different input shapes, so
only the *output* is unified — forcing a common invocation signature
would have been exactly the kind of premature, leaky abstraction the
"no shortcuts" instruction ruled out). `bootstrap.py` is the one,
explicitly-labeled composition-root module that imports both concrete
engines and registers them — adding a third engine later means editing
only this one file, never `contracts.py`, `registry.py`, or either
existing engine.

One deliberate asymmetry, disclosed rather than silently fixed: M2.2's
files remain at `src/analysis/{types,registry,technical_analysis_engine}.py`
(not moved into a `src/analysis/technical/` subpackage to mirror
`src/analysis/fundamental/`), because renaming/moving already-merged
M2.2 files for cosmetic folder symmetry would itself have been
"modifying an existing engine," which the architectural directive
explicitly ruled out.

Same fundamentals-vendor gap as M2.1/M2.2's market-data gap: **no
fundamentals data vendor is contracted.** `IFundamentalDataProvider`
(`src/market_data/providers/fundamental_data_provider.py`) is an
interface + factory only; `DevFundamentalDataProvider` is
deterministic synthetic data, labeled `source="dev-synthetic"`/
`is_synthetic=True` in every returned value, the same discipline as
`DevMarketDataProvider`. One real bug class was proactively guarded
against, not discovered after the fact: the autogenerated migration's
`downgrade()` again dropped the table but not the new `periodtype`
Postgres ENUM type — the same defect class 0001's `timeframe` ENUM had
in M2.1 — caught and fixed before the upgrade→downgrade→upgrade
verification, not after.

No claim in this document should be read as "production ready," "fully
complete," or "100% successful" — none of those are accurate, and this
document does not use those phrases as characterizations of the platform.
