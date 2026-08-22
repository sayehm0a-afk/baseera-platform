"""URGENT LIVE DATA CONNECTION RECOVERY (one-off, temporary, read-only,
zero SAHMK cost): the production frontend is showing "تعذر الحصول على
بيانات حقيقية من مزود البيانات" (RealDataStatusBanner.tsx, driven by GET
/health/market-data's can_publish_recommendations=false under
STRICT_REAL_DATA). This script gathers every real signal needed to
diagnose the failing provider/path without ever calling SAHMK itself:

  - GET /health/live, /health/ready (DB/Redis connectivity)
  - GET /health/market-data (provider auth/connectivity/strict-mode state)
  - GET /api/v1/admin/system/summary (zero-network-call snapshot: SAHMK
    quota, scheduler/Live-Market-Mode running state, last scan
    timestamps, market_data_status classification)
  - GET /api/v1/radar/summary (the exact consumer Radar page payload --
    Stage 1/2 funnel counts, last_full_scan_at, most_recent_emitted_at)
  - Recent `railway logs` tail, grepped for the exact failure signatures
    (401/403/429/5xx/timeout/DNS/TLS/connection-refused)

Never triggers a scan, never calls SAHMK, never modifies anything.
Throwaway diagnostic tooling, same convention as the other scripts in
this directory."""

import json
import os
import re
import subprocess
import sys

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def get(session, path, **kw):
    try:
        r = session.get(f"{BACKEND_URL}{path}", timeout=30, **kw)
        return r
    except requests.RequestException as exc:
        print(f"GET {path} raised: {exc}")
        return None


section("0. Public health probes (no auth required)")
anon = requests.Session()
for path in ("/health/live", "/health/ready", "/health/market-data"):
    r = get(anon, path)
    if r is None:
        continue
    print(f"\n--- GET {path} -> HTTP {r.status_code} ---")
    try:
        print(json.dumps(r.json(), indent=2, default=str))
    except ValueError:
        print(r.text[:1000])

section("1. Staff login")
staff = requests.Session()
r = staff.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
print("Staff login OK.")

section("2. Zero-cost admin system summary (quota / scheduler / scan state)")
r = get(staff, "/api/v1/admin/system/summary")
summary = {}
if r is not None and r.status_code == 200:
    summary = r.json()
    print(json.dumps(summary, indent=2, default=str))
else:
    print(f"GET /admin/system/summary failed: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("3. Consumer Radar page payload (GET /api/v1/radar/summary -- exactly what the frontend Radar page shows)")
r = get(staff, "/api/v1/radar/summary")
radar_summary = {}
if r is not None and r.status_code == 200:
    radar_summary = r.json()
    print(json.dumps(radar_summary, indent=2, default=str))
else:
    print(f"GET /api/v1/radar/summary failed: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("4. Recent backend logs (tail, grepped for the exact failure signatures)")
try:
    proc = subprocess.run(
        ["timeout", "25", "railway", "logs", "--service", "backend"],
        capture_output=True, text=True, timeout=30,
    )
    raw_logs = (proc.stdout or "") + (proc.stderr or "")
except Exception as exc:  # noqa: BLE001 -- diagnostic tooling, never fatal
    raw_logs = ""
    print(f"Could not fetch railway logs: {exc}")

error_pattern = re.compile(
    r"(timeout|timed out|DNS|dns resolution|TLS|SSL|certificate|401|403|429|"
    r"5\d{2}\b|connection refused|ConnectionError|ConnectTimeout|"
    r"StrictRealDataUnavailableError|circuit.?breaker|SAHMK|sahmk)",
    re.IGNORECASE,
)
matched_lines = [line for line in raw_logs.splitlines() if error_pattern.search(line)]
print(f"Total log lines fetched: {len(raw_logs.splitlines())}")
print(f"Lines matching failure-signature patterns: {len(matched_lines)}")
for line in matched_lines[-80:]:
    print(line)

section("5. Backend environment variable NAMES only (no values -- checks for missing/invalid config)")
try:
    proc = subprocess.run(
        ["railway", "variables", "--service", "backend", "--kv"],
        capture_output=True, text=True, timeout=30,
    )
    var_names = sorted({line.split("=", 1)[0] for line in (proc.stdout or "").splitlines() if "=" in line})
    relevant = [n for n in var_names if any(k in n.upper() for k in ("SAHMK", "STRICT_REAL_DATA", "DATABASE", "REDIS"))]
    print("Relevant variable names present on backend service:")
    for n in relevant:
        print(f"  {n}")
    if proc.stderr:
        print("stderr:", proc.stderr[:500])
except Exception as exc:  # noqa: BLE001
    print(f"Could not list railway variables: {exc}")

section("6. Derived diagnosis")
market_data_status = summary.get("market_data_status")
market_data_provider = summary.get("market_data_provider")
market_data_health = summary.get("market_data_health")
last_connectivity_status = summary.get("market_data_last_connectivity_status")
last_connectivity_at = summary.get("market_data_last_connectivity_at")
last_real_data_at = summary.get("market_data_last_real_data_at")
breaker_state = summary.get("market_data_circuit_breaker_state")
quota = summary.get("sahmk_quota_status") or {}

print(f"market_data_status:              {market_data_status}")
print(f"market_data_provider:            {market_data_provider}")
print(f"market_data_health:              {market_data_health}")
print(f"market_data_last_connectivity_status: {last_connectivity_status}")
print(f"market_data_last_connectivity_at:     {last_connectivity_at}")
print(f"market_data_last_real_data_at:        {last_real_data_at}")
print(f"market_data_circuit_breaker_state:    {breaker_state}")
print("sahmk_key_present (from /health/market-data above -- see section 0)")
print(f"upstream_confirmed_exhausted:    {quota.get('upstream_confirmed_exhausted')}")
print(f"remaining_today:                 {quota.get('remaining_today')}")
print(f"remaining_today_for_background:  {quota.get('remaining_today_for_background')}")
print(f"market_intelligence_scheduler_running: {summary.get('market_intelligence_scheduler_running')}")
print(f"live_market_mode_enabled:        {summary.get('live_market_mode_enabled')}")
print(f"live_market_mode_running:        {summary.get('live_market_mode_running')}")
print(f"live_market_mode_market_currently_open: {summary.get('live_market_mode_market_currently_open')}")
print(f"last_scan_id/status:             {summary.get('last_scan_id')} / {summary.get('last_scan_status')}")
print(f"last_scan_started_at/finished_at: {summary.get('last_scan_started_at')} / {summary.get('last_scan_finished_at')}")
print(f"scan_lock_active:                {summary.get('scan_lock_active')}")
print(f"last_full_scan_at (Radar V2):    {radar_summary.get('last_full_scan_at')}")
print(f"most_recent_emitted_at:          {radar_summary.get('most_recent_emitted_at')}")
print(f"stage1_universe_size:            {radar_summary.get('stage1_universe_size')}")
print(f"stage1_evaluated_count:          {radar_summary.get('stage1_evaluated_count')}")
print(f"stage1_candidate_count:          {radar_summary.get('stage1_candidate_count')}")
print(f"stage2_validated_count:          {radar_summary.get('stage2_validated_count')}")
print(f"final_opportunities_count:       {radar_summary.get('final_opportunities_count')}")
print(f"live_opportunity_count:          {radar_summary.get('live_opportunity_count')}")

print("\nDone. See sections above for the complete real evidence.")
