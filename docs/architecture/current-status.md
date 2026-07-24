# Current Status — Authoritative

This is the only authoritative status document for the Basirah platform.
Where anything in `docs/archive/legacy-reports/` or elsewhere conflicts
with this document, this document is correct — it is derived from direct
code inspection and executed validation, not narrative claims. It
supersedes `docs/architecture/m0-build-status.md` for overall status (that
document remains as the detailed M0 evidence record) and is itself
superseded by whatever the next milestone's equivalent document says,
once code-verified.

As of M2.8 (branch `feature/m2.8-momentum-expert`, stacked on the
not-yet-merged M2.4/M2.4.1/M2.7 branch chain -- `main` itself is still
at `efda46013b5e682213476c74d7d868fc3de0d61e`, M2.3's merge commit):

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
- **Composite Intelligence Engine** (M2.4): `src/analysis/composite/
  composite_intelligence_engine.py`'s `CompositeIntelligenceEngine`
  fuses already-computed results from independent analysis engines
  (today: `TechnicalAnalysisEngine`, `FundamentalAnalysisEngine`) into
  one `CompositeResult`. It never calls either concrete engine or
  loads OHLCV/financial data itself — running each source engine
  remains the caller's responsibility; `CompositeIntelligenceEngine`'s
  only dependency is the structural `AnalysisEngineResult`/
  `AnalysisOutput` contract from `src/analysis/core/`. Three composite
  factors: `trend_fundamental_alignment` (SuperTrend direction vs.
  revenue-growth sign — `+1.0`/`-1.0` on agreement, `0.0` on
  disagreement, with an explicit `Agreement.AGREE`/`DISAGREE` flag,
  never a falsely-blended middle value), `valuation_momentum_context`
  (normalized RSI with P/E carried as context, not folded into the
  number — deliberately no invented compound formula), and
  `data_quality_summary` (fraction of supplied engine results that are
  fresh). Neither `TechnicalAnalysisResult` nor
  `FundamentalAnalysisResult` carries an "as of" timestamp, so
  freshness is modeled externally via `EngineResultEnvelope` +
  `classify_freshness()`'s documented default staleness policy,
  **without editing either already-merged engine**.
  `src/analysis/composite/registry.py`'s `CompositeFactorRegistry` is
  this engine's own extension point — a third, completely separate
  registry from M2.2's `IndicatorRegistry` and M2.3's `RatioRegistry`;
  none of the three import each other. Every factor returns
  `value=None` plus a `DataCompleteness` marker (`COMPLETE`/`PARTIAL`/
  `INSUFFICIENT`) on missing/undefined input, never raises.
  `CompositeFactorOutput`/`CompositeResult` satisfy
  `AnalysisOutput`/`AnalysisEngineResult` structurally, proven directly
  by `isinstance()` assertions in tests, with zero changes to
  `src/analysis/core/contracts.py` — meaning a future Signal Engine
  can consume `CompositeResult` exactly like Composite consumes each
  engine's result today. **Not included**: no persistence, no API
  route, no Signal Engine/Confidence Scoring/Explainable AI Engine/AI
  Decision Layer/Multi-Agent Orchestrator (only their future
  pluggability is prepared for), and no News/Corporate
  Actions/Market Events/Risk Assessment engines exist to fuse in yet
  (the extension point is proven ready for them only via a test-only
  placeholder factor, never shipped as a real engine).
  `CompositeIntelligenceEngine` is registered into
  `src/analysis/core/registry.py`'s `DEFAULT_ENGINE_REGISTRY` under the
  name `"composite_analysis"` (via `bootstrap.py`, a small dedicated
  M2.4 follow-up, PR #9) — the spec-flagged optional addition, done
  once explicitly confirmed. `TechnicalAnalysisEngine`/
  `FundamentalAnalysisEngine` were not modified to make this possible;
  the registration proves the cross-engine contract holds recursively,
  not just for the two engines it was designed against first.
- **BEIF expert layer, Technical Council (M2.7 + M2.8)**: `src/analysis/
  experts/` — a fourth, independent registry
  (`ExpertRegistry`/`DEFAULT_EXPERT_REGISTRY`) and a generic
  `CouncilEngine`, interpreting already-computed Technical Analysis
  Engine output into structured, evidence-bearing `ExpertResult`s
  (never recomputing an indicator itself). Two real experts exist:
  **Trend Expert** (`technical.trend`, M2.7), reading `sma_20`/`ema_20`/
  `adx_14`/`supertrend`, and **Momentum Expert** (`technical.momentum`,
  M2.8), reading `rsi_14`/`macd` — disjoint metric sets, verified by a
  registry-level test per BEIF Section 6/16's double-counting guard.
  Momentum Expert reads RSI-14 as a continuous, symmetric momentum-
  direction-and-magnitude measure (`(rsi - 50) / 50`), deliberately
  never as a binary "overbought means sell" trigger — the specific
  misapplication Document 1 Section 5.2 identifies as RSI's most common
  failure mode — with an extreme reading still disclosed via
  `warnings`, informational only. MACD's histogram contributes by sign
  only (±1), never scaled by magnitude, since no non-fabricated,
  price-scale-independent normalization exists for MACD's absolute
  value (unlike ADX's own standard 0–100 range, which Trend Expert
  uses directly). Both experts share per-expert failure isolation and
  numeric-bounds validation mirroring `CompositeIntelligenceEngine`'s
  established pattern. Registered as `TechnicalCouncilEngine` into
  `DEFAULT_ENGINE_REGISTRY` under `"technical_council"` via
  `src/analysis/experts/bootstrap.py`, imported from `main.py`
  alongside the existing `core.bootstrap` import (same production-
  reachability discipline M2.4.1 established). Both experts ship at
  `ExpertStatus.EXPERIMENTAL` (BEIF's lifecycle, Section 15) —
  reachable and fully tested, but deliberately excluded from
  `CouncilEngine.analyze()`'s default (shadow-mode-gated) output until
  a real promotion process exists; `include_all_statuses=True` is the
  explicit override used by the full-pipeline integration test.
  **Not included**: Volatility/Volume/Candlestick Expert
  (BEIF's remaining Technical Council v1 set, sequenced next), Market
  Structure Expert (BEIF v2, blocked pending a swing-high/low and
  gap-detection indicator), any Fundamental/Saudi/Risk Council expert,
  and no Signal Engine/Decision Layer to consume `CouncilResult` yet —
  `CouncilResult` satisfies `AnalysisEngineResult` structurally, proven
  the same way `CompositeResult` was, so a future Signal Engine can
  consume it identically once it exists.

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

- **Signal Engine, Confidence Scoring, Explainable AI Engine, AI
  Decision Layer, Multi-Agent Orchestrator**: none of these exist yet.
  `src/analysis/composite/`'s `CompositeResult` (M2.4) was built
  specifically so these can be added later without modifying
  `CompositeIntelligenceEngine`, `TechnicalAnalysisEngine`,
  `FundamentalAnalysisEngine`, or any indicator/ratio/factor inside
  any of them, but no such layer has been written.
- **News Intelligence Engine, Market Intelligence Engine, Sector
  Intelligence Engine, Macro Analysis Engine, Smart Money/ICT Engine,
  Wyckoff Engine, Corporate Actions, Market Events, Risk Assessment
  Engine**: none exist yet — only Technical (M2.2), Fundamental
  (M2.3), and Composite (M2.4) analysis are implemented so far, each
  independent and each satisfying the same `src/analysis/core/`
  contract these future engines will also satisfy. M2.4's composite
  factors only combine Technical + Fundamental, the only two real
  engines available — the extension point for these six is proven
  ready only via a test-only placeholder factor, never a shipped
  placeholder engine.
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

## Verified test/build state (M2.8)

- Compile sweep: 0 syntax errors across `src/`, `tests/`, `main.py`.
- Boot smoke test: `import main` succeeds, 11 routes (unchanged since
  M2.1), no `PYTHONPATH` manipulation required.
- Full test suite: 1027 passed / 12 skipped (Redis unavailable) / 0
  failed, verified in this environment (no live Redis instance was
  reachable here — `redis-cli ping` refused the connection — so the
  with-Redis count from M2.4.1's report is carried forward
  unverified this session rather than re-asserted). 1039 total test
  functions in the repository (up from 1019 at M2.7's close — 20 new
  tests for M2.8's Momentum Expert reference-value and edge-case
  coverage, registration, and a registry-level disjoint-metrics
  double-counting check; `test_main_boot.py` and
  `test_full_pipeline.py` extended in place, zero other existing
  tests modified).
- Coverage of the `src/analysis/experts/` package: **100%**
  (258/258 statements), measured via
  `pytest --cov=src/analysis/experts --cov-report=term-missing`.
- flake8: **0** violations across `src/`, `tests/`, `main.py`, gated in
  CI at `FLAKE8_BASELINE: 0` since M2.0 (see "Completed: M2.0" below).
- No new migration in this milestone (no persistence in M2.7's scope);
  the `fundamental_snapshots` migration cycle verified at M2.3's close
  is unchanged.

## Completed: M2.7 — Expert Intelligence Core (BEIF Phase 1–3)

Implements BEIF (the Basirah Expert Intelligence Framework
specification) exactly as scoped in that document's own Section 20:
core contracts, the expert registry, and **one** reference expert —
Trend Expert — wired end to end, deliberately not the full Technical
Council v1 set. Per BEIF Section 19 ("do not attempt to create all
experts at once") and the explicit instruction this milestone was
authorized under, this is Phases 1–3 only; Momentum/Volatility/Volume/
Candlestick Expert follow as separate, later milestones now that the
pattern is proven.

1. **`src/analysis/experts/types.py`**: `Council` (five values, per
   BEIF Section 3), `ExpertDirection`, `ExpertStatus` (BEIF's seven-
   state lifecycle, Section 15), `EvidenceItem`, `ExpertResult`
   (satisfies `AnalysisOutput` structurally — `name`, `category`,
   `value`, `.latest()` — the same technique `IndicatorOutput`/
   `RatioOutput`/`CompositeFactorOutput` already use), and
   `CouncilResult` (satisfies `AnalysisEngineResult` structurally, the
   same technique `CompositeResult` already uses). Reuses
   `DataCompleteness`/`Freshness` from `src.analysis.composite.types`
   rather than redefining them, per BEIF Section 4.
2. **`src/analysis/experts/registry.py`**: `ExpertSpec`/`ExpertRegistry`/
   `DEFAULT_EXPERT_REGISTRY`, mirroring `CompositeFactorRegistry`'s
   shape as a fourth, completely independent registry. `ExpertSpec`'s
   `compute` signature takes `(symbol, envelopes)`, not just
   `envelopes` — a small, disclosed completion of BEIF's own
   specification: `ExpertResult` requires a `symbol` field
   (BEIF Section 4) that no `EngineResultEnvelope` carries (unlike
   `CompositeFactorOutput`, which has no `symbol` field at all), so
   the compute call must receive it explicitly. Flagged to the user as
   a mechanical implementation-detail fix, not an architecture
   reopening, before proceeding.
3. **`src/analysis/experts/council_engine.py`**: `CouncilEngine`, a
   direct structural copy of `CompositeIntelligenceEngine.analyze()`'s
   per-item failure-isolation loop (BEIF Section 6), extended with
   numeric-bounds validation (`normalized_score`/`confidence`
   NaN/Infinity/out-of-range is isolated exactly like a raised
   exception, per BEIF Section 18) and `ExpertStatus`-based default
   visibility (`PRODUCTION`/`VALIDATED` only by default;
   `include_all_statuses=True` for shadow-mode/debug use).
4. **`src/analysis/experts/technical/trend_expert.py`**: Trend Expert
   (`technical.trend`), reading only `sma_20`/`ema_20`/`adx_14`/
   `supertrend` from an already-computed `"technical_analysis"`
   envelope — never a raw OHLCV DataFrame, enforced structurally by
   the function's own signature. Direction from EMA-vs-SMA sign and
   SuperTrend's own direction flag (agreement raises confidence,
   disagreement is disclosed as a `conflicts` entry and punished
   harder than agreement is rewarded — BIIC Article III.3); magnitude
   scaled by ADX-14's own standard 0–100 range, never an invented
   calibration. Confidence is capped below 1.0 unconditionally
   (Document 1 Section 13 / BIIC Article IV.4). Ships at
   `ExpertStatus.EXPERIMENTAL` — registered and fully tested, but
   excluded from `CouncilEngine.analyze()`'s default output until a
   real shadow-mode/promotion process exists, per BEIF Section 15.
5. **`src/analysis/experts/bootstrap.py`**: the BEIF composition root,
   mirroring `src/analysis/core/bootstrap.py`'s pattern as a sibling,
   not a modification — imports `src.analysis.experts.technical`
   (triggering Trend Expert's self-registration, mirroring
   `src/analysis/composite/factors/__init__.py`'s established
   self-registration pattern) and registers `CouncilEngine(council=
   Council.TECHNICAL)` into `DEFAULT_ENGINE_REGISTRY` under
   `"technical_council"`.
6. **`main.py`** gained one new import,
   `import src.analysis.experts.bootstrap`, alongside the existing
   `core.bootstrap` import — the same production-reachability
   discipline M2.4.1 established, applied from the start this time
   rather than retrofitted: `tests/unit/test_main_boot.py` now asserts
   `DEFAULT_EXPERT_REGISTRY` and `DEFAULT_ENGINE_REGISTRY`'s
   `"technical_council"` entry are both non-empty via the real
   production import path.
7. **`tests/integration/test_full_pipeline.py`** gained a seventh
   stage: the real `TechnicalCouncilEngine`, run against the same
   real `technical_analysis` envelope Stage 4 already built from real
   ingested/persisted/loaded data, asserting a real, non-mocked
   `technical.trend` result with the expected bullish direction on the
   test's steady synthetic uptrend.

**Scope discipline**: per explicit instruction, M2.7 implemented
exactly BEIF Phases 1–3 and nothing else — no Momentum/Volatility/
Volume/Candlestick/Market Structure Expert, no Fundamental/Saudi/Risk
Council, no Signal Engine, no Decision Engine, no API route, no
persistence. These are explicitly the next, separately-authorized
iterations.

## Completed: M2.8 — Momentum Expert

The second Technical Council v1 expert, following the exact shape
M2.7's Trend Expert established — proving the BEIF pattern generalizes
to a second expert without any change to `types.py`, `registry.py`, or
`council_engine.py`. Six `[M2.8]`-prefixed commits on
`feature/m2.8-momentum-expert` (stacked on the merged M2.7 branch).

1. **`src/analysis/experts/technical/momentum_expert.py`**: Momentum
   Expert (`technical.momentum`), reading only `rsi_14`/`macd` from an
   already-computed `"technical_analysis"` envelope. RSI-14 is scaled
   to a continuous, symmetric `(rsi - 50) / 50` momentum-direction-
   and-magnitude measure — deliberately never a binary "overbought
   means sell" trigger, the specific failure mode Document 1
   Section 5.2 names as RSI's most common misapplication; an extreme
   reading is still disclosed via `warnings`, informational only, not
   folded into a reversal call this expert has no evidentiary basis to
   make. MACD's histogram contributes by sign only (±1), never scaled
   by magnitude — MACD's absolute value is price-scale-dependent with
   no non-fabricated, universal normalization available the way ADX's
   own standard 0–100 range gave Trend Expert a principled scale for
   the same role. Disagreement between the two is disclosed as a
   `conflicts` entry, confidence penalized harder than agreement is
   rewarded (BIIC Article III.3), identical discipline to Trend
   Expert. Ships at `ExpertStatus.EXPERIMENTAL`, same reasoning as
   Trend Expert (no shadow-mode history yet).
2. **`src/analysis/experts/technical/__init__.py`** gained one import
   (`momentum_expert`, alongside the existing `trend_expert`) —
   self-registration, the same pattern already established.
3. **No change to `types.py`, `registry.py`, `council_engine.py`, or
   `bootstrap.py`** — the entire BEIF core built in M2.7 absorbed a
   second expert with zero modification, the direct proof its
   extension-point design (BEIF Section 8/6) holds beyond the one
   expert it was first proven against.
4. **`tests/unit/test_main_boot.py`** and
   **`tests/integration/test_full_pipeline.py`** extended in place:
   the reachability test now asserts both expert IDs are present via
   the real `import main` path, and the full-pipeline test's Stage 7
   now asserts a real, non-mocked `technical.momentum` result
   (bullish, on the same real ingested/persisted/loaded steady-uptrend
   data Trend Expert's own assertion already used).
5. A new registry-level test
   (`test_momentum_and_trend_experts_have_disjoint_contributing_metrics`)
   directly enforces BEIF Section 6/16's double-counting guard for
   Technical Council's first two experts, not merely as a design
   intention.

**Scope discipline**: per explicit instruction, M2.8 implemented
exactly one expert and touched no previously-stable module except the
two test files and the one `__init__.py` import line already
described — no Volatility/Volume/Candlestick/Market Structure Expert,
no Fundamental/Saudi/Risk Council, no Signal Engine, no Decision
Engine, no API route, no persistence.

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

## Completed: M2.4 — Composite Intelligence Engine

`CompositeIntelligenceEngine`, three composite factors, a third
independent extension-point registry, and the `EngineResultEnvelope`
freshness-tracking mechanism — see "Implemented" above for exactly
what each is and isn't. Six `[M2.4]`-prefixed commits on
`feature/m2.4-composite-intelligence-engine`, PR #8.

This milestone deliberately scores cross-engine *agreement, context,
and data quality* — never the stock itself. Producing a single
trading score or decision remains explicitly out of scope, reserved
for the not-yet-built Signal Engine/Confidence Scoring/AI Decision
Layer. `trend_fundamental_alignment` never collapses a disagreement
between Technical and Fundamental into a falsely-confident blended
number — it reports the raw per-engine directional inputs plus an
explicit `Agreement.AGREE`/`DISAGREE` flag instead, verified directly
by a real-engine integration test pairing a strong, sustained
downtrend with positive revenue growth and confirming `DISAGREE` is
reported, not averaged away.

Two design decisions worth recording verbatim:
- Neither `TechnicalAnalysisResult` (M2.2) nor `FundamentalAnalysisResult`
  (M2.3) carries a timestamp. Rather than retrofit one into either
  already-merged engine — which the architectural directive explicitly
  ruled out as "modifying an existing engine merely to force symmetry"
  — freshness is modeled externally via `EngineResultEnvelope` and a
  documented default staleness policy (`classify_freshness()`), leaving
  both engines completely untouched.
- The approved specification flagged one optional addition pending
  explicit confirmation: registering `CompositeIntelligenceEngine`
  itself into `src/analysis/core/registry.py`'s `DEFAULT_ENGINE_REGISTRY`
  (via `bootstrap.py`). That confirmation was not given at the time,
  so it was **not done** in this milestone's initial PR, per "do not
  expand scope" — noted here rather than assumed silently either way.
  Confirmation was given as a separate, explicit follow-up request; the
  registration itself landed as a small, dedicated M2.4 follow-up (one
  commit, `bootstrap.py` + its test only, PR #9) rather than being
  folded back into this section's original scope.

## Completed: M2.4 follow-up — Register CompositeIntelligenceEngine

The one item M2.4's initial PR (#8) deliberately left undone pending
explicit confirmation (see above) is now done. `bootstrap.py` gained
one import and one `.register()` call for `CompositeIntelligenceEngine`
under the name `"composite_analysis"` — `TechnicalAnalysisEngine`
and `FundamentalAnalysisEngine` were not touched, no existing API
changed, no new functionality introduced beyond the registration
itself. One `[M2.4]`-prefixed commit on
`feature/m2.4-register-composite-engine` (stacked on the still-open
`feature/m2.4-composite-intelligence-engine`), PR #9. With this,
**M2.4 is 100% complete** relative to the approved specification.

## Completed: M2.4.1 — Foundation Hardening

A full Backend Readiness & Architecture Audit (repository-wide,
read-only, five parallel deep-dive investigations plus direct
first-hand verification) was performed before M2.5 to check for
hidden architectural gaps rather than assuming M2.2–M2.4 were
production-ready simply because their own tests passed. It found
several real, previously-undisclosed issues; M2.4.1 closes the four
the audit judged as directly affecting what a Signal Engine (M2.5)
would build on, and one more it uncovered along the way. Four
`[M2.4.1]`-prefixed commits on `feature/m2.4.1-foundation-hardening`
(stacked on the still-open M2.4/M2.4-follow-up branch chain).

1. **`DEFAULT_ENGINE_REGISTRY` was dormant in production.**
   `src/analysis/core/bootstrap.py` — the composition root that
   registers all three engines — was previously imported only by its
   own test file; `main.py` never imported it, so the registry stayed
   permanently empty in the actual running application despite tests
   suggesting otherwise. Fixed with one `import src.analysis.core.bootstrap`
   at `main.py`'s module level (pure in-memory registration, no I/O,
   no Redis/DB dependency, no change to startup behavior otherwise).
2. **A full-pipeline integration test now exists**
   (`tests/integration/test_full_pipeline.py`): `ingest_ohlcv`/
   `ingest_fundamentals` (real ingestion, via a sequential fake
   provider replaying pre-built bars/periods one call at a time,
   exactly the real per-day call pattern) → a real SQLite database →
   `ohlcv_loader`/`fundamental_loader` → `TechnicalAnalysisEngine` →
   `FundamentalAnalysisEngine` → `CompositeIntelligenceEngine`, in one
   continuous test. Nothing before this proved the full chain works —
   every prior test exercised one stage in isolation.
   **Writing this test surfaced a second, real, previously-hidden
   dormant-registry bug**, the same class as item 1 but one layer
   down: `DEFAULT_COMPOSITE_REGISTRY` was only ever populated when the
   three composite factor modules happened to be imported by
   something — nothing in the production import chain
   (`composite_intelligence_engine.py`, `bootstrap.py`, `main.py`)
   imported them. It had only ever appeared to work because other
   test files' own imports populated the shared registry singleton
   first when the full suite ran together; the new test, run alone,
   failed immediately with an empty composite result. Also discovered
   in the process: `src/analysis/composite/factors/__init__.py` had
   never actually been committed in M2.4 — the package had been
   running as an implicit Python 3 namespace package since its
   creation. Fixed the same way as item 1: `factors/__init__.py` now
   imports all three factor modules (mirroring
   `src/domain/models/__init__.py`'s identical established pattern),
   and `composite_intelligence_engine.py` imports the `factors`
   package at module level.
3. **`CompositeIntelligenceEngine.analyze()` gained per-factor failure
   isolation.** A factor that violates the "never raise" convention
   (a bug, an unexpected input shape) is now caught, logged
   server-side with its full traceback, and isolated as a
   `DataCompleteness.INSUFFICIENT` entry with a structured explanation
   — every other factor still computes normally, in the same
   deterministic order. Mirrors the per-symbol failure isolation
   `ingest_ohlcv`/`ingest_fundamentals` already had. No change to any
   of the three real M2.4 factors, which don't raise today.
4. **`main.py`'s five raw-exception leaks were fixed.**
   `readiness_check`, `get_stats`, `submit_task`, `get_task_status`,
   and `get_agent_status` previously returned `str(e)` — the internal
   exception's own text — directly in the HTTP response body. Replaced
   with fixed, generic per-route messages; the real exception is still
   fully logged server-side via `logger.error(..., exc_info=True)`
   (previously missing on two of the five, losing the stack trace from
   logs too). Fixing this surfaced a related, previously-undocumented
   correctness bug: `readiness_check` and `get_stats` were each
   missing the `except HTTPException: raise` guard the other three
   routes already had, so their own intentionally-raised
   `HTTPException`s (e.g. 503 "kernel not initialized") were being
   caught by the broad `except Exception` directly below and
   miscategorized as generic 500s — fixed alongside the leak.

**Scope discipline**: per explicit instruction, M2.4.1 did not begin
the Signal Engine, build an AI Decision Layer, add any API route,
implement any persistence, integrate a real market-data vendor, add
authentication, or touch the frontend. Every other finding from the
Backend Readiness Audit (missing FCF/operating-margin/standalone-BVPS
fundamental metrics, no auth/rate-limiting, floor-only dependency
pins, 116 committed coverage-artifact files, the unreachable legacy
`autonomous_intelligence_layer`/`multi_agent_system` trees, Redis
being a hard non-lazy boot dependency unlike the deliberately-lazy DB)
remains open by design, tracked in that audit's own priority list, not
addressed here.

No claim in this document should be read as "production ready," "fully
complete," or "100% successful" — none of those are accurate, and this
document does not use those phrases as characterizations of the platform.
