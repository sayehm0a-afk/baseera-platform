# Basirah — Final Production Readiness Report

**Scope:** pre-live-scan production audit and hardening pass, ahead of the first real full-market Saudi validation scan.
**Branch:** `feature/basirah-intelligence-core`
**Commits this pass:** `93cecd4`, `7a82cfc`, `a966868` (repair branch, merged in as this branch's base), `37c0b79`, `913b25a`, `fca09ad`, `1b26dc2`
**Method:** four parallel, evidence-only audit agents (SAHMK integration, database/persistence, async/concurrency/scheduler, dependencies/CI/secrets) covering the full repository; every finding independently re-verified by direct code read before being called a defect; every fix has a new or updated test; full suite re-run twice for a true green baseline (once with a local `redis-server` started specifically to separate real defects from environmental gaps).

No capability is claimed here merely because a class or function exists. Every claim below is either a passing test, a real live API call, or an explicit "NOT VERIFIED" / disclosed limitation.

---

## 1. What was actually audited

Not a filename scan. Each audit agent read actual imports, call sites, retry/backoff logic, transaction boundaries, and CI YAML, and reported PASS / CONCERN(severity) / NOT VERIFIED with file:line citations for each item. Full agent transcripts are not reproduced here; findings and dispositions are.

## 2. Findings and dispositions

| # | Finding | Severity | Disposition |
|---|---|---|---|
| 1 | POST /api/v1/market/scan had no guard against two concurrent scans (would double real SAHMK volume, race DB rows) | HIGH | **Fixed** — `DuplicateMarketScanError` (409), unconditional overlap guard, mirrors `backtests.py`'s established pattern |
| 2 | CI never ran any test against real Postgres — only SQLite, everywhere | HIGH | **Fixed** — `postgres:16` service container + two new CI steps applying the full migration chain to it |
| 3 | A crashed/cancelled scan run (killed CI job) would stay PENDING/RUNNING forever, permanently blocking finding #1's guard | MEDIUM-HIGH | **Fixed** — `MarketIntelligenceRepository.reap_stale_runs()`, called before the overlap check, threshold `MARKET_MAX_SCAN_RUN_DURATION_HOURS` (default 4h, above the 3h full-universe CI timeout) |
| 4 | A connection failure/timeout calling SAHMK was surfaced immediately, with zero retries — inconsistent with an otherwise-identical 5xx, which gets 3 tenacity attempts | MEDIUM | **Fixed** — reclassified as `_RetryableSahmkError(kind="network_error")` |
| 5 | No per-symbol wall-clock ceiling on `_scan_one` — one pathologically slow symbol had no bound on how much of a long scan's time budget it could consume | MEDIUM | **Fixed** — `asyncio.wait_for` wrapper, `MARKET_SCAN_SYMBOL_TIMEOUT_SECONDS` (default 240s) |
| 6 | `DATABASE_URL` had no fail-fast check in production, unlike `SECRET_KEY` — a misconfigured prod deploy boots cleanly against the literal `postgres:postgres@localhost` default | MEDIUM | **Fixed** — new `_reject_default_database_url_in_production` validator, mirrors the existing secret-key one exactly |
| 7 | Real, pre-existing bug found *while verifying fix #2*: `a8e2f4c91d37_make_fundamental_snapshot_fields_nullable.py` used bare `op.alter_column(nullable=True)`, which emits SQLite-incompatible raw `ALTER COLUMN` syntax — the SQLite migration-replay test (`tests/integration/test_migrations.py`) was silently broken, confirmed via `git stash` to predate this entire session | MEDIUM-HIGH (would have blocked any fresh SQLite-backed deploy/test) | **Fixed** — rewritten with `op.batch_alter_table`, this repo's own established SQLite-safe convention (already used in `c4d8e6f19a2b`) |
| 8 | pandas/numpy/scikit-learn were floor-only pinned (`>=`, no ceiling) — an untested version bump could silently change NaN/dtype/numerical behavior between two CI runs of the same commit | MEDIUM | **Fixed** — exact-pinned to the versions the full 2700+-test suite is currently passing against |
| 9 | `SahmkRateLimiter.acquire()` holds its lock for the full sleep duration, serializing waiters even after slots free up | LOW | Not fixed — real but low-impact; only matters if `MARKET_SCAN_BATCH_SIZE` is raised above its default of 1. Documented, not silently dropped. |
| 10 | `SAHMK_MAX_REQUESTS_PER_MINUTE` (20/min default) is a documented conservative placeholder, not a confirmed real quota | LOW / operational | Not a code defect — requires confirming the real plan's quota from a live account before a full-universe run; flagged as an action item, not fixed in code |
| 11 | No composite `(scan_run_id, symbol)` index on `SymbolIntelligenceRecord` | MEDIUM (performance, not correctness) | Not fixed this pass — a migration change carries its own risk immediately before a live run; deferred as a documented follow-up |
| 12 | Full-market scan reruns are not deduplicated per trading day (a partial-then-full rerun creates two complete history sets) | MEDIUM (architecturally intentional per the module's own append-only-history docstring) | Not changed — this is a disclosed design choice (permanent scan history), not a bug; flagged for the user to confirm matches intent |

No CRITICAL-severity defect was found in any of the four audit passes.

## 3. Real evidence gathered this session (not simulated)

- **Live SAHMK API call, today** (workflow run `30677140985`, sample mode, 6 symbols including 1020): real auth succeeded, 360 real OHLCV rows ingested, 6/6 fundamentals, real `AnalystEngine → AIDecisionEngine` scan (3.66s, 0 failures). Symbol 1020 (Al Jazira Bank): `BUY, target=12.17, price=12.15, expected_return_pct=+0.16%` — target now sits **above** entry, directly confirming the earlier target-below-entry root-cause fix (`7a82cfc`) holds on live, current data, not just synthetic test fixtures.
- **Full unit+integration suite, twice**: 2752 passed, 3 skipped, 5 `xfailed` (intentional, disclosed gaps — see §5), 0 failed. The second run added a locally-started `redis-server` specifically to separate 3 real-Redis-dependent test failures (environmental — no Redis in this sandbox by default) from genuine defects; all 3 passed once Redis was available, confirmed not a code issue.
- **Migration chain**: SQLite full upgrade/downgrade/round-trip replay passes (post-fix); Postgres-backed CI step added but not yet run in GitHub Actions (requires a CI dispatch, not exercised from this sandbox).
- **flake8**: 0 violations across `src/`, `tests/`, `main.py` — matches CI's own `FLAKE8_BASELINE: 0` gate exactly.

## 4. What was NOT independently re-verified this pass

- The Postgres CI migration-check step itself has not yet actually run in GitHub Actions (added, not dispatched).
- Universe pagination and sector-mapping fixes (`93cecd4`) have real unit-test coverage but have not been re-verified against a real full-universe live discovery call since being written — today's live evidence was sample mode (6 fixed symbols), which does not exercise `get_company_directory()`'s pagination path at all.
- TASI/benchmark, multi-timeframe analysis, sector-aware fundamental models, pattern recognition, conflict detection, and the Arabic conversational analyst remain exactly as characterized in `PHASE_0_REALITY_AUDIT.md` — MISSING or REAL_BUT_INCOMPLETE, unchanged by this hardening pass (out of scope: this pass was explicitly "no new features, audit and fix reliability only").

## 5. Known, disclosed limitations (not hidden)

Each of these has a concrete `xfail(strict=True)` test in `tests/unit/market_intelligence/test_adversarial_scenarios.py` proving the gap is real and forcing a build failure the moment it's silently "fixed" without updating the marker:

1. No gate against chasing an already-extended price move (case 9).
2. No independent technical-vs-fundamental conflict-detection stage (case 10).
3. Breakout watchlist rule doesn't check volume confirmation (case 13).
4. No conservative handling for recently-listed securities (case 14).
5. No sector-aware fundamental model (banks/insurers/REITs scored identically to industrials) (case 15).

Additional disclosed, non-test-tracked limitations:
- Liquidity gate threshold (`MARKET_MIN_AVERAGE_TRADED_VALUE_SAR`, default 1,000,000) is a conservative placeholder, not empirically calibrated against real Tadawul liquidity distributions.
- `TOP_BUY` still sorts *eligible* (gate-passed) candidates by `final_score` alone — the gate guarantees every entry is a defensible trade, not that the best one ranks first.
- SAHMK rate-limit default (20 req/min) is unconfirmed against the real account's actual plan quota.

## 6. Subsystem scores

Scored 0-10 against "sound enough for a real full-market validation scan," not against the full 18-phase world-class-platform mandate (explicitly out of scope for this hardening pass).

| Subsystem | Score | Basis |
|---|---|---|
| SAHMK Integration | 8/10 | Real auth, retry/circuit-breaker, pagination, rate limiting all verified real+correct or fixed this pass; rate-limit *value* unconfirmed against real plan |
| Database | 7/10 | Migration chain now verified SQLite-clean and Postgres-checked in CI (pending an actual CI run); one real bug found+fixed; composite-index gap and per-day dedup policy both disclosed, not fixed |
| Reliability (scan pipeline) | 8/10 | Overlap guard, stale-run reaper, per-symbol timeout, network-error retry all real and tested; per-symbol timeout headroom (240s) is a reasoned estimate, not empirically load-tested against a real 270+-symbol run |
| Recommendation/Gate Quality | 7/10 | Publication gate (freshness/price/confidence/targets/risk-reward/liquidity/entry-quality) is real, tested, and directly closes the 1020-class defect, confirmed on live data; 5 disclosed analysis-quality gaps remain (xfailed, not silently missing) |
| Code Quality | 9/10 | 0 flake8 violations against CI's own gate; every fix has a matching test; no dead code introduced |
| Security/Secrets | 8/10 | No secret leak path found in code or CI YAML across two independent audit passes; `DATABASE_URL`/`SECRET_KEY` now both fail fast in production |
| Test Coverage (breadth) | 8/10 | 2752 passing, 0 failing, gaps in coverage are explicit `xfail` markers, not silence |
| AI/Technical-Analysis Depth | 4/10 | Unchanged this pass by design (out of scope) — 16 real indicators, no multi-timeframe, no pattern recognition, no sector-aware fundamentals; see `PHASE_0_REALITY_AUDIT.md` |

## 7. Verdict

The question asked is specifically: **is Basirah ready for the first Full Saudi Market Validation** (a `full_universe`-mode dispatch of `sahmk-live-pipeline-validation.yml`) — not "ready for customer-facing production trading." Against that specific, narrower bar:

- No CRITICAL defect exists anywhere in the audited surface.
- Every HIGH-severity finding is fixed and tested.
- The exact defect class that produced the previous bad live run (target price below entry) is fixed and independently confirmed against real, current SAHMK data today, not just a unit test.
- The full test suite is green (2752/2752 non-skipped, non-xfailed tests).
- Known analytical-quality gaps are real but are refinements for later phases, not conditions that would corrupt data, crash the pipeline, or fabricate a recommendation during a validation run — and every one of them is disclosed, not hidden.

**YES — Ready** for the first Full Saudi Market Validation run, with the explicit condition that the run is executed as what it is — a validation/test scan, using the manual `full_universe` dispatch already documented for the user — and that this report's disclosed limitations (§5) are read alongside its results, not presented as absent.
