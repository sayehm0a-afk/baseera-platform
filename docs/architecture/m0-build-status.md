# M0 Build Status — Verified Facts Only

This document reports only what was directly executed and observed during
M0 (build stability) on branch `chore/m0-build-stability`, baseline commit
`873507eea224c1020556a6a7d90826fe38bb5935` (`origin/main`). It intentionally
contains no completion percentage and does not use the phrases "production
ready," "fully complete," or "100% successful" — those claims are not
supported by M0, which is a narrow build-stability milestone, not a
statement about the product.

Every number below was produced by actually running the command shown, in
this environment, on this branch. Where a check could not be fully
exercised (e.g. it depends on infrastructure not present here), that is
stated explicitly rather than assumed.

## 1. Baseline (before any M0 change)

- Branch: `claude/github-capabilities-check-bofnfl`, same commit as `origin/main`
- Commit: `873507eea224c1020556a6a7d90826fe38bb5935`
- `git status`: clean, no uncommitted changes
- Python: 3.11.15
- To get an honest baseline, `psycopg2-binary` and `prometheus_client` (installed
  ad hoc in an earlier, separate investigation session) were uninstalled first,
  so the baseline reflects exactly what `requirements.txt` declared at that commit.

### 1.1 Baseline compile sweep (`python3 -m py_compile`, every file under `src/`, `tests/`, plus `main.py`)

Two syntax errors found:

- `src/core/runtime/agent_runtime.py:124` — `SyntaxError: f-string: unmatched '('`
- `src/core/multi_agent_system/supervisor_agent.py:120` — `SyntaxError: f-string: unmatched '['`

Both are nested double-quotes inside an f-string expression
(`f"{d["key"]}"`), invalid on Python < 3.12.

### 1.2 Baseline `pytest tests/ -q --continue-on-collection-errors`

```
8 failed, 398 passed, 12 skipped, 38 errors in 49.56s
```

- 38 collection errors: 37 were `ModuleNotFoundError: No module named 'core'`
  (bare `from core.X import ...` imports with no installed package and no
  `PYTHONPATH` set — the package had never been installed: `pip show basirah`
  returned "Package(s) not found"). 1 was a third `SyntaxError` of the same
  kind as above, in `tests/unit/core/runtime/execution_engine/test_execution_graph.py:127`.
- 8 failures, by exact cause:
  - 4 caused by `src/core/db/database.py` calling `create_engine()` at
    **import time**, which requires `psycopg2` to be installed
    (`ModuleNotFoundError: No module named 'psycopg2'`):
    `test_load_validation.py::test_database_connection_pool_load`,
    `::test_concurrent_database_access`,
    `test_security_validation.py::test_database_connection_security`,
    `::test_error_handling`.
  - 4 caused by hardcoded absolute paths (`/home/ubuntu/basirah/...`) in
    `tests/security/test_security_validation.py` that do not exist in this
    or any other checkout:
    `test_no_hardcoded_credentials`, `test_docker_security`,
    `test_kubernetes_security`, `test_environment_configuration`.
- 12 skipped: all `tests/integration/test_production_integration.py`, self-skipped
  with reason "Redis not available" — no Redis server was running.

## 2. Fixes made (chronological, one commit each)

| Commit | Change |
|---|---|
| `[M0] fix confirmed Python syntax errors` | Fixed the 2 authorized syntax errors plus the 3rd instance of the same bug class found in `test_execution_graph.py` during baseline verification (it was blocking test collection, and is the identical one-line quote fix). |
| `[M0] align declared runtime dependencies` | Added to `requirements.txt`: `psycopg2-binary`, `aiohttp`, `tenacity`, `redis`, `prometheus-client`, `pytest-mock`, `PyYAML` — all directly imported by shipped code or existing tests but previously undeclared. No technical-analysis library added (M3 scope). |
| `[M0] normalize package imports` | Standardized on `src.core.X` / `src.api.X` (the convention already used by `main.py` and `dependency_injection.py`, the live application entry point). Fixed `setup.py` to install `src` as a real package (`find_packages(include=['src','src.*'])`) instead of the never-exercised `package_dir={'':'src'}` remapping. Added 6 missing `__init__.py` files so `find_packages()` discovers all subpackages. Converted 45 files off the bare `core.X` style. Fixed 4 string-literal module-path references (`mock.patch(...)` targets, one logger-name assertion) that had to change to match. Added `pytest-benchmark`, discovered missing during full-suite validation. |
| `[M0] make database initialization lazy` | `src/core/db/database.py`: `engine`/`SessionLocal` are now `None` until `init_engine()` runs; `Base` stays eager (no I/O). Added `get_engine()`, `get_session_factory()`, `shutdown_engine()`. `dependency_injection.py`'s `setup_production_dependencies()` (called only from `main.py`'s FastAPI startup event) now calls `get_engine()`/`get_session_factory()` explicitly. `main.py`'s shutdown event now calls `shutdown_engine()`. Dropped one unused `engine` import in `runtime_kernel.py` (verified dead via grep). |
| `[M0] fix hardcoded absolute paths in security tests` | Replaced the 4 hardcoded `/home/ubuntu/basirah/...` paths with a `REPO_ROOT` computed from the test file's own location. No assertion or intent changed. Necessary because otherwise the CI gate added in this same milestone could never pass in any real checkout. |
| `[M0] add CI and application smoke checks` | Added `.github/workflows/ci.yml` (details in §4). |

**Not done, and explicitly out of scope for M0:** no files moved, archived,
deleted, or renamed; no legacy report touched; no agent, indicator, market
data, domain model, or frontend code written; no database schema or
migration created; no redesign of `agent_runtime.py` or
`supervisor_agent.py` beyond the one-line syntax fix.

## 3. Final verification (this environment, after all M0 commits)

All commands below were run for real; output is summarized, not assumed.

| Check | Command | Result |
|---|---|---|
| Clean dependency install | `pip install -r requirements.txt` | Succeeds, no errors |
| Editable package install | `pip install -e . --no-deps` | Succeeds (required upgrading this environment's stock `setuptools` first — see §6) |
| Compile sweep | `py_compile` over every file in `src/`, `tests/`, `main.py` | **0 syntax errors** (was 3) |
| Boot smoke test | `import main` (cwd = repo root, `PYTHONPATH` unset) | **Succeeds**, 11 routes exposed, unchanged from baseline (no route added/removed) |
| Full startup lifecycle (beyond the required smoke test) | `await main.startup_event()` | With no Redis reachable: reaches real Redis-connection code and raises there (`Failed to initialize runtime kernel` — a live-infrastructure failure, not a code/dependency defect). With a local `redis-server` running: **completes successfully** — "Basirah started successfully", health check `{'message_bus': True, 'task_queue': True, 'service_layer': True}`. Both runs prove the DB-lazy-init and DI wiring are correct; neither is required by M0's boot-smoke-test bar, included as stronger evidence. |
| Test collection | `pytest tests/ --collect-only -q` | **729 tests collected, 0 collection errors** (was 38 errors) |
| Full test run, no Redis (matches CI) | `pytest tests/ -q -rA` | **717 passed, 12 skipped, 0 failed** |
| Full test run, with local Redis | `pytest tests/ -q -rA` | **729 passed, 0 skipped, 0 failed** |
| Lint | `flake8 src/ tests/ main.py --count` | **1515** (pre-existing; see §5) |
| Diff review | `git diff origin/main...HEAD --stat` + secret-pattern scan | 60 files changed, all within the areas listed in §2; no secrets found |

### 3.1 Test result categories (explicit, per the validation requirements)

- **Passed:** 717 (729 when Redis is reachable) — actually executed, assertions ran, no error.
- **Failed:** 0.
- **Skipped:** 12, always the same set (`tests/integration/test_production_integration.py`), all self-skip with an explicit `"Redis not available"` reason at test time. These are infrastructure-dependent tests, not defects — they run and pass when Redis is reachable (verified above) and skip, not fail, when it isn't.
- **Not collected:** 0 (was 38 at baseline).
- **Infrastructure-dependent, not fully exercised in this environment's default state:** the same 12 Redis-dependent integration tests; and the full `main.py` startup lifecycle against a real, externally-reachable Postgres (only the engine/driver construction path was verified live — no live Postgres server was available to exercise an actual query in this sandbox).

No test is reported as passed unless it was actually executed and observed to pass.

## 4. CI (`.github/workflows/ci.yml`)

Two jobs: `build-and-test` (checkout → setup Python 3.11 → upgrade
pip/setuptools/wheel → `pip install -r requirements.txt` → `pip install -e .
--no-deps` → compile sweep → boot smoke test → `pytest --collect-only` →
full `pytest` → flake8 gate) and `secrets-scan` (`gitleaks/gitleaks-action`).

Every step's exact command was run by hand in this environment before being
committed, including with no Redis reachable (matching the GitHub Actions
runner, which has no Redis service configured) — see §3 for the results.
CI fails on: compile failure, collection failure, any required test
failing, an undeclared dependency blocking import, the boot smoke test
failing, or a flake8 regression above the documented baseline. Nothing is
suppressed via `xfail`, `skip`, exclusion, or deletion to force a green
result.

## 5. Lint baseline (flake8)

Repository-wide count at the end of M0: **1515** violations across
`src/`, `tests/`, `main.py` (`flake8 src/ tests/ main.py --count`).
Breakdown by rule code (measured before the M0 test-path fix, 1517 total;
the two-violation reduction came from that fix, not a deliberate cleanup):

```
717 E302  (expected 2 blank lines)
438 W293  (blank line contains whitespace)
148 F401  (imported but unused)
 60 E261  (comment spacing)
 28 W605  (invalid escape sequence)
 27 F841  (local variable assigned but never used)
 25 E704  (statement on same line as def)
 20 E402  (module level import not at top of file)
 20 E306  (expected blank line before nested def)
 11 E303  (too many blank lines)
  7 W391  (blank line at end of file)
  4 E722  (bare except)
  3 W291  (trailing whitespace)
  2 F821  (undefined name)
  1 each: F824, E305, E226, E128, E122, E117, E111
```

This debt **predates M0** and is almost entirely pre-existing style
formatting (E302/W293/F401 alone account for ~85%). Fixing it would mean
touching the majority of files in the repository — disproportionate to a
"small, purely technical build-stability milestone," and in direct tension
with the instruction to make the smallest safe changes and not redesign
modules outside the two explicitly authorized for a syntax fix. CI (§4)
enforces this count as a **regression ceiling**: new code cannot add lint
debt, and the full, real count is always printed, never hidden or
excluded. Reducing this baseline is explicitly out of M0 scope and is
listed as a known remaining defect in §7.

The 2 `F821` (undefined name) violations were inspected individually:
one is in `src/core/service_layer/service_layer.py:33` (`asyncio` used
but never imported) — this file is part of the confirmed-legacy/unused
cluster (§8, `service_layer.py`), not on the reachable path from `main.py`,
and is a real bug but out of M0's authorized-changes list.

## 6. Environment note (not a code defect)

`pip install -e .` initially failed in this environment with
`AttributeError: install_layout` — a known interaction between an old
system-provided `setuptools`/`distutils` and the legacy `setup.py develop`
codepath. Resolved by upgrading `setuptools` (`pip install --upgrade
setuptools`) before the editable install, which is what `ci.yml` does.
This is an environment/tooling detail, not a repository defect.

## 7. Known remaining defects (left unchanged, documented per the "leave it unchanged" instruction)

- **1515 pre-existing flake8 violations** (§5) — mass style-debt, out of
  M0 scope, tracked as a CI regression ceiling rather than fixed.
- **`src/core/service_layer/service_layer.py:33`** — `asyncio.Future` (or
  similar) referenced without importing `asyncio` (`F821`). Part of the
  legacy/unused runtime cluster (§8); not reachable from `main.py`.
- **`tests/security/test_security_validation.py::test_dependency_versions`**
  (line ~172) has the same hardcoded-`/home/ubuntu/basirah/`-path pattern
  as the 4 tests fixed in M0, but is guarded by `if os.path.exists(...)`,
  so it currently silently no-ops instead of failing. Not fixed in M0
  (it does not block CI), left as a known weak test.
- **No live Postgres or Tadawul/market-data endpoint was available in this
  environment** to exercise an actual database query or real market-data
  call; only import-time and engine-construction behavior was verified.
- **Duplicate runtime implementations are unresolved** — see §8. Nothing
  was deleted, renamed, or consolidated in M0; this is reported, not acted
  on, per the explicit instruction.

## 8. Duplicate runtime ownership map (report only — nothing deleted, renamed, or consolidated)

Evidence-based, from `grep` of every `.py` file in the repository for each
module's import path (both `core.X` and `src.core.X` forms, post-M0
normalization), immediately before and after the M0 changes. Import edges
below reflect the current (post-M0) `src.core.X` convention.

| File | Imported by | Reachable from `main.py`? | Has its own test | Status |
|---|---|---|---|---|
| `src/core/runtime/real_runtime_kernel.py` | `main.py` (direct) | **Yes — main.py's own kernel** | No dedicated unit test file (exercised indirectly via the boot smoke test and manual startup-lifecycle verification in §3) | **Active — this is the live kernel.** |
| `src/core/runtime/runtime_kernel.py` | `tests/unit/core/runtime/test_runtime_kernel.py` only | No | Yes, `test_runtime_kernel.py` (passes, fully mocked) | **Unused in production — test-only.** Legacy/duplicate of `real_runtime_kernel.py`. |
| `src/core/runtime/worker/real_worker.py` | `main.py` (direct), `dependency_injection.py`, `tests/integration/test_production_integration.py` | **Yes** | Exercised via integration tests (Redis-dependent, skip without Redis) | **Active.** |
| `src/core/runtime/worker/worker.py` | `runtime_kernel.py` (itself unused-in-production), `test_runtime_kernel.py` | No (only via the unused `runtime_kernel.py`) | Indirectly via `test_runtime_kernel.py` | **Unused in production — reachable only through the other unused file.** |
| `src/core/runtime/task_queue/real_task_queue.py` | `dependency_injection.py`, `tests/integration/test_production_integration.py`, `tests/security/test_security_validation.py` | **Yes** (via `dependency_injection.py`, called from `main.py`'s startup event) | Yes, integration + security tests | **Active.** |
| `src/core/runtime/task_queue/task_queue.py` | `runtime_kernel.py` (unused), `test_runtime_kernel.py`, `tests/unit/core/runtime/task_queue/test_task_queue.py` | No | Yes, dedicated unit test (passes) | **Unused in production.** |
| `src/core/runtime/real_service_layer.py` | `dependency_injection.py`, `tests/integration/test_production_integration.py`, `tests/security/test_security_validation.py` | **Yes** | Yes | **Active.** |
| `src/core/service_layer/service_layer.py` | `runtime_kernel.py` (unused), `test_runtime_kernel.py` | No | Indirectly, mocked | **Unused in production.** Also contains the `F821` bug noted in §7. |
| `src/core/runtime/agent_runtime.py` | `tests/unit/core/runtime/test_agent_runtime.py` only | No | Yes (passes, post syntax-fix) | **Unused in production — test-only.** This is the file with the syntax error fixed in M0; it is dead code that still shipped broken before this milestone. |
| `src/core/runtime/real_agent_runtime.py` | `dependency_injection.py`, `tests/integration/test_production_integration.py`, `tests/security/test_security_validation.py` | **Yes** | Yes | **Active** (no syntax error; unaffected by the fix above). |

**Pattern:** every "`real_*`" file is reachable from `main.py`, either
directly or via `dependency_injection.py`'s `setup_production_dependencies()`
(itself only invoked from `main.py`'s FastAPI startup event). Every
non-`real_*` counterpart is reachable only from `runtime_kernel.py`, which
is itself reachable only from its own dedicated unit test — i.e. the
non-`real_*` cluster forms a self-contained, fully-mocked test island with
no path from the application's actual entry point. All files in both
clusters compile cleanly and have passing tests as of this milestone; the
distinction here is production reachability, not correctness. No file
in this table was deleted, renamed, or merged in M0, per the explicit
instruction to report only.

## 9. Out-of-scope work (not performed, per M0 authorization)

- Repository restructuring, file moves, archiving of legacy reports (M1).
- Deleting or consolidating the duplicate runtime files identified in §8.
- Any agent, technical-indicator, market-data-provider, domain-model, or
  frontend implementation.
- Database schema or Alembic migrations.
- Reducing the 1515-violation flake8 baseline.
- Fixing the `F821` bug in `service_layer.py` or the guarded weak test in
  `test_dependency_versions`.
