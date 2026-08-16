"""One-off, real-production execution script for the approved "safe
continuation rotation" (Mandate C -- APPROVED OPTION A).

Calls the new staff/OWNER-gated POST /admin/market-intelligence/
continue-scan-cycle repeatedly, once per HTTP call = one bounded,
stale-first, BACKGROUND-priority, leader-locked scan cycle of at most
MARKET_SCAN_SYMBOLS_PER_CYCLE symbols -- the exact same code path
(`IntervalMarketIntelligenceScheduler._run_one_cycle()`) the production
scheduler itself runs on its own interval, invoked manually and safely
through the dedicated endpoint (see PR #44, commit 82acdb2).

Every cycle's full response is recorded (run id, symbols
requested/succeeded/skipped/failed, exact symbols_scanned, quota
before/after, recommendation/decision counts, published/rejected/
watch_only counts) as JSON evidence, never summarized in-flight.

Stops on the first of:
  - `executed: false` (any stop_reason the endpoint itself reports --
    not_leader, sahmk_not_live, upstream_confirmed_exhausted,
    background_quota_low, scan_in_progress, database_unhealthy,
    redis_unhealthy, universe_complete)
  - cumulative distinct symbols_scanned this run reaches the real
    active+price-history-eligible universe size (from GET .../coverage)
  - a hard cycle-count safety cap (defense in depth, independent of the
    endpoint's own quota gate)
  - a wall-clock time budget (defense in depth for the CI job's own
    timeout)

Never fabricates coverage: only symbols a cycle's own `executed=true`
response actually lists in `symbols_scanned` are counted.
"""

import json
import os
import sys
import time

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
EXPECTED_COMMIT = os.environ.get("EXPECTED_COMMIT", "").strip()
MAX_CYCLES = int(os.environ.get("MAX_CYCLES", "40"))
TIME_BUDGET_SECONDS = int(os.environ.get("TIME_BUDGET_SECONDS", "3000"))
BASELINE_ALREADY_SCANNED = int(os.environ.get("BASELINE_ALREADY_SCANNED", "0"))
EVIDENCE_FILE = os.environ.get("EVIDENCE_FILE", "/tmp/continue_scan_evidence.json")

session = requests.Session()

print("=== Staff login ===")
r = session.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
print("Login OK.")
csrf_token = session.cookies.get("csrf_token")
session.headers.update({"X-CSRF-Token": csrf_token})

print("\n=== Pre-flight: /admin/system/summary ===")
r = session.get(f"{BACKEND_URL}/api/v1/admin/system/summary", timeout=30)
if r.status_code != 200:
    print(f"GET /admin/system/summary failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
summary = r.json()
deployed_commit = summary.get("deployment_commit")
print(f"deployment_commit reported: {deployed_commit}")
if EXPECTED_COMMIT and deployed_commit != EXPECTED_COMMIT:
    print(f"FATAL: deployed commit '{deployed_commit}' does not match expected '{EXPECTED_COMMIT}'. Aborting -- refuse to run against an unverified deployment.")
    sys.exit(1)

print("\n=== Pre-flight: /admin/market-intelligence/coverage (real universe size) ===")
r = session.get(f"{BACKEND_URL}/api/v1/admin/market-intelligence/coverage", timeout=30)
if r.status_code != 200:
    print(f"GET .../coverage failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
coverage_before = r.json()
target_universe = coverage_before["stocks_with_price_history"]
print(f"active_stocks={coverage_before['active_stocks']} stocks_with_price_history={target_universe} coverage_pct={coverage_before.get('coverage_pct')}")

evidence = {
    "started_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    "deployed_commit": deployed_commit,
    "coverage_before": coverage_before,
    "baseline_already_scanned": BASELINE_ALREADY_SCANNED,
    "target_universe": target_universe,
    "cycles": [],
}

distinct_symbols_scanned = set()
start_time = time.monotonic()
stop_reason_final = None

print(f"\n=== Continuation loop: target_universe={target_universe} baseline_already_scanned={BASELINE_ALREADY_SCANNED} max_cycles={MAX_CYCLES} time_budget_s={TIME_BUDGET_SECONDS} ===")

for cycle_num in range(1, MAX_CYCLES + 1):
    elapsed = time.monotonic() - start_time
    if elapsed > TIME_BUDGET_SECONDS:
        stop_reason_final = "script_time_budget_exhausted"
        print(f"\n[cycle {cycle_num}] STOP: time budget exhausted ({elapsed:.0f}s > {TIME_BUDGET_SECONDS}s)")
        break

    covered_so_far = BASELINE_ALREADY_SCANNED + len(distinct_symbols_scanned)
    if covered_so_far >= target_universe:
        stop_reason_final = "coverage_target_reached"
        print(f"\n[cycle {cycle_num}] STOP: coverage target reached ({covered_so_far} >= {target_universe})")
        break

    print(f"\n[cycle {cycle_num}] POST /continue-scan-cycle ... (covered_so_far={covered_so_far}/{target_universe})")
    t0 = time.monotonic()
    try:
        r = session.post(f"{BACKEND_URL}/api/v1/admin/market-intelligence/continue-scan-cycle", timeout=280)
    except requests.exceptions.RequestException as exc:
        stop_reason_final = f"http_error:{exc.__class__.__name__}"
        print(f"[cycle {cycle_num}] HTTP request failed: {exc}")
        break
    dt = time.monotonic() - t0

    if r.status_code != 200:
        stop_reason_final = f"http_status_{r.status_code}"
        print(f"[cycle {cycle_num}] non-200 response: status={r.status_code} body={r.text[:800]}")
        evidence["cycles"].append({"cycle_num": cycle_num, "http_status": r.status_code, "body": r.text[:2000], "wall_seconds": dt})
        break

    body = r.json()
    body["_wall_seconds"] = dt
    body["_cycle_num"] = cycle_num
    evidence["cycles"].append(body)

    executed = body.get("executed")
    print(f"[cycle {cycle_num}] executed={executed} stop_reason={body.get('stop_reason')} run_id={body.get('run_id')} "
          f"symbols_scanned={len(body.get('symbols_scanned') or [])} wall={dt:.1f}s")

    if not executed:
        stop_reason_final = body.get("stop_reason") or "executed_false_no_reason"
        print(f"[cycle {cycle_num}] STOP: endpoint reported executed=false, stop_reason={stop_reason_final}")
        break

    new_symbols = set(body.get("symbols_scanned") or [])
    overlap = new_symbols & distinct_symbols_scanned
    if overlap:
        print(f"[cycle {cycle_num}] WARNING: {len(overlap)} symbols overlap with a previous cycle this run: {sorted(overlap)}")
    distinct_symbols_scanned |= new_symbols

    print(f"[cycle {cycle_num}] quota_before={body.get('quota_before')}")
    print(f"[cycle {cycle_num}] quota_after={body.get('quota_after')}")
    print(f"[cycle {cycle_num}] recommendation_counts={body.get('recommendation_counts')} decision_counts={body.get('decision_counts')}")
    print(f"[cycle {cycle_num}] published={body.get('published_count')} rejected={body.get('rejected_count')} watch_only={body.get('watch_only_count')}")

    # Be a polite, single-threaded caller -- no reason to hammer the
    # endpoint faster than the leader-lock lease renewal cadence needs.
    time.sleep(2)
else:
    stop_reason_final = "max_cycles_reached"
    print(f"\nSTOP: max_cycles ({MAX_CYCLES}) reached")

print("\n=== Post-loop: /admin/market-intelligence/coverage (final) ===")
r = session.get(f"{BACKEND_URL}/api/v1/admin/market-intelligence/coverage", timeout=30)
coverage_after = r.json() if r.status_code == 200 else {"error": r.text[:500]}
evidence["coverage_after"] = coverage_after

evidence["stop_reason_final"] = stop_reason_final
evidence["distinct_symbols_scanned_this_run"] = sorted(distinct_symbols_scanned)
evidence["distinct_symbols_scanned_count_this_run"] = len(distinct_symbols_scanned)
evidence["total_covered_including_baseline"] = BASELINE_ALREADY_SCANNED + len(distinct_symbols_scanned)
evidence["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

executed_run_ids = [c.get("run_id") for c in evidence["cycles"] if c.get("executed") and c.get("run_id") is not None]
evidence["executed_run_ids"] = executed_run_ids

print("\n=== Collecting ranked opportunities across every executed run this pass ===")
all_categories = {}
for rid in executed_run_ids:
    r = session.get(f"{BACKEND_URL}/api/v1/market/opportunities", params={"run_id": rid}, timeout=60)
    if r.status_code != 200:
        print(f"GET /market/opportunities?run_id={rid} failed: status={r.status_code} body={r.text[:300]}")
        continue
    data = r.json()
    for cat in data.get("categories", []):
        all_categories.setdefault(cat["category"], {"label_ar": cat["label_ar"], "entries_by_symbol": {}})
        for entry in cat["entries"]:
            entry["_scan_run_id"] = rid
            all_categories[cat["category"]]["entries_by_symbol"][entry["symbol"]] = entry

evidence["opportunities_by_category"] = {
    cat: {"label_ar": v["label_ar"], "entries": list(v["entries_by_symbol"].values())}
    for cat, v in all_categories.items()
}

print("\n=== Decision-intelligence window aggregate (cross-run, real SQL aggregate) ===")
r = session.get(f"{BACKEND_URL}/api/v1/admin/market-intelligence/decision-intelligence", params={"within_hours": 24}, timeout=30)
evidence["decision_intelligence_24h"] = r.json() if r.status_code == 200 else {"error": r.text[:500]}

with open(EVIDENCE_FILE, "w") as f:
    json.dump(evidence, f, indent=2, default=str)

print(f"\n=== DONE. stop_reason_final={stop_reason_final} ===")
print(f"cycles_executed={len([c for c in evidence['cycles'] if c.get('executed')])}")
print(f"distinct_symbols_scanned_this_run={len(distinct_symbols_scanned)}")
print(f"total_covered_including_baseline={evidence['total_covered_including_baseline']} / target_universe={target_universe}")
print(f"Evidence written to {EVIDENCE_FILE}")
