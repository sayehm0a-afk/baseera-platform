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
out["all_live_opportunities_summary"] = [
    {
        "id": o.get("id"),
        "symbol": o.get("symbol"),
        "company_name_ar": o.get("company_name_ar"),
        "classification": o.get("classification"),
        "emitted_at": o.get("emitted_at"),
    }
    for o in sorted(all_live_opportunities, key=lambda o: o.get("emitted_at", ""))
]

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

# Every other currently-live opportunity (not emitted today) -- pulled in
# full detail too, so a symbol requested for audit whose most recent live
# call predates AUDIT_DATE (e.g. it wasn't re-evaluated today) can still
# be reported honestly with its real fields, rather than omitted.
non_today = [o for o in all_live_opportunities if o not in todays]
non_today_details = []
for opp in sorted(non_today, key=lambda o: o.get("emitted_at", "")):
    r = session.get(
        f"{BACKEND_URL}/api/v1/admin/market-intelligence/radar-v2/opportunities/{opp['id']}",
        timeout=30,
    )
    if r.status_code != 200:
        non_today_details.append({"id": opp["id"], "symbol": opp.get("symbol"), "ERROR": f"status={r.status_code} body={r.text[:300]}"})
        continue
    non_today_details.append(r.json())
    symbols_seen.add(opp["symbol"])

out["opportunities_detail_other_live_not_from_today"] = non_today_details

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

out["price_history_from_audit_date"] = price_histories

# Separately: for every non-today live opportunity, also pull its price
# history starting from ITS OWN signal date (not AUDIT_DATE) -- e.g.
# 2330's signal was 2026-08-18, so its outcome evaluation needs bars from
# 2026-08-18 forward, not from today.
price_histories_from_own_signal_date = {}
for opp in non_today:
    symbol = opp.get("symbol")
    signal_date = str(opp.get("emitted_at", ""))[:10]
    if not symbol or not signal_date:
        continue
    r = session.get(
        f"{BACKEND_URL}/api/v1/stocks/{symbol}/history",
        params={"start": f"{signal_date}T00:00:00Z"},
        timeout=30,
    )
    if r.status_code != 200:
        price_histories_from_own_signal_date[symbol] = {"ERROR": f"status={r.status_code} body={r.text[:300]}"}
        continue
    price_histories_from_own_signal_date[symbol] = r.json()

out["price_history_from_own_signal_date_for_non_today_opportunities"] = price_histories_from_own_signal_date

print("===AUDIT_JSON_START===")
print(json.dumps(out, indent=2, default=str))
print("===AUDIT_JSON_END===")

# Concise, human-reviewable report -- printed LAST (after the full JSON
# dump above) so a tail-of-log fetch can retrieve it even when the full
# JSON is too large for that. One row per live opportunity: entry/target/
# stop, and its real outcome-tracking status so far -- never a fabricated
# success rate, just what is actually persisted.
print("\n===CONCISE_REPORT_START===")
all_details = details + non_today_details
print(f"Total live opportunities reported below: {len(all_details)} ({len(details)} from {AUDIT_DATE}, {len(non_today_details)} from earlier still-live)")
print("")
unresolved_no_outcome_yet = []
for d in sorted(all_details, key=lambda x: x.get("emitted_at", "")):
    if "ERROR" in d:
        print(f"[{d.get('id')}] {d.get('symbol')}: ERROR fetching detail -- {d['ERROR']}")
        continue
    outcome_status = d.get("outcome_status")
    outcome_return = d.get("outcome_return_pct")
    outcome_evaluated_at = d.get("outcome_evaluated_at")
    if outcome_status is None:
        unresolved_no_outcome_yet.append(d.get("symbol"))
    print(
        f"[{d.get('id')}] {d.get('symbol')} ({d.get('company_name_ar', '')}) "
        f"classification={d.get('classification')} emitted_at={d.get('emitted_at')}\n"
        f"    entry_zone=[{d.get('entry_zone_low')}, {d.get('entry_zone_high')}] "
        f"stop_loss={d.get('stop_loss')} "
        f"targets=[{d.get('target_1')}, {d.get('target_2')}, {d.get('target_3')}]\n"
        f"    entry_status={d.get('entry_status')} "
        f"outcome_status={outcome_status!r} "
        f"outcome_return_pct={outcome_return} "
        f"outcome_evaluated_at={outcome_evaluated_at}"
    )

print(f"\nSymbols with NO outcome_status yet (not fabricated as a result -- genuinely un-evaluated/pending): {unresolved_no_outcome_yet}")
print("===CONCISE_REPORT_END===")
