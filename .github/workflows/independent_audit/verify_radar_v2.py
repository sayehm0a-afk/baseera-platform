"""One-off, real-production evidence script for Basirah Radar V2
(2026-08-16, PR #49): proves, with real measured numbers (never
assumed, never fabricated), that:

  1. The exact expected commit is running in production.
  2. GET .../radar-v2/summary, .../opportunities, .../performance, and
     .../sahmk-consumption all respond (zero SAHMK cost -- read-only
     queries against already-persisted data).
  3. POST .../radar-v2/scan -- the one call that MAY spend real SAHMK
     quota -- is measured with a before/after sahmk_quota_status diff,
     exactly like verify_two_stage_scan.py already does for Stage 2.
     If Radar V2 declines to run (any real stop_reason -- quota-related
     or otherwise), that refusal is reported as real evidence, never
     silently retried or worked around.
  4. The critical/protected reserve
     (critical_requests_used_today) is unchanged before/after the
     scan call, regardless of whether it executed.

Every number in the printed evidence comes directly from a live
production HTTP response.
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
evidence = {}


def _get(path, **kwargs):
    r = session.get(f"{BACKEND_URL}{path}", timeout=60, **kwargs)
    if r.status_code != 200:
        print(f"GET {path} failed: status={r.status_code} body={r.text[:500]}")
        sys.exit(1)
    return r.json()


def _post(path, body, **kwargs):
    r = session.post(f"{BACKEND_URL}{path}", json=body, timeout=90, **kwargs)
    if r.status_code != 200:
        print(f"POST {path} failed: status={r.status_code} body={r.text[:500]}")
        sys.exit(1)
    return r.json()


print("=== Staff login ===")
r = session.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
print("Login OK.")
csrf_token = session.cookies.get("csrf_token")
session.headers.update({"X-CSRF-Token": csrf_token})

print("\n=== Pre-flight: /admin/system/summary ===")
summary_before = _get("/api/v1/admin/system/summary")
deployed_commit = summary_before.get("deployment_commit")
print(f"deployment_commit reported: {deployed_commit}")
if EXPECTED_COMMIT and deployed_commit != EXPECTED_COMMIT:
    print(f"FATAL: deployed commit '{deployed_commit}' does not match expected '{EXPECTED_COMMIT}'. Aborting.")
    sys.exit(1)

quota_before_anything = summary_before.get("sahmk_quota_status") or {}
evidence["quota_before_anything"] = quota_before_anything
print("sahmk_quota_status (before anything):")
print(json.dumps(quota_before_anything, indent=2, default=str))

print("\n=== GET .../radar-v2/summary (zero SAHMK cost) ===")
radar_summary = _get("/api/v1/admin/market-intelligence/radar-v2/summary")
evidence["radar_summary_before_scan"] = radar_summary
print(json.dumps(radar_summary, indent=2, default=str))

print("\n=== GET .../radar-v2/opportunities (zero SAHMK cost) ===")
radar_opportunities_before = _get("/api/v1/admin/market-intelligence/radar-v2/opportunities?limit=20")
evidence["radar_opportunities_before_scan_count"] = len(radar_opportunities_before)
print(f"Live opportunities before scan: {len(radar_opportunities_before)}")

print("\n=== GET .../radar-v2/performance (zero SAHMK cost) ===")
radar_performance_before = _get("/api/v1/admin/market-intelligence/radar-v2/performance")
evidence["radar_performance_before_scan"] = radar_performance_before
print(json.dumps(radar_performance_before, indent=2, default=str))

print("\n=== GET .../radar-v2/sahmk-consumption (zero SAHMK cost) ===")
radar_consumption_before = _get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")
evidence["radar_sahmk_consumption_before_scan"] = radar_consumption_before
print(json.dumps(radar_consumption_before, indent=2, default=str))

print("\n=== POST .../radar-v2/scan (may spend real SAHMK quota) ===")
quota_before_scan = _get("/api/v1/admin/system/summary").get("sahmk_quota_status") or {}
scan_result = _post("/api/v1/admin/market-intelligence/radar-v2/scan", {})
quota_after_scan = _get("/api/v1/admin/system/summary").get("sahmk_quota_status") or {}

evidence["radar_scan_result"] = scan_result
print(json.dumps(scan_result, indent=2, default=str))

requests_before = quota_before_scan.get("requests_used_today")
requests_after = quota_after_scan.get("requests_used_today")
critical_before = quota_before_scan.get("critical_requests_used_today")
critical_after = quota_after_scan.get("critical_requests_used_today")
scan_sahmk_delta = (
    (requests_after - requests_before) if requests_before is not None and requests_after is not None else None
)
critical_delta = (
    (critical_after - critical_before) if critical_before is not None and critical_after is not None else None
)
evidence["radar_scan_sahmk_requests_delta"] = scan_sahmk_delta
evidence["radar_scan_critical_reserve_delta"] = critical_delta

print(f"\nstage1_universe_size: {scan_result.get('stage1_universe_size')}")
print(f"stage1_candidate_count: {scan_result.get('stage1_candidate_count')}")
print(f"stage2_candidate_cap: {scan_result.get('stage2_candidate_cap')}")
print(f"stage2_symbols_selected: {scan_result.get('stage2_symbols_selected')}")
print(f"stage2_executed: {scan_result.get('stage2_executed')}")
print(f"stage2_stop_reason: {scan_result.get('stage2_stop_reason')}")
print(f"opportunities_emitted: {len(scan_result.get('opportunities_emitted') or [])}")
print(f"opportunities_suppressed_as_duplicate: {scan_result.get('opportunities_suppressed_as_duplicate')}")
print(f"\nSAHMK requests_used_today before scan: {requests_before}")
print(f"SAHMK requests_used_today after scan:  {requests_after}")
print(f"Radar V2 scan real SAHMK cost (delta): {scan_sahmk_delta}")
print(f"critical_requests_used_today before/after: {critical_before} / {critical_after} "
      f"(delta={critical_delta})  <-- must be 0")

print("\n=== Final: radar-v2/summary + sahmk-consumption after the scan ===")
radar_summary_after = _get("/api/v1/admin/market-intelligence/radar-v2/summary")
radar_consumption_after = _get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")
evidence["radar_summary_after_scan"] = radar_summary_after
evidence["radar_sahmk_consumption_after_scan"] = radar_consumption_after
print("radar-v2/summary (after):")
print(json.dumps(radar_summary_after, indent=2, default=str))
print("\nradar-v2/sahmk-consumption (after):")
print(json.dumps(radar_consumption_after, indent=2, default=str))

print("\n=== EVIDENCE (full JSON) ===")
print(json.dumps(evidence, indent=2, default=str))
