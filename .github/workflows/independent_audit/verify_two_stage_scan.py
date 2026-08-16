"""One-off, real-production evidence script for the SAHMK quota
optimization mandate (2026-08-16, PR #47): proves, with real measured
numbers (not theoretical arithmetic), that:

  1. Stage 1 (GET .../stage1-scan) evaluates the full eligible universe
     using ONLY local data -- zero real SAHMK provider calls, verified
     by diffing /admin/system/summary's sahmk_quota_status.requests_used_
     today immediately before and immediately after the Stage 1 call.
  2. Stage 1's real candidate count and the exact narrowed symbol list
     it hands to Stage 2 -- never assumed, always read from the live
     response.
  3. Stage 2 (POST .../stage2-validate-candidates) spends real SAHMK
     quota ONLY on that narrowed list -- measured the same way (a
     requests_used_today diff around the Stage 2 call), and the 1,000
     critical-reserve counter (critical_requests_used_today) is
     confirmed unchanged, since Stage 2 runs entirely under
     priority_scope(BACKGROUND).
  4. The new by_operation breakdown (both the rate limiter's and the
     shared cache's) is real and non-fabricated by printing it
     verbatim, before and after.

Every number in the printed evidence comes directly from a live
production HTTP response -- nothing here is computed from
configuration or assumed from code, matching this repo's existing
verify_deployment.py/continue_full_market_scan.py convention.
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

quota_before_all = summary_before.get("sahmk_quota_status") or {}
cache_before_all = summary_before.get("market_data_cache_status") or {}
evidence["quota_before_anything"] = quota_before_all
evidence["cache_before_anything"] = cache_before_all
print("sahmk_quota_status (before anything):")
print(json.dumps(quota_before_all, indent=2, default=str))

print("\n=== Real eligible universe size: /admin/market-intelligence/coverage ===")
coverage = _get("/api/v1/admin/market-intelligence/coverage")
evidence["coverage_stocks_with_price_history"] = coverage.get("stocks_with_price_history")
print(f"stocks_with_price_history (real eligible universe): {coverage.get('stocks_with_price_history')}")

print("\n=== Stage 1: GET /admin/market-intelligence/stage1-scan ===")
quota_before_stage1 = _get("/api/v1/admin/system/summary").get("sahmk_quota_status") or {}
stage1 = _get("/api/v1/admin/market-intelligence/stage1-scan")
quota_after_stage1 = _get("/api/v1/admin/system/summary").get("sahmk_quota_status") or {}

stage1_summary = {
    "universe_size": stage1.get("universe_size"),
    "evaluated_count": stage1.get("evaluated_count"),
    "skipped_count": stage1.get("skipped_count"),
    "candidate_count": stage1.get("candidate_count"),
    "candidate_symbols": [c["symbol"] for c in stage1.get("candidates", [])],
}
evidence["stage1"] = stage1_summary
evidence["stage1_full_response"] = stage1
print(json.dumps(stage1_summary, indent=2, default=str))

requests_before_stage1 = quota_before_stage1.get("requests_used_today")
requests_after_stage1 = quota_after_stage1.get("requests_used_today")
stage1_sahmk_delta = (
    (requests_after_stage1 - requests_before_stage1)
    if requests_before_stage1 is not None and requests_after_stage1 is not None
    else None
)
evidence["stage1_sahmk_requests_delta"] = stage1_sahmk_delta
print(f"\nSAHMK requests_used_today before Stage 1: {requests_before_stage1}")
print(f"SAHMK requests_used_today after Stage 1:  {requests_after_stage1}")
print(f"Stage 1 real SAHMK cost (delta):           {stage1_sahmk_delta}  <-- must be 0")

print("\n=== Stage 2: POST /admin/market-intelligence/stage2-validate-candidates ===")
candidate_symbols = stage1_summary["candidate_symbols"]
if not candidate_symbols:
    print("Stage 1 produced zero candidates right now -- Stage 2 has nothing to validate. "
          "This is a legitimate real-market outcome, not a failure; Stage 2 is skipped.")
    evidence["stage2"] = None
else:
    quota_before_stage2 = _get("/api/v1/admin/system/summary").get("sahmk_quota_status") or {}
    stage2 = _post("/api/v1/admin/market-intelligence/stage2-validate-candidates", {"symbols": candidate_symbols})
    quota_after_stage2 = _get("/api/v1/admin/system/summary").get("sahmk_quota_status") or {}

    evidence["stage2_full_response"] = stage2
    print(json.dumps(stage2, indent=2, default=str))

    requests_before_stage2 = quota_before_stage2.get("requests_used_today")
    requests_after_stage2 = quota_after_stage2.get("requests_used_today")
    critical_before_stage2 = quota_before_stage2.get("critical_requests_used_today")
    critical_after_stage2 = quota_after_stage2.get("critical_requests_used_today")
    stage2_sahmk_delta = (
        (requests_after_stage2 - requests_before_stage2)
        if requests_before_stage2 is not None and requests_after_stage2 is not None
        else None
    )
    critical_delta = (
        (critical_after_stage2 - critical_before_stage2)
        if critical_before_stage2 is not None and critical_after_stage2 is not None
        else None
    )
    evidence["stage2_sahmk_requests_delta"] = stage2_sahmk_delta
    evidence["stage2_critical_reserve_delta"] = critical_delta
    print(f"\nSAHMK requests_used_today before Stage 2: {requests_before_stage2}")
    print(f"SAHMK requests_used_today after Stage 2:  {requests_after_stage2}")
    print(f"Stage 2 real SAHMK cost (delta):           {stage2_sahmk_delta}")
    print(f"critical_requests_used_today before/after: {critical_before_stage2} / {critical_after_stage2} "
          f"(delta={critical_delta})  <-- must be 0")

print("\n=== Final: /admin/system/summary (per-operation telemetry) ===")
summary_after = _get("/api/v1/admin/system/summary")
quota_after_all = summary_after.get("sahmk_quota_status") or {}
cache_after_all = summary_after.get("market_data_cache_status") or {}
evidence["quota_after_everything"] = quota_after_all
evidence["cache_after_everything"] = cache_after_all
print("sahmk_quota_status.by_operation (after everything):")
print(json.dumps(quota_after_all.get("by_operation"), indent=2, default=str))
print("\nmarket_data_cache_status.by_operation (after everything):")
print(json.dumps(cache_after_all.get("by_operation"), indent=2, default=str))

print("\n=== EVIDENCE (full JSON) ===")
print(json.dumps(evidence, indent=2, default=str))
