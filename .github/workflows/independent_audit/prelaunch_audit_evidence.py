"""BASIRAH PRE-LAUNCH QUALITY AUDIT -- Parts 1-3 evidence gathering
(one-off, temporary, read-only, zero SAHMK cost). Pulls every real
signal needed to reconstruct the 2026-08-20 session and the current
Radar state, without ever calling SAHMK or mutating anything:

  - /health/market-data, /health/ready (current provider/infra state)
  - /api/v1/admin/system/summary (zero-network-call snapshot)
  - /api/v1/radar/summary (consumer-facing Radar payload -- top 5 only)
  - /api/v1/admin/market-intelligence/radar-v2/opportunities (up to 200
    LIVE opportunities, full RadarOpportunitySummaryOut per symbol --
    every currently-displayed opportunity, not just the top 5)
  - /api/v1/admin/market-intelligence/radar-v2/opportunities/{id} for
    each live opportunity -- adds outcome_status/outcome_return_pct/
    outcome_evaluated_at, decision_timestamp, why_now_ar, reasoning
  - /api/v1/admin/market-intelligence/radar-v2/daily-validation-report
    for report_date=2026-08-20 -- the exact aggregate BASIRAH LIVE
    VALIDATION TRACKING numbers for that session (verified win rate,
    target-1 hit rate, stop-before-target rate, entries triggered/not,
    sample size)
  - a Railway backend log pull, grepped for the same failure
    signatures used in the live-data-connection diagnostic, PLUS a
    best-effort scan for any lines timestamped on 2026-08-20 (disclosed
    honestly if the CLI's log buffer no longer reaches back that far --
    Railway's `railway logs` only returns a recent rolling tail, not an
    arbitrary historical range, so this is a best-effort attempt, not a
    guarantee)

Never triggers a scan, never calls SAHMK. Throwaway diagnostic tooling,
same convention as the other scripts in this directory."""

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
        return session.get(f"{BACKEND_URL}{path}", timeout=30, **kw)
    except requests.RequestException as exc:
        print(f"GET {path} raised: {exc}")
        return None


section("1. Public health probes")
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

section("2. Staff login")
staff = requests.Session()
r = staff.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
print("Staff login OK.")

section("3. Zero-cost admin system summary")
r = get(staff, "/api/v1/admin/system/summary")
summary = {}
if r is not None and r.status_code == 200:
    summary = r.json()
    print(json.dumps(summary, indent=2, default=str))
else:
    print(f"FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("4. Consumer Radar page payload (GET /api/v1/radar/summary)")
r = get(staff, "/api/v1/radar/summary")
radar_summary = {}
if r is not None and r.status_code == 200:
    radar_summary = r.json()
    print(json.dumps(radar_summary, indent=2, default=str))
else:
    print(f"FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("5. FULL live opportunity list (admin radar-v2/opportunities, limit=200)")
r = get(staff, "/api/v1/admin/market-intelligence/radar-v2/opportunities", params={"limit": 200})
live_opportunities = []
if r is not None and r.status_code == 200:
    live_opportunities = r.json()
    print(f"Total live opportunities: {len(live_opportunities)}")
    print(json.dumps(live_opportunities, indent=2, default=str))
else:
    print(f"FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("6. Per-opportunity detail (outcome_status/decision_timestamp/why_now_ar) for every live opportunity")
details = []
for opp in live_opportunities:
    opp_id = opp.get("id")
    r = get(staff, f"/api/v1/admin/market-intelligence/radar-v2/opportunities/{opp_id}")
    if r is not None and r.status_code == 200:
        d = r.json()
        details.append(d)
        print(f"\n--- opportunity {opp_id} ({opp.get('symbol')}) ---")
        print(json.dumps({
            "symbol": d.get("symbol"),
            "company_name_ar": d.get("company_name_ar"),
            "company_name_en": d.get("company_name_en"),
            "classification": d.get("classification"),
            "classification_label_ar": d.get("classification_label_ar"),
            "confidence_score": d.get("confidence_score"),
            "basirah_score": d.get("basirah_score"),
            "price_at_signal": d.get("price_at_signal"),
            "entry_zone_low": d.get("entry_zone_low"),
            "entry_zone_high": d.get("entry_zone_high"),
            "stop_loss": d.get("stop_loss"),
            "target_1": d.get("target_1"),
            "target_2": d.get("target_2"),
            "target_3": d.get("target_3"),
            "decision_timestamp": d.get("decision_timestamp"),
            "emitted_at": d.get("emitted_at"),
            "market_status": d.get("market_status"),
            "outcome_status": d.get("outcome_status"),
            "outcome_return_pct": d.get("outcome_return_pct"),
            "outcome_evaluated_at": d.get("outcome_evaluated_at"),
            "why_now_ar": d.get("why_now_ar"),
            "data_freshness_status": d.get("data_freshness_status"),
        }, indent=2, default=str))
    else:
        print(f"opportunity {opp_id}: FAILED status={getattr(r, 'status_code', None)}")

section("7. Daily validation report for 2026-08-20 (BASIRAH LIVE VALIDATION TRACKING)")
r = get(staff, "/api/v1/admin/market-intelligence/radar-v2/daily-validation-report", params={"report_date": "2026-08-20"})
daily_report_aug20 = {}
if r is not None and r.status_code == 200:
    daily_report_aug20 = r.json()
    print(json.dumps(daily_report_aug20, indent=2, default=str))
else:
    print(f"FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("8. Radar V2 extended performance (all-time win rate / calibration, for cross-reference)")
r = get(staff, "/api/v1/admin/market-intelligence/radar-v2/performance/extended")
if r is not None and r.status_code == 200:
    print(json.dumps(r.json(), indent=2, default=str))
else:
    print(f"FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("9. Recent backend logs -- full tail, then filtered for 2026-08-20 timestamps and failure signatures")
try:
    proc = subprocess.run(
        ["timeout", "25", "railway", "logs", "--service", "backend"],
        capture_output=True, text=True, timeout=30,
    )
    raw_logs = (proc.stdout or "") + (proc.stderr or "")
except Exception as exc:  # noqa: BLE001
    raw_logs = ""
    print(f"Could not fetch railway logs: {exc}")

all_lines = raw_logs.splitlines()
print(f"Total log lines fetched: {len(all_lines)}")
if all_lines:
    print(f"Earliest line: {all_lines[0][:120]}")
    print(f"Latest line:   {all_lines[-1][:120]}")

aug20_lines = [line for line in all_lines if line.startswith("2026-08-20")]
print(f"\nLines timestamped 2026-08-20: {len(aug20_lines)}")
if not aug20_lines:
    print("NONE FOUND -- Railway's log CLI only returns a recent rolling tail; "
          "2026-08-20 has scrolled out of the retained buffer as of this run. "
          "This script cannot reconstruct that day's log timeline from here; "
          "say so honestly rather than fabricating a timeline.")
else:
    for line in aug20_lines[:200]:
        print(line)

error_pattern = re.compile(
    r"(timeout|timed out|DNS|dns resolution|TLS|SSL|certificate|401|403|429|"
    r"5\d{2}\b|connection refused|ConnectionError|ConnectTimeout|"
    r"StrictRealDataUnavailableError|circuit.?breaker|Traceback|ERROR)",
    re.IGNORECASE,
)
matched = [line for line in all_lines if error_pattern.search(line)]
print(f"\nLines matching hard-failure signatures (any date, current buffer): {len(matched)}")
for line in matched[-100:]:
    print(line)

print("\nDone. See sections above for the complete real evidence.")
