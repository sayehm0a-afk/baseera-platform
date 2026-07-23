# Repository Structure

Code-verified as of the M1 restructuring (branch `chore/m1-repository-restructure`,
based on `main` at `6ff474a289156a39d2ce05e5803a8d8a532f835d`, tag
`v0.1.0-m0-stable`). Every path below was checked to exist; every status
label was checked against actual file contents, not assumed.

```
baseera-platform/
├── main.py                          IMPLEMENTED — canonical FastAPI entry point
├── src/
│   ├── api/
│   │   ├── routes/                  NOT IMPLEMENTED — empty (__init__.py only)
│   │   ├── schemas/                 NOT IMPLEMENTED — empty
│   │   └── middleware/              NOT IMPLEMENTED — empty
│   │   └── health_check.py          IMPLEMENTED (15 lines)
│   ├── core/
│   │   ├── runtime/                 IMPLEMENTED — task queue, execution engine,
│   │   │                            reliability layer, observability layer;
│   │   │                            see runtime-ownership.md for canonical vs
│   │   │                            legacy-but-referenced files within it
│   │   ├── llm_abstraction/         IMPLEMENTED — real OpenAI client wrapper,
│   │   │                            but not wired into any agent by default
│   │   ├── messaging/               IMPLEMENTED — Redis pub/sub
│   │   ├── db/                      IMPLEMENTED — lazy SQLAlchemy engine/session
│   │   │                            (M0); NO domain schema/models (M1 does not add any)
│   │   ├── monitoring/              IMPLEMENTED — structured logging, Prometheus metrics
│   │   ├── autonomous_intelligence_layer/  PARTIALLY IMPLEMENTED, LEGACY —
│   │   │                            real orchestration data structures (DAG,
│   │   │                            debate, voting, fusion, knowledge graph),
│   │   │                            each with passing tests, but NOT reachable
│   │   │                            from main.py (see runtime-ownership.md).
│   │   │                            Deliberately not relocated in M1.
│   │   ├── multi_agent_system/      PARTIALLY IMPLEMENTED, LEGACY — same
│   │   │                            reachability status as above
│   │   ├── base_agent/              PARTIALLY IMPLEMENTED — generic agent base
│   │   │                            class, no domain logic
│   │   ├── service_layer/, shared_models/, exceptions/, utils/ — small,
│   │   │                            legacy-but-referenced or minimal utility code
│   ├── market_data/
│   │   ├── providers/               PARTIALLY IMPLEMENTED — one generic HTTP
│   │   │                            client shell (market_data_provider.py);
│   │   │                            no real Tadawul/Yahoo/CSV provider, no
│   │   │                            live data source connected, zero importers
│   │   ├── validators/              NOT IMPLEMENTED — empty
│   │   └── schemas/                 NOT IMPLEMENTED — empty
│   ├── analysis/
│   │   ├── indicators/              NOT IMPLEMENTED — empty. No RSI, MACD, EMA,
│   │   │                            SMA, Bollinger, ATR, ADX, or SuperTrend
│   │   │                            exists anywhere in this repository.
│   │   ├── price_action/            NOT IMPLEMENTED — empty
│   │   └── volume/                  NOT IMPLEMENTED — empty
│   ├── agents/
│   │   └── base/                    NOT IMPLEMENTED — empty. This is the future
│   │                                clean agent interface; it is not the same
│   │                                thing as the legacy autonomous_intelligence_layer/
│   │                                or multi_agent_system/ code under src/core/.
│   ├── pipeline/                    NOT IMPLEMENTED — empty
│   ├── domain/                      NOT IMPLEMENTED — empty
│   └── learning/                    NOT IMPLEMENTED — empty
├── prompts/                         NOT IMPLEMENTED — empty (.gitkeep only)
├── frontend/                        NOT IMPLEMENTED — empty. No frontend exists
│                                    in this repository in any form.
├── tests/
│   ├── unit/                        IMPLEMENTED — 730 test functions total
│   │                                across the repo (unit + integration + e2e +
│   │                                load + security combined), covering the
│   │                                runtime/orchestration scaffolding only
│   ├── integration/                 IMPLEMENTED
│   ├── e2e/, load/, security/       IMPLEMENTED — kept in place; do not map
│   │                                unambiguously onto financial_validation/
│   │                                operational (see m1-move-map.md §6)
│   ├── financial_validation/        NOT IMPLEMENTED — empty, scaffolded in M1
│   └── operational/                 NOT IMPLEMENTED — empty, scaffolded in M1
├── migrations/
│   ├── env.py, script.py.mako, README   IMPLEMENTED (Alembic config)
│   └── versions/                    NOT IMPLEMENTED — empty. No migration has
│                                    ever been generated; there is no database
│                                    schema (confirmed in the original audit
│                                    and unchanged since).
├── docs/
│   ├── architecture/                IMPLEMENTED — this file, current-status.md,
│   │                                runtime-ownership.md, m1-move-map.md,
│   │                                m0-build-status.md
│   ├── governance/                  IMPLEMENTED — Arabic charter, roadmap,
│   │                                blueprint, SRS, ADRs, standards (moved
│   │                                from الوثائق_الرئيسية/ in M1, content
│   │                                and filenames unchanged)
│   ├── archive/
│   │   ├── legacy-reports/          42 historical reports archived in M1,
│   │   │                            see its own README.md — not evidence of
│   │   │                            implementation status
│   │   └── legacy-structure/        6 confirmed-empty directory skeletons
│   │                                archived in M1, see its own README.md
│   └── (remaining top-level docs: design specs, ADRs, operational guides,
│        diagrams — kept in place, not misleading claims; see
│        m1-move-map.md §2 for the per-file reasoning)
├── scripts/                         IMPLEMENTED — deploy/rollback/start/stop/
│                                    validate-deployment shell scripts
│                                    (not independently verified as working
│                                    against a real environment in M0 or M1)
├── kubernetes/, helm/               IMPLEMENTED as config — present, plausible,
│                                    never validated by actually deploying
├── .github/workflows/ci.yml         IMPLEMENTED — M0's CI gate, unchanged in M1
├── Dockerfile, docker-compose.yml   IMPLEMENTED as config, not independently
│                                    re-validated by building/running in M1
├── requirements.txt, setup.py       IMPLEMENTED — M0's fixed dependency
│                                    declarations and src.* packaging, unchanged
├── alembic.ini                      IMPLEMENTED as config
├── LICENSE, README.md, CHANGELOG.md, CONTRIBUTING.md, SECURITY.md   IMPLEMENTED
├── الأدوات_والنصوص/                 CONTAINS ONE REAL FILE — backup.sh
│                                    (النسخ_الاحتياطي/), unreferenced by
│                                    anything else in the repo; not moved,
│                                    not archived (see m1-move-map.md §7)
└── السجلات/                         CONTAINS ONE REAL FILE — config/
                                     logging_config.yml, unreferenced by
                                     anything else in the repo; not moved,
                                     not archived (see m1-move-map.md §7)
```

## Status label definitions

- **Implemented** — real, working code or config, verified by direct
  inspection (and, where applicable, passing tests or a successful CI run).
- **Partially implemented** — real code exists and does something, but not
  the full scope implied by its name/location, or it is not reachable
  from the running application.
- **Not implemented** — the directory exists (scaffolding only) or the
  name suggests a capability, but no code implements it. Empty
  `__init__.py`/`.gitkeep` only.
- **Retained only as legacy reference** — real historical content, kept
  for context, explicitly not trusted as evidence of current status
  (the 42 files in `docs/archive/legacy-reports/`).

No product feature, indicator, agent, market-data provider, or frontend
behavior was added while producing this document or anywhere else in M1.
