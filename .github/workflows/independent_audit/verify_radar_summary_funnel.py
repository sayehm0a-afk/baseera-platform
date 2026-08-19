"""One-off (temporary, read-only, zero SAHMK cost): confirms the deployed
commit and that GET /api/v1/radar/summary honestly exposes the new Radar
V2 Stage 1 scan-funnel fields (stage1_universe_size/stage1_candidate_count/
stage2_candidate_cap/last_full_scan_at) added in PR #75 -- either honestly
null (no Radar V2 cycle has completed since this deploy) or a real number,
never fabricated. Does not trigger a scan; only reads already-persisted
state via the existing consumer route, same as a real subscriber's page
load would.
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
print("--- deployment_commit ---")
print(actual_commit)

r = session.get(f"{BACKEND_URL}/api/v1/radar/summary", timeout=30)
print("\n--- /api/v1/radar/summary ---")
if r.status_code != 200:
    print(f"FAILED: status={r.status_code} body={r.text[:1000]}")
    sys.exit(1)

radar_summary = r.json()
print(json.dumps(radar_summary, indent=2, default=str))

print("\n--- funnel field presence check ---")
for field in ("stage1_universe_size", "stage1_candidate_count", "stage2_candidate_cap", "last_full_scan_at"):
    present = field in radar_summary
    print(f"{field}: present={present} value={radar_summary.get(field)!r}")

if "stage2_candidate_cap" not in radar_summary or radar_summary.get("stage2_candidate_cap") != 15:
    print(f"\nUNEXPECTED: stage2_candidate_cap should be 15, got {radar_summary.get('stage2_candidate_cap')!r}")
    sys.exit(1)

print("\n--- verification ---")
print(f"deployment_commit: {actual_commit}")
if EXPECTED_COMMIT:
    match = actual_commit == EXPECTED_COMMIT
    print(f"expected_commit:   {EXPECTED_COMMIT}")
    print(f"MATCH: {match}")
    sys.exit(0 if match else 1)
