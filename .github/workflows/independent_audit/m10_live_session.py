"""M10 LIVE VALIDATION SESSION 1 -- strict GO/NO-GO check, then (only on
GO) create the real (is_dry_run=False) ValidationSession, run exactly
ONE controlled diagnostic scan as the session's live-freshness proof
and first real evidence, and close the session -- all against real
production, no mocking, no backfilling, no simulated data.

Cost discipline (mandate: "protect SAHMK quota aggressively, do not
perform redundant provider calls"):
  - Steps 1-3 below cost zero SAHMK quota (pure HTTP/DB reads).
  - Creating the ValidationSession costs zero SAHMK quota; the market-
    open/closed check is read back for free from the session's own
    `market_regime_at_start` (captured via the local, zero-network
    `get_market_status()` at creation time) -- NOT from the costly
    GET /market/status route, which bundles a real provider health
    probe.
  - If the market is not OPEN, the session is immediately aborted and
    NO further calls are made -- zero SAHMK quota spent on this path.
  - If OPEN, exactly ONE POST /diagnostic-scan call is made. It is
    simultaneously the required "prove SAHMK returns a fresh real
    quote" evidence AND the session's first real scan -- never two
    separate calls for the same purpose.

This script and its wrapper workflow are throwaway one-off tooling,
same convention as api_audit.py / dump_logs.py in this directory --
not application code.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
EXPECTED_COMMIT = os.environ.get("EXPECTED_COMMIT", "").strip()

evidence = {}


def log(label, obj):
    evidence[label] = obj
    print(f"\n--- {label} ---")
    print(json.dumps(obj, indent=2, default=str))


def print_final_bundle():
    print("\n--- final_evidence_bundle ---")
    print(json.dumps(evidence, indent=2, default=str))


def call(session, method, path, csrf=None, **kw):
    headers = kw.pop("headers", {})
    if csrf:
        headers["X-CSRF-Token"] = csrf
    url = f"{BACKEND_URL}{path}"
    try:
        resp = session.request(method, url, headers=headers, timeout=60, **kw)
        return resp
    except requests.RequestException as exc:
        return exc


def get_csrf(session):
    return session.cookies.get("csrf_token")


def no_go(reason, extra=None):
    print("\n" + "=" * 70)
    print("M10 LIVE GO: NO")
    print(f"BLOCKER: {reason}")
    print("=" * 70)
    if extra is not None:
        log("no_go_evidence", extra)
    print_final_bundle()
    sys.exit(0)


def infra_error(reason, extra=None):
    print("\n" + "=" * 70)
    print("M10 LIVE SESSION: INFRA ERROR (not a normal NO-GO -- investigate)")
    print(f"REASON: {reason}")
    print("=" * 70)
    if extra is not None:
        log("infra_error_evidence", extra)
    print_final_bundle()
    sys.exit(1)


# ---------------------------------------------------------------------------
# 0. Staff login (OWNER role required to create/close a ValidationSession)
# ---------------------------------------------------------------------------
print("=== 0. Staff login ===")
staff = requests.Session()
r = call(staff, "POST", "/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD})
if not isinstance(r, requests.Response) or r.status_code != 200:
    infra_error("Staff login failed", {"status": getattr(r, "status_code", None), "body": getattr(r, "text", str(r))[:500]})
csrf = get_csrf(staff)

r = call(staff, "GET", "/api/v1/auth/me")
me = r.json() if isinstance(r, requests.Response) and r.status_code == 200 else {}
log("staff_identity", {"status": getattr(r, "status_code", None), "is_staff": me.get("is_staff"), "staff_role": me.get("staff_role")})

# ---------------------------------------------------------------------------
# 1. Zero-cost precheck: deployment commit + SAHMK quota, via
#    /admin/system/summary (no network call to SAHMK).
# ---------------------------------------------------------------------------
print("\n=== 1. Zero-cost precheck: deployment commit + quota ===")
r = call(staff, "GET", "/api/v1/admin/system/summary")
if not isinstance(r, requests.Response) or r.status_code != 200:
    infra_error("GET /admin/system/summary failed", {"status": getattr(r, "status_code", None), "body": getattr(r, "text", str(r))[:500]})
summary = r.json()
log("system_summary", summary)

actual_commit = summary.get("deployment_commit") or ""
if EXPECTED_COMMIT and actual_commit != EXPECTED_COMMIT:
    no_go(
        f"Deployed commit ({actual_commit}) does not match expected verified M10 commit ({EXPECTED_COMMIT}).",
        {"deployment_commit": actual_commit, "expected_commit": EXPECTED_COMMIT},
    )

quota = summary.get("sahmk_quota_status") or {}
remaining_bg = quota.get("remaining_today_for_background")
remaining_today = quota.get("remaining_today")
upstream_exhausted = quota.get("upstream_confirmed_exhausted")
if upstream_exhausted:
    no_go("SAHMK upstream is confirmed exhausted (upstream_confirmed_exhausted=true).", quota)
if remaining_bg is not None and remaining_bg <= 0:
    no_go("SAHMK background-eligible quota is exhausted (remaining_today_for_background<=0).", quota)
if remaining_today is not None and remaining_today <= 0:
    no_go("SAHMK daily quota is exhausted (remaining_today<=0).", quota)

market_data_status = summary.get("market_data_status")
market_data_provider = summary.get("market_data_provider")
if market_data_provider != "sahmk":
    no_go(f"Current market data provider is not sahmk (got {market_data_provider!r}) -- refusing to validate off non-real data.", summary)

last_scan_status = summary.get("last_scan_status")
if last_scan_status in ("PENDING", "RUNNING"):
    no_go(
        f"A production market scan is already in progress (last_scan_id={summary.get('last_scan_id')}, "
        f"status={last_scan_status}) -- refusing to make the diagnostic-scan call while it's active, to "
        "avoid a redundant SAHMK connectivity probe and an overlap-guard rejection.",
        summary,
    )

# ---------------------------------------------------------------------------
# 2. Zero-cost health check
# ---------------------------------------------------------------------------
print("\n=== 2. Zero-cost health check ===")
for path in ["/health/live", "/health/ready"]:
    r = call(staff, "GET", path)
    ok = isinstance(r, requests.Response) and r.status_code == 200
    log(f"health{path.replace('/', '_')}", {"status": getattr(r, "status_code", None), "ok": ok})
    if not ok:
        infra_error(f"GET {path} did not return 200", {"status": getattr(r, "status_code", None)})

# ---------------------------------------------------------------------------
# 3. Zero-cost infra check: M10 validation-session infra reachable, and
#    no conflicting real (is_dry_run=false) session already RUNNING.
# ---------------------------------------------------------------------------
print("\n=== 3. Zero-cost M10 infra check ===")
r = call(staff, "GET", "/api/v1/admin/ai-evolution/validation-sessions", params={"is_dry_run": "false"})
if not isinstance(r, requests.Response) or r.status_code != 200:
    infra_error("GET /admin/ai-evolution/validation-sessions failed", {"status": getattr(r, "status_code", None), "body": getattr(r, "text", str(r))[:500]})
existing_sessions = r.json().get("sessions", [])
log("existing_real_validation_sessions", existing_sessions)
running = [s for s in existing_sessions if s.get("status") == "RUNNING"]
if running:
    no_go(f"A real (non-dry-run) validation session is already RUNNING (id={running[0]['id']}).", running[0])

# ---------------------------------------------------------------------------
# 4. Create the real ValidationSession (zero SAHMK cost). Its
#    market_regime_at_start is captured for free at creation time by
#    the local get_market_status() computation -- read back below
#    instead of calling the costly GET /market/status route.
# ---------------------------------------------------------------------------
print("\n=== 4. Create real ValidationSession ===")
session_name = f"M10 Live Validation Session 1 - {datetime.now(timezone.utc).isoformat()}"
r = call(
    staff, "POST", "/api/v1/admin/ai-evolution/validation-sessions", csrf=csrf,
    json={"name": session_name, "is_dry_run": False, "notes": "M10 LIVE SESSION 1 -- automated strict GO/NO-GO run."},
)
if isinstance(r, requests.Response) and r.status_code == 409:
    no_go("Conflict creating ValidationSession (race with another session).", {"status": 409, "body": r.text[:500]})
if isinstance(r, requests.Response) and r.status_code == 403:
    no_go("STAFF_EMAIL account lacks OWNER role -- cannot create a ValidationSession.", {"status": 403, "body": r.text[:500]})
if not isinstance(r, requests.Response) or r.status_code != 201:
    infra_error("POST /admin/ai-evolution/validation-sessions failed", {"status": getattr(r, "status_code", None), "body": getattr(r, "text", str(r))[:500]})

vsession = r.json()
log("created_validation_session", vsession)
vsession_id = vsession["id"]

# Gate 6, explicit: this run must be tagged as the real M10 LIVE
# validation session, never a dry run -- assert it against the
# session record the backend actually persisted, not just the
# request payload we sent.
if vsession.get("is_dry_run") is not False:
    infra_error(
        f"Created session id={vsession_id} is not tagged is_dry_run=false (got {vsession.get('is_dry_run')!r}) "
        "-- refusing to treat it as a real M10 live session.",
        vsession,
    )
log("gate_6_live_not_dry_run_confirmed", {"validation_session_id": vsession_id, "is_dry_run": vsession.get("is_dry_run")})

# ---------------------------------------------------------------------------
# 5. Free market-status read-back. If not OPEN, abort immediately --
#    zero SAHMK quota ever spent on this run.
# ---------------------------------------------------------------------------
print("\n=== 5. Free Tadawul market-status read-back ===")
regime = vsession.get("market_regime_at_start") or {}
log("market_regime_at_start", regime)
market_status = regime.get("market_status")

if market_status != "OPEN":
    r = call(staff, "POST", f"/api/v1/admin/ai-evolution/validation-sessions/{vsession_id}/close",
             params={"aborted": "true"}, csrf=csrf)
    closed = r.json() if isinstance(r, requests.Response) and r.status_code == 200 else {"status": getattr(r, "status_code", None)}
    log("aborted_session", closed)
    no_go(
        f"Tadawul is not currently in an OPEN trading window (market_status={market_status!r}). "
        "Session aborted; zero SAHMK quota spent.",
        regime,
    )

# ---------------------------------------------------------------------------
# 6. Exactly ONE controlled diagnostic scan -- doubles as the required
#    live-freshness proof AND the session's first real evidence. Rows
#    are tagged to this already-open session automatically.
# ---------------------------------------------------------------------------
print("\n=== 6. ONE controlled diagnostic scan (live freshness proof + first evidence) ===")
r = call(staff, "POST", "/api/v1/admin/market-intelligence/diagnostic-scan", csrf=csrf, json={})
if not isinstance(r, requests.Response) or r.status_code != 200:
    body = getattr(r, "text", str(r))[:1000]
    call(staff, "POST", f"/api/v1/admin/ai-evolution/validation-sessions/{vsession_id}/close",
         params={"aborted": "true"}, csrf=csrf)
    no_go(f"POST /diagnostic-scan failed (status={getattr(r, 'status_code', None)}).", {"body": body})

scan = r.json()
log("diagnostic_scan_result", scan)

blockers = []
if scan.get("current_provider_kind") != "sahmk":
    blockers.append(f"current_provider_kind={scan.get('current_provider_kind')!r} (not sahmk)")
if scan.get("sahmk_error"):
    blockers.append(f"sahmk_error={scan.get('sahmk_error')!r}")
if scan.get("sahmk_connectivity_status") != "SUCCESS":
    blockers.append(f"sahmk_connectivity_status={scan.get('sahmk_connectivity_status')!r} (not SUCCESS)")
if scan.get("data_is_fresh") is not True:
    blockers.append(f"data_is_fresh={scan.get('data_is_fresh')!r}")
if not scan.get("rows_written"):
    blockers.append(f"rows_written={scan.get('rows_written')!r} (no real rows persisted)")

if blockers:
    call(staff, "POST", f"/api/v1/admin/ai-evolution/validation-sessions/{vsession_id}/close",
         params={"aborted": "true"}, csrf=csrf)
    no_go("Diagnostic scan did not prove fresh, real, non-fallback SAHMK data: " + "; ".join(blockers), scan)

# ---------------------------------------------------------------------------
# GO. Report it, then close the session normally and pull final evidence.
# ---------------------------------------------------------------------------
print("\n" + "=" * 70)
print("M10 LIVE GO: YES")
print("=" * 70)

print("\n=== 7. Metrics + ledger (real evidence collected this session) ===")
r = call(staff, "GET", f"/api/v1/admin/ai-evolution/validation-sessions/{vsession_id}/metrics")
metrics = r.json() if isinstance(r, requests.Response) and r.status_code == 200 else {"error": getattr(r, "status_code", None)}
log("validation_session_metrics", metrics)

r = call(staff, "GET", f"/api/v1/admin/ai-evolution/validation-sessions/{vsession_id}/ledger")
ledger = r.json() if isinstance(r, requests.Response) and r.status_code == 200 else {"error": getattr(r, "status_code", None)}
log("validation_session_ledger", ledger)

print("\n=== 8. Close ValidationSession (normal close) ===")
r = call(staff, "POST", f"/api/v1/admin/ai-evolution/validation-sessions/{vsession_id}/close", csrf=csrf)
closed = r.json() if isinstance(r, requests.Response) and r.status_code == 200 else {"error": getattr(r, "status_code", None)}
log("closed_validation_session", closed)

print_final_bundle()
print("\nM10 LIVE VALIDATION SESSION 1 complete. See final_evidence_bundle above for the complete evidence.")
sys.exit(0)
