# Current Status — Authoritative

This is the only authoritative status document for the Basirah platform.
Where anything in `docs/archive/legacy-reports/` or elsewhere conflicts
with this document, this document is correct — it is derived from direct
code inspection and executed validation, not narrative claims. It
supersedes `docs/architecture/m0-build-status.md` for overall status (that
document remains as the detailed M0 evidence record) and is itself
superseded by whatever the next milestone's equivalent document says,
once code-verified.

As of M1.5 (branch `chore/m1.5-lint-debt-reduction`, based on `main` at
`c21317663b7bfe5a9b20ab3f01ec9d3b77318a21` / tag `v0.2.0-m1-stable`,
M1's merge commit):

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

## Partially implemented

- **`autonomous_intelligence_layer/` and `multi_agent_system/`**
  (~30 files under `src/core/`): real Python data structures for a
  Supervisor/Planner/Debate/Voting/Fusion/Knowledge-Graph pattern, each
  with passing unit tests — but not reachable from `main.py`'s actual
  startup path, and not connected to any real LLM call except
  `ReflectionEngine`. This is orchestration scaffolding for a future
  agent framework, not a working expert-agent system.
- **Market data**: one generic HTTP client shell
  (`src/market_data/providers/market_data_provider.py`, moved from
  `src/core/market_data/` in M1, logic unchanged) with retry/rate-limiting
  plumbing — but zero real provider (no Tadawul, no Yahoo Finance, no
  CSV), zero importers anywhere in the codebase, never exercised against
  a real data source.

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
- **Domain models and persistence**: no `Stock`, `Candle`,
  `MarketSnapshot`, `DecisionRecord`, or any other domain model exists.
  `src/domain/` is empty. No database migration has ever been generated
  (`migrations/versions/` is empty); there is no schema.
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
`src/agents/base/`, `src/pipeline/`, `src/domain/`, `src/learning/`,
`prompts/`, `frontend/`, `tests/{financial_validation,operational}/`,
`migrations/versions/` — created in M1 as directory scaffolding only
(`.gitkeep`/empty `__init__.py`), per the canonical target architecture.
None contain code. None are placeholder implementations.

## Verified test/build state (M1.5)

- Compile sweep: 0 syntax errors across `src/`, `tests/`, `main.py`.
- Boot smoke test: `import main` succeeds, 11 routes, no `PYTHONPATH`
  manipulation required.
- Full test suite: 717 passed / 12 skipped (Redis unavailable) / 0 failed
  without a live Redis; 729 passed / 0 skipped / 0 failed with one.
  730 total test functions in the repository (unchanged since M1).
- flake8: **0** violations across `src/`, `tests/`, `main.py` (down from
  1515 at M1's close — see "Completed: M1.5" below).

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

No claim in this document should be read as "production ready," "fully
complete," or "100% successful" — none of those are accurate, and this
document does not use those phrases as characterizations of the platform.
