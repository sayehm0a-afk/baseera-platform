"""BASIRAH -- PHASE 3 ZERO-ACTIONABLE-SIGNAL ROOT-CAUSE DIAGNOSTIC.

Read-only. Pulls the same real OHLCV as run 32581662713 (zero SAHMK
calls -- the export route only reads already-ingested PriceBar rows),
then walks the SAME (symbol, evaluation_date) grid but calls only the
DECISION-generating functions (build_replay_point / run_baseline_v2 /
run_phase3_v2) -- it deliberately never calls evaluate_decision_v2_
backtest_outcome (no forward price-path / target-stop tracking), which
is what made the original backtest heavy. This is a lighter,
decision-only diagnostic pass, not a re-run of the full backtest.

Never modifies DecisionEngineV2, never changes thresholds, never
merges or deploys anything.
"""

import bisect
import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.getcwd())

from src.backtesting.data_access import evaluation_dates  # noqa: E402
from src.backtesting.decision_v2_strategies import build_replay_point, run_baseline_v2, run_phase3_v2  # noqa: E402
from src.core.db.database import Base  # noqa: E402
from src.domain.models import PriceBar, Stock, Timeframe  # noqa: E402

BACKEND_URL = os.environ["BACKEND_URL"].rstrip("/")
STAFF_EMAIL = os.environ["STAFF_EMAIL"]
STAFF_PASSWORD = os.environ["STAFF_PASSWORD"]

EXPORT_PATH = "/api/v1/admin/historical-data-export/ohlcv"
BATCH_SIZE = 50
DATA_START = date(2015, 1, 1)
DATA_END = datetime.now(timezone.utc).date()
TOP_LEVEL_WINDOW_DAYS = 3650
EVAL_FREQUENCY_DAYS = 3
MIN_TECHNICAL_BARS = 35  # src/analysis/technical_analysis_engine.py:151, literal constant


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


section("1. Staff login + real OHLCV pull (identical to run 32581662713, zero SAHMK calls)")
staff = requests.Session()
r = staff.post(f"{BACKEND_URL}/api/v1/auth/login", json={"email": STAFF_EMAIL, "password": STAFF_PASSWORD}, timeout=30)
if r.status_code != 200:
    print(f"Staff login failed: status={r.status_code}")
    sys.exit(1)
csrf = staff.cookies.get("csrf_token")
if csrf:
    staff.headers.update({"X-CSRF-Token": csrf})

symbols_meta = []
offset, limit = 0, 200
while True:
    r = staff.get(f"{BACKEND_URL}/api/v1/stocks/directory", params={"limit": limit, "offset": offset}, timeout=30)
    body = r.json()
    page = body.get("results", [])
    symbols_meta.extend(page)
    offset += limit
    if offset >= body.get("total", 0) or not page:
        break
symbols = [s["symbol"] for s in symbols_meta]
print(f"Discovered {len(symbols)} active symbols.")


def date_windows(start, end, max_days):
    windows, cur = [], start
    while cur <= end:
        nxt = min(end, cur + timedelta(days=max_days - 1))
        windows.append((cur, nxt))
        cur = nxt + timedelta(days=1)
    return windows


all_rows = []


def fetch_range(batch, start, end, depth=0):
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
    if body.get("truncated") and (end - start).days > 1 and depth <= 20:
        mid = start + (end - start) // 2
        fetch_range(batch, start, mid, depth + 1)
        fetch_range(batch, mid + timedelta(days=1), end, depth + 1)


batches = [symbols[i:i + BATCH_SIZE] for i in range(0, len(symbols), BATCH_SIZE)]
top_windows = date_windows(DATA_START, DATA_END, TOP_LEVEL_WINDOW_DAYS)
for batch in batches:
    for (ws, we) in top_windows:
        fetch_range(batch, ws, we)
print(f"Total rows pulled: {len(all_rows)} (SAHMK calls used: 0)")
min_ts = min((row["timestamp"] for row in all_rows), default=None)
max_ts = max((row["timestamp"] for row in all_rows), default=None)
print(f"earliest_date: {min_ts}  latest_date: {max_ts}")

section("2. Building local dataset (same as run 32581662713 -- OHLCV only, no fundamentals/news/breadth ingested)")
engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
Base.metadata.create_all(bind=engine)
Session = sessionmaker(bind=engine)
session = Session()

stock_by_symbol = {}
bars_per_symbol = Counter()
for meta in symbols_meta:
    stock = Stock(symbol=meta["symbol"], name_en=meta.get("name_en"), name_ar=meta.get("name_ar"), sector=meta.get("sector"), is_active=True)
    session.add(stock)
    stock_by_symbol[meta["symbol"]] = stock
session.commit()

for row in all_rows:
    stock = stock_by_symbol.get(row["symbol"])
    if stock is None:
        continue
    session.add(PriceBar(
        stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
        timestamp=datetime.fromisoformat(row["timestamp"]),
        open=Decimal(str(row["open"])), high=Decimal(str(row["high"])), low=Decimal(str(row["low"])), close=Decimal(str(row["close"])),
        volume=int(row["volume"]), source=row.get("data_source") or "sahmk", is_synthetic=bool(row.get("is_synthetic")),
    ))
    bars_per_symbol[row["symbol"]] += 1
session.commit()
print(f"Loaded {len(all_rows)} PriceBar rows across {len(stock_by_symbol)} Stock rows.")
print(f"Bars per symbol: min={min(bars_per_symbol.values())} max={max(bars_per_symbol.values())} "
      f"median={sorted(bars_per_symbol.values())[len(bars_per_symbol) // 2]}")

# Precomputed sorted bar-date lists per symbol -- O(log n) lookups
# below instead of an O(grid_points * total_rows) linear rescan.
bar_dates_by_symbol = defaultdict(list)
for row in all_rows:
    bar_dates_by_symbol[row["symbol"]].append(row["timestamp"])
for sym in bar_dates_by_symbol:
    bar_dates_by_symbol[sym].sort()

section("3. Warm-up requirement (from source, not inferred)")
print("TechnicalAnalysisEngine.analyze() raises ValueError below this bar count "
      f"(src/analysis/technical_analysis_engine.py:151): minimum_rows = {MIN_TECHNICAL_BARS}")
print("Indicators actually registered (src/analysis/registry.py): "
      "sma_20, ema_20, adx_14, rsi_14, macd(12,26,9), bollinger(20,2.0), atr_14, volume_sma_20 "
      "-- no 50/100/200-day indicator exists anywhere in this codebase's registry.")
print("MACD(12,26,9) is the true binding constraint: slow EMA(26) + signal EMA(9) needs ~34 bars "
      "to produce a non-NaN signal line -- the engine's 35-bar floor is set just above that, not for the SMA/RSI/ADX/ATR/Bollinger legs (all <=20).")

backend_start = datetime.fromisoformat(min_ts).date() if min_ts else DATA_START
backend_end = datetime.fromisoformat(max_ts).date() if max_ts else DATA_END
dates = evaluation_dates(backend_start, backend_end, EVAL_FREQUENCY_DAYS)
print(f"\nEvaluation grid: {len(symbols)} symbols x {len(dates)} dates = {len(symbols) * len(dates)} points "
      f"(window {backend_start}..{backend_end}, every {EVAL_FREQUENCY_DAYS} days)")

section("4. DECISION-ONLY pass over the full grid (no outcome/target-stop tracking -- lighter than the full backtest)")
decision_counts = {"baseline": Counter(), "phase3": Counter()}
raw_recommendation_counts = Counter()
gate_status_counts = {"baseline": defaultdict(Counter), "phase3": defaultdict(Counter)}
blocking_gate_counts = {"baseline": Counter(), "phase3": Counter()}
skip_reasons = Counter()
warmup_insufficient = 0
warmup_sufficient_but_skipped = 0
sub_score_avail_hist = Counter()
market_risk_state_counts = Counter()
sector_strength_used_count = 0
breakout_status_counts = Counter()
confidence_by_decision = defaultdict(list)
examples = []
evaluated_points = 0

for symbol in symbols:
    stock = stock_by_symbol.get(symbol)
    if stock is None or bars_per_symbol.get(symbol, 0) == 0:
        continue
    sym_bar_dates = bar_dates_by_symbol.get(symbol, [])
    for as_of in dates:
        cutoff = as_of.isoformat() + "T23:59:59"
        bars_as_of = bisect.bisect_right(sym_bar_dates, cutoff)
        point = build_replay_point(session, stock, as_of)
        if point is None:
            skip_reasons["no_replay_point (has_any_input False)"] += 1
            if bars_as_of < MIN_TECHNICAL_BARS:
                warmup_insufficient += 1
            else:
                warmup_sufficient_but_skipped += 1
            continue

        evaluated_points += 1
        raw_recommendation_counts[str(point.investment_decision.recommendation.value)] += 1

        baseline = run_baseline_v2(point)
        phase3 = run_phase3_v2(point)

        decision_counts["baseline"][baseline.decision.value] += 1
        decision_counts["phase3"][phase3.decision.value] += 1
        confidence_by_decision[("phase3", phase3.decision.value)].append(phase3.confidence_score)

        for arm_name, result in (("baseline", baseline), ("phase3", phase3)):
            first_blocking_fail = None
            for g in result.gates:
                gate_status_counts[arm_name][g.name][g.status.value] += 1
                if g.status.value == "FAIL" and g.blocking and first_blocking_fail is None:
                    first_blocking_fail = g.name
            blocking_gate_counts[arm_name][first_blocking_fail or "none_all_passed"] += 1

        sub_score_avail_hist[sum(1 for v in [
            phase3.sub_scores.trend_score, phase3.sub_scores.momentum_score, phase3.sub_scores.volume_score,
            phase3.sub_scores.liquidity_score, phase3.sub_scores.volatility_score, phase3.sub_scores.risk_reward_score,
            phase3.sub_scores.market_context_score,
        ] if v is not None)] += 1
        market_risk_state_counts[phase3.market_risk_state] += 1
        if phase3.sector_strength_used:
            sector_strength_used_count += 1
        breakout_status_counts[phase3.breakout_status] += 1

        if phase3.decision.value not in ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE") and len(examples) < 25:
            blocking = blocking_gate_counts["phase3"]  # noqa: F841 (already recorded above per-point; recompute for this point)
            point_blocking = None
            for g in phase3.gates:
                if g.status.value == "FAIL" and g.blocking:
                    point_blocking = f"{g.name}: {g.detail}"
                    break
            examples.append({
                "symbol": symbol, "as_of": str(as_of),
                "raw_recommendation": str(point.investment_decision.recommendation.value),
                "decision": phase3.decision.value,
                "confidence": round(phase3.confidence_score, 1),
                "risk_reward_target_1": phase3.risk_reward_target_1,
                "entry_status": phase3.entry_status.value if phase3.entry_status else None,
                "trend_score": phase3.sub_scores.trend_score,
                "market_context_score": phase3.sub_scores.market_context_score,
                "market_risk_state": phase3.market_risk_state,
                "sector_strength_used": phase3.sector_strength_used,
                "sector_strength_score": phase3.sector_strength_score,
                "breakout_status": phase3.breakout_status,
                "bars_available_as_of": bars_as_of,
                "final_blocking_gate": point_blocking or "(none blocking -- non-actionable via HOLD/SELL-side mapping, not a gate FAIL)",
            })

section("5. Decision distribution (both arms, full evaluated grid)")
print(json.dumps({"baseline": dict(decision_counts["baseline"]), "phase3": dict(decision_counts["phase3"])}, indent=2))

section("6. Raw underlying Recommendation (V1 AIDecisionEngine score band, pre-gates -- identical for both arms)")
print(json.dumps(dict(raw_recommendation_counts), indent=2))

section("7. Gate-level PASS/FAIL/NOT_EVALUATED tallies (phase3 arm)")
print(json.dumps({k: dict(v) for k, v in gate_status_counts["phase3"].items()}, indent=2))

section("8. First BLOCKING gate that actually determined a non-STRONG_BUY/BUY_CANDIDATE-eligible outcome")
print("baseline:", json.dumps(dict(blocking_gate_counts["baseline"]), indent=2))
print("phase3:  ", json.dumps(dict(blocking_gate_counts["phase3"]), indent=2))

section("9. Skip accounting (points that never reached the engine at all)")
print(json.dumps({
    "total_grid_points": len(symbols) * len(dates),
    "evaluated_points": evaluated_points,
    "skipped_total": sum(skip_reasons.values()),
    "skipped_warmup_insufficient (<35 real bars as-of that date)": warmup_insufficient,
    "skipped_despite_35plus_bars (other has_any_input=False cause)": warmup_sufficient_but_skipped,
}, indent=2))

section("10. Evidence coverage / market-risk / sector-strength / breakout distributions (phase3 arm, evaluated points only)")
print("available_sub_score_count histogram (0-7, excludes data_quality_score which is always populated):")
print(json.dumps(dict(sub_score_avail_hist), indent=2))
print("\nmarket_risk_state distribution:")
print(json.dumps(dict(market_risk_state_counts), indent=2))
print(f"\nsector_strength_used: {sector_strength_used_count}/{evaluated_points}")
print("\nbreakout_status distribution:")
print(json.dumps(dict(breakout_status_counts), indent=2))

section("11. Confidence score by decision (phase3 arm)")
for (arm, decision_val), scores in confidence_by_decision.items():
    if scores:
        print(f"{decision_val}: n={len(scores)} min={min(scores):.1f} max={max(scores):.1f} mean={sum(scores) / len(scores):.1f}")

section("12. 25 representative non-actionable evaluation points (phase3 arm)")
print(json.dumps(examples, indent=2, default=str))

with open("phase3_zero_signal_root_cause.json", "w") as f:
    json.dump({
        "decision_counts": {k: dict(v) for k, v in decision_counts.items()},
        "raw_recommendation_counts": dict(raw_recommendation_counts),
        "gate_status_counts_phase3": {k: dict(v) for k, v in gate_status_counts["phase3"].items()},
        "blocking_gate_counts": {k: dict(v) for k, v in blocking_gate_counts.items()},
        "skip_accounting": {
            "total_grid_points": len(symbols) * len(dates), "evaluated_points": evaluated_points,
            "warmup_insufficient": warmup_insufficient, "warmup_sufficient_but_skipped": warmup_sufficient_but_skipped,
        },
        "sub_score_avail_hist": dict(sub_score_avail_hist),
        "market_risk_state_counts": dict(market_risk_state_counts),
        "sector_strength_used_count": sector_strength_used_count,
        "breakout_status_counts": dict(breakout_status_counts),
        "examples": examples,
    }, f, indent=2, default=str)
print("\nWrote phase3_zero_signal_root_cause.json")
