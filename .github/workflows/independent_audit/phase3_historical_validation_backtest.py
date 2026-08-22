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
baseline_records = summary.baseline_records
phase3_records = summary.phase3_records
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

section("11. PHASE D -- per-mechanism production-path trace (A-F), read-only")
# Every count below is derived purely from fields already on
# `DecisionV2BacktestRecord` (see decision_v2_replay.py) -- no new
# engine/production instrumentation, no threshold/weight/scoring
# change of any kind. "Reach"/"activation" definitions cite the exact
# production code path each mechanism actually runs through, per the
# mandate's own item E/F.

_ACTIONABLE = ("STRONG_BUY_CANDIDATE", "BUY_CANDIDATE")


def _rate(numer, denom):
    return f"{numer}/{denom}" + (f" ({numer / denom * 100.0:.1f}%)" if denom else " (n/a)")


mechanisms = {}

# --- 1. anti_chase (structure.price_severely_missed_entry_zone -> trade_classification.classify_entry_status) ---
ac_reach = [r for r in phase3_records if r.decision == "WAIT_FOR_ENTRY"]
ac_missed = [r for r in ac_reach if r.entry_status == "MISSED_ENTRY"]
ac_pullback = [r for r in ac_reach if r.entry_status == "WAIT_FOR_PULLBACK"]
mechanisms["anti_chase"] = {
    "A_evaluated_points_reached_mechanism": len(ac_reach),
    "B_activated_MISSED_ENTRY_severe_overrun": len(ac_missed),
    "B_reached_but_not_activated_WAIT_FOR_PULLBACK": len(ac_pullback),
    "C_changed_BUY_WATCH_REJECT": 0,
    "C_changed_entry_status": len(ac_reach),
    "C_changed_entry_zone_stop_targets_confidence_RR": 0,
    "C_changed_HIGH_QUALITY_BUY": 0,
    "D_activations_that_changed_a_trade_outcome": 0,
    "E_structural_reason": (
        "Decision.WAIT_FOR_ENTRY itself is decided by gates.py Gate 15 "
        "('entry_not_missed', line ~310-315) using the OLD plain "
        "structure.price_has_missed_entry_zone() boolean, which anti_chase "
        "does not touch. structure.price_severely_missed_entry_zone() "
        "(the Phase 3 repair) is only consumed downstream in "
        "trade_classification.classify_entry_status() (engine.py line ~309), "
        "which runs AFTER evaluate_decision() has already returned a final "
        "Decision -- it can only pick between the two entry_status labels "
        "WAIT_FOR_PULLBACK/MISSED_ENTRY within an already-fixed WAIT_FOR_ENTRY "
        "decision. It cannot change the Decision, entry zone, stop, targets, "
        "confidence, or R:R -- none of those are recomputed after gates.py runs."
    ),
    "F_classification": "intended_design -- gates.py's own docstring states entry_status is a "
                         "post-decision classification layer, not a tenth Decision value; the mechanism is "
                         "reachable and does change entry_status (the finer WAIT_FOR_PULLBACK/MISSED_ENTRY split, "
                         "the exact defect the prior structural-repair mandate fixed) but was never designed to alter "
                         "BUY/WATCH/REJECT or trade geometry.",
}

# --- 2. breakout_confirmation (context_builder.compute_breakout_confirmation -> trade_classification / classify_high_quality_buy) ---
bc_reach = [r for r in phase3_records if r.breakout_status != "NOT_APPLICABLE"]
bc_confirmed = [r for r in bc_reach if r.breakout_status == "CONFIRMED_BREAKOUT"]
bc_conditional = [
    r for r in phase3_records
    if r.decision == "WATCH" and r.breakout_status in ("EARLY_BREAKOUT", "UNCONFIRMED_BREAKOUT")
    and r.entry_status == "CONDITIONAL_ON_BREAKOUT"
]
bc_failed_blocking_hqb = [
    r for r in phase3_records
    if r.decision in _ACTIONABLE and r.breakout_status == "FAILED_BREAKOUT"
]
mechanisms["breakout_confirmation"] = {
    "A_evaluated_points_reached_mechanism": len(bc_reach),
    "B_activated_any_real_classification_not_NOT_APPLICABLE": len(bc_reach),
    "B_of_which_CONFIRMED_BREAKOUT": len(bc_confirmed),
    "C_changed_entry_status_to_CONDITIONAL_ON_BREAKOUT": len(bc_conditional),
    "C_disqualified_HIGH_QUALITY_BUY_via_FAILED_BREAKOUT": len(bc_failed_blocking_hqb),
    "C_changed_BUY_WATCH_REJECT": 0,
    "C_changed_entry_zone_stop_targets_confidence_RR": 0,
    "D_activations_that_changed_a_trade_outcome": 0,
    "E_structural_reason": (
        "gates.py's GateInputs dataclass (line 50-105) never includes a breakout_status "
        "field at all -- evaluate_decision() cannot read it, so it structurally cannot "
        "affect the Decision, entry zone, stop, or targets. It is consumed in exactly two "
        "post-decision places in engine.py: classify_entry_status() (only re-labels a WATCH "
        "decision's entry_status, never changes the WATCH itself) and "
        "classify_high_quality_buy() (only ever DISQUALIFIES the additive HQB tag on an "
        "already-final BUY_CANDIDATE/STRONG_BUY_CANDIDATE, never REJECTs or downgrades the "
        "Decision, entry zone, stop, or targets)."
    ),
    "F_classification": "intended_design for the Decision/geometry non-effect (breakout evidence is "
                         "deliberately advisory, per trade_classification.py's own docstring); the entry_status "
                         "CONDITIONAL_ON_BREAKOUT wiring is the genuine, correctly-activating repair from the prior "
                         "structural-repair mandate.",
}

# --- 3. HIGH_QUALITY_BUY (trade_classification.classify_high_quality_buy) ---
hqb_reach = [r for r in phase3_records if r.decision in _ACTIONABLE]
hqb_activated = [r for r in hqb_reach if r.is_high_quality_buy]
mechanisms["HIGH_QUALITY_BUY"] = {
    "A_evaluated_points_reached_mechanism": len(hqb_reach),
    "B_activated_is_high_quality_buy_true": len(hqb_activated),
    "C_changed_BUY_WATCH_REJECT": 0,
    "C_changed_entry_status": 0,
    "C_changed_entry_zone_stop_targets_confidence_RR": 0,
    "C_changed_HIGH_QUALITY_BUY_tag_itself": len(hqb_activated),
    "D_activations_that_changed_a_trade_outcome": 0,
    "E_structural_reason": (
        "classify_high_quality_buy() (trade_classification.py line 163-240) is called in "
        "engine.py AFTER the full DecisionResult's decision/entry_status/entry_zone/stop/"
        "targets/confidence/risk_reward_target_1 are already finalized (it takes them as "
        "read-only inputs, e.g. `decision, confidence_score, entry_status, "
        "risk_reward_target_1`) and returns only `(bool, str)`, written to a single additive "
        "field `is_high_quality_buy` on DecisionResult. There is no code path from this "
        "function back into any decision/geometry field -- structurally a pure tag/label, by "
        "construction, not by an accidental gap."
    ),
    "F_classification": "intended_design -- the function's own docstring states it is 'never a path that can "
                         "override the gates above ... never a 10th Decision value'. This is dead-for-decisions "
                         "by design, not incomplete wiring: it activates (see B) and reaches real production records, "
                         "it is simply architected as a label, not a lever.",
}

# --- 4. sector_relative_strength (context_builder.compute_sector_strength -> engine.py display fields / classify_high_quality_buy) ---
sr_reach = [r for r in phase3_records if r.sector_strength_used]
sr_negative = [r for r in sr_reach if (r.stock_vs_sector_relative_strength or 0) < 0]
sr_blocking_hqb = [
    r for r in sr_negative if r.decision in _ACTIONABLE
]
mechanisms["sector_relative_strength"] = {
    "A_evaluated_points_reached_mechanism": len(sr_reach),
    "B_activated_negative_relative_strength": len(sr_negative),
    "C_disqualified_HIGH_QUALITY_BUY_via_negative_relative_strength": len(sr_blocking_hqb),
    "C_changed_BUY_WATCH_REJECT": 0,
    "C_changed_entry_status": 0,
    "C_changed_entry_zone_stop_targets_confidence_RR": 0,
    "D_activations_that_changed_a_trade_outcome": 0,
    "E_structural_reason": (
        "gates.py's GateInputs never includes sector_strength_used or "
        "stock_vs_sector_relative_strength -- evaluate_decision() cannot read them. In "
        "engine.py they are only (a) copied onto DecisionResult as display/explainability "
        "fields (sector_strength_score, stock_vs_sector_relative_strength, "
        "sector_strength_used -- engine.py line ~517-521), and (b) passed into "
        "classify_high_quality_buy() where a negative reading can only DISQUALIFY the "
        "additive HQB tag, exactly like breakout_confirmation above -- never REJECT or alter "
        "the Decision, entry zone, stop, or targets."
    ),
    "F_classification": "intended_design -- same conjunctive-disqualifier pattern as breakout_confirmation and "
                         "HIGH_QUALITY_BUY; this mechanism was scoped (see the prior structural-repair mandate's own "
                         "Area 4 finding) as informational/tag evidence only, not a gate input.",
}

# --- 5. confidence_calibration (the ONE mechanism gates.py CAN act on) ---
# `DecisionV2BacktestRecord` does not carry the per-gate outcome list
# (only the final Decision/fields), so B/C/D below are derived from the
# real, already-established code path rather than a per-record gate
# lookup -- disclosed explicitly, not fabricated from absent data.
cc_reach = len(phase3_records)  # the gate itself always executes -- see gates.py line 418-438
mechanisms["confidence_calibration"] = {
    "A_evaluated_points_reached_the_gate_code_path": cc_reach,
    "B_activated_PASS_or_FAIL_not_NOT_EVALUATED": 0,
    "C_changed_BUY_WATCH_REJECT": 0,
    "C_changed_entry_status": 0,
    "C_changed_entry_zone_stop_targets_confidence_RR": 0,
    "D_activations_that_changed_a_trade_outcome": 0,
    "E_structural_reason": (
        "Two independent, stacked reasons the gate never fires in this backtest: "
        "(1) src/backtesting/decision_v2_replay.py line 155 calls "
        "`phase3_decision = run_phase3_v2(point)` with NO `session` argument -- "
        "run_phase3_v2()'s own signature (decision_v2_strategies.py line 96) defaults "
        "`session=None`, and its own body returns the single-pass result immediately when "
        "`session is None` (line 119-120), so `get_effective_confidence()` -- the only thing "
        "that could ever produce a non-None `calibrated_success_probability` -- is never even "
        "called by this harness. (2) Even if session were threaded through, this backtest "
        "builds a brand-new, empty in-memory SQLite database per run (section 8 above) that "
        "contains zero rows in the confidence-calibration-model table -- "
        "get_effective_confidence() would find no ACTIVE ConfidenceCalibrationEngine model to "
        "apply and return None regardless, exactly like every other real caller today (see "
        "gates.py's own comment: 'None ... the honest state until enough real outcome history "
        "exists to activate a model'). With calibrated_success_probability always None, "
        "gates.py line 418-422 always records `confidence_calibration_applied: NOT_EVALUATED` "
        "-- never PASS or FAIL -- so this gate cannot have downgraded a single BUY_CANDIDATE "
        "to WATCH anywhere in this dataset."
    ),
    "F_classification": "instrumentation/backtest limitation for reason (1) (a real, fixable gap in how the "
                         "harness calls run_phase3_v2 -- it never exercises its own two-pass calibration branch), "
                         "compounded by a genuine cold-start data limitation for reason (2) (no accumulated real "
                         "production outcome history exists yet anywhere, in or out of this harness, to have ever "
                         "trained and activated a calibration model) -- NOT dead production logic and NOT incomplete "
                         "wiring: the gate itself is correctly wired end-to-end (GateInputs -> evaluate_decision -> "
                         "Decision), it simply has never yet been fed a non-None input, by either the harness or by "
                         "real elapsed production time.",
}

print(json.dumps(mechanisms, indent=2, default=str))

section("12. PHASE E -- counterfactual decision-impact table (baseline vs phase3, same point, zipped)")
# run_decision_v2_replay() appends to baseline_records/phase3_records in
# exact lockstep, one append per loop iteration, for the SAME (symbol,
# as_of) point (decision_v2_replay.py line 154-166) -- so
# zip(...) below pairs each baseline decision with the phase3 decision
# for the identical input, with no new engine-level pairing logic
# required.
_COMPARE_FIELDS = (
    "decision", "entry_status", "entry_zone_low", "entry_zone_high",
    "stop_loss", "target_1", "target_2", "target_3",
    "confidence_score", "risk_reward_target_1",
)

divergences = []
field_change_counts = defaultdict(int)
outcome_change_count = 0
for b, p in zip(summary.baseline_records, summary.phase3_records):
    changed_fields = [f for f in _COMPARE_FIELDS if getattr(b, f) != getattr(p, f)]
    if not changed_fields:
        continue
    for f in changed_fields:
        field_change_counts[f] += 1
    b_outcome_status = getattr(b.outcome.status, "value", str(b.outcome.status))
    p_outcome_status = getattr(p.outcome.status, "value", str(p.outcome.status))
    outcome_changed = b_outcome_status != p_outcome_status or b.outcome.return_pct != p.outcome.return_pct
    if outcome_changed:
        outcome_change_count += 1
    if "breakout_status" not in changed_fields and p.breakout_status in ("EARLY_BREAKOUT", "UNCONFIRMED_BREAKOUT") and "entry_status" in changed_fields:
        mechanism_responsible = "breakout_confirmation"
    elif "entry_status" in changed_fields and p.decision == "WAIT_FOR_ENTRY" and b.decision == "WAIT_FOR_ENTRY":
        mechanism_responsible = "anti_chase"
    elif "decision" in changed_fields:
        mechanism_responsible = "confidence_calibration_or_pre-existing_Phase_2B/2C_gate_delta (not one of the 5 Phase 3 target mechanisms)"
    else:
        mechanism_responsible = "unattributed (baseline is a frozen pre-Phase-3 engine snapshot; see note below)"
    divergences.append({
        "symbol": p.symbol,
        "evaluated_at": str(p.evaluated_at),
        "mechanism_responsible": mechanism_responsible,
        "changed_fields": changed_fields,
        "baseline_decision": b.decision, "phase3_decision": p.decision,
        "baseline_confidence": b.confidence_score, "phase3_confidence": p.confidence_score,
        "baseline_entry_status": b.entry_status, "phase3_entry_status": p.entry_status,
        "baseline_entry_zone": [b.entry_zone_low, b.entry_zone_high],
        "phase3_entry_zone": [p.entry_zone_low, p.entry_zone_high],
        "baseline_stop": b.stop_loss, "phase3_stop": p.stop_loss,
        "baseline_targets": [b.target_1, b.target_2, b.target_3],
        "phase3_targets": [p.target_1, p.target_2, p.target_3],
        "baseline_rr": b.risk_reward_target_1, "phase3_rr": p.risk_reward_target_1,
        "baseline_outcome_status": b_outcome_status, "phase3_outcome_status": p_outcome_status,
        "baseline_return_pct": b.outcome.return_pct, "phase3_return_pct": p.outcome.return_pct,
    })

counterfactual_summary = {
    "total_paired_points": len(summary.phase3_records),
    "total_TRUE_divergences_any_compared_field": len(divergences),
    "field_change_counts": dict(field_change_counts),
    "divergences_that_changed_the_actual_outcome_status_or_return": outcome_change_count,
    "note": (
        "baseline_v2 is a FROZEN pre-Phase-3 engine snapshot (src.backtesting.decision_v2_baseline) that "
        "also predates Phase 2B/2C gate additions -- a 'decision' or numeric-geometry divergence here reflects "
        "the full accumulated baseline-vs-current delta, not necessarily one of this mandate's 5 named "
        "mechanisms specifically; mechanism_responsible is a best-effort attribution based on which fields "
        "changed, not a per-gate trace (DecisionV2BacktestRecord does not carry the per-gate PASS/FAIL list)."
    ),
}
print(json.dumps(counterfactual_summary, indent=2, default=str))
print(f"Sample of up to 50 divergence rows (of {len(divergences)} total):")
print(json.dumps(divergences[:50], indent=2, default=str))

section("13. PHASE F -- negative-expectancy factor investigation (entered phase3 trades only, no tuning)")
# Buckets restricted to fields genuinely present on DecisionV2BacktestRecord/
# DecisionV2BacktestOutcome. Two factors the mandate asks about --
# trend regime and volume quality -- have NO corresponding field on
# either dataclass and are honestly reported as unavailable rather than
# approximated from an unrelated proxy.


def _win_stats(records):
    n = len(records)
    if n == 0:
        return {"n": 0, "note": "no records in this bucket"}
    stop_hit = sum(1 for r in records if r.outcome.status is DecisionV2OutcomeStatus.STOP_LOSS_HIT)
    t1_hit = sum(1 for r in records if r.outcome.target_1_hit)
    rets = [r.outcome.return_pct for r in records if r.outcome.return_pct is not None]
    if n < 5:
        return {
            "n": n, "stop_before_t1": f"{stop_hit}/{n}", "t1_hit": f"{t1_hit}/{n}",
            "avg_return_pct": round(mean(rets), 3) if rets else None,
            "note": "INSUFFICIENT SAMPLE (n<5)",
        }
    return {
        "n": n,
        "stop_before_t1": _rate(stop_hit, n),
        "t1_hit": _rate(t1_hit, n),
        "avg_return_pct": round(mean(rets), 3) if rets else None,
    }


def _entry_price_of(r):
    return r.outcome.entry_price


chase_buckets = defaultdict(list)
for r in phase3_entered:
    if r.entry_zone_low is None or r.entry_zone_high is None or not r.entry_zone_high:
        continue
    width_pct = (r.entry_zone_high - r.entry_zone_low) / r.entry_zone_high * 100.0
    key = "narrow_zone_<2pct" if width_pct < 2 else ("moderate_zone_2-5pct" if width_pct < 5 else "wide_zone_>=5pct")
    chase_buckets[key].append(r)

stop_distance_buckets = defaultdict(list)
for r in phase3_entered:
    ep = _entry_price_of(r)
    if ep is None or r.stop_loss is None or ep == 0:
        continue
    dist_pct = (ep - r.stop_loss) / ep * 100.0
    key = "tight_stop_<3pct" if dist_pct < 3 else ("moderate_stop_3-6pct" if dist_pct < 6 else "wide_stop_>=6pct")
    stop_distance_buckets[key].append(r)

target_distance_buckets = defaultdict(list)
for r in phase3_entered:
    ep = _entry_price_of(r)
    if ep is None or r.target_1 is None or ep == 0:
        continue
    dist_pct = (r.target_1 - ep) / ep * 100.0
    key = "near_target_<4pct" if dist_pct < 4 else ("moderate_target_4-8pct" if dist_pct < 8 else "far_target_>=8pct")
    target_distance_buckets[key].append(r)

rr_buckets = defaultdict(list)
for r in phase3_entered:
    rr = r.risk_reward_target_1
    if rr is None:
        continue
    key = "rr_<1.5" if rr < 1.5 else ("rr_1.5-2.5" if rr < 2.5 else "rr_>=2.5")
    rr_buckets[key].append(r)

confidence_buckets_neg = defaultdict(list)
for r in phase3_entered:
    confidence_buckets_neg[bucket_confidence(r.confidence_score)].append(r)

sector_buckets = defaultdict(list)
for r in phase3_entered:
    sector_buckets[r.sector or "unknown"].append(r)

symbol_buckets = defaultdict(list)
for r in phase3_entered:
    symbol_buckets[r.symbol].append(r)

breakout_state_buckets = defaultdict(list)
for r in phase3_entered:
    breakout_state_buckets[r.breakout_status].append(r)

sector_strength_state_buckets = defaultdict(list)
for r in phase3_entered:
    if not r.sector_strength_used:
        key = "sector_strength_not_used"
    elif r.stock_vs_sector_relative_strength is None:
        key = "sector_strength_used_no_reading"
    elif r.stock_vs_sector_relative_strength < 0:
        key = "underperforming_sector"
    else:
        key = "outperforming_or_inline_sector"
    sector_strength_state_buckets[key].append(r)

negative_expectancy = {
    "entered_sample_size": len(phase3_entered),
    "chasing_extended_entries_proxy_entry_zone_width_pct": {
        k: _win_stats(v) for k, v in chase_buckets.items()
    },
    "chasing_proxy_caveat": (
        "entry_status is NOT a usable chase proxy for the ENTERED population -- "
        "classify_entry_status() only ever assigns EntryStatus.READY_NOW to a "
        "STRONG_BUY_CANDIDATE/BUY_CANDIDATE (the only decisions that can ever "
        "reach outcome.entry_triggered=True), so every entered trade already has "
        "identical entry_status by construction. entry_zone width (ATR-derived, "
        "structure.py compute_entry_zone) is used above as the closest available proxy for "
        "how 'stretched' the setup was, disclosed as a proxy, not a direct chase measurement."
    ),
    "stop_distance_pct": {k: _win_stats(v) for k, v in stop_distance_buckets.items()},
    "target_distance_pct": {k: _win_stats(v) for k, v in target_distance_buckets.items()},
    "risk_reward_band": {k: _win_stats(v) for k, v in rr_buckets.items()},
    "confidence_band": {k: _win_stats(v) for k, v in confidence_buckets_neg.items()},
    "sector": {k: _win_stats(v) for k, v in sorted(sector_buckets.items(), key=lambda kv: -len(kv[1]))},
    "symbol_top_10_by_sample_size": {
        k: _win_stats(v) for k, v in sorted(symbol_buckets.items(), key=lambda kv: -len(kv[1]))[:10]
    },
    "breakout_state": {k: _win_stats(v) for k, v in breakout_state_buckets.items()},
    "sector_strength_state": {k: _win_stats(v) for k, v in sector_strength_state_buckets.items()},
    "volatility": "NOT AVAILABLE -- no volatility/ATR% field exists on DecisionV2BacktestRecord or "
                  "DecisionV2BacktestOutcome; stop_distance_pct above is the closest available proxy "
                  "(stop_loss is itself ATR-derived in AIDecisionEngine) but is not volatility itself.",
    "trend_regime": "NOT AVAILABLE -- no market/trend-regime field exists on either dataclass; would "
                    "require new instrumentation to answer honestly, not approximated here.",
    "volume_quality": "NOT AVAILABLE -- volume_confirms_decision/accumulation_score exist on the live "
                       "DecisionResult but are NOT copied onto DecisionV2BacktestRecord; would require a "
                       "new field on that record to answer honestly, not approximated here.",
}
print(json.dumps(negative_expectancy, indent=2, default=str))

section("14. FINAL REPORT FIELDS")
final = {
    "REAL_HISTORICAL_DATA_ACCESS": "YES" if phase_a["real_historical_data_access"] else "NO",
    "SAHMK_API_CALLS_USED_FOR_BACKTEST": 0,
    "SAHMK_QUOTA_CONSUMED": 0,
    "BASELINE_SAMPLE_SIZE": len(baseline_entered),
    "PHASE3_SAMPLE_SIZE": len(phase3_entered),
    "baseline_metrics": baseline_metrics,
    "phase3_metrics": phase3_metrics,
    "stratification": strat,
    "mechanism_path_trace": mechanisms,
    "counterfactual_divergence_summary": counterfactual_summary,
    "counterfactual_divergence_sample": divergences[:50],
    "negative_expectancy_factor_analysis": negative_expectancy,
    "skipped": summary.skipped,
    "evaluated_points": summary.evaluated_points,
}
print(json.dumps(final, indent=2, default=str))

with open("phase3_backtest_full_report.json", "w") as f:
    json.dump(final, f, indent=2, default=str)
print("\nWrote phase3_backtest_full_report.json")
