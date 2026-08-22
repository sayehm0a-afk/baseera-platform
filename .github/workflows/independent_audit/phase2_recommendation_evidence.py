"""BASIRAH PHASE 2 -- RECOMMENDATION INTELLIGENCE + LIVE VALIDATION
evidence gathering (one-off, temporary, read-only, zero SAHMK cost).

Pulls the real, already-persisted DecisionV2Outcome-backed performance
data needed for Phase 2 Parts 2-3 (live recommendation validation +
performance report) without calling SAHMK or mutating anything:

  - /api/v1/admin/system/summary (deployment commit sanity check)
  - /api/v1/admin/market-intelligence/radar-v2/performance/extended
    (ALL-TIME: win rate by classification/confidence-band/market-regime,
    performance by sector/holding-horizon/market segment, MFE/MAE,
    calibration -- the full RadarOpportunity/DecisionV2Outcome history)
  - /api/v1/admin/market-intelligence/radar-v2/daily-validation-report
    for today (UTC) and each of the preceding 6 days, printed
    individually AND manually summed here into a WEEKLY rollup --
    there is no dedicated weekly endpoint in the backend, so this
    7-day sum is a diagnostic-script aggregation only, not a claim
    that the backend itself computes "weekly" anywhere.

Never triggers a scan, never calls SAHMK. Throwaway diagnostic
tooling, same convention as prelaunch_audit_evidence.py and the other
scripts in this directory."""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

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


section("1. Staff login")
staff = requests.Session()
r = staff.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code} body={r.text[:500]}")
    sys.exit(1)
print("Staff login OK.")

section("2. Deployment commit sanity check")
r = get(staff, "/api/v1/admin/system/summary")
if r is not None and r.status_code == 200:
    summary = r.json()
    print(f"deployment_commit: {summary.get('deployment_commit')}")
    print(f"last_scan_id: {summary.get('last_scan_id')}")
else:
    print(f"FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("3. ALL-TIME extended performance (radar-v2/performance/extended)")
r = get(staff, "/api/v1/admin/market-intelligence/radar-v2/performance/extended")
extended = {}
if r is not None and r.status_code == 200:
    extended = r.json()
    print(json.dumps(extended, indent=2, default=str))
else:
    print(f"FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:500]}")

section("4. DAILY validation report -- today (UTC) and preceding 6 days")
today = datetime.now(timezone.utc)
daily_reports = []
for i in range(7):
    day = today - timedelta(days=i)
    date_str = day.date().isoformat()
    r = get(
        staff,
        "/api/v1/admin/market-intelligence/radar-v2/daily-validation-report",
        params={"report_date": date_str},
    )
    if r is not None and r.status_code == 200:
        rep = r.json()
        daily_reports.append(rep)
        print(f"\n--- {date_str} ---")
        print(json.dumps(rep, indent=2, default=str))
    else:
        print(f"\n--- {date_str} --- FAILED: status={getattr(r, 'status_code', None)} body={getattr(r, 'text', '')[:300]}")

section("5. WEEKLY rollup (manual sum of the 7 daily reports above -- diagnostic-script arithmetic, not a backend feature)")
if daily_reports:
    total_opportunities = sum(d["total_opportunities"] for d in daily_reports)
    actionable_buy_signals = sum(d["actionable_buy_signals"] for d in daily_reports)
    entries_triggered = sum(d["entries_triggered"] for d in daily_reports)
    target_1_wins = sum(d["target_1_wins"] for d in daily_reports)
    target_2_wins = sum(d["target_2_wins"] for d in daily_reports)
    target_3_wins = sum(d["target_3_wins"] for d in daily_reports)
    stop_before_target_losses = sum(d["stop_before_target_losses"] for d in daily_reports)
    entries_not_triggered = sum(d["entries_not_triggered"] for d in daily_reports)
    invalidated = sum(d["invalidated"] for d in daily_reports)
    wins = target_1_wins + target_2_wins + target_3_wins
    verified_sample_size = wins + stop_before_target_losses
    weekly = {
        "date_range": f"{(today - timedelta(days=6)).date().isoformat()} .. {today.date().isoformat()}",
        "total_opportunities": total_opportunities,
        "actionable_buy_signals": actionable_buy_signals,
        "entries_triggered": entries_triggered,
        "entry_trigger_rate": round(entries_triggered / actionable_buy_signals, 4) if actionable_buy_signals else None,
        "target_1_wins": target_1_wins,
        "target_2_wins": target_2_wins,
        "target_3_wins": target_3_wins,
        "stop_before_target_losses": stop_before_target_losses,
        "entries_not_triggered": entries_not_triggered,
        "invalidated": invalidated,
        "verified_sample_size": verified_sample_size,
        "verified_win_rate": round(wins / verified_sample_size, 4) if verified_sample_size else None,
    }
    print(json.dumps(weekly, indent=2, default=str))
else:
    print("No daily reports fetched successfully -- cannot compute weekly rollup.")

section("6. ALL-TIME summary line (from section 3, for quick reference)")
if extended:
    print(f"total_signals_by_classification: {extended.get('total_signals_by_classification')}")
    print(f"calibration_pair_count: {extended.get('calibration_pair_count')}")
    print(f"expected_calibration_error: {extended.get('expected_calibration_error')}")
    print(f"average_return_pct: {extended.get('average_return_pct')}")
    print(f"average_favorable_excursion_pct (MFE): {extended.get('average_favorable_excursion_pct')}")
    print(f"average_adverse_excursion_pct (MAE): {extended.get('average_adverse_excursion_pct')}")

print("\nDone. See sections above for the complete real evidence.")
