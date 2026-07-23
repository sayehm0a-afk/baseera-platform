# Current Status — Authoritative

This is the only authoritative status document for the Basirah platform.
Where anything in `docs/archive/legacy-reports/` or elsewhere conflicts
with this document, this document is correct — it is derived from direct
code inspection and executed validation, not narrative claims. It
supersedes `docs/architecture/m0-build-status.md` for overall status (that
document remains as the detailed M0 evidence record) and is itself
superseded by whatever the next milestone's equivalent document says,
once code-verified.

As of M2.1 (branch `feature/m2-saudi-stock-analysis-engine`, based on
`main` at `4567c9fb7c0c509a098b84faaa26b10f4d90f281`, M2.0's merge
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

- **Saudi Stock Analysis Engine**: RSI, MACD, EMA, SMA, Bollinger Bands,
  ATR, ADX, SuperTrend, volume analysis, candlestick pattern detection,
  support/resistance, trend detection, signal generation, confidence
  scoring — none of this exists anywhere in the repository, in any form.
  `src/analysis/{indicators,price_action,volume}/` are empty scaffolding.
- **Expert agent system** (the 15-agent organization described in the
  approved recovery plan: Chief Investment Intelligence, Market Regime,
  Technical Analysis, Price Action, Volume/Liquidity, Fundamental,
  News/Events, Macro/Sector, Risk Manager, Red-Team, Decision Fusion,
  Confidence Calibration, Explainability, Outcome/Learning, Governance):
  not started. `src/agents/base/` is empty scaffolding, distinct from the
  legacy `autonomous_intelligence_layer/`/`multi_agent_system/` code.
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

`src/market_data/{validators,schemas}/`, `src/analysis/*`,
`src/agents/base/`, `src/pipeline/`, `src/learning/`, `prompts/`,
`frontend/`, `tests/{financial_validation,operational}/` — created in M1
as directory scaffolding only (`.gitkeep`/empty `__init__.py`), per the
canonical target architecture. None contain code. None are placeholder
implementations. (`src/domain/` and `migrations/versions/` are no
longer empty as of M2.1 — see "Implemented" above.)

## Verified test/build state (M2.1)

- Compile sweep: 0 syntax errors across `src/`, `tests/`, `main.py`.
- Boot smoke test: `import main` succeeds, 11 routes, no `PYTHONPATH`
  manipulation required.
- Full test suite: 735 passed / 12 skipped (Redis unavailable) / 0 failed
  without a live Redis; 747 passed / 0 skipped / 0 failed with one.
  747 total test functions in the repository (up from 730 at M1.5's
  close — 18 new tests for the M2.1 domain models, dev market-data
  provider, and ingestion job; zero existing tests modified).
- flake8: **0** violations across `src/`, `tests/`, `main.py`, gated in
  CI at `FLAKE8_BASELINE: 0` since M2.0 (see "Completed: M2.0" below).
- Migration cycle (`alembic upgrade head` → `downgrade base` →
  `upgrade head`) verified against a real local Postgres 16 instance
  matching `database.py`'s default `DATABASE_URL` exactly.

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

No claim in this document should be read as "production ready," "fully
complete," or "100% successful" — none of those are accurate, and this
document does not use those phrases as characterizations of the platform.
