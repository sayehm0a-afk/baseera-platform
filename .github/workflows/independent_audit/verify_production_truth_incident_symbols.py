"""BASIRAH -- URGENT PRODUCTION TRUTH & DECISION CONSISTENCY AUDIT.

Temporary, one-off, read-only, zero-additional-SAHMK-cost evidence
gathering for 5 incident symbols (2286, 6060, 2030, 4050, 1301) reported
inconsistent across surfaces on 2026-09-06. Never calls a fresh
GET /decision-v2/{symbol} (that recomputes live and inserts a brand new
DecisionV2Snapshot row, costing SAHMK quota and polluting the very
evidence this audit needs to stay clean) and never triggers any scan.
Only reads already-persisted state via existing consumer/admin routes,
exactly as a real subscriber/staff page load would.
"""

import json
import os
import sys

import requests

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]

INCIDENT_SYMBOLS = ["2286", "6060", "2030", "4050", "1301"]
WATCHLIST_CATEGORIES = [
    "MOMENTUM",
    "INVESTMENT",
    "SWING",
    "HIGH_RISK",
    "DIVIDEND",
    "RECOVERY",
    "BREAKOUT_CANDIDATES",
    "OVERSOLD_OPPORTUNITIES",
    "OVERBOUGHT_WARNINGS",
]

session = requests.Session()
evidence = {}


def _get(path, **params):
    r = session.get(f"{BACKEND_URL}{path}", params=params or None, timeout=60)
    return r.status_code, (r.json() if r.headers.get("content-type", "").startswith("application/json") else r.text)


print("--- staff login ---")
r = session.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
print("login OK")

print("\n--- deployment_commit ---")
code, body = _get("/api/v1/admin/system/summary")
evidence["system_summary"] = body
print(f"HTTP {code}: deployment_commit={body.get('deployment_commit') if isinstance(body, dict) else body!r}")

print("\n--- /api/v1/radar/summary (funnel + market_risk_is_live) ---")
code, body = _get("/api/v1/radar/summary")
evidence["radar_summary"] = body
print(f"HTTP {code}")
print(json.dumps(body, indent=2, default=str) if isinstance(body, dict) else body)

print("\n--- /api/v1/radar/opportunities?limit=200 (live, non-superseded only) ---")
code, body = _get("/api/v1/radar/opportunities", limit=200)
evidence["radar_opportunities"] = body
matched_radar = {}
if code == 200 and isinstance(body, list):
    print(f"HTTP {code}: {len(body)} live opportunities")
    for row in body:
        if row.get("symbol") in INCIDENT_SYMBOLS:
            matched_radar[row["symbol"]] = row
    for sym in INCIDENT_SYMBOLS:
        row = matched_radar.get(sym)
        if row is None:
            print(f"  {sym}: NOT PRESENT in current live Radar opportunities")
        else:
            print(
                f"  {sym}: id={row['id']} classification={row['classification']} "
                f"confidence={row['confidence_score']} price_at_signal={row.get('price_at_signal')} "
                f"entry=[{row.get('entry_zone_low')},{row.get('entry_zone_high')}] "
                f"stop={row.get('stop_loss')} target_1={row.get('target_1')}"
            )
else:
    print(f"HTTP {code}: {body}")

print("\n--- /api/v1/radar/opportunities/{id} detail for matched incident symbols ---")
evidence["radar_opportunity_detail"] = {}
for sym, row in matched_radar.items():
    code, detail = _get(f"/api/v1/radar/opportunities/{row['id']}")
    evidence["radar_opportunity_detail"][sym] = detail
    print(f"\n  {sym} (opportunity_id={row['id']}) HTTP {code}")
    if code == 200 and isinstance(detail, dict):
        print(
            "   ",
            json.dumps(
                {
                    k: detail.get(k)
                    for k in (
                        "classification",
                        "confidence_score",
                        "basirah_score",
                        "price_at_signal",
                        "entry_zone_low",
                        "entry_zone_high",
                        "stop_loss",
                        "target_1",
                        "target_2",
                        "target_3",
                        "stage1_risk_reward_ratio",
                        "entry_status",
                        "entry_status_label_ar",
                        "market_risk_state",
                        "why_not_buy_reasons",
                        "negative_reasons",
                        "warnings",
                    )
                },
                indent=2,
                default=str,
            ),
        )

print("\n--- /api/v1/admin/market-intelligence/decision-intelligence?within_hours=72 ---")
code, body = _get("/api/v1/admin/market-intelligence/decision-intelligence", within_hours=72)
evidence["decision_intelligence"] = body
print(f"HTTP {code}")
print(json.dumps(body, indent=2, default=str) if isinstance(body, dict) else body)

print("\n--- /api/v1/admin/market-intelligence/radar-v2/daily-validation-report ---")
code, body = _get("/api/v1/admin/market-intelligence/radar-v2/daily-validation-report")
evidence["daily_validation_report"] = body
print(f"HTTP {code}")
print(json.dumps(body, indent=2, default=str) if isinstance(body, dict) else body)

print("\n--- /api/v1/admin/market-intelligence/radar-v2/sahmk-consumption (confirms this audit spent 0 quota) ---")
code, body = _get("/api/v1/admin/market-intelligence/radar-v2/sahmk-consumption")
evidence["sahmk_consumption"] = body
print(f"HTTP {code}")
print(json.dumps(body, indent=2, default=str) if isinstance(body, dict) else body)

print("\n--- /api/v1/market/watchlists?category=... (legacy V1 Recommendation engine, per category) ---")
evidence["legacy_watchlists"] = {}
for cat in WATCHLIST_CATEGORIES:
    code, body = _get("/api/v1/market/watchlists", category=cat)
    evidence["legacy_watchlists"][cat] = body
    watchlists = body.get("watchlists", []) if isinstance(body, dict) else None
    if code != 200 or watchlists is None:
        print(f"  {cat}: HTTP {code} body={str(body)[:200]}")
        continue
    entries = watchlists[0]["entries"] if watchlists else []
    hits = [e for e in entries if e.get("symbol") in INCIDENT_SYMBOLS]
    print(f"  {cat}: HTTP {code}, {len(entries)} entries, {len(hits)} incident-symbol matches")
    for e in hits:
        print(f"    {e.get('symbol')}: recommendation={e.get('recommendation')} confidence={e.get('confidence')}")

print("\n--- /api/v1/watchlist (staff account's personal watchlist, best-effort) ---")
code, body = _get("/api/v1/watchlist")
evidence["personal_watchlist"] = body
print(f"HTTP {code}")
if code == 200 and isinstance(body, dict):
    items = body.get("items", [])
    print(f"{len(items)} items")
    for it in items:
        if it.get("symbol") in INCIDENT_SYMBOLS:
            print(f"  MATCH {json.dumps(it, indent=2, default=str)}")
else:
    print(body)

with open("/tmp/production_truth_evidence.json", "w") as f:
    json.dump(evidence, f, indent=2, default=str)

print("\n--- DONE: full evidence written to /tmp/production_truth_evidence.json ---")
