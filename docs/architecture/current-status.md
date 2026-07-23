# Current Status — Authoritative

This is the only authoritative status document for the Basirah platform.
Where anything in `docs/archive/legacy-reports/` or elsewhere conflicts
with this document, this document is correct — it is derived from direct
code inspection and executed validation, not narrative claims. It
supersedes `docs/architecture/m0-build-status.md` for overall status (that
document remains as the detailed M0 evidence record) and is itself
superseded by whatever the next milestone's equivalent document says,
once code-verified.

As of M1 (branch `chore/m1-repository-restructure`, based on `main` at
`6ff474a289156a39d2ce05e5803a8d8a532f835d` / tag `v0.1.0-m0-stable`):

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

## Verified test/build state (M1, unchanged from M0's verified end state)

- Compile sweep: 0 syntax errors across `src/`, `tests/`, `main.py`.
- Boot smoke test: `import main` succeeds, 11 routes, no `PYTHONPATH`
  manipulation required.
- Full test suite: 717 passed / 12 skipped (Redis unavailable) / 0 failed
  without a live Redis; 729 passed / 0 skipped / 0 failed with one.
  730 total test functions in the repository.
- flake8: 1515 pre-existing violations, enforced in CI as a regression
  ceiling (not reduced in M0 or M1 — see the M1 PR description for the
  planned M1.5 follow-up).

No claim in this document should be read as "production ready," "fully
complete," or "100% successful" — none of those are accurate, and this
document does not use those phrases as characterizations of the platform.
