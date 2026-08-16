"""One-off, read-only, zero-SAHMK-cost status check for the "continue
the real full-universe M10 scan rotation" request.

Two reads, neither of which touches SAHMK:
  1. The actual production Railway env vars for the backend service
     (MARKET_INTELLIGENCE_SCAN_INTERVAL, MARKET_SCAN_SYMBOLS_PER_CYCLE,
     MARKET_SCAN_LEADER_LEASE_SECONDS, LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS)
     -- dumped to JSON by a prior `railway variables --service backend
     --json` step (see full-market-scan-status.yml), read here rather
     than guessed from source-code defaults.
  2. GET /admin/system/summary (staff auth) -- deployment commit,
     health, SAHMK quota counters, scan_lock_active, market status.
     Same zero-cost local/cached-state read verify_deployment.py and
     m10_live_session.py already use.

Throwaway diagnostic tooling, same convention as the other scripts in
this directory -- not application code.
"""

import json
import os
import sys

import requests

RAILWAY_VARS_FILE = os.environ.get("RAILWAY_VARS_FILE", "").strip()
BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]

INTERESTING_VARS = [
    "MARKET_INTELLIGENCE_SCAN_INTERVAL",
    "MARKET_SCAN_SYMBOLS_PER_CYCLE",
    "MARKET_SCAN_LEADER_LEASE_SECONDS",
    "MARKET_SCAN_MIN_BACKGROUND_QUOTA_REMAINING",
    "LIVE_MARKET_MODE_POLL_INTERVAL_SECONDS",
    "MARKET_MAX_SCAN_RUN_DURATION_HOURS",
    "MARKET_INTELLIGENCE_SCHEDULER_ENABLED",
]

print("=== Real production Railway env vars ===")
if RAILWAY_VARS_FILE and os.path.exists(RAILWAY_VARS_FILE):
    with open(RAILWAY_VARS_FILE) as f:
        all_vars = json.load(f)
    found = {k: all_vars.get(k) for k in INTERESTING_VARS}
    print(json.dumps(found, indent=2, default=str))
else:
    print("RAILWAY_VARS_FILE not provided or not found -- skipped.")

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
print("\n=== /admin/system/summary (zero SAHMK cost) ===")
print(json.dumps(summary, indent=2, default=str))

quota = summary.get("sahmk_quota_status") or {}
print("\n=== Quota counters ===")
for key in (
    "requests_used_today", "background_requests_used_today", "critical_requests_used_today",
    "remaining_today", "remaining_today_for_background", "reserved_for_critical", "max_per_day",
    "upstream_confirmed_exhausted",
):
    print(f"{key}: {quota.get(key)}")

print("\n=== Health / lock / market status ===")
for key in (
    "database_health", "redis_health", "market_data_health", "market_data_status",
    "market_data_circuit_breaker_state", "scan_lock_active", "live_market_mode_running",
    "live_market_mode_market_currently_open", "market_status", "market_intelligence_scheduler_running",
    "last_scan_id", "last_scan_status", "last_scan_symbols_requested", "last_scan_symbols_succeeded",
):
    print(f"{key}: {summary.get(key)}")
