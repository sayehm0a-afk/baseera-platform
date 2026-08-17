"""One-off, read-only pre-market readiness check for Basirah Radar V2
(2026-08-17, Saudi market open at 10:00 Riyadh / 07:00 UTC).

Makes ONLY GET requests against endpoints that are already proven
zero-SAHMK-cost (see verify_radar_v2.py / verify_two_stage_scan.py for
the same pattern applied to the scan endpoints themselves). No POST is
made here -- this script exists purely to observe real, current
production telemetry before deciding anything about today's live test:

  1. Full /admin/system/summary -- SAHMK quota state (used/remaining/
     reserved/by_operation/resets_at_utc) AND scheduler-running flags
     (ingestion_scheduler_running, market_intelligence_scheduler_running,
     live_market_mode_*), plus any currently-DEFERRED ingestion job.
  2. Radar V2 summary + sahmk-consumption (RADAR_V2-tagged usage so
     far today).

Every number printed comes directly from a live production HTTP
response. Nothing here is estimated, and nothing here spends any
SAHMK quota.
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


def _get(path, **kwargs):
    r = session.get(f"{BACKEND_URL}{path}", timeout=60, **kwargs)
    if r.status_code != 200:
        print(f"GET {path} failed: status={r.status_code} body={r.text[:500]}")
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

print("\n=== GET /admin/system/summary (full, zero SAHMK cost) ===")
summary = _get("/api/v1/admin/system/summary")
deployed_commit = summary.get("deployment_commit")
print(f"deployment_commit reported: {deployed_commit}")
if EXPECTED_COMMIT and deployed_commit != EXPECTED_COMMIT:
    print(f"WARNING: deployed commit '{deployed_commit}' does not match expected '{EXPECTED_COMMIT}'.")

print(json.dumps(summary, indent=2, default=str))

print("\n--- Quota headline ---")
quota = summary.get("sahmk_quota_status") or {}
print(f"day_window_key_utc: {quota.get('day_window_key_utc')}")
print(f"resets_at_utc: {quota.get('resets_at_utc')}")
print(f"max_per_day: {quota.get('max_per_day')}  reserved_for_critical: {quota.get('reserved_for_critical')}")
print(f"requests_used_today: {quota.get('requests_used_today')}")
print(f"critical_requests_used_today: {quota.get('critical_requests_used_today')}")
print(f"background_requests_used_today: {quota.get('background_requests_used_today')}")
print(f"remaining_today: {quota.get('remaining_today')}")
print(f"remaining_today_for_background: {quota.get('remaining_today_for_background')}")
print(f"upstream_confirmed_exhausted: {quota.get('upstream_confirmed_exhausted')}")
print(f"by_operation: {json.dumps(quota.get('by_operation'), indent=2)}")

print("\n--- Scheduler state ---")
print(f"ingestion_scheduler_running: {summary.get('ingestion_scheduler_running')}")
print(f"ingestion_deferred_job_count: {summary.get('ingestion_deferred_job_count')}")
print(f"ingestion_next_retry_at: {summary.get('ingestion_next_retry_at')}")
print(f"market_intelligence_scheduler_running: {summary.get('market_intelligence_scheduler_running')}")
print(f"live_market_mode_enabled: {summary.get('live_market_mode_enabled')}")
print(f"live_market_mode_running: {summary.get('live_market_mode_running')}")
print(f"live_market_mode_market_currently_open: {summary.get('live_market_mode_market_currently_open')}")
print(f"last_scan_id/status: {summary.get('last_scan_id')} / {summary.get('last_scan_status')}")
print(f"last_scan_started_at/finished_at: {summary.get('last_scan_started_at')} / {summary.get('last_scan_finished_at')}")

print("\n=== GET .../radar-v2/summary (zero SAHMK cost) ===")
radar_summary = _get("/api/v1/admin/market-intelligence/radar-v2/summary")
print(json.dumps(radar_summary, indent=2, default=str))

print("\n=== GET .../radar-v2/sahmk-consumption (zero SAHMK cost) ===")
radar_consumption = _get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")
print(json.dumps(radar_consumption, indent=2, default=str))

print("\n=== DONE (read-only, zero SAHMK requests made by this script) ===")
