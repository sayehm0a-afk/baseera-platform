"""BASIRAH -- PHASE 3 REAL HISTORICAL VALIDATION DATA ACCESS.

One-off, temporary, read-only evidence-gathering script (same
convention as every other script in this directory). Pulls the real,
already-ingested OHLCV history out of production via the new
GET /api/v1/admin/historical-data-export/ohlcv route (staff/admin
only, no SAHMK calls, no writes) so the DecisionEngineV2 historical
validation harness can run against real Saudi-market data instead of
synthetic data.

Zero SAHMK quota consumed: this script only calls already-deployed
REST endpoints that themselves only read already-ingested PriceBar
rows via the ORM -- confirmed by reading historical_data_export.py's
own route body, which contains no SAHMK client call anywhere.

Output: two JSON files written to the runner's working directory and
uploaded as a workflow artifact --
  historical_ohlcv_export.json  (every real OHLCV row pulled, keyed by
                                  symbol -- the actual dataset the
                                  local harness will replay against)
  phase_a_report.json           (the Phase A data-quality report
                                  fields, computed here from the real
                                  rows, never estimated)
"""

import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
EXPECTED_COMMIT = os.environ.get("EXPECTED_COMMIT", "")

EXPORT_PATH = "/api/v1/admin/historical-data-export/ohlcv"
BATCH_SIZE = 50
START_DATE = date(2015, 1, 1)
END_DATE = datetime.now(timezone.utc).date()
TOP_LEVEL_WINDOW_DAYS = 3650


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


def date_windows(start, end, max_days):
    windows = []
    cur = start
    while cur <= end:
        nxt = min(end, cur + timedelta(days=max_days - 1))
        windows.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return windows


section("1. Staff login")
staff = requests.Session()
r = staff.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
csrf = staff.cookies.get("csrf_token")
if csrf:
    staff.headers.update({"X-CSRF-Token": csrf})
print("Staff login OK.")

section("2. Deployment commit sanity check (proves the isolated export-only branch is what's actually serving)")
r = staff.get(f"{BACKEND_URL}/api/v1/admin/system/summary", timeout=30)
deployed_commit = None
if r.status_code == 200:
    deployed_commit = r.json().get("deployment_commit")
    print(f"deployment_commit: {deployed_commit}")
    if EXPECTED_COMMIT and deployed_commit and not EXPECTED_COMMIT.startswith(deployed_commit) and not deployed_commit.startswith(EXPECTED_COMMIT[:7]):
        print(f"::warning::deployed commit {deployed_commit} does not match expected {EXPECTED_COMMIT}")
else:
    print(f"FAILED to read deployment_commit: status={r.status_code} body={r.text[:300]}")

section("3. Access-control proof against the REAL production endpoint (unauthenticated)")
anon = requests.Session()
r = anon.get(f"{BACKEND_URL}{EXPORT_PATH}", params={"symbols": "1111", "start_date": "2026-01-01", "end_date": "2026-01-02"}, timeout=30)
print(f"Unauthenticated call -> HTTP {r.status_code} (expect 401)")
if r.status_code != 401:
    print("::error::Unauthenticated caller was NOT rejected by the production endpoint -- STOP, do not proceed with the data pull.")
    sys.exit(1)

section("4. Market coverage snapshot (aggregate, already-deployed endpoint)")
r = staff.get(f"{BACKEND_URL}/api/v1/admin/market-intelligence/coverage", timeout=30)
coverage = {}
if r.status_code == 200:
    coverage = r.json()
    for k in ("total_stocks", "active_stocks", "stocks_with_price_history", "stocks_without_price_history", "main_market_stocks", "nomu_market_stocks"):
        print(f"{k}: {coverage.get(k)}")
else:
    print(f"FAILED: status={r.status_code} body={r.text[:300]}")

section("5. Full active-symbol universe (paged /api/v1/stocks/directory)")
symbols = []
offset = 0
limit = 200
while True:
    r = staff.get(f"{BACKEND_URL}/api/v1/stocks/directory", params={"limit": limit, "offset": offset}, timeout=30)
    if r.status_code != 200:
        print(f"FAILED at offset={offset}: status={r.status_code} body={r.text[:300]}")
        break
    body = r.json()
    page_symbols = [item["symbol"] for item in body.get("results", [])]
    symbols.extend(page_symbols)
    total = body.get("total", 0)
    offset += limit
    if offset >= total or not page_symbols:
        break
print(f"Discovered {len(symbols)} active symbols (directory total={coverage.get('active_stocks')}).")

section("6. Real OHLCV pull (batched, adaptive window-splitting, zero SAHMK calls)")
all_rows = []
symbols_not_found_overall = set()
truncation_warnings = 0
export_calls = 0


def fetch_range(batch, start, end, depth=0):
    global export_calls, truncation_warnings
    export_calls += 1
    r = staff.get(
        f"{BACKEND_URL}{EXPORT_PATH}",
        params={"symbols": ",".join(batch), "start_date": start.isoformat(), "end_date": end.isoformat()},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"::error::export call failed batch={batch[:3]}... range={start}..{end} status={r.status_code} body={r.text[:300]}")
        return
    body = r.json()
    all_rows.extend(body["rows"])
    symbols_not_found_overall.update(body.get("symbols_not_found", []))
    if body.get("truncated"):
        if (end - start).days <= 1 or depth > 20:
            truncation_warnings += 1
            print(f"::warning::still truncated at minimal window batch={batch[:3]}... range={start}..{end}")
            return
        mid = start + (end - start) // 2
        fetch_range(batch, start, mid, depth + 1)
        fetch_range(batch, mid + timedelta(days=1), end, depth + 1)


batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
top_windows = date_windows(START_DATE, END_DATE, TOP_LEVEL_WINDOW_DAYS)
print(f"{len(batches)} symbol batches x {len(top_windows)} top-level date windows.")
for batch in batches:
    for (ws, we) in top_windows:
        fetch_range(batch, ws, we)

print(f"\nTotal export HTTP calls: {export_calls}")
print(f"Total rows pulled: {len(all_rows)}")
print(f"Symbols never found in any batch: {sorted(symbols_not_found_overall)}")
if truncation_warnings:
    print(f"::warning::{truncation_warnings} window(s) remained truncated at minimal split -- see warnings above.")

section("7. Phase A data-quality computation (from the real rows just pulled, nothing estimated)")
by_symbol = {}
seen_keys = set()
duplicates = 0
invalid_ohlc = 0
zero_or_negative = 0
source_counts = {}
synthetic_count = 0
min_ts = None
max_ts = None
for row in all_rows:
    key = (row["symbol"], row["timestamp"])
    if key in seen_keys:
        duplicates += 1
    else:
        seen_keys.add(key)
    o, h, low, c = row["open"], row["high"], row["low"], row["close"]
    if h < low or h < o or h < c or low > o or low > c:
        invalid_ohlc += 1
    if o <= 0 or h <= 0 or low <= 0 or c <= 0:
        zero_or_negative += 1
    src = row.get("data_source") or "unknown"
    source_counts[src] = source_counts.get(src, 0) + 1
    if row.get("is_synthetic"):
        synthetic_count += 1
    ts = row["timestamp"]
    if min_ts is None or ts < min_ts:
        min_ts = ts
    if max_ts is None or ts > max_ts:
        max_ts = ts
    by_symbol.setdefault(row["symbol"], []).append(row)

distinct_symbols_with_data = len(by_symbol)
report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "deployed_commit": deployed_commit,
    "sahmk_api_calls_used_for_export": 0,
    "real_historical_data_access": len(all_rows) > 0,
    "earliest_date": min_ts,
    "latest_date": max_ts,
    "number_of_symbols_requested": len(symbols),
    "number_of_symbols_with_at_least_one_bar": distinct_symbols_with_data,
    "total_historical_bars": len(all_rows),
    "data_source_breakdown": source_counts,
    "synthetic_row_count": synthetic_count,
    "duplicate_symbol_timestamp_rows": duplicates,
    "invalid_ohlc_rows": invalid_ohlc,
    "zero_or_negative_price_rows": zero_or_negative,
    "corporate_action_adjustment_available": False,
}
print(json.dumps(report, indent=2, default=str))

section("8. Writing artifact files")
with open("historical_ohlcv_export.json", "w") as f:
    json.dump({"rows": all_rows}, f)
with open("phase_a_report.json", "w") as f:
    json.dump(report, f, indent=2, default=str)
print("Wrote historical_ohlcv_export.json and phase_a_report.json")
