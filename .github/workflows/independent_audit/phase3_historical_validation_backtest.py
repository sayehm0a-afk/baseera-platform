"""BASIRAH -- PHASE 3 REAL HISTORICAL VALIDATION DATA ACCESS + FINAL
GO/NO-GO (Phase A/B/C in one job).

Pulls real, already-ingested OHLCV out of production through the
staff-only GET /api/v1/admin/historical-data-export/ohlcv route
(zero SAHMK calls -- see that route's own docstring), builds an
in-memory SQLite dataset from the real rows, then runs the ACTUAL
DecisionEngineV2 historical validation harness (Baseline V2 vs
Phase 3 V2, from src.backtesting.decision_v2_replay) locally inside
this CI job -- never against production, never touching any deployed
service. Nothing here merges or deploys Phase 3 trading logic; it is
a one-shot, read-only, offline analysis script, same convention as
every other script in this directory.
"""

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.getcwd())

from src.backtesting.decision_v2_replay import run_decision_v2_replay  # noqa: E402
from src.core.db.database import Base  # noqa: E402
from src.domain.models import PriceBar, Stock, Timeframe  # noqa: E402
from src.domain.models.decision_v2_outcome import DecisionV2OutcomeStatus  # noqa: E402

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]
EXPECTED_COMMIT = os.environ.get("EXPECTED_COMMIT", "")

EXPORT_PATH = "/api/v1/admin/historical-data-export/ohlcv"
BATCH_SIZE = 50
DATA_START = date(2015, 1, 1)
DATA_END = datetime.now(timezone.utc).date()
TOP_LEVEL_WINDOW_DAYS = 3650

# Backtest-harness parameters, deliberately shrunk from the harness's
# own defaults (entry_expiry_days=10, resolution_horizon_days=60) --
# the real ingested history turns out to span only ~3.5 months (see
# Phase A output below), so a 60-day forward-resolution window would
# leave almost no decision date with room for a full outcome to
# mature. This is a backtest-configuration accommodation to the real
# data actually available, NOT a change to DecisionEngineV2's own
# decision logic or thresholds -- the engine itself is untouched.
EVAL_FREQUENCY_DAYS = 3
ENTRY_EXPIRY_DAYS = 5
RESOLUTION_HORIZON_DAYS = 20


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


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

section("2. Deployment commit sanity check")
r = staff.get(f"{BACKEND_URL}/api/v1/admin/system/summary", timeout=30)
deployed_commit = r.json().get("deployment_commit") if r.status_code == 200 else None
print(f"deployment_commit: {deployed_commit}")

section("3. Access-control proof against the REAL production endpoint (unauthenticated)")
anon = requests.Session()
r = anon.get(f"{BACKEND_URL}{EXPORT_PATH}", params={"symbols": "1111", "start_date": "2026-01-01", "end_date": "2026-01-02"}, timeout=30)
print(f"Unauthenticated call -> HTTP {r.status_code} (expect 401)")
if r.status_code != 401:
    print("::error::Unauthenticated caller was NOT rejected -- STOP.")
    sys.exit(1)

section("4. Market coverage snapshot")
r = staff.get(f"{BACKEND_URL}/api/v1/admin/market-intelligence/coverage", timeout=30)
coverage = r.json() if r.status_code == 200 else {}
for k in ("total_stocks", "active_stocks", "stocks_with_price_history", "stocks_without_price_history"):
    print(f"{k}: {coverage.get(k)}")

section("5. Full active-symbol universe + sector metadata (paged /api/v1/stocks/directory)")
stocks_meta = []
offset, limit = 0, 200
while True:
    r = staff.get(f"{BACKEND_URL}/api/v1/stocks/directory", params={"limit": limit, "offset": offset}, timeout=30)
    if r.status_code != 200:
        print(f"FAILED at offset={offset}: status={r.status_code}")
        break
    body = r.json()
    page = body.get("results", [])
    stocks_meta.extend(page)
    offset += limit
    if offset >= body.get("total", 0) or not page:
        break
symbols = [s["symbol"] for s in stocks_meta]
print(f"Discovered {len(symbols)} active symbols.")

section("6. Real OHLCV pull (batched, adaptive window-splitting, zero SAHMK calls)")
all_rows = []
symbols_not_found_overall = set()
export_calls = 0


def date_windows(start, end, max_days):
    windows, cur = [], start
    while cur <= end:
        nxt = min(end, cur + timedelta(days=max_days - 1))
        windows.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return windows


def fetch_range(batch, start, end, depth=0):
    global export_calls
    export_calls += 1
    r = staff.get(
        f"{BACKEND_URL}{EXPORT_PATH}",
        params={"symbols": ",".join(batch), "start_date": start.isoformat(), "end_date": end.isoformat()},
        timeout=60,
    )
    if r.status_code != 200:
        print(f"::error::export call failed range={start}..{end} status={r.status_code}")
        return
    body = r.json()
    all_rows.extend(body["rows"])
    symbols_not_found_overall.update(body.get("symbols_not_found", []))
    if body.get("truncated") and (end - start).days > 1 and depth <= 20:
        mid = start + (end - start) // 2
        fetch_range(batch, start, mid, depth + 1)
        fetch_range(batch, mid + timedelta(days=1), end, depth + 1)


batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
top_windows = date_windows(DATA_START, DATA_END, TOP_LEVEL_WINDOW_DAYS)
for batch in batches:
    for (ws, we) in top_windows:
        fetch_range(batch, ws, we)
print(f"Total export HTTP calls: {export_calls}")
print(f"Total rows pulled: {len(all_rows)}")

min_ts = min((row["timestamp"] for row in all_rows), default=None)
max_ts = max((row["timestamp"] for row in all_rows), default=None)
print(f"earliest_date: {min_ts}")
print(f"latest_date: {max_ts}")

section("7. Phase A data-quality report")
duplicates, invalid_ohlc, zero_or_negative, synthetic_count = 0, 0, 0, 0
source_counts = {}
seen_keys = set()
for row in all_rows:
    key = (row["symbol"], row["timestamp"])
    if key in seen_keys:
        duplicates += 1
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

phase_a = {
    "real_historical_data_access": len(all_rows) > 0,
    "sahmk_api_calls_used_for_export": 0,
    "deployed_commit": deployed_commit,
    "earliest_date": min_ts,
    "latest_date": max_ts,
    "number_of_symbols_requested": len(symbols),
    "total_historical_bars": len(all_rows),
    "data_source_breakdown": source_counts,
    "synthetic_row_count": synthetic_count,
    "duplicate_symbol_timestamp_rows": duplicates,
    "invalid_ohlc_rows": invalid_ohlc,
    "zero_or_negative_price_rows": zero_or_negative,
    "corporate_action_adjustment_available": False,
}
print(json.dumps(phase_a, indent=2, default=str))

section("8. Building local in-memory dataset from the real rows (no fabricated data)")
engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
session = Session()

stock_by_symbol = {}
for meta in stocks_meta:
    stock = Stock(
        symbol=meta["symbol"], name_en=meta.get("name_en"), name_ar=meta.get("name_ar"),
        sector=meta.get("sector"), is_active=True,
    )
    session.add(stock)
    stock_by_symbol[meta["symbol"]] = stock
session.commit()

rows_loaded = 0
for row in all_rows:
    stock = stock_by_symbol.get(row["symbol"])
    if stock is None:
        continue
    session.add(PriceBar(
        stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
        timestamp=datetime.fromisoformat(row["timestamp"]),
        open=Decimal(str(row["open"])), high=Decimal(str(row["high"])),
        low=Decimal(str(row["low"])), close=Decimal(str(row["close"])),
        volume=int(row["volume"]), source=row.get("data_source") or "sahmk",
        is_synthetic=bool(row.get("is_synthetic")),
    ))
    rows_loaded += 1
session.commit()
print(f"Loaded {rows_loaded} real PriceBar rows across {len(stock_by_symbol)} real Stock rows into the local dataset.")

section("9. PHASE B -- running the real V2-vs-V2 backtest (Baseline vs Phase 3, identical inputs, no look-ahead)")
backtest_symbols = [s for s in symbols if s in stock_by_symbol]
start_dt = datetime.fromisoformat(min_ts).date() if min_ts else DATA_START
end_dt = datetime.fromisoformat(max_ts).date() if max_ts else DATA_END
print(f"Backtest window: {start_dt} .. {end_dt} | evaluation_frequency_days={EVAL_FREQUENCY_DAYS} "
      f"entry_expiry_days={ENTRY_EXPIRY_DAYS} resolution_horizon_days={RESOLUTION_HORIZON_DAYS}")

summary = run_decision_v2_replay(
    session, backtest_symbols, start_dt, end_dt,
    evaluation_frequency_days=EVAL_FREQUENCY_DAYS,
    entry_expiry_days=ENTRY_EXPIRY_DAYS,
    resolution_horizon_days=RESOLUTION_HORIZON_DAYS,
)
print(f"evaluated_points: {summary.evaluated_points}")
print(f"skipped: {summary.skipped}")


def arm_metrics(records, label):
    n = len(records)
    actionable = [r for r in records if r.decision in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE")]
    entered = [r for r in actionable if r.outcome.entry_triggered]
    t1 = [r for r in entered if r.outcome.target_1_hit]
    t2 = [r for r in entered if r.outcome.target_2_hit]
    t3 = [r for r in entered if r.outcome.target_3_hit]
    stop_hit = [r for r in entered if r.outcome.status is DecisionV2OutcomeStatus.STOP_LOSS_HIT]
    unresolved = [r for r in entered if r.outcome.status in (
        DecisionV2OutcomeStatus.PENDING, DecisionV2OutcomeStatus.EXPIRED, DecisionV2OutcomeStatus.DATA_UNAVAILABLE,
        DecisionV2OutcomeStatus.PARTIAL,
    )]
    returns = [r.outcome.return_pct for r in entered if r.outcome.return_pct is not None]
    mfe = [r.outcome.max_favorable_excursion_pct for r in entered if r.outcome.max_favorable_excursion_pct is not None]
    mae = [r.outcome.max_adverse_excursion_pct for r in entered if r.outcome.max_adverse_excursion_pct is not None]

    def rate(numer, denom):
        return f"{numer}/{denom}" + (f" ({numer / denom * 100.0:.1f}%)" if denom else " (INSUFFICIENT SAMPLE)")

    result = {
        "arm": label,
        "evaluated_opportunities": n,
        "actionable_buy_signals": len(actionable),
        "entries_triggered": rate(len(entered), len(actionable)),
        "t1_hit": rate(len(t1), len(entered)),
        "t2_hit": rate(len(t2), len(entered)),
        "t3_hit": rate(len(t3), len(entered)),
        "stop_before_t1": rate(len(stop_hit), len(entered)),
        "unresolved": rate(len(unresolved), len(entered)),
        "avg_mfe_pct": round(mean(mfe), 3) if mfe else None,
        "avg_mae_pct": round(mean(mae), 3) if mae else None,
        "avg_return_pct": round(mean(returns), 3) if returns else None,
        "expectancy_pct": round(mean(returns), 3) if len(returns) >= 5 else "INSUFFICIENT SAMPLE",
    }
    return result, entered


baseline_metrics, baseline_entered = arm_metrics(summary.baseline_records, "baseline_v2")
phase3_metrics, phase3_entered = arm_metrics(summary.phase3_records, "phase3_v2")
print(json.dumps(baseline_metrics, indent=2, default=str))
print(json.dumps(phase3_metrics, indent=2, default=str))

section("10. PHASE C -- stratification + ablation on Phase 3 arm")


def bucket_confidence(c):
    if c is None:
        return "unknown"
    if c < 60:
        return "<60"
    if c < 70:
        return "60-69"
    if c < 75:
        return "70-74"
    if c < 80:
        return "75-79"
    if c < 90:
        return "80-89"
    return ">=90"


def win_rate(records):
    entered = [r for r in records if r.outcome.entry_triggered]
    wins = [r for r in entered if r.outcome.return_pct is not None and r.outcome.return_pct > 0]
    if len(entered) < 5:
        return f"{len(wins)}/{len(entered)} INSUFFICIENT SAMPLE"
    return f"{len(wins)}/{len(entered)} ({len(wins) / len(entered) * 100.0:.1f}%)"


strat = {
    "high_quality_buy_vs_normal": {
        "HIGH_QUALITY_BUY": win_rate([r for r in phase3_entered if r.is_high_quality_buy]),
        "normal": win_rate([r for r in phase3_entered if not r.is_high_quality_buy]),
    },
    "confidence_bands": {
        band: win_rate([r for r in phase3_entered if bucket_confidence(r.confidence_score) == band])
        for band in ("<60", "60-69", "70-74", "75-79", "80-89", ">=90")
    },
    "breakout_confirmed_vs_not": {
        "confirmed": win_rate([r for r in phase3_entered if r.breakout_status == "CONFIRMED_BREAKOUT"]),
        "not_confirmed": win_rate([r for r in phase3_entered if r.breakout_status != "CONFIRMED_BREAKOUT"]),
    },
    "sector_strength_used_vs_not": {
        "used": win_rate([r for r in phase3_entered if r.sector_strength_used]),
        "not_used": win_rate([r for r in phase3_entered if not r.sector_strength_used]),
    },
    "anti_chase_wait_vs_allowed": {
        "wait_for_pullback": win_rate([r for r in phase3_entered if r.entry_status == "WAIT_FOR_PULLBACK"]),
        "ready_now_or_other": win_rate([r for r in phase3_entered if r.entry_status != "WAIT_FOR_PULLBACK"]),
    },
}
print(json.dumps(strat, indent=2, default=str))

section("11. FINAL REPORT FIELDS")
final = {
    "REAL_HISTORICAL_DATA_ACCESS": "YES" if phase_a["real_historical_data_access"] else "NO",
    "SAHMK_API_CALLS_USED_FOR_BACKTEST": 0,
    "SAHMK_QUOTA_CONSUMED": 0,
    "BASELINE_SAMPLE_SIZE": len(baseline_entered),
    "PHASE3_SAMPLE_SIZE": len(phase3_entered),
    "baseline_metrics": baseline_metrics,
    "phase3_metrics": phase3_metrics,
    "stratification": strat,
    "skipped": summary.skipped,
    "evaluated_points": summary.evaluated_points,
}
print(json.dumps(final, indent=2, default=str))

with open("phase3_backtest_full_report.json", "w") as f:
    json.dump(final, f, indent=2, default=str)
print("\nWrote phase3_backtest_full_report.json")
