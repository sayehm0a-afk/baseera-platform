"""One-off (temporary, read-only, zero SAHMK cost): pulls every real
BASIRAH Radar V2 opportunity emitted "today" (the UTC calendar date
passed in via AUDIT_DATE) directly from the live production backend, for
the "TODAY'S RECOMMENDATION VALIDATION AUDIT" mandate.

Never triggers a scan, never calls a live-quote/decision-v2 endpoint
(that would spend SAHMK quota and would return a *new* decision, not the
historical one at signal time) -- only reads what is already persisted:

  1. GET /api/v1/admin/system/summary               -- deployment/market context
  2. GET /api/v1/admin/market-intelligence/radar-v2/opportunities (limit=200)
     -- the live (non-superseded) opportunity list; filtered client-side
     to AUDIT_DATE by emitted_at. NOTE: this is the one disclosed
     completeness gap -- a symbol emitted today and then superseded by a
     newer same-day re-emission would only appear once, as its newest
     row; there is no admin endpoint that lists superseded historical
     rows. This script does not fabricate completeness beyond that.
  3. For each matching opportunity: GET .../radar-v2/opportunities/{id}
     for the full detail record (entry/targets/stop/why-now/negative
     reasons/warnings/invalidation/market+sector state/etc).
  4. For each unique symbol: GET /api/v1/stocks/{symbol}/history?start=...
     for the platform's own real, already-ingested daily-close bars from
     the signal date forward -- never a fabricated or interpolated price.
"""

import json
import os
import sys
from datetime import datetime, timezone

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
AUDIT_DATE = os.environ["AUDIT_DATE"]  # "YYYY-MM-DD", UTC calendar date

session = requests.Session()
r = session.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)

out = {"audit_date_utc": AUDIT_DATE, "generated_at": datetime.now(timezone.utc).isoformat()}

r = session.get(f"{BACKEND_URL}/api/v1/admin/system/summary", timeout=30)
if r.status_code != 200:
    print(f"GET /admin/system/summary failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
system_summary = r.json()
out["system_summary"] = {
    "deployment_commit": system_summary.get("deployment_commit"),
    "market_intelligence_scheduler_running": system_summary.get("market_intelligence_scheduler_running"),
    "live_market_mode_enabled": system_summary.get("live_market_mode_enabled"),
    "live_market_mode_running": system_summary.get("live_market_mode_running"),
    "live_market_mode_market_currently_open": system_summary.get("live_market_mode_market_currently_open"),
}

r = session.get(
    f"{BACKEND_URL}/api/v1/admin/market-intelligence/radar-v2/opportunities",
    params={"limit": 200},
    timeout=30,
)
if r.status_code != 200:
    print(f"GET .../radar-v2/opportunities failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
all_live_opportunities = r.json()
out["total_live_opportunities_all_time"] = len(all_live_opportunities)

todays = [o for o in all_live_opportunities if str(o.get("emitted_at", "")).startswith(AUDIT_DATE)]
todays.sort(key=lambda o: o.get("emitted_at", ""))
out["todays_opportunity_count"] = len(todays)
out["todays_opportunity_ids_chronological"] = [o["id"] for o in todays]

details = []
symbols_seen = set()
for opp in todays:
    r = session.get(
        f"{BACKEND_URL}/api/v1/admin/market-intelligence/radar-v2/opportunities/{opp['id']}",
        timeout=30,
    )
    if r.status_code != 200:
        details.append({"id": opp["id"], "symbol": opp.get("symbol"), "ERROR": f"status={r.status_code} body={r.text[:300]}"})
        continue
    details.append(r.json())
    symbols_seen.add(opp["symbol"])

out["opportunities_detail_chronological"] = details

price_histories = {}
for symbol in sorted(symbols_seen):
    r = session.get(
        f"{BACKEND_URL}/api/v1/stocks/{symbol}/history",
        params={"start": f"{AUDIT_DATE}T00:00:00Z"},
        timeout=30,
    )
    if r.status_code != 200:
        price_histories[symbol] = {"ERROR": f"status={r.status_code} body={r.text[:300]}"}
        continue
    price_histories[symbol] = r.json()

out["price_history_from_signal_date"] = price_histories

print("===AUDIT_JSON_START===")
print(json.dumps(out, indent=2, default=str))
print("===AUDIT_JSON_END===")
