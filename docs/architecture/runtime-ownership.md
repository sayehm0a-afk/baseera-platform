# Runtime Ownership Map

Evidence-based, from `grep` of every `.py` file in the repository for each
module's import path, plus which files `main.py`'s actual startup path
(`main.py` → `dependency_injection.setup_production_dependencies()`)
reaches. Re-verified as part of M1 — nothing in `src/core/runtime/` moved
during this milestone, so the paths and findings below are current.

No file listed here was deleted, renamed, or consolidated in M1. This is
a report, per the milestone's explicit instruction; disposition decisions
are for a separate, future, explicitly-approved deletion PR.

## Classification

| File | Imported by | Reachable from `main.py`? | Tested | Classification |
|---|---|---|---|---|
| `src/core/runtime/real_runtime_kernel.py` | `main.py` (direct) | **Yes** | Indirectly (boot smoke test + manual startup-lifecycle verification in M0) | **Canonical runtime** |
| `src/core/runtime/runtime_kernel.py` | `tests/unit/core/runtime/test_runtime_kernel.py` only | No | Yes (`test_runtime_kernel.py`, fully mocked, passes) | **Legacy but still referenced** (by its own dedicated test only) |
| `src/core/runtime/worker/real_worker.py` | `main.py` (direct), `dependency_injection.py`, `tests/integration/test_production_integration.py` | **Yes** | Yes (integration tests, Redis-dependent) | **Canonical runtime** |
| `src/core/runtime/worker/worker.py` | `runtime_kernel.py` (itself legacy-but-referenced), `test_runtime_kernel.py` | No (only via the legacy `runtime_kernel.py`) | Indirectly via `test_runtime_kernel.py` | **Legacy but still referenced** |
| `src/core/runtime/task_queue/real_task_queue.py` | `dependency_injection.py` (→ `main.py`), integration + security tests | **Yes** | Yes | **Canonical runtime** |
| `src/core/runtime/task_queue/task_queue.py` | `runtime_kernel.py` (legacy), `test_runtime_kernel.py`, its own dedicated unit test | No | Yes (dedicated unit test, passes) | **Legacy but still referenced** |
| `src/core/runtime/real_service_layer.py` | `dependency_injection.py` (→ `main.py`), integration + security tests | **Yes** | Yes | **Canonical runtime** |
| `src/core/service_layer/service_layer.py` | `runtime_kernel.py` (legacy), `test_runtime_kernel.py` | No | Indirectly, mocked | **Legacy but still referenced.** Also contains a real bug: `service_layer.py:33` uses `asyncio` without importing it (`F821`, confirmed via `flake8`). Not fixed — out of scope for both M0 and M1. |
| `src/core/runtime/real_agent_runtime.py` | `dependency_injection.py` (→ `main.py`), integration + security tests | **Yes** | Yes | **Canonical runtime** |
| `src/core/runtime/agent_runtime.py` | `tests/unit/core/runtime/test_agent_runtime.py` only | No | Yes (passes, post-M0 syntax fix) | **Legacy but still referenced** (by its own dedicated test only). This is the file with the syntax error fixed in M0; it shipped broken before that milestone despite being unreachable from the live app. |

## Pattern

Every `real_*` file is reachable from `main.py`, directly or via
`dependency_injection.setup_production_dependencies()` (itself only
invoked from `main.py`'s FastAPI startup event). Every non-`real_*`
counterpart is reachable only from `runtime_kernel.py`, which is itself
reachable only from its own dedicated unit test — the non-`real_*`
cluster is a self-contained, fully-mocked test island with no path from
the application's actual entry point.

**None of the 9 files above are classified as "confirmed dead" or
"unclear ownership."** Every one has at least one real importer (its own
dedicated test, if nothing else), so per this milestone's instruction to
document rather than delete, all 9 are left exactly where they are.
"Legacy but still referenced" is the correct classification for the 4
non-`real_*` files — not "dead code" — because deleting them today would
also require deleting their passing tests, which is out of scope for a
structural-only milestone.

## Beyond the `runtime_kernel`/`worker`/`task_queue`/`service_layer` cluster

Two related files outside that specific cluster, checked for completeness
per the instruction to include "`agent_runtime.py` and related legacy
variants":

- `src/core/multi_agent_system/supervisor_agent.py` — the other file with
  a syntax error fixed in M0. Imported by
  `tests/unit/core/multi_agent_system/test_multi_agent_system.py` only;
  not imported by `main.py` or `dependency_injection.py`. **Legacy but
  still referenced**, same category as the runtime cluster above.
- `src/core/autonomous_intelligence_layer/` (~30 files: `SupervisorAI`,
  `PlannerAI`, `DebateEngine`, `KnowledgeGraph`, `LearningEngine`, etc.) —
  not imported anywhere by `main.py`'s dependency-injection path. Each
  individual file has its own passing unit test (fully mocked), and the
  cluster as a whole has an integration test
  (`tests/integration/autonomous_intelligence_layer/test_core_integration.py`)
  that exercises the components together with each other, but never
  through `main.py`. **Legacy but still referenced** (by its own test
  suite, extensively) — not dead code, not reachable from the live
  application. This is the cluster `docs/architecture/m1-move-map.md`
  section 5 explains was deliberately *not* relocated into `src/agents/`
  in this milestone: it isn't "confirmed dead" (its tests are real and
  pass), but its future is a product/architecture decision (retire it,
  or evolve it into the real agent framework), not a structural one.

## Deletion candidates (for a future, separately-approved PR — not acted on here)

None of the files in this report are recommended for deletion without
further decision-making, because every one is covered by a passing test
that would also need to be addressed. The realistic path for the
`runtime_kernel`/`worker`/`task_queue`/`service_layer` legacy cluster is:
decide whether `real_runtime_kernel.py` etc. should be renamed to drop
the `real_` prefix (making them the unqualified canonical names) once the
legacy duplicates and their tests are retired together — that rename is
explicitly deferred per this milestone's rules ("do not rename `real_*`
files yet if doing so would require logic changes or produce an
unreviewable diff").
