"""One-off: confirm the exact commit currently running in production
after a deploy, via the one already-existing zero-SAHMK-cost read
(GET /admin/system/summary -- a local/cached state read, never a live
provider call, per m10_live_session.py's own step-1 docstring). Prints
deployment_commit, sahmk_quota_status, and the scheduler/leader-lock
fields the 2026-08-16 SAHMK quota-exhaustion fix (PR #39) added, so a
human/AI reviewer can confirm the fix is actually live without any
SAHMK quota spent. Throwaway diagnostic tooling, same convention as
dump_logs.py / api_audit.py in this directory.

Also (read-only, zero SAHMK cost -- both routes read already-persisted
DB rows from the most recent scan, never touch the provider) prints
the real per-symbol opportunity detail for the most recent MarketScanRun
(GET /scan/{run_id} + GET /opportunities?run_id=...), so the exact
symbols/prices/scores/targets/stops a live scan produced can be
inspected without re-running a scan.
"""

import json
import os
import sys

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
EXPECTED_COMMIT = os.environ.get("EXPECTED_COMMIT", "").strip()

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
actual_commit = summary.get("deployment_commit")
print(json.dumps(summary, indent=2, default=str))

last_scan_id = summary.get("last_scan_id")
if last_scan_id is not None:
    r = session.get(f"{BACKEND_URL}/api/v1/market/scan/{last_scan_id}", timeout=30)
    print(f"\n--- scan_run_{last_scan_id} ---")
    print(json.dumps(r.json() if r.status_code == 200 else {"status": r.status_code, "body": r.text[:500]}, indent=2, default=str))

    r = session.get(f"{BACKEND_URL}/api/v1/market/opportunities", params={"run_id": last_scan_id}, timeout=30)
    print(f"\n--- opportunities_run_{last_scan_id} ---")
    print(json.dumps(r.json() if r.status_code == 200 else {"status": r.status_code, "body": r.text[:500]}, indent=2, default=str))

print("\n--- verification ---")
print(f"deployment_commit: {actual_commit}")
if EXPECTED_COMMIT:
    match = actual_commit == EXPECTED_COMMIT
    print(f"expected_commit:   {EXPECTED_COMMIT}")
    print(f"MATCH: {match}")
    sys.exit(0 if match else 1)
