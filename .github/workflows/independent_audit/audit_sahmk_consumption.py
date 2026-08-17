"""Read-only, zero-SAHMK-cost root-cause audit script (2026-08-17,
post-live-market-test): pulls real evidence for "where did today's
3503 SAHMK requests come from" -- GET /coverage (SQL-backed
active-symbol counts, universe buckets, and each ingestion job's
MOST RECENT real run row: symbols_requested/succeeded/failed,
started_at/finished_at, status, retry_count) plus a fresh
/admin/system/summary and the Redis-backed market-data cache status.

Makes ONLY GET requests. No POST, no scan trigger, no code/config
change. Every number printed is a direct query result from production,
never estimated.
"""

import json
import os
import sys

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]

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

print("\n=== GET /admin/system/summary (fresh quota + scheduler state, zero SAHMK cost) ===")
summary = _get("/api/v1/admin/system/summary")
print(json.dumps(summary.get("sahmk_quota_status"), indent=2, default=str))
print("\nscheduler flags:")
for key in (
    "ingestion_scheduler_running", "ingestion_deferred_job_count", "ingestion_next_retry_at",
    "market_intelligence_scheduler_running", "live_market_mode_enabled", "live_market_mode_running",
    "live_market_mode_market_currently_open", "last_scan_id", "last_scan_status",
    "last_scan_started_at", "last_scan_finished_at", "scan_lock_active",
):
    print(f"  {key}: {summary.get(key)}")
print("\nmarket_data_cache_status:")
print(json.dumps(summary.get("market_data_cache_status"), indent=2, default=str))

print("\n=== GET /admin/market-intelligence/coverage (real SQL evidence, zero SAHMK cost) ===")
coverage = _get("/api/v1/admin/market-intelligence/coverage")
print(json.dumps(coverage, indent=2, default=str))

print("\n--- Coverage headline ---")
print(f"total_stocks: {coverage.get('total_stocks')}")
print(f"active_stocks: {coverage.get('active_stocks')}")
print(f"inactive_stocks: {coverage.get('inactive_stocks')}")
print(f"stocks_with_price_history: {coverage.get('stocks_with_price_history')}")
print(f"stocks_without_price_history: {coverage.get('stocks_without_price_history')}")
print(f"ingestion_auto_discover_enabled: {coverage.get('ingestion_auto_discover_enabled')}")
print(f"ingestion_configured_seed_symbols: {coverage.get('ingestion_configured_seed_symbols')}")
print(f"main_market_stocks: {coverage.get('main_market_stocks')}")
print(f"nomu_market_stocks: {coverage.get('nomu_market_stocks')}")
print(f"stocks_with_fundamentals: {coverage.get('stocks_with_fundamentals')}")
print(f"stocks_without_fundamentals: {coverage.get('stocks_without_fundamentals')}")
print(f"stocks_with_dividends: {coverage.get('stocks_with_dividends')}")
print(f"stocks_without_dividends: {coverage.get('stocks_without_dividends')}")

print("\n--- latest_ingestion_runs (most recent row per job) ---")
for run in coverage.get("latest_ingestion_runs") or []:
    print(json.dumps(run, indent=2, default=str))

print("\n--- latest_scan_run (legacy MarketScanRun) ---")
print(json.dumps(coverage.get("latest_scan_run"), indent=2, default=str))

print("\n=== DONE (read-only, zero SAHMK requests made by this script) ===")
