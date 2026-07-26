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
- **Technical Analysis Engine** (M2.2, extended Phase 11):
  `src/analysis/technical_analysis_engine.py` computes 16 indicators —
  SMA, EMA, ADX, SuperTrend (trend); RSI, MACD, Stochastic Oscillator
  (momentum); Bollinger Bands, ATR (volatility); OBV, Volume SMA, VWAP,
  Volume Profile (volume); 5 candlestick patterns (Doji, Hammer,
  Shooting Star, Bullish/Bearish Engulfing), Fibonacci retracement
  levels, swing-pivot support/resistance detection (price_action) —
  against one OHLCV `DataFrame`, all implemented directly on
  `pandas`/`numpy` (no new dependency).
  `src/analysis/registry.py`'s `IndicatorRegistry`/`IndicatorSpec` is
  the extension point: a future indicator (including a Smart Money/ICT/
  Wyckoff-style one) is one pure function plus one registry entry, with
  no change to the engine or any existing indicator.
  `TechnicalAnalysisResult.latest_snapshot()` gives the flat "current
  value of everything" shape a future Signal Engine/Confidence Scoring/
  AI Decision Layer would consume. `ohlcv_loader.py` bridges `PriceBar`
  (M2.1) to this pure-computation layer and is the only module in
  `src/analysis/` that touches a database session. Exposed via
  `GET /api/v1/stocks/{symbol}/technical`. **Not included**: no
  persistence of computed indicator values (nothing is written back to
  the database); VWAP is a rolling N-bar approximation, not true
  session-anchored intraday VWAP (needs tick data this platform doesn't
  have); Volume Profile attributes each bar's entire volume to one
  price bucket via its typical price, not a true intrabar
  volume-at-price distribution (same tick-data gap). None of the 5
  Phase-11 additions are yet wired into `RecommendationEngine`/
  `AIDecisionEngine`'s scoring/contributor layers — they exist and are
  tested, but nothing downstream reads them yet.
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

16 technical indicators plus a registry-based extension point and an
engine facade — see "Implemented" above for exactly what each is and
isn't. Nine `[M2.2]`-prefixed commits on
`feature/m2.2-technical-analysis-engine`, PR #6. Extended (Phase 11,
`claude/sahmk-api-key-verify-lpw25l`) with 5 more indicators the
original 11 didn't cover: Stochastic Oscillator (%K/%D, momentum),
VWAP (rolling N-bar volume-weighted average price -- documented as the
daily-bar analog of session-anchored intraday VWAP, which needs tick
data this platform doesn't have), Fibonacci retracement levels
(0/23.6/38.2/50/61.8/78.6/100% between the window's swing high and
low), swing-pivot support/resistance detection (a bar's high/low is a
pivot when it's the strict, unique extreme within a symmetric
`order`-bar window), and a Volume Profile histogram (volume-at-price
approximated per bar via typical price, since real intrabar
volume-at-price also needs tick data). Each addition is a pure
function following the existing package's conventions (no I/O, no
registry awareness) plus one new `IndicatorSpec` in
`src/analysis/registry.py` -- `TechnicalAnalysisEngine` itself did not
change, exactly as the extension point was designed to allow.

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

## Completed: SAHMK Integration — Live Provider, Auto-Selection, Unit Tests

Closes the market-data-vendor gap M2.1/M2.2/M2.3 each disclosed:
`SAHMK_API_KEY` (a Tadawul-licensed Saudi market data vendor,
sahmk.sa) is now a real, working credential, and a full
`IMarketDataProvider` implementation exists behind it. See
`docs/SAHMK_INTEGRATION.md` for the verified endpoint/auth contract,
including what was confirmed against the real account (the key is
accepted; `/market/summary/` and `/historical/` currently return `403
PLAN_LIMIT` for this account — disclosed, not hidden, and not yet
understood as plan-tier vs. account-activation).

1. **`src/market_data/sahmk/`** (new) — `client.py` (`SahmkClient`, the
   reusable, low-level async wrapper for every endpoint used:
   `/quote/`, `/historical/`, `/market/summary/`, `/events/`;
   `X-API-Key` auth, 3-attempt retry with `Retry-After`-aware backoff
   on 429/5xx, wrapped in the existing `CircuitBreaker`), `service.py`
   (`SahmkMarketDataService`, the typed/cached business layer —
   `TTLCache` with in-flight request coalescing), `models.py` (typed
   response shapes), `exceptions.py` (`SahmkAuthenticationError`/
   `SahmkEntitlementError`/`SahmkRateLimitError`/
   `SahmkResponseValidationError`/`SahmkRequestError`, matching SAHMK's
   confirmed 401/403 `PLAN_LIMIT` semantics).
2. **`src/market_data/providers/sahmk_market_data_provider.py`** (new)
   — `SahmkMarketDataProvider`, an `IMarketDataProvider` implementation
   (unchanged interface, per M2.1's design) returning the exact same
   dict shape `DevMarketDataProvider` does (`source="sahmk"`,
   `is_synthetic=False` instead of the dev markers), registered with
   the existing `MarketDataProviderFactory` under `"sahmk"`.
3. **`src/market_data/provider_factory.py`** (new) — the automatic
   live/synthetic selection point. `SAHMK_API_KEY` unset →
   `DevMarketDataProvider`, always, no live call ever attempted. Key
   set → a short, timeout-bounded connectivity probe
   (`SahmkMarketDataProvider.authenticate()`) decides: reachable and
   accepted → live `SahmkMarketDataProvider`; any connectivity failure,
   auth rejection, or timeout → `DevMarketDataProvider`, logged, never
   a startup failure. Selection is cached (default 60s) to avoid
   re-probing on every call. `MARKET_DATA_PROVIDER=dev|sahmk|auto` can
   force a specific choice for testing; even a forced `"sahmk"` still
   falls back to `"dev"` on an unreachable host, since booting must
   never depend on live third-party network access.
4. **`src/market_data/caching/ttl_cache.py`**,
   **`src/market_data/validators/symbol_validator.py`** (new) —
   in-process TTL cache with in-flight coalescing (a concurrent burst
   of requests for the same key triggers one upstream call, not one
   per caller), and the existing 4-digit Tadawul symbol format check
   used by `IMarketDataProvider`'s ingestion callers.
5. **`main.py`** — one new `GET /market-data/status` endpoint reporting
   which provider is currently active and its health, without ever
   exposing the configured key. `.env.example` documents
   `SAHMK_API_KEY`/`SAHMK_BASE_URL`/`MARKET_DATA_PROVIDER`.
6. **125 new unit tests** (`tests/unit/market_data/{sahmk,caching,
   validators,providers}/`, `test_config.py`, `test_provider_factory.py`)
   — every SAHMK/network call is mocked (a `FakeSession`/`FakeResponse`
   pair replaying scripted responses for the client, `AsyncMock` for
   the service/provider layers); no test opens a real socket. Covers
   every status-code mapping, the retry/circuit-breaker paths, cache
   coalescing and expiry, and every branch of the auto-selection logic
   (forced dev/sahmk, no credentials, rejected key, unreachable host,
   probe timeout, cache hit, forced refresh).

**A real bug was caught and fixed during this milestone, not after**:
an early manual smoke-test constructed `aiohttp.ClientSession()` without
`trust_env=True`. `aiohttp`, unlike `curl`, does not honor
`HTTPS_PROXY` by default, so that session dialed `sahmk.sa` directly —
bypassing this environment's own egress policy proxy instead of
receiving its allow/deny decision, exactly the kind of restriction
bypass the task explicitly prohibited. `SahmkClient` now always passes
`trust_env=True`, verified afterward by confirming the same call
correctly receives the proxy's policy-denial response instead of
reaching the real host directly.

**Scope discipline**: `feature/sahmk-integration` (a separate,
pre-existing branch based on `feature/m2.13-live-data-integration`, 47
commits ahead of `main`) already contains SAHMK research and a
provider rebuild; that branch's *research* (verified endpoints, auth
model, error semantics) informed this work, but its code was
deliberately not merged — it carries roughly ten milestones'
(M2.4–M2.13) worth of unreviewed work (composite intelligence engine,
technical experts, API auth foundation, etc.) that this task did not
ask for and `main` has not reviewed. This milestone is built directly
on `main` (M2.3) instead, touching only the market-data layer.
`ingest_ohlcv.py`/`ingest_fundamentals.py` remain unwired to any
worker/task-queue (still explicitly out of scope, per M2.1's own
disclosed boundary) — `provider_factory.get_market_data_provider()` is
available for that wiring whenever it is taken on.

## Completed: SAHMK Starter-plan expansion — Fundamentals provider, key rotation, live-verification attempt

Follow-up to the SAHMK Integration milestone above, after the account
was upgraded Free → Starter and `SAHMK_API_KEY` was rotated (old key
revoked). Every finding the previous milestone recorded about a real
response (`403 PLAN_LIMIT` against the old Free-tier key) is superseded
and not relied upon here — see `docs/SAHMK_INTEGRATION.md`'s "Key
rotation & plan upgrade" section.

1. **New Starter-tier endpoint wrappers** on `SahmkClient`:
   `get_company_profile()` (`GET /company/{symbol}/`), `get_financials()`
   (`GET /financials/{symbol}/`), `get_dividends()`
   (`GET /dividends/{symbol}/`) — plus matching `SahmkMarketDataService`
   methods (typed, cached) and `models.py` dataclasses
   (`SahmkCompanyProfile`, `SahmkFinancials`, `SahmkDividend`).
   `/financials/`'s exact field names are undocumented by every source
   consulted, so parsing tries several plausible key names per field
   (`_first_present()`) rather than assuming one, and always keeps the
   untouched raw response alongside the parsed one.
2. **`src/market_data/providers/sahmk_fundamental_data_provider.py`**
   (new) — `SahmkFundamentalDataProvider`, an `IFundamentalDataProvider`
   implementation (M2.3's interface, unchanged) combining
   `/financials/` + `/dividends/` into exactly
   `DevFundamentalDataProvider`'s dict shape (`source="sahmk"`,
   `is_synthetic=False`), registered with the existing
   `FundamentalDataProviderFactory` under `"sahmk"`. Raises
   `SahmkResponseValidationError` — rather than passing a dict with a
   missing key downstream to fail with a less legible `KeyError` in
   `ingest_fundamentals.py`'s `_upsert_fundamental_snapshot` — if any
   field that function actually requires is still absent after the
   defensive multi-name parse.
3. **`src/market_data/fundamental_provider_factory.py`** (new) — the
   fundamentals-side twin of `provider_factory.py`: identical
   network-aware auto-selection policy (`MARKET_DATA_PROVIDER` env var,
   same connectivity probe, same graceful fallback to
   `DevFundamentalDataProvider`), so the "no synthetic data left where
   avoidable" requirement now covers both provider families, not just
   market data. This closes the last remaining synthetic-only data path
   in the codebase — `grep -rl is_synthetic src/` now returns only the
   two `Dev*Provider`/`Sahmk*Provider` pairs, nothing else.
4. **`main.py`**'s `GET /market-data/status` now reports both
   selections (`market_data` and `fundamentals`) and each provider's
   health, still never the key.
5. **35 new unit tests** (mocked; no real network call) covering the
   three new client wrappers, the three new service methods,
   `SahmkFundamentalDataProvider` (including the required-field
   validation raising instead of propagating a bad dict), and
   `fundamental_provider_factory`'s selection logic — 160 total in
   `tests/unit/market_data/`, full repo suite still green.
6. **Live verification was attempted, honestly, and could not be
   completed in this sandbox**: both `curl` and the real
   `SahmkClient`/`SahmkMarketDataProvider` code path (which, since the
   prior milestone, always sets `trust_env=True` so it honors this
   environment's egress proxy) were used to call
   `GET /market/summary/` with the new key. Both were rejected
   identically by the environment's own egress-policy proxy at the
   CONNECT layer (`403`, from the proxy's own `127.0.0.1` address, not
   from `sahmk.sa`) — a network-policy fact about this sandbox, not
   about the key, the plan, or this code. Per this environment's own
   documented policy, this was not retried or routed around, and is
   reported rather than worked around. Every endpoint's live status is
   therefore "not verified this session" in
   `docs/SAHMK_INTEGRATION.md`'s endpoint table, not "confirmed
   working" — the auto-selection mechanism (item 3, and its
   market-data twin from the prior milestone) is what actually runs in
   this condition today, and is exactly what will self-verify the
   moment this code runs somewhere with real network access to
   `sahmk.sa`.

## Next-phase analysis and prioritization (before this milestone)

Before starting new work, the actual state of six candidate
next-phase items was checked against the code, not assumed from a
generic roadmap:

- **Technical analysis engine (RSI/MACD/EMA/Bollinger/ATR/etc.) was
  already fully built in M2.2** — `TechnicalAnalysisEngine` +
  `src/analysis/indicators/{momentum,trend,volatility,_common}.py`
  already cover RSI, MACD, SMA, EMA, ADX, SuperTrend, Bollinger Bands,
  ATR, OBV, volume SMA, and candlestick patterns, all tested. No new
  indicator work was needed.
- **Fundamental analysis engine was already fully built in M2.3** —
  `FundamentalAnalysisEngine` + `src/analysis/fundamental/ratios/*`
  cover profitability, liquidity, leverage, efficiency, growth, and
  valuation ratios, all tested. No new ratio work was needed either.
- **Consumer-facing REST APIs did not exist** — `src/api/routes/`,
  `schemas/`, and `middleware/` were empty placeholders;
  `src/api/health_check.py` existed but was never mounted in `main.py`;
  no CORS; no auth libraries installed.
- **A data ingestion scheduler did not exist** — `ingest_ohlcv.py`/
  `ingest_fundamentals.py` (M2.1/M2.3) are tested and
  `RealWorker.register_handler`-compatible by design, but nothing ever
  calls them. The existing `Scheduler`/`IScheduler` class
  (`src/core/runtime/task_queue/scheduler.py`) only records
  `{task_id, delay}` in a dict — there is no loop that actually fires
  a task later.
- **A recommendation/confidence-scoring engine did not exist** —
  `src/analysis/core/bootstrap.py`/`registry.py` are explicitly built
  as a composition root anticipating a third engine, but nothing
  registers one.
- **Frontend readiness**: `frontend/` is a literal empty directory
  (`.gitkeep` only) — zero frontend code exists.

Given that, prioritized by impact: (1) REST APIs — highest impact,
lowest cost, since it wraps two already-complete engines and the
already-hardened SAHMK provider layer rather than building new
intelligence, and nothing downstream is possible without it; (2)
ingestion scheduler — makes the API's DB-backed endpoints return real
data instead of empty tables and reduces per-request dependency on a
live, rate-limited SAHMK call; (3) recommendation/confidence engine —
the one genuinely new capability, but needs (1) to be consumable; (4)
frontend readiness — mostly falls out of (1) (CORS + a consistent
error shape), not a separate workstream. This milestone implements (1).

## Completed: Consumer-facing REST API (`GET /api/v1/stocks/*`)

1. **`src/api/routes/stocks.py`** (new) — five read-only routes:
   `GET /{symbol}` (DB lookup, 404 if unregistered),
   `GET /{symbol}/quote` (live pass-through via
   `provider_factory.get_market_data_provider()` — no DB row required,
   since nothing is persisted; symbol format is validated at this
   layer rather than trusted to the provider, since
   `DevMarketDataProvider` — unlike `SahmkClient` — does not validate
   it itself, and consumer-facing behavior must not depend on which
   provider happens to be selected),
   `GET /{symbol}/history` (DB-backed via the existing
   `ohlcv_loader.load_price_bars`, optional `start`/`end`; an empty
   `bars` list is a valid 200, not an error, for a symbol with nothing
   ingested yet), `GET /{symbol}/technical` (runs the existing
   `TechnicalAnalysisEngine` over DB-loaded bars; a `422
   insufficient_data` if fewer than the engine's own 35-bar minimum),
   and `GET /{symbol}/fundamentals` (runs the existing
   `FundamentalAnalysisEngine` over DB-loaded facts plus a live quote
   for valuation ratios — a provider outage degrades only the
   price-dependent ratios to `None`, it never fails the whole
   response).
2. **`src/api/exceptions.py` + `error_handlers.py`** (new) — one
   consistent error JSON shape (`{"error": {"code", "message"}}`) for
   every API-layer exception (`stock_not_found` 404,
   `insufficient_data` 422, `invalid_symbol_format` 422,
   `provider_unavailable` 503), so a frontend can branch on `code`
   rather than parse message text.
3. **`src/api/schemas/stocks.py`** (new) — every schema carrying
   provider-sourced data (`QuoteOut`, `FundamentalAnalysisOut`) keeps
   `source`/`is_synthetic`, the same honesty discipline
   Dev/SahmkMarketDataProvider already enforce, all the way to the
   HTTP response. Disclosed gap: `PriceBar` has no
   `source`/`is_synthetic` columns (unlike `FundamentalSnapshot`), so
   `/history` cannot currently tell a caller whether an already-
   ingested bar came from real or synthetic data — a schema migration,
   not done in this milestone.
4. **`main.py`** — routes mounted, `register_error_handlers(app)`
   called, and `CORSMiddleware` added only when `CORS_ALLOWED_ORIGINS`
   is explicitly set (empty/no cross-origin access by default, the
   same secure-by-default posture as `SAHMK_LIVE_DATA_ENABLED`).
5. **First API-level tests in this repository** — 19 new integration
   tests (`tests/integration/api/`) using `fastapi.testclient.TestClient`
   against an in-memory SQLite DB (`StaticPool`, so every session in a
   test shares one database — plain `sqlite:///:memory:` gives each
   connection its own isolated database, which silently breaks the
   moment a route's session is different from the seeding session) and
   `app.dependency_overrides` swapping in `Dev*Provider` instances
   directly rather than routing through `provider_factory`'s real
   network-aware selection (hermetic — no env-var dependence, no risk
   of that module's process-wide cache leaking across test files).
   Covers every route's success path, 404/422/503 error paths, the
   empty-history-is-not-an-error case, growth ratios needing a prior
   period, and a provider outage degrading gracefully rather than
   failing. `TestClient(app)` is deliberately never entered as `with
   TestClient(app) as c:` — that would run `main.py`'s startup
   lifecycle (Redis message bus, DB kernel init), infrastructure these
   routes don't need and this environment doesn't have running.
   1057 tests pass repo-wide.

## Completed: Ingestion scheduler (automatic SAHMK → DB sync)

1. **`src/market_data/ingestion/scheduler.py`** (new) — `IngestionScheduler`
   owns four independent `asyncio.Task` loops (symbols, historical OHLCV,
   fundamentals, dividends), each simply `await run, then await
   sleep(interval)` — strictly sequential by construction, so a job can
   never overlap with its own previous run and no lock is needed to
   prevent that. A slow or failing job never blocks another job's
   schedule. `run_ingestion_job()` wraps every run: writes a `RUNNING`
   `IngestionRunLog` row immediately, retries the whole job with
   exponential backoff on an uncaught exception (job-level retry — distinct
   from `SahmkClient`'s own per-HTTP-request retry), and always updates the
   same row in place with the final status/timing/counts, never raising —
   one job's total failure can't crash the scheduler or stop the other
   three loops. `_NonDisconnectingProviderProxy` suppresses
   `authenticate()`/`disconnect()` on the shared, cached provider instance
   from `provider_factory`/`fundamental_provider_factory` (each ingestion
   function calls both, correct for a caller that owns a provider for one
   run, wrong for a shared cache other callers still depend on), while
   still forwarding every other call, including provider-specific "extra"
   methods not on the formal interface (`get_dividends`,
   `get_symbol_directory`).
2. **`src/market_data/ingestion/ingest_historical_ohlcv.py`,
   `ingest_symbols.py`, `ingest_dividends.py`** (new) — join the
   pre-existing `ingest_ohlcv.py`/`ingest_fundamentals.py` from M2.1.
   Historical OHLCV is incremental: for a symbol with no bars yet it
   backfills `INGESTION_OHLCV_BACKFILL_DAYS` (default 90) days; for a
   symbol with existing bars it only fetches the gap since the latest
   stored bar (`func.max(PriceBar.timestamp)`), so steady-state runs are
   cheap. Symbol sync optionally discovers SAHMK's full company directory
   in one request (`INGESTION_AUTO_DISCOVER_SYMBOLS`) and merges it with
   the configured explicit universe; dividend ingestion is a no-op (logged,
   not an error) against any provider that doesn't implement
   `get_dividends` (`DevMarketDataProvider` does not). Every job isolates
   per-symbol failures — one bad symbol never aborts the batch — and every
   write goes through an idempotent upsert keyed on each table's unique
   constraint (`PriceBar(stock_id, timeframe, timestamp)`,
   `FundamentalSnapshot(stock_id, period_type, fiscal_period_end)`,
   `Dividend(stock_id, ex_date)`), so duplicate prevention and safe re-runs
   fall out of the schema, not job-level bookkeeping.
   **`src/market_data/ingestion/_common.py`** (new) factors
   `IngestionResult`/`get_or_create_stock`/`upsert_price_bar` out of the
   original two jobs (behavior-preserving refactor) so all four jobs share
   one implementation instead of duplicating it.
3. **`src/market_data/sahmk/rate_limiter.py`** (new) — `SahmkRateLimiter`,
   a sliding-window limiter (`SAHMK_MAX_REQUESTS_PER_MINUTE`, default 20;
   optional `SAHMK_MAX_REQUESTS_PER_DAY`) shared as a process-wide
   singleton across every `SahmkClient` instance, since SAHMK's quota is
   per-API-key/account, not per client object. `SahmkClient._request()`
   calls `acquire()` before the circuit-breaker-wrapped retry logic —
   deliberately outside the circuit breaker's view, the same reasoning
   already applied to business errors, so being throttled can never be
   mistaken for an infrastructure failure and trip the breaker.
4. **`src/domain/models/dividend.py`, `ingestion_run_log.py`** (new) +
   migration `ff4223acbe72` — `Dividend` (unique on `(stock_id, ex_date)`)
   and `IngestionRunLog` (`job_name`, timing, symbols
   requested/succeeded/failed, `rows_upserted`, `retry_count`, `status`,
   `error_summary`) both carry the same `source`/`is_synthetic` honesty
   discipline as `FundamentalSnapshot`.
5. **`src/market_data/ingestion/config.py`** (new) — every scheduler
   behavior is environment-configurable and secure/inert by default:
   `INGESTION_SCHEDULER_ENABLED` defaults to `false` (matching
   `SAHMK_API_KEY`/`CORS_ALLOWED_ORIGINS`'s existing opt-in posture), with
   per-job intervals, backfill window, auto-discovery, fundamentals period
   type, and job-level retry policy all overridable. See `.env.example`
   for the full list.
6. **`main.py`** — starts the scheduler in `startup_event()` only when
   enabled, in its own independent `try`/`except` block that runs before
   the Redis/kernel section, so a scheduler failure can't block kernel
   startup and vice versa; stops it cleanly in `shutdown_event()`. New
   `GET /ingestion/status` reports whether the scheduler is running and
   the most recent run (status, timing, row counts) of each job, so
   "is the database still syncing" doesn't require grepping logs.
7. **Tests** — unit tests for the rate limiter, scheduler (proxy behavior,
   `run_ingestion_job` success/partial/failure/retry paths, task
   lifecycle, exception survival), all four ingestion jobs, and config
   parsing; an integration suite
   (`tests/integration/test_ingestion_e2e.py`) proving the full pipeline
   against real `Dev*Provider`s and a real in-memory DB — empty database
   to fully populated, idempotent re-runs producing no duplicates, and a
   provider outage failing its own job without corrupting previously
   ingested data — plus `tests/integration/api/test_ingestion_status.py`
   for the new status endpoint. One notable test bug caught and fixed
   along the way: `run_ingestion_job`'s `retry_count` was originally
   computed inside the generic `except` handler using the
   currently-failing attempt number, so a later successful attempt could
   leave it at a stale value instead of reflecting the total retries
   before the final outcome — moved to be set exactly once, at the point
   of final success or exhausted-retries failure. **1151 tests pass,
   12 skipped, repo-wide.**
8. **Disclosed gaps** — the scheduler's symbol universe is a fixed,
   explicitly configured list by default (`INGESTION_SYMBOL_UNIVERSE`,
   defaulting to 5 well-known Tadawul symbols); full-market auto-discovery
   exists (`INGESTION_AUTO_DISCOVER_SYMBOLS`) but has not been exercised
   against the live SAHMK API in this milestone, only against
   `DevMarketDataProvider`/mocked SAHMK responses in tests. Corporate
   actions (as opposed to dividends specifically) are still not ingested.
   With `INGESTION_SCHEDULER_ENABLED=true` and a valid `SAHMK_API_KEY`,
   the database now stays synchronized with SAHMK automatically —
   symbols, historical OHLCV, fundamentals, and dividends — without any
   manual ingestion step; with no key set it ingests synthetic
   `DevMarketDataProvider`/`DevFundamentalDataProvider` data on the same
   schedule instead, which is inert but not harmful.

## Completed: Recommendation & Confidence Engine

1. **`src/analysis/recommendation/`** (new) — an orchestration layer,
   deliberately *not* a third analysis engine: it never computes an
   indicator or a ratio itself, it only combines outputs
   `TechnicalAnalysisEngine` (M2.2) and `FundamentalAnalysisEngine`
   (M2.3) already produced, both reused completely unmodified.
   - **`types.py`** — `Recommendation` (`STRONG_BUY`/`BUY`/`HOLD`/
     `SELL`/`STRONG_SELL`), `Signal` (one human-readable observation,
     with a `direction` and a point `impact`), `ScoreContribution` (one
     module's 0-100 score/weight/confidence/signals — `score=None`,
     `weight=0.0` when that module had nothing to work with, the same
     honesty-by-omission discipline `RatioOutput.value=None` already
     uses), `AnalysisContext` (everything available for one symbol:
     `technical_result`, `fundamental_result`, plus a free-form `extra`
     bag), and the `ScoreContributor` protocol every scoring module
     implements.
   - **`technical_contributor.py`** — reads only
     `TechnicalAnalysisResult`'s already-computed indicators (never
     touches a DataFrame). Six always-computable indicators (RSI,
     MACD, Supertrend, EMA-vs-SMA momentum, OBV trend, volume trend)
     drive the score; ADX (trend strength, not direction) only adjusts
     confidence; candlestick patterns add a capped contribution;
     Bollinger Band width is reported as an informational, zero-impact
     signal (volatility context, not a directional call).
   - **`fundamental_contributor.py`** — reads only
     `FundamentalAnalysisResult`'s named ratio properties. Eight ratios
     across profitability (ROE, net margin), liquidity (current
     ratio), leverage (debt-to-equity), valuation (P/E, P/B — skipped,
     not penalized, when a company is loss-making and P/E is not
     meaningful), and growth (revenue, EPS) drive the score; any `None`
     ratio is simply skipped, lowering confidence rather than raising.
   - **`recommendation_engine.py`** — `RecommendationEngine.generate(context)`
     blends every contributor's score by weight into a 0-100
     `final_score`, maps it to a `Recommendation` via fixed thresholds
     (`>=75` Strong Buy, `>=60` Buy, `>40` Hold, `>25` Sell, else Strong
     Sell), and computes confidence as coverage (how many of the
     nominal contributors actually had data) times each module's own
     confidence, adjusted by an explicit agreement/disagreement
     heuristic — modules landing close together raise confidence,
     modules pulling opposite directions lower it. Builds a
     human-readable explanation citing the recommendation, both
     component scores, any unavailable module, and the top 5
     highest-impact signals.
2. **Extension point, exercised, not just asserted** — `generate()`'s
   signature never changes when a module is added: unit tests
   construct a third fake `news_sentiment`-style contributor and
   confirm the engine blends it correctly with zero engine-code
   changes, proving out the stated design goal for future modules
   (news sentiment, insider trades, macro indicators, an AI reasoning
   layer) ahead of any of them existing.
3. **`GET /api/v1/stocks/{symbol}/recommendation`** (new route in the
   existing `src/api/routes/stocks.py`) — assembles `AnalysisContext`
   from the same DB-backed price bars and fundamental snapshots
   `/technical` and `/fundamentals` already use, plus a live quote for
   valuation ratios. Each leg degrades independently and gracefully,
   exactly like the existing routes: insufficient price history or no
   ingested fundamentals only drops that one leg's score/weight
   (confidence reflects the reduced coverage); a market-data-provider
   outage only drops the price-dependent valuation ratios. Only a
   symbol with *neither* leg available is a 422
   (`insufficient_data`) — a recommendation built from zero inputs
   would not be an honest 200. New `RecommendationOut`/
   `ScoreContributionOut`/`SignalOut` schemas in
   `src/api/schemas/stocks.py`.
4. **Tests** — 74 unit tests (`tests/unit/analysis/recommendation/`):
   both contributors' scoring rules built from hand-constructed
   `TechnicalAnalysisResult`/`FundamentalAnalysisResult` values (so
   each bucket/threshold is exercised deterministically, independent
   of how a real price series happens to make RSI/MACD/etc. come out),
   and the engine's blending/confidence/threshold/explanation/
   pluggability logic tested against small fake contributors, isolated
   from either real module. Plus 6 integration tests
   (`tests/integration/api/test_recommendation_route.py`) against real
   engines, a real in-memory DB, and Dev providers: both legs
   available, 404 for an unknown symbol, each leg degrading
   independently, the 422 all-unavailable case, and a provider-outage
   valuation degradation. **1231 tests pass, 12 skipped, repo-wide.**
5. **Disclosed gaps** — the scoring rules (thresholds, point values,
   confidence weighting) are a reasonable, explainable first cut, not
   a backtested or ML-derived model; no historical validation of
   recommendation accuracy has been done. The confidence-scoring
   agreement/disagreement adjustment is a heuristic, not a statistically
   calibrated measure. News sentiment, insider trades, macro
   indicators, and an AI reasoning layer are architecturally supported
   (the `ScoreContributor` extension point) but not implemented.

## Completed: AI Decision Intelligence Layer

1. **`src/analysis/decision/`** (new) — sits above `TechnicalAnalysisEngine`,
   `FundamentalAnalysisEngine`, and `RecommendationEngine` (which
   already includes confidence scoring) by calling
   `RecommendationEngine.generate()` as a black box, not by
   duplicating its blending/confidence math. `RecommendationEngine`
   is configured with an expanded, nine-module contributor list —
   the existing Technical/Fundamental contributors plus five new ones
   satisfying the *same*, unmodified `ScoreContributor` protocol
   `RecommendationEngine` already supported (the exact extension point
   that milestone was built for):
   - **`contributors/momentum_contributor.py`** / **`volume_contributor.py`**
     — read the same `TechnicalAnalysisResult` series
     `TechnicalScoreContributor` reads, but score genuinely different
     facts from them, so nothing is double-counted: RSI/MACD-histogram
     *velocity* (rate of change over the last 5 bars, not level) and
     ADX trend-strength magnitude (previously used only to adjust
     `TechnicalScoreContributor`'s confidence, never scored) for
     Momentum; OBV flow *acceleration* and a volume-vs-its-own-baseline
     surge check for Volume.
   - **`contributors/risk_contributor.py`** — scores ATR(14)-to-price
     and Bollinger Band width-to-price, two measurements no existing
     contributor scores at all. Sign convention is deliberately
     inverted from every other contributor (positive = low risk,
     favorable): elevated volatility is treated as reducing conviction
     regardless of direction. The same measurements also set
     `InvestmentDecision.risk_level` directly, so risk is never only
     folded into the score.
   - **`contributors/external_factor_contributors.py`** — News
     Intelligence, Macro Economy, Insider Transactions, Sector
     Rotation: requirement 5's remaining future-module list, proven
     concretely rather than only architecturally. No real vendor is
     contracted for any of the four (same disclosed-gap status
     `SaudiMarketDataProvider` had before SAHMK), so each reads its
     input from `AnalysisContext.extra` (a new, additive, optional
     field alongside a new `latest_price` field — both backward
     compatible, no existing contributor reads either) and honestly
     reports itself unavailable when its key is absent, exactly like
     `FundamentalScoreContributor` already does for a missing ratio.
     Unit tests supply fake `extra` data and confirm each scores it
     correctly, proving the plug-in point works end-to-end today, not
     just in principle.
   - **`ai_decision_engine.py`** — `AIDecisionEngine.decide(context)`
     calls `RecommendationEngine` once, then derives everything only
     this layer produces from the result plus one live/derived price:
     an ATR-multiple target price and stop loss (reward distance
     scales with conviction, 2x-4x ATR; stop fixed at 1.5x ATR — a
     standard, documented technical-analysis convention, not
     fabricated), a time horizon (short/medium/long, from conviction
     and confirmed trend strength), a risk level (from the Risk
     contributor's own score), a position-size recommendation (from
     recommendation strength, discounted for low confidence or
     elevated risk), plain-language reasons (the top signals by
     impact, any unavailable module disclosed, a closing risk/sizing
     statement), and a category-level explainable breakdown —
     "Technical Analysis: +35", "Risk: -6", etc. — matching the
     requested format exactly (each contributor's 0-100 score
     re-centered on its 50-point neutral baseline).
2. **`GET /api/v1/stocks/{symbol}/decision`** (new route in the
   existing `src/api/routes/stocks.py`) — the assembly logic shared
   with `/recommendation` (load price bars, fundamental snapshots, a
   live quote) was factored into one `_build_analysis_context()`
   helper both routes call, rather than duplicated between them; the
   only behavior change is `/recommendation` now always attempts a
   live quote (previously only when fundamentals existed), so
   `AnalysisContext.latest_price` is populated whenever possible for
   `/decision`'s target-price math too. Same graceful-degradation and
   422-only-when-both-legs-unavailable rules as `/recommendation`,
   since `/decision` runs the same two engines first. New
   `InvestmentDecisionOut`/`DecisionFactorBreakdownOut` schemas in
   `src/api/schemas/stocks.py`.
3. **Tests** — 78 unit tests (`tests/unit/analysis/decision/`):
   Momentum/Volume/Risk contributors built from hand-constructed
   `TechnicalAnalysisResult` values (deterministic, independent of how
   a real price series happens to come out); the four external-factor
   contributors covering both the unavailable-by-default path and the
   scored-when-data-is-supplied path; `AIDecisionEngine` orchestration
   tests (target/stop direction and conviction scaling, risk-level
   thresholds, position-size downgrades, time-horizon rules, breakdown
   point-centering, reasons content) built against small fake
   contributors, isolated from the real scoring rules. Plus 6
   integration tests (`tests/integration/api/test_decision_route.py`)
   against real engines, a real in-memory DB, and Dev providers.
   **1315 tests pass, 12 skipped, repo-wide.**
4. **Disclosed gaps** — target price/stop loss/expected return use a
   documented ATR-multiple heuristic, not a backtested or
   statistically calibrated model. Time horizon, risk level, and
   position size are rule-based, not portfolio-aware (no existing
   position, cash balance, or diversification is considered — there is
   no portfolio/watchlist model in this codebase yet). "One decision
   per stock" is satisfied per-symbol (the engine is symbol-agnostic,
   like every engine below it); a batch/universe-wide execution
   endpoint does not exist, though it would reuse the ingestion
   scheduler's symbol-universe pattern (`src/market_data/ingestion/config.py`)
   if built. Portfolio Optimizer and a genuine AI Reasoning layer
   (requirement 5's remaining two items) are not implemented — a
   portfolio optimizer's natural input is a *list* of
   `InvestmentDecision`s across symbols, a different interface shape
   than the per-symbol `ScoreContributor` extension point this layer
   uses, so it is a disclosed, deliberately out-of-scope extension
   point rather than a stub.

### Extended (Phase 11) — Stochastic/VWAP/Fibonacci/Support-Resistance/
### Volume Profile wired into the decision engine

The 5 Phase-11 technical indicators (see the M2.2 extension entry above)
were computed but unused by any scoring path until this update. Now:

- **`technical_contributor.py`** scores Stochastic %K alongside RSI (a
  7th core signal, smaller point weights than RSI since the two
  oscillators are correlated and must not double-count).
- **`contributors/price_structure_contributor.py`** (new) — support/
  resistance proximity (including breakout/breakdown when price clears
  every detected level) and Fibonacci-retracement proximity
  (direction-aware: an uptrend's level reads as support, a downtrend's
  as resistance). Weight 0.08.
- **`contributors/value_area_contributor.py`** (new) — price vs. VWAP
  and price vs. the Volume Profile's point of control (institutional
  "fair value" positioning). Weight 0.07.
- **`risk_contributor.py`** gained a 3rd signal: resistance *headroom*
  (tight room to the nearest resistance = elevated near-term risk,
  independent of the recommendation's direction) — deliberately
  distinct from `PriceStructureScoreContributor`'s resistance-proximity
  signal, which scores direction, not risk.
- **`AIDecisionEngine.default_contributors()`** now returns 11
  contributors, not 9; every existing weight was proportionally trimmed
  so the total still sums to 1.0 rather than letting the two new
  modules dilute the blend silently — Technical/Fundamental remain the
  two largest weights by a wide margin ("no single indicator dominates
  the decision").
- **Entry/stop/target refinement**: `_compute_price_targets()`'s
  ATR-based stop loss and target price are now nudged toward a real
  support/resistance level when one falls inside the ATR-derived range
  — the stop tightens to just beyond a level price has actually
  respected before, and the target caps just short of a level price has
  struggled to clear before, rather than projecting a pure ATR multiple
  through it. Falls back to the unrefined ATR-only values when no level
  sits in range. The adjustment (with which level and why) is appended
  to `InvestmentDecision.reasons`, e.g. "target price capped just below
  the nearest resistance at 87.54" — verified with a live end-to-end
  run against synthetic OHLCV, not only unit tests.
- **Explainability got these signals for free**: `src/analysis/analyst/`
  (`EvidenceCollector`, `SignalInterpreter`, etc.) reads `Signal`/
  `DecisionFactorBreakdown` generically by source key, falling back to
  a title-cased label for any source not in `CATEGORY_LABELS` — the two
  new contributors' signals flow through bullish/bearish factor
  interpretation, conflict resolution, and narrative generation with
  zero changes to that framework, exactly the extension point it was
  built for.
- **Scan/Watchlist/Opportunities/Portfolio** all consume
  `AnalystReport.decision` (`market_intelligence/scanner.py` ->
  `AnalystEngine.analyze()` -> `AIDecisionEngine` ->
  `RecommendationEngine`; `portfolio_intelligence/portfolio_engine.py`
  the same path) — verified unaffected (186 tests green) since none of
  them hardcode the contributor set; they read `DecisionFactorBreakdown`
  by category label generically.
- `src/backtesting/calibration/parameters.py`'s `_CONTRIBUTOR_CLASSES`
  registry (a second, independent place that names every contributor
  class, for calibration-candidate weight overrides) had to be updated
  too — this was a real, caught gap: without it, a calibration
  candidate could never touch `price_structure`/`value_area` weights,
  silently.
- Full pytest suite green (2089 passed, 3 skipped pre-existing/
  unrelated), flake8 clean.
- Superseded by the next entry: Fibonacci/support-resistance/VWAP/
  Volume-Profile now influence `time_horizon`/`position_size`/entry
  timing/stop/target/risk-reward/confidence directly, not only through
  the blended score.

### Extended (Phase 11) — price structure drives Entry Quality, Time
### Horizon, Position Size, Stop/Target basis, Risk/Reward, Confidence

The prior entry left one gap: Fibonacci/support-resistance/VWAP/Volume
Profile only reached the final decision indirectly, through
`PriceStructureScoreContributor`/`ValueAreaScoreContributor`'s blended
score. This update makes them decision-layer facts in their own right,
each one a real conditional on the underlying indicator values (no
constant/random adjustment):

- **`EntryQuality` (new enum: POOR/FAIR/GOOD/EXCELLENT)** —
  `_derive_entry_quality()` answers "is *this* price a good entry for
  the recommended direction right now," reusing the exact same support/
  resistance/Fibonacci/VWAP/Volume-Profile facts the two Phase-11
  contributors already score, applied to a distinct decision-layer
  question a blended score can't answer (a STRONG_BUY can still be a
  POOR entry if price already ran up to just under resistance). ±15 pts
  for buying/selling right at a support/resistance level (direction-
  aware), ±10 pts for Fibonacci proximity (favorable only when the
  retracement direction agrees with the recommended direction), ±10/+5
  pts for VWAP extension vs. fair-value positioning, +5 pts for Volume
  Profile point-of-control proximity; thresholds map the resulting
  score to the enum.
- **`_derive_time_horizon()`** now caps the horizon at `SHORT_TERM`
  whenever price sits within 1.5% of any detected support/resistance/
  Fibonacci level, regardless of how strong the underlying conviction
  or ADX trend reading otherwise looks — a decision point right at hand
  is likely to resolve before a multi-month thesis could play out.
- **`_calibrate_confidence()` (new)** — a small adjustment layer on top
  of `RecommendationEngine`'s blended confidence: ±3 pts for whether
  price is on the "right side" of VWAP for the recommended direction
  (intraday positioning), ±3 pts for whether price sits in a thin
  (illiquid) or thick (liquid) Volume Profile bin relative to the
  average bin. Clamped to [0, 100].
- **`_derive_position_size()`** gained two new inputs: a POOR
  `entry_quality` or a weak risk/reward ratio (< 1.0) each shrink the
  size by one step; an EXCELLENT entry quality combined with a strong
  risk/reward ratio (>= 2.0) can grow it by one step — but never for a
  HOLD (guarded explicitly: HOLD always stays at `PositionSize.NONE`
  regardless of entry quality/reward ratio, since HOLD means "no new
  position warranted").
- **Stop/target basis is now typed and explained**: `_refine_with_key_levels()`/
  `_compute_price_targets()` return `stop_loss_basis`/`target_price_basis`
  (`"atr" | "support_level" | "resistance_level"`) alongside the
  refined values, threaded onto `InvestmentDecision` and into the REST
  response — "why is the stop/target here" is answerable both
  structurally and in prose.
- **`risk_reward_ratio` (new field)** — `abs(target - price) /
  abs(price - stop)`, computed once the ATR/key-level refinement has
  settled; feeds both position sizing and the explanation.
- **Explainability**: `NarrativeBuilder.build_target_price_explanation`/
  `build_stop_loss_explanation` now cite the real basis ("capped just
  below a nearby resistance level..." vs. "...average true range"),
  the entry quality rating and its notes, and the risk/reward ratio.
  `build_time_horizon_explanation` cites the nearby key level when it
  capped the horizon. `build_risk_explanation` cites how entry quality/
  risk-reward affected sizing. All four read real `InvestmentDecision`
  fields, never re-derive or duplicate the decision itself.
- `InvestmentDecisionOut`/`AnalystReportOut` REST schemas and their
  route constructions gained the six new fields (`entry_quality`,
  `entry_quality_notes`, `risk_reward_ratio`, `stop_loss_basis`,
  `target_price_basis`, `confidence_calibration_notes`).
  `market_intelligence/read_model.py` reconstructs `risk_reward_ratio`
  honestly from persisted target/stop/latest-price columns; the other
  five fields stay at `InvestmentDecision`'s honest defaults for a
  reconstructed record since the DB schema never captured the
  intermediate support/resistance/Fibonacci/VWAP state needed to derive
  them after the fact — not a fabrication, a disclosed gap.
- All new fields are defaulted on `InvestmentDecision`/`AIDecisionTuning`
  so the existing keyword-only construction sites (`read_model.py`,
  3 test fixture files) needed no changes beyond the one honest
  `risk_reward_ratio` addition.
- Verified with a live end-to-end run against synthetic OHLCV through
  the real `TechnicalAnalysisEngine` + `AIDecisionEngine`, not only unit
  tests: e.g. `risk_reward_ratio: 0.47`, `stop_loss_basis: atr
  target_price_basis: resistance_level`, reasons citing "entering
  against the 23.6% Fibonacci retracement level -- weaker timing" and
  "price sits in a high-volume (liquid) zone of the volume profile --
  liquidity confidence boosted."
- New tests: 39 new cases in `test_ai_decision_engine.py` covering every
  branch of `_derive_entry_quality`/`_derive_time_horizon`'s key-level
  override/`_calibrate_confidence`/`_derive_position_size`'s new
  branches (including a dedicated regression test proving HOLD never
  receives a position size regardless of entry quality/reward ratio),
  plus end-to-end field population via `decide()`; 17 new cases in
  `test_narrative_builder.py` covering every new explanation clause.
  Full pytest suite green (2142 passed, 3 skipped pre-existing/
  unrelated), flake8 clean.
- **Remaining gaps**: `_derive_entry_quality`'s point weights (±15/±10/
  ±5) and `_calibrate_confidence`'s ±3-point adjustments are documented
  heuristics, not backtested/calibrated against historical outcomes —
  the Backtesting & Calibration Engine could validate/tune them the same
  way it already validates `AIDecisionTuning`'s ATR multiples, but that
  calibration run has not been executed. Volume Profile's liquidity
  read is still the same daily-bar approximation noted at its original
  introduction (no true intrabar volume-at-price data).

## Completed: Backtesting & Calibration Engine

Full detail in `docs/BACKTESTING_AND_CALIBRATION.md`; summary here.

1. **`src/backtesting/`** (new package) — `BacktestingEngine` evaluates
   one symbol, a group of symbols, or a bounded full universe over a
   historical period at a configurable evaluation frequency, using
   only already-ingested database data (never a live provider call).
   `data_access.py` is the anti-look-ahead boundary: price bars are
   read with a hard `end=as_of` cutoff, fundamentals with an
   additional configurable reporting-lag buffer, both backed by
   regression tests that fail loudly on a leak. `metrics.py` is a
   pure, independently-tested statistics module (direction accuracy,
   target/stop hit rates, win/loss/profit factor, max drawdown,
   volatility, Sharpe/Sortino, Expected Calibration Error, and
   breakdowns by recommendation/confidence/risk/horizon/sector/symbol/
   regime). `baselines.py` provides transparent comparison strategies
   (buy-and-hold, SMA-crossover, RSI-only, technical-only,
   fundamental-only, uncalibrated AI decision engine) alongside the
   real `AIDecisionEngineStrategy`, all through one `Strategy`
   protocol. `walk_forward.py` splits a date range into rolling/
   expanding (train, validation) windows plus a reserved, untouched
   test period, structurally guaranteeing no window ever overlaps it.
2. **Reused, not duplicated**: `TechnicalAnalysisEngine`,
   `FundamentalAnalysisEngine`, `RecommendationEngine`,
   `AIDecisionEngine`, and every `ScoreContributor`, called exactly as
   the live `/recommendation`/`/decision` routes already do. Two small,
   additive, backward-compatible extensions were made so calibration
   could be genuinely functional: `PriceBar` gained `source`/
   `is_synthetic` columns (both providers already returned them;
   `upsert_price_bar` was discarding them -- migration `9d260aefc6a7`),
   `load_fundamental_snapshots` gained an optional `as_of` parameter,
   and `RecommendationEngine`/`AIDecisionEngine` gained an optional
   `tuning` object whose defaults exactly reproduce their prior
   hardcoded constants (locked in by regression tests).
3. **`src/backtesting/calibration/`** — `CalibrationEngine` implements
   the full propose → validate → activate → rollback lifecycle against
   a new `CalibrationConfig` model. `validate()` runs the candidate and
   the currently-active configuration (or engine defaults) through
   `BacktestingEngine` over the identical validation period and applies
   an explicit anti-overfitting guard: a candidate is only `VALIDATED`
   if it does not regress direction accuracy **and** does not
   materially worsen max drawdown, even when the primary metric
   improved -- otherwise `REJECTED` with the reason recorded. At most
   one configuration is `ACTIVE` at a time; activating a new one marks
   the previous `SUPERSEDED`; `rollback()` is always an explicit,
   auditable call. Not wired into the live production routes this
   milestone (disclosed).
4. **New domain models + migration `9d260aefc6a7`**: `RecommendationSnapshot`
   (the durable, auditable record of one historical AI decision --
   every score, target/stop, provenance field, and engine/calibration
   version, upserted idempotently), `BacktestRun` (configuration,
   status, progress, metrics), `CalibrationConfig`.
5. **REST API** (`src/api/routes/backtests.py`, `calibrations.py`) --
   `POST /api/v1/backtests` schedules a FastAPI `BackgroundTask` and
   never blocks on the run itself; idempotent (an identical request
   returns the existing run); rejects a second large-scope run while
   one is already in flight. `GET .../status`, `/metrics`, `/trades`
   (paginated), `/confidence-calibration`, `/comparison`; calibration
   CRUD plus `/validate`, `/activate`, `/rollback`. Bounded symbol
   counts and date ranges throughout, all env-var configurable.
6. **Tests** -- 154 unit tests under `tests/unit/backtesting/`
   (data access/anti-look-ahead, metrics, regime, baselines, engine,
   walk-forward, calibration parameters/engine, job runner), 12 domain
   model tests, 37 integration tests (REST routes for both routers,
   plus a full Alembic chain upgrade/downgrade/re-upgrade round-trip
   test against SQLite -- this repository's first migration test).
   Every metric formula, every anti-look-ahead boundary, every
   idempotency/retry/cancellation path, and the full calibration state
   machine has a deterministic regression test. **1531 tests pass, 12
   skipped, repo-wide** (up from 1315). `flake8 src/ tests/ main.py`
   is clean at 0 violations (7 pre-existing violations from earlier
   milestones were also fixed while here, restoring the CI-documented
   baseline).
7. **Disclosed limitations** -- no corporate-action price adjustment;
   fundamental "as of" uses a configurable reporting-lag approximation,
   not exact filing dates; market regime is per-symbol (no TASI index
   history is ingested -- `MarketSnapshot` remains unpopulated);
   drawdown/volatility/Sharpe/Sortino are computed on a discrete,
   equal-weighted trade-sequence equity curve, not a true portfolio
   simulation; an active calibration does not yet affect live
   production routes. **No live SAHMK network access exists in this
   environment -- every test in this milestone runs against synthetic,
   hand-seeded data; no metric value anywhere in this codebase's tests
   is a claim about real market performance.** Full detail, including
   exactly what remains before the Autonomous AI Analyst phase, in
   `docs/BACKTESTING_AND_CALIBRATION.md`.

### Extended (Phase 12) -- per-indicator attribution + statistically
### calibrated contributor weights

Full detail in `docs/BACKTESTING_AND_CALIBRATION.md` §5a/§5b; summary
here. Closes the last major gap named in requirement 4 of the Phase 11
milestone report: point weights inside the decision engine were still
purely heuristic, never measured against real replayed history.

- **`calibration/indicator_signals.py`** (new) -- eleven standalone,
  backtesting-only pure readers, one per named indicator (Fibonacci,
  Support/Resistance, VWAP, Volume Profile, RSI, MACD, ADX, EMA, SMA,
  Bollinger, ATR), deliberately independent of the live scoring
  contributors' internal functions so each indicator's own predictive
  power can be measured in isolation, not blended. Nine make a real
  BULLISH/BEARISH/NEUTRAL claim; ATR and Bollinger (non-directional in
  this codebase's own live risk scoring) get a volatility-ratio
  reading instead of a fabricated direction.
- **`calibration/indicator_attribution.py`** (new) -- replays the same
  anti-look-ahead (symbol, date) grid as `BacktestingEngine` (via a
  newly-shared `data_access.collect_as_of_evaluations()` primitive) and
  scores each directional indicator through the exact same
  `metrics.compute_all_metrics()` every other report in this engine
  uses (win rate, average return, drawdown, Sharpe, **precision/
  recall** and **calibration/confidence accuracy** -- both new, see
  below), plus a dedicated volatility-bucket report for ATR/Bollinger.
- **`metrics.py` gained two new metrics**: `precision_recall()`
  (standard binary-classification precision/recall, ground truth from
  the sign of the realized forward return) and
  `position_sizing_quality()` (buckets directional calls by their
  recorded `position_size`, reports win rate/average P&L per bucket
  plus a Pearson-correlation `monotonicity_score` -- does a larger size
  really earn a better outcome). `EvaluationOutcome` gained a
  `position_size` field; `engine.py`'s own outcome construction was
  fixed to actually populate it (a real, caught gap -- it was computed
  on every `StrategyCall` and persisted to `RecommendationSnapshot`,
  but silently dropped before reaching `EvaluationOutcome`).
- **`calibration/statistical_calibration.py`** (new) -- measures each
  of the eleven scoring contributors' own standalone directional edge
  over a training period (the same "one contributor, weight 1.0"
  technique two baseline strategies already used for two contributors,
  now generalized to all eleven), tests it with a dependency-free
  two-sided z-test (`statistics.NormalDist`, no scipy) against "no real
  edge," and proposes a new weight only when the evidence is
  significant **and** the sample size clears a floor (default 30) --
  non-significant or under-sampled contributors keep their *exact*
  existing weight, never drift from renormalization
  (`RecommendationEngine.generate()` already self-normalizes by
  whichever weights are present). The weight-proposal formula (a
  bounded, disclosed t-statistic-to-weight-multiplier scaling, capped
  at ±50%) is itself a heuristic -- disclosed as such, not fabricated
  precision; the significance *test* underneath it is not.
- **Report shape matches the requirement exactly**: every contributor
  gets old weight, new weight, mean edge, t-statistic, p-value, sample
  size, and an explicit action
  (`reweighted`/`unchanged_insufficient_evidence`/`unchanged_not_significant`)
  -- including the four external-factor contributors
  (news/macro/insider/sector-rotation), which honestly report zero
  sample size every time since no real feed for them exists in
  `data_access.AsOfDataset` (disclosed gap, not a fabricated result).
- **Reusable for continuous improvement**: `report.contributor_weights`
  is the exact JSON shape the *existing, unmodified*
  `CalibrationEngine.propose()` already accepts -- any later date range
  with newly ingested data can be re-run through
  `propose_statistical_weights()` to produce a fresh, independently
  re-validated candidate through the same propose -> validate ->
  activate -> rollback lifecycle. No new lifecycle infrastructure was
  built or needed.
- **REST API**: `POST /api/v1/calibrations/indicator-attribution` and
  `POST /api/v1/calibrations/statistical-weights` (the latter can
  create a `DRAFT` `CalibrationConfig` directly via
  `create_draft_calibration: true`), both staff-only, both bounded and
  synchronous like the existing `/validate` route.
- **Tests**: 83 new unit tests (indicator signals, indicator
  attribution, statistical calibration, the two new metrics, the
  shared grid-walk primitive, `position_size` passthrough regression),
  7 new integration tests for the two new routes. Full repo-wide suite:
  2232 passed, 3 skipped (pre-existing/unrelated), `flake8 src/ tests/
  main.py` clean at 0.
- **Remaining gaps**: the per-indicator `magnitude` scaling constants
  and the statistical weight-proposal edge-to-weight formula are
  themselves disclosed heuristics, not yet backtested/calibrated the
  way `AIDecisionTuning`'s ATR multiples already are; the four
  external-factor contributors need a real data source before they can
  ever be statistically calibrated; nothing from this milestone is
  wired into live production routes (an `ACTIVE` calibration still
  doesn't affect `/recommendation`/`/decision` -- an existing, already-
  disclosed gap from the original Backtesting & Calibration milestone,
  not new here).

## Completed: Autonomous AI Analyst Framework

Full detail in `docs/AUTONOMOUS_AI_ANALYST_FRAMEWORK.md`; summary here.
**Not an LLM integration** — no code in this codebase connects to
OpenAI, the Claude API, Gemini, or any other external AI model.

1. **`src/analysis/analyst/`** (new package) — twelve modules
   (`AnalystEngine`, `ReasoningPipeline`, `EvidenceCollector`,
   `SignalInterpreter`, `ConflictResolver`, `ConfidenceValidator`,
   `NarrativeBuilder`, `RecommendationComposer`, `ExplanationGenerator`,
   `PromptTemplateManager`, `LLMAdapter`, `OutputFormatter`) that turn
   an already-computed `InvestmentDecision` into a twelve-section,
   human-quality `Explanation` (investment summary; technical/
   fundamental/risk reasoning; bullish/bearish factors; confidence,
   target price, stop loss, and time horizon explanations; alternative
   scenarios; final recommendation rationale). Fully deterministic and
   template-based today — see point 3.
2. **Reused, not duplicated**: `AnalystEngine.analyze()` calls
   `AIDecisionEngine.decide()` as a black box, exactly as `/decision`
   already does — no score, target price, stop loss, confidence value,
   or risk level is computed anywhere in this new package. One small,
   additive, precedented rename enabled reuse: `ai_decision_engine.py`'s
   private `_CATEGORY_LABELS` became the public `CATEGORY_LABELS`, so
   `SignalInterpreter` doesn't redefine the same source-to-label
   mapping. No other pre-existing engine, contributor, route, or schema
   was modified.
3. **`LLMAdapter` is an abstract interface only** — `ReasoningPipeline`
   accepts an optional adapter; when none is supplied (the only
   configuration `AnalystEngine()`'s default construction ever uses),
   every section is produced by the deterministic pipeline, no network
   call occurs. The only implementation in this codebase is
   `NullLLMAdapter`, a no-op test double that echoes its prompt back,
   used solely to prove the extension point's wiring
   (`test_reasoning_pipeline.py`) without connecting to any real
   provider. If an adapter were ever injected, only three sections
   (technical/fundamental/risk reasoning) would be offered to it for
   rephrasing, always grounded in the already-computed deterministic
   baseline, which is kept whenever the adapter's result is empty.
4. **REST API** (`src/api/routes/stocks.py`) — `GET
   /api/v1/stocks/{symbol}/analyst-report`, reusing
   `_build_analysis_context()` unchanged (the same helper
   `/recommendation`/`/decision` already share). Same
   graceful-degradation and 422 rules. `format=json|markdown|text`
   query parameter exercises `OutputFormatter`'s three renderers.
5. **New schema**: `AnalystReportOut`
   (`src/api/schemas/stocks.py`) — every `InvestmentDecision` summary
   field plus all twelve `Explanation` fields plus
   `generated_at`/`engine_version`.
6. **Tests** — 78 unit tests under `tests/unit/analysis/analyst/` (one
   file per module, hand-built fixtures, zero real engine runs) plus
   8 integration tests
   (`tests/integration/api/test_analyst_report_route.py`, real FastAPI
   routing + real engines against in-memory SQLite + Dev* providers),
   including an explicit end-to-end proof that `ReasoningPipeline`
   correctly calls and falls back around an injected `LLMAdapter`.
   **1617 tests pass, 12 skipped, repo-wide** (up from 1531).
   `flake8 src/ tests/ main.py` is clean at 0 violations.
7. **Disclosed limitations** — no real LLM integration exists or is
   called; prose is template-based (a fixed set of named templates),
   not free-form generation; `join_factors()` lowercases only the
   joined clause's first character, not each factor, which can read
   slightly awkwardly when a factor begins with an acronym;
   `ConflictResolver`'s tension level is anchored specifically to the
   Technical-vs-Fundamental point spread, not a general N-way conflict
   metric; the "reference price" cited in target price/stop loss
   explanations is reconstructed from `target_price`/
   `expected_return_pct` (or a Bollinger midpoint fallback) since
   `InvestmentDecision` does not itself store the price it was computed
   against; no batch/multi-symbol report endpoint exists. **No live
   SAHMK network access exists in this environment — every test in this
   milestone runs against hand-built fixtures or synthetic, hand-seeded
   data; no text produced by any test is a claim about real market
   behavior.** Full detail in
   `docs/AUTONOMOUS_AI_ANALYST_FRAMEWORK.md`.

## Completed: Autonomous Market Intelligence Layer

Full detail in `docs/MARKET_INTELLIGENCE.md`; summary here.

1. **`src/market_intelligence/`** (new package) — continuously
   discovers opportunities across the entire tracked symbol universe
   without a user selecting a stock. `SymbolSelector` resolves every
   active, price-eligible `Stock`; `MarketScanner` runs the reused
   pipeline per symbol with bounded concurrency and per-symbol retry;
   `RankingEngine`/`WatchlistEngine` produce the 17 ranking categories
   and 9 watchlists via declarative filter/sort/predicate rules (no
   hand-duplicated logic per category); `SectorAnalyzer` computes
   per-sector aggregates, strongest/weakest, momentum, and rotation;
   `ChangeDetector` diffs a scan against the previous one's persisted
   records; `AlertEngine` produces `Alert` *objects only* (no
   notification/delivery mechanism exists); `MarketSnapshotBuilder`
   assembles market-wide sentiment; `MarketIntelligenceEngine`
   orchestrates all of it; `IntervalMarketIntelligenceScheduler`
   (behind the replaceable `IMarketIntelligenceScheduler` interface)
   provides recurring, unattended scans, disabled by default.
2. **Reused, not duplicated**: every symbol's analysis is exactly
   `AnalystEngine.analyze()` (itself `AIDecisionEngine` ->
   `RecommendationEngine` -> `TechnicalAnalysisEngine`/
   `FundamentalAnalysisEngine`, unmodified) called once per symbol --
   no score, target, confidence, or narrative is computed anywhere in
   this new package. One behavior-preserving refactor made this
   possible without duplicating the context-assembly logic: `stocks.py`'s
   private `_build_analysis_context` was extracted, unchanged, into
   the public `src.analysis.context_builder.build_analysis_context()`,
   reused by both the REST routes and the new scanner. Rankings and
   watchlists are computed on read from the persisted
   `SymbolIntelligenceRecord` rows (the single source of truth), never
   stored as separate materialized tables -- a deliberate choice
   against a stale-prone duplicate cache.
3. **New domain models + migration `bc03fb48f33b`**: `MarketScanRun`
   (scan history), `SymbolIntelligenceRecord` (per-symbol market
   snapshot), `SectorIntelligenceSummary` (needed for momentum's t-1
   comparison), `MarketAlert`, `MarketChangeEvent`.
4. **REST API** (`src/api/routes/market.py`) -- `POST
   /api/v1/market/scan` schedules a `BackgroundTask` and never blocks;
   `GET /scan/{run_id}`, `/summary`, `/rankings` (+`/top-buy`,
   `/top-strong-buy` convenience wrappers), `/watchlists`, `/sectors`,
   `/changes`, `/alerts` -- every GET route reconstructs
   `SymbolScanOutcome`s from persisted rows via
   `src.market_intelligence.read_model` and hands them to the exact
   same engines the scan itself used, so no ranking/watchlist/
   sentiment rule is duplicated between the write and read paths.
   Every read route defaults to the latest successful scan and returns
   404 `no_market_scan_data` when none exists yet.
5. **Tests** -- 90 unit tests under `tests/unit/market_intelligence/`
   (including 12 repository tests against real in-memory SQLite), 3
   unit tests for the extracted `build_analysis_context`, and 10
   integration tests (`tests/integration/api/test_market_routes.py`,
   a real background-task scan exercised end-to-end through every
   read route). **1720 tests pass, 12 skipped, repo-wide** (up from
   1617). `flake8 src/ tests/ main.py` is clean at 0 violations.
6. **Disclosed limitations** -- no real parallel scanning is exercised
   (`MARKET_SCAN_BATCH_SIZE` defaults to 1, architecture supports
   more); `new_symbols`/`removed_symbols` aren't persisted separately
   from the change-event log, a small gap between the live-scan and
   read-a-past-scan paths for the `NEW_OPPORTUNITIES` ranking;
   `REMOVED_OPPORTUNITIES` means "dropped out of BUY territory," not
   "vanished from the universe"; no corporate-action price adjustment
   or true portfolio model (inherited from the engines this layer
   reuses); sector breadth/momentum/rotation are per-scan aggregates
   only, not TASI-index-relative (no broad-market index history is
   ingested). **No live SAHMK network access exists in this
   environment -- every test in this milestone runs against hand-built
   fixtures or synthetic, hand-seeded data; no ranking/watchlist/
   alert/sentiment value anywhere in this codebase's tests is a claim
   about real market performance.** Full detail in
   `docs/MARKET_INTELLIGENCE.md`.

## Completed: Autonomous Portfolio Intelligence Layer

Full detail in `docs/PORTFOLIO_INTELLIGENCE.md`; summary here.

1. **`src/portfolio_intelligence/`** (new package) — reasons about an
   entire investment portfolio rather than isolated stocks.
   `HoldingAnalyzer`/`PortfolioEngine` orchestrate per-holding reuse of
   `AnalystEngine` plus ten portfolio-level engines:
   `AllocationEngine` (weight/market value), `ExposureEngine`
   (dollar-weighted sector exposure -- deliberately distinct from
   Phase 7's equal-weighted `SectorAnalyzer`), `DiversificationEngine`
   (Herfindahl-Hirschman-Index concentration + score), `RiskEngine`
   (real correlation matrix and volatility from ingested price
   history via Modern Portfolio Theory math -- `w^T Σ w` -- plus a
   drawdown estimate; portfolio beta is architecture-ready: the
   `cov/var` formula is implemented and unit-tested, but always
   returns `None` with a disclosed reason since no market/TASI index
   data is ingested), `CashManager` (target cash-reserve band),
   `PositionSizer` (per-holding increase/reduce/exit/hold),
   `RebalanceEngine` (full rebalance plan; new-buy opportunities reuse
   Phase 7's `RankingEngine`/`MarketIntelligenceRepository` directly,
   honestly empty when no market scan has ever run), `PortfolioScore`
   (0-100 health score), `OptimizationEngine` (prioritized
   recommendations), `RecommendationBuilder` (pure assembly).
2. **Reused, not duplicated**: every holding's analysis is exactly
   `AnalystEngine.analyze()` (unmodified), called once per held symbol
   via the same `build_analysis_context()` Phase 7 already extracted --
   no score, target, or narrative is computed anywhere in this new
   package. New-buy opportunities are the *same* `RankingEngine`
   output `GET /api/v1/market/top-buy` already serves, filtered to
   unheld symbols, never a re-implementation of "what counts as a buy."
3. **New domain models + migration `f2b3a2cfd231`**: `Portfolio`,
   `PortfolioHolding`, `PortfolioAnalysisSnapshot` (the durable analysis
   record -- named scalar columns plus a JSON blob with every
   summary field, never the full nested `AnalystReport` narrative per
   holding, the same discipline `SymbolIntelligenceRecord` already
   applies).
4. **REST API** (`src/api/routes/portfolio.py`) -- `POST
   /api/v1/portfolio/analyze` runs synchronously (no background job --
   a portfolio's holdings count is small and bounded by
   `PORTFOLIO_MAX_HOLDINGS`); `GET /{id}`, `/{id}/recommendations`,
   `/{id}/risk`, `/{id}/allocation`, `/{id}/diversification`,
   `/{id}/rebalance`, `/{id}/health` all read the latest persisted
   `PortfolioAnalysisSnapshot`, never re-running an analysis. Routes
   are scoped by portfolio ID in the path (`/{id}/risk`, not
   `/risk`), a disclosed, deliberate adherence to this codebase's own
   existing sub-resource routing convention.
5. **Tests** -- 66 unit tests under `tests/unit/portfolio_intelligence/`
   (including 11 repository tests against real in-memory SQLite), 17
   integration tests (`tests/integration/api/test_portfolio_routes.py`,
   a real synchronous analysis exercised through every route, plus a
   genuine cross-milestone reuse test sourcing new-buy opportunities
   from a real `POST /api/v1/market/scan`). **1803 tests pass, 12
   skipped, repo-wide** (up from 1720). `flake8 src/ tests/ main.py`
   is clean at 0 violations. Two real bugs were caught and fixed during
   self-review: a `numpy.float64` leaking through the volatility
   calculation into every downstream score (JSON/Pydantic-unsafe,
   fixed by casting to plain `float`), and
   `get_latest_analysis_snapshot()` ordering only by a caller-supplied,
   collision-prone timestamp (fixed to order by `id`, matching
   `MarketScanRun`'s existing tie-break convention).
6. **Disclosed limitations** -- portfolio beta is never computed
   against real market data (no TASI index history is ingested);
   drawdown assumes constant current-day weights applied
   retrospectively, not actual historical weight drift; a correlation
   cell with insufficient pairwise overlap is treated as 0 rather than
   left undefined; no user/ownership model exists yet (no auth
   anywhere in this codebase); new-buy opportunities are empty until a
   market scan has run at least once. **No live SAHMK network access
   exists in this environment -- every test in this milestone runs
   against hand-built fixtures or synthetic, hand-seeded data; no
   allocation/risk/diversification/health/recommendation value
   anywhere in this codebase's tests is a claim about real investment
   performance.** Full detail in `docs/PORTFOLIO_INTELLIGENCE.md`.

## Completed: Real News Intelligence Engine

Full detail in `docs/NEWS_INTELLIGENCE.md`; summary here.

1. **`src/news_intelligence/`** (new package) — collects, deduplicates,
   classifies, and scores news, then feeds the result into the
   **existing** AI Decision Engine rather than a second recommendation
   path. `NewsCollector` wraps the already-existing
   `IMarketDataProvider.get_market_news()` (real for `SahmkMarketDataProvider`
   via SAHMK's `/events/` endpoint, honestly synthetic for
   `DevMarketDataProvider`) in a `TTLCache`; `NewsAnalyzer` uses the
   already-existing `OpenAILLMClient` for entity recognition,
   20-category classification, 5-label sentiment, and short/medium/
   long-term + price/risk/volatility impact estimation, one LLM call per
   canonical article, never fabricating a result on failure (returns
   `None`, persisted as an honestly-unanalyzed event).
2. **Reused, not duplicated**: `context_builder.build_analysis_context()`
   — the one function `/recommendation`, `/decision`, `/analyst-report`,
   portfolio holding analysis, and market scan all already call — now
   populates `context.extra["news_sentiment"]` from a pure,
   network-free DB read (`NewsIntelligenceService.get_symbol_sentiment()`).
   Zero changes to any of those five call sites. The pre-existing
   `NewsSentimentScoreContributor`'s blended score/confidence formula is
   unchanged; it now emits one `Signal` per news event (for
   explainability) instead of a single aggregate signal, flowing through
   `AIDecisionEngine`'s already-existing top-signals explanation logic
   with zero changes to `ai_decision_engine.py` itself.
3. **Deduplication and idempotency**, two independent mechanisms: an
   `external_key` (hash of source + normalized headline + timestamp)
   unique constraint makes re-ingesting the same article a structural
   no-op; `difflib`-based headline-similarity matching merges syndicated/
   republished copies into their canonical event via `duplicate_of_id`
   — a duplicate is never independently analyzed and never increases
   `SourceReliabilityService`'s `articles_seen` count, directly
   implementing "duplicate news must not increase confidence."
4. **New domain models + migration `6a9ccaf29e1f`**: `NewsEvent`,
   `NewsEntity`, `NewsSourceReliability`, `PortfolioNewsAlert` (the last
   reuses the pre-existing `AlertSeverity` enum rather than redefining
   it).
5. **Portfolio integration**: `PortfolioNewsAlertEngine` re-evaluates
   held positions against newly analyzed news via a pure, confidence-
   gated classification function (`HIGH_RISK`/`MAJOR_OPPORTUNITY`/
   `UPGRADE`/`DOWNGRADE`), persisting idempotent alerts plus reusing the
   pre-existing `Notification(type=PORTFOLIO_ALERT)` model — no new
   notification infrastructure built.
6. **REST API**: `GET /api/v1/news/{symbol}`, `GET /api/v1/news/market`,
   `GET /api/v1/news/sources` (staff-only), `POST /api/v1/news/refresh`
   (staff-only, synchronous, bounded), `GET
   /api/v1/portfolio/{id}/news-alerts`, `POST
   /api/v1/portfolio/{id}/news-alerts/refresh` (both owner-scoped,
   404-not-403 for another user's portfolio).
7. **Tests** — 74 unit tests (`tests/unit/domain/models/
   test_news_intelligence_models.py`, `tests/unit/news_intelligence/`,
   plus new cases added to `test_external_factor_contributors.py` and
   `test_context_builder.py`), 36 integration tests
   (`tests/integration/api/test_news_routes.py`, new cases in
   `test_portfolio_routes.py`). **2329 tests pass, 3 skipped,
   repo-wide.** `flake8 src/ tests/ main.py` is clean at 0 violations.
8. **Disclosed limitations** — market-wide/government news is not yet
   blended into per-symbol decision-engine sentiment (only `COMPANY`
   entities matching the exact symbol are aggregated); source
   reliability is seeded neutral and only changes via manual staff
   override, no automated outcome-driven calibration yet; both refresh
   routes run synchronously rather than as background jobs; no
   scheduled/recurring refresh job exists (must be explicitly
   triggered); `Notification` rows are generated but not delivered
   (push/email/SMS), matching the platform's existing `MarketAlert`
   posture. **No live SAHMK or OpenAI network access exists in this
   environment — every test in this milestone runs against synthetic,
   hand-seeded data and a fake LLM client returning deterministic JSON;
   no sentiment/classification/impact value anywhere in this codebase's
   tests is a claim about real news content or real market reaction.**
   Full detail in `docs/NEWS_INTELLIGENCE.md`.

## Completed: Frontend Integration (News + Portfolio News Alerts)

An audit of every existing `frontend/src/app/(app)/*` screen found
Dashboard, Scan, Watchlist, Opportunities, Portfolio, AI
(Recommendations/Stock Details), Reports, and Strategies/Settings were
**already** fully wired to real `/api/v1/*` endpoints with zero mock
data (built across Phases 9–11). The one disclosed placeholder was
`frontend/src/lib/api/news.ts`, a stub that always returned
`{available: false}` because no `/api/v1/news/*` backend route existed
until this session's News Intelligence milestone. This milestone:

1. **News screen, rewired for real.** `news.ts` now calls the real
   `GET /api/v1/news/market` and `GET /api/v1/news/{symbol}` routes
   (`news-types.ts` mirrors `src/api/schemas/news.py` exactly). The
   screen (`news/page.tsx` + new `NewsScreenClient.tsx`) defaults to
   the market-wide/government feed and lets a user search a symbol,
   reusing the same `useCategoryFetch` hook pattern the Scan/Watchlist
   screens already established. Each card shows headline, source,
   published date, category, sentiment (new `SentimentBadge`
   component + `news-labels.ts` Arabic label maps for the 20
   `NewsCategory`/5 `SentimentLabel` values), confidence, entities, an
   honest "awaiting analysis" state for unanalyzed events, and a
   synthetic-data disclosure badge when `is_synthetic` is true —
   mirroring the Settings screen's existing data-source disclosure
   convention.
2. **Portfolio News Alerts** (the "Alerts" objective): two new
   `portfolio.ts` functions (`getPortfolioNewsAlerts`/
   `refreshPortfolioNewsAlerts`) call the Phase 12 `GET`/`POST
   /api/v1/portfolio/{id}/news-alerts[/refresh]` routes. A new
   "تنبيهات الأخبار" section in `PortfolioDetail.tsx` lists persisted
   alerts with severity-colored type badges and a manual refresh
   button — nothing here was previously surfaced anywhere in the
   frontend.
3. **A real, previously-undetected backend bug was found and fixed
   during manual verification, not simulated.** Running an actual
   scan against real PostgreSQL (not the SQLite every test in this
   repo uses) failed: `numpy.float64` values from technical/
   fundamental indicator computations reached
   `MarketIntelligenceRepository.save_symbol_records()`/
   `save_sector_summaries()`/`save_change_events()` uncast, and
   SQLAlchemy 2.0's `insertmanyvalues` path literal-renders `RETURNING`
   parameters for Postgres — numpy's `repr()` (`np.float64(1.23)`) is
   not valid SQL, so every multi-row market-scan insert failed with
   `schema "np" does not exist`. SQLite (every existing test) tolerates
   the numpy type silently, which is exactly why this was never caught
   before. Fixed with a small `_f()` cast helper applied at every
   numeric field crossing into these three insert sites — the same
   "cast to plain float at the DB boundary" fix already applied once
   before to a different numpy leak in the Portfolio Intelligence
   milestone. A regression test
   (`test_save_symbol_records_coerces_numpy_floats_before_they_reach_the_orm`)
   spies on `session.add()` to check the *exact* pre-flush attribute
   type (a post-commit read-back can't distinguish the bug, since a
   `Numeric` column always returns `Decimal` regardless of what was
   written) — confirmed to fail without the fix and pass with it.
4. **Manually verified**, not just typechecked. A local Postgres +
   Redis + real `uvicorn` + real `next dev` stack was stood up in this
   session; a real user registered → verified email → logged in
   through the actual `/login` form (Playwright driving real Chromium,
   not an API bypass); disclosed-synthetic price/fundamental data was
   seeded (`source="manual-seed"`, `is_synthetic=True`); a real market
   scan, portfolio analysis, and news refresh were triggered through
   the live REST API. All 8 objective screens (Dashboard, Scan,
   Watchlist, Opportunities, Portfolio, AI/Recommendations, News ×2)
   were screenshotted rendering real backend data with zero browser
   console errors. Notably, the seeded Aramco earnings news event
   appeared verbatim in the AI screen's fundamental-reasoning text
   ("...supported by earnings news (أرامكو السعودية تعلن عن أرباح
   سنوية ربع قياسية): +13.2 pts)"), confirming the full Phase 12 →
   `NewsSentimentScoreContributor` → `AnalystEngine` → frontend chain
   works end-to-end with the zero frontend changes documented in
   `docs/NEWS_INTELLIGENCE.md` §4.
5. **Verification**: `npm run typecheck`, `npm run lint`, `npm test`
   (34 passed), `npx next build` all clean; backend regression test
   added and passing; **2333 tests pass repo-wide** (up from 2329, +1
   new regression test, +3 previously-Redis-skipped tests now running
   since Redis was live during this verification session); `flake8
   src/ tests/ main.py` clean at 0 violations.
6. **Disclosed remaining gaps**: no "list my portfolios" backend
   endpoint exists yet, so the Portfolio screen still remembers "last
   analyzed portfolio_id" via a single-device `localStorage` key
   (`local-portfolio.ts`) rather than a real per-account list — this
   predates this milestone and wasn't introduced by it, but is now a
   more visible gap given `Portfolio.user_id` ownership has existed
   since Phase 10 M10.5. Periodic PDF report generation
   (`docs/architecture/current-status.md`'s Reports section) remains
   an honestly-disclosed "awaiting backend" placeholder, unrelated to
   this milestone's scope. The admin frontend (M10.14) is still not
   built. No live SAHMK/OpenAI network access exists in this sandbox;
   the manual verification pass used disclosed-synthetic seed data
   exactly like every other milestone's tests, never presented as live
   market data.

No claim in this document should be read as "production ready," "fully
complete," or "100% successful" — none of those are accurate, and this
document does not use those phrases as characterizations of the platform.
