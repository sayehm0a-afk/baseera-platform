"""One-off (temporary, read-only, zero SAHMK cost): root-causes why
stage1_universe_size/stage1_evaluated_count/stage1_candidate_count/
last_full_scan_at are still null on GET /api/v1/radar/summary in
production despite the write path (record_stage1_metrics, called from
run_radar_v2_cycle) having been deployed. Reads only already-persisted
state via GET /api/v1/admin/system/summary (which scan is genuinely
the most recent MarketScanRun row, when it ran, whether the scheduler
that would produce a NEW one is even running) and GET /api/v1/radar/
summary (the funnel fields themselves) -- never triggers a scan.
"""

import json
import os
import sys

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]

session = requests.Session()
r = session.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)

r = session.get(f"{BACKEND_URL}/api/v1/admin/system/summary", timeout=30)
if r.status_code != 200:
    print(f"GET /admin/system/summary failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)

summary = r.json()
print("--- deployment_commit ---")
print(summary.get("deployment_commit"))

print("\n--- scheduler state ---")
for field in (
    "market_intelligence_scheduler_running",
    "live_market_mode_enabled",
    "live_market_mode_running",
    "live_market_mode_market_currently_open",
):
    print(f"{field}: {summary.get(field)!r}")

print("\n--- most recent MarketScanRun (any kind) ---")
for field in (
    "last_scan_id",
    "last_scan_status",
    "last_scan_started_at",
    "last_scan_finished_at",
    "last_scan_symbols_requested",
    "last_scan_symbols_succeeded",
    "last_scan_symbols_failed",
):
    print(f"{field}: {summary.get(field)!r}")

r = session.get(f"{BACKEND_URL}/api/v1/radar/summary", timeout=30)
print("\n--- /api/v1/radar/summary (funnel fields) ---")
if r.status_code != 200:
    print(f"FAILED: status={r.status_code} body={r.text[:1000]}")
    sys.exit(1)

radar_summary = r.json()
for field in (
    "stage1_universe_size",
    "stage1_evaluated_count",
    "stage1_candidate_count",
    "stage2_candidate_cap",
    "stage2_validated_count",
    "final_opportunities_count",
    "last_full_scan_at",
    "most_recent_emitted_at",
    "live_opportunity_count",
):
    print(f"{field}: {radar_summary.get(field)!r}")

print("\n--- full radar summary JSON (for reference) ---")
print(json.dumps(radar_summary, indent=2, default=str))
