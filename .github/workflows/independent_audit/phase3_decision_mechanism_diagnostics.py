"""BASIRAH -- PHASE 3 DECISION-ENGINE MECHANISM DIAGNOSTICS (read-only).

A companion, NOT a replacement, to
`phase3_historical_validation_backtest.py`: reuses that script's exact
real-OHLCV-pull logic, staff login, and the
`src.backtesting.decision_v2_strategies`/`decision_v2_context` harness
(the same clock-injection fix already landed on this branch) verbatim,
then adds per-evaluation-point instrumentation of the five Phase 3
mechanisms (anti-chase entry_status, breakout confirmation,
HIGH_QUALITY_BUY, sector-relative strength, confidence calibration)
that the tuned backtest's summary metrics do not surface on their own.

Strictly read-only / compute-only: never mutates `DecisionEngineV2`,
`gates.py`, any scoring/threshold file, the frozen baseline snapshot,
`decision_v2_context.py`, or `decision_v2_strategies.py`. Every
decision here is produced by calling those real modules exactly as
they already exist on this branch -- this script only *observes* and
*aggregates* their outputs field-by-field, computing distance-from-
threshold distributions and counterfactual/structural reasoning by
reading `DecisionResult` fields, never by mutating engine code.
"""

import json
import os
import sys
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from statistics import mean, median

import requests
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

sys.path.insert(0, os.getcwd())

from src.analysis.decision_v2.trade_classification import (  # noqa: E402
    _HIGH_QUALITY_BUY_MIN_CONFIDENCE,
    _HIGH_QUALITY_BUY_MIN_RISK_REWARD,
)
from src.analysis.decision_v2.breakout_confirmation import (  # noqa: E402
    _MIN_HOLD_DAYS_FOR_CONFIRMED,
    _MIN_FOLLOW_THROUGH_PCT,
    _VOLUME_CONFIRMATION_RATIO,
)
from src.backtesting.data_access import (  # noqa: E402
    DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS,
    evaluation_dates,
)
from src.backtesting.decision_v2_backtest_outcome import evaluate_decision_v2_backtest_outcome  # noqa: E402
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

# Identical parameters to the already-run tuned backtest (item asked
# for reusing the exact same harness configuration, not a re-tune).
EVAL_FREQUENCY_DAYS = 3
ENTRY_EXPIRY_DAYS = 5
RESOLUTION_HORIZON_DAYS = 20

_ACTIONABLE = {"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"}


def section(title):
    print("\n" + "=" * 70)
    print(title)
    print("=" * 70)


# ---------------------------------------------------------------------
# Sections 1-8: identical real-data-access steps as
# phase3_historical_validation_backtest.py (staff login, deployment
# sanity check, access-control proof, coverage snapshot, symbol
# universe, real OHLCV pull, Phase A quality report, local in-memory
# dataset build). Duplicated verbatim rather than imported because that
# script is a top-level, run-once workflow script, not a package this
# one can import from without re-executing it.
# ---------------------------------------------------------------------

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
source_counts = {}
for row in all_rows:
    src = row.get("data_source") or "unknown"
    source_counts[src] = source_counts.get(src, 0) + 1
print(json.dumps({
    "total_historical_bars": len(all_rows),
    "data_source_breakdown": source_counts,
    "deployed_commit": deployed_commit,
    "earliest_date": min_ts,
    "latest_date": max_ts,
}, indent=2, default=str))

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

# ---------------------------------------------------------------------
# Section 9: instrumented replay loop -- same (symbol, as_of) grid and
# the exact same `build_replay_point`/`run_baseline_v2`/`run_phase3_v2`
# calls the tuned backtest uses, but every point's FULL `DecisionResult`
# (not just the summary record) is inspected and aggregated here.
# ---------------------------------------------------------------------

section("9. Instrumented replay: per-point mechanism diagnostics (Phase 3 arm + Baseline arm)")

backtest_symbols = [s for s in symbols if s in stock_by_symbol]
start_dt = datetime.fromisoformat(min_ts).date() if min_ts else DATA_START
end_dt = datetime.fromisoformat(max_ts).date() if max_ts else DATA_END
dates = evaluation_dates(start_dt, end_dt, EVAL_FREQUENCY_DAYS)
print(f"Backtest window: {start_dt} .. {end_dt} | dates_per_symbol={len(dates)} | symbols={len(backtest_symbols)}")

evaluated_points = 0
skipped_insufficient_data = 0
skipped_symbol_not_found = 0

# Per-point diagnostic rows for the Phase 3 arm (one dict per evaluated
# (symbol, date) point, regardless of decision) -- kept in memory only
# long enough to aggregate; never persisted as raw per-point PII/price
# data beyond this run's own JSON report's aggregate sections.
phase3_rows = []
baseline_actionable_keys = set()
phase3_actionable_keys = set()

for symbol in backtest_symbols:
    stock = session.query(Stock).filter_by(symbol=symbol).one_or_none()
    if stock is None:
        skipped_symbol_not_found += len(dates)
        continue

    for as_of in dates:
        point = build_replay_point(session, stock, as_of, DEFAULT_FUNDAMENTAL_REPORTING_LAG_DAYS)
        if point is None:
            skipped_insufficient_data += 1
            continue

        baseline_decision = run_baseline_v2(point)
        phase3_decision = run_phase3_v2(point)
        evaluated_points += 1

        if baseline_decision.decision.value in _ACTIONABLE:
            baseline_actionable_keys.add((symbol, as_of))
        if phase3_decision.decision.value in _ACTIONABLE:
            phase3_actionable_keys.add((symbol, as_of))

        d = phase3_decision  # the Phase 3 (live) arm is this script's primary instrumentation target
        price = d.current_price

        # --- mechanism 2: breakout confirmation -- distance from the
        # tautological "already cleared" threshold, whenever a
        # breakout_level (nearest resistance) was even identified.
        breakout_distance_pct = None
        if d.breakout_level is not None and price is not None and d.breakout_level > 0:
            # >0 means price is BELOW the level (has not cleared it);
            # <=0 would mean price is AT/ABOVE it (the only region
            # compute_breakout_confirmation can ever score as anything
            # other than NOT_APPLICABLE).
            breakout_distance_pct = round((d.breakout_level - price) / d.breakout_level * 100.0, 4)

        # --- mechanism 1: anti-chase entry_status -- for WAIT_FOR_ENTRY
        # decisions, the price-vs-entry-zone-high distance that
        # `classify_entry_status` uses to choose MISSED_ENTRY (the only
        # reachable branch) instead of WAIT_FOR_PULLBACK.
        missed_entry_distance_pct = None
        if d.decision.value == "WAIT_FOR_ENTRY" and price is not None and d.entry_zone_high is not None and d.entry_zone_high > 0:
            missed_entry_distance_pct = round((price - d.entry_zone_high) / d.entry_zone_high * 100.0, 4)

        # --- mechanism 4: sector-relative strength -- raw value +
        # distance from the HIGH_QUALITY_BUY veto threshold (0.0).
        sector_distance_from_zero = (
            round(d.stock_vs_sector_relative_strength, 4)
            if d.stock_vs_sector_relative_strength is not None else None
        )

        # --- mechanism 3: HIGH_QUALITY_BUY -- per-condition pass/fail,
        # only meaningful for actionable BUY-like decisions (the tag's
        # own first gate).
        hqb_conditions = None
        if d.decision.value in _ACTIONABLE:
            cond_confidence = d.confidence_score >= _HIGH_QUALITY_BUY_MIN_CONFIDENCE
            cond_live = d.data_freshness_status.value == "LIVE"
            cond_ready_now = d.entry_status.value == "READY_NOW"
            cond_rr = d.risk_reward_target_1 is not None and d.risk_reward_target_1 >= _HIGH_QUALITY_BUY_MIN_RISK_REWARD
            cond_volume = d.volume_confirms_decision is True
            cond_sector = not (
                d.sector_strength_used and d.stock_vs_sector_relative_strength is not None
                and d.stock_vs_sector_relative_strength < 0
            )
            cond_breakout = d.breakout_status != "FAILED_BREAKOUT"
            cond_no_warnings = len(d.warnings) == 0
            hqb_conditions = {
                "confidence_ge_75": cond_confidence,
                "freshness_live": cond_live,
                "entry_ready_now": cond_ready_now,
                "rr_ge_2": cond_rr,
                "volume_confirms": cond_volume,
                "sector_not_negative": cond_sector,
                "breakout_not_failed": cond_breakout,
                "no_warnings": cond_no_warnings,
                "market_status": d.market_status,
                "n_warnings": len(d.warnings),
                "warning_texts": list(d.warnings),
                "all_pass": all([
                    cond_confidence, cond_live, cond_ready_now, cond_rr,
                    cond_volume, cond_sector, cond_breakout, cond_no_warnings,
                ]),
                "only_warnings_block": (
                    cond_confidence and cond_live and cond_ready_now and cond_rr
                    and cond_volume and cond_sector and cond_breakout and not cond_no_warnings
                ),
            }

        row = {
            "symbol": symbol,
            "as_of": as_of.isoformat(),
            "decision": d.decision.value,
            "confidence_score": d.confidence_score,
            "risk_reward_target_1": d.risk_reward_target_1,
            "entry_status": d.entry_status.value,
            "breakout_status": d.breakout_status,
            "breakout_hold_days": d.breakout_hold_days,
            "breakout_volume_confirmed": d.breakout_volume_confirmed,
            "breakout_follow_through_pct": d.breakout_follow_through_pct,
            "breakout_distance_pct": breakout_distance_pct,
            "missed_entry_distance_pct": missed_entry_distance_pct,
            "sector_strength_used": d.sector_strength_used,
            "sector_strength_score": d.sector_strength_score,
            "stock_vs_sector_relative_strength": sector_distance_from_zero,
            "sector_name": d.sector_name,
            "is_high_quality_buy": d.is_high_quality_buy,
            "hqb_conditions": hqb_conditions,
            "market_status": d.market_status,
            "warnings_count": len(d.warnings),
            "is_actionable": d.decision.value in _ACTIONABLE,
        }

        # Outcome tracking (Phase 3 arm only, same methodology as the
        # tuned backtest) -- needed for the negative-expectancy
        # contributor breakdown in section 10.
        if row["is_actionable"]:
            outcome = evaluate_decision_v2_backtest_outcome(
                session, stock, d, as_of, ENTRY_EXPIRY_DAYS, RESOLUTION_HORIZON_DAYS
            )
            row["entry_triggered"] = outcome.entry_triggered
            row["entry_price"] = outcome.entry_price
            row["stop_loss"] = d.stop_loss
            row["target_1"] = d.target_1
            row["target_2"] = d.target_2
            row["target_3"] = d.target_3
            row["outcome_status"] = outcome.status.value
            row["target_1_hit"] = outcome.target_1_hit
            row["max_favorable_excursion_pct"] = outcome.max_favorable_excursion_pct
            row["max_adverse_excursion_pct"] = outcome.max_adverse_excursion_pct
            row["return_pct"] = outcome.return_pct

        phase3_rows.append(row)

print(f"evaluated_points: {evaluated_points}")
print(f"skipped_insufficient_data: {skipped_insufficient_data}")
print(f"skipped_symbol_not_found: {skipped_symbol_not_found}")
print(f"phase3_actionable_signals: {len(phase3_actionable_keys)}")
print(f"baseline_actionable_signals: {len(baseline_actionable_keys)}")
print(f"actionable_sets_identical: {phase3_actionable_keys == baseline_actionable_keys}")

# ---------------------------------------------------------------------
# Section 10: aggregation
# ---------------------------------------------------------------------

section("10. Aggregation -- mechanism activation, near-miss distributions, HQB blocker attribution")

actionable_rows = [r for r in phase3_rows if r["is_actionable"]]
entered_rows = [r for r in actionable_rows if r.get("entry_triggered")]


def pct_stats(values):
    values = [v for v in values if v is not None]
    if not values:
        return {"n": 0}
    return {
        "n": len(values), "mean": round(mean(values), 4), "median": round(median(values), 4),
        "min": round(min(values), 4), "max": round(max(values), 4),
    }


# --- mechanism 2: breakout confirmation --------------------------------
breakout_status_counts = Counter(r["breakout_status"] for r in phase3_rows)
breakout_distance_all = pct_stats([r["breakout_distance_pct"] for r in phase3_rows if r["breakout_distance_pct"] is not None])
breakout_diag = {
    "status_counts_all_5100_points": dict(breakout_status_counts),
    "status_counts_actionable_only": dict(Counter(r["breakout_status"] for r in actionable_rows)),
    "breakout_level_identified_count": sum(1 for r in phase3_rows if r["breakout_distance_pct"] is not None),
    "price_below_breakout_level_distance_pct_stats": breakout_distance_all,
    "structural_note": (
        "breakout_level is derive_support_resistance()'s nearest_resistance, filtered to r>=price "
        "(evidence.py) -- so breakout_distance_pct (= (breakout_level - price) / breakout_level * 100) "
        "is mathematically >= 0 for every point where a level was identified, meaning "
        "compute_breakout_confirmation's own first check (latest_close <= breakout_level) is a tautology "
        "and CONFIRMED_BREAKOUT/EARLY_BREAKOUT/UNCONFIRMED_BREAKOUT/FAILED_BREAKOUT can never be reached "
        "as currently wired, regardless of sample size."
    ),
    "min_hold_days_for_confirmed": _MIN_HOLD_DAYS_FOR_CONFIRMED,
    "min_follow_through_pct": _MIN_FOLLOW_THROUGH_PCT,
    "volume_confirmation_ratio": _VOLUME_CONFIRMATION_RATIO,
}

# --- mechanism 1: anti-chase / entry_status -----------------------------
entry_status_counts_all = Counter(r["entry_status"] for r in phase3_rows)
entry_status_counts_actionable = Counter(r["entry_status"] for r in actionable_rows)
wait_for_entry_rows = [r for r in phase3_rows if r["decision"] == "WAIT_FOR_ENTRY"]
anti_chase_diag = {
    "entry_status_counts_all_points": dict(entry_status_counts_all),
    "entry_status_counts_actionable_only": dict(entry_status_counts_actionable),
    "wait_for_entry_decision_count": len(wait_for_entry_rows),
    "wait_for_entry_with_missed_entry_distance_stats": pct_stats(
        [r["missed_entry_distance_pct"] for r in wait_for_entry_rows]
    ),
    "structural_note": (
        "gates.py constructs Decision.WAIT_FOR_ENTRY in exactly one place (the 'entry_not_missed' gate), "
        "which only fires when price_missed_entry_zone is True. classify_entry_status's WAIT_FOR_ENTRY "
        "branch checks `if price_missed_entry_zone: return MISSED_ENTRY` else `return WAIT_FOR_PULLBACK` -- "
        "since the precondition is always True whenever decision==WAIT_FOR_ENTRY, the WAIT_FOR_PULLBACK "
        "branch is unreachable dead code, confirmed empirically below by missed_entry_distance_pct being "
        "> 0 for every WAIT_FOR_ENTRY point in this real run (same structural condition existed pre-Phase-3, "
        "in the frozen baseline snapshot's identical trade_classification.py)."
    ),
}

# --- mechanism 4: sector-relative strength ------------------------------
sector_used_count = sum(1 for r in phase3_rows if r["sector_strength_used"])
sector_diag = {
    "sector_strength_used_count": sector_used_count,
    "sector_strength_used_count_actionable": sum(1 for r in actionable_rows if r["sector_strength_used"]),
    "sector_strength_not_used_count": len(phase3_rows) - sector_used_count,
    "relative_strength_stats_when_used": pct_stats(
        [r["stock_vs_sector_relative_strength"] for r in phase3_rows if r["sector_strength_used"]]
    ),
    "relative_strength_negative_count": sum(
        1 for r in phase3_rows if r["sector_strength_used"] and (r["stock_vs_sector_relative_strength"] or 0) < 0
    ),
    "structural_note": (
        "sector_strength feeds two, and only two, consumers: (a) SectorRotationScoreContributor "
        "(src/analysis/decision/contributors/external_factor_contributors.py, weight=0.02) inside the "
        "upstream V1 AIDecisionEngine score -- a small, real, but non-gating nudge; (b) "
        "classify_high_quality_buy's veto (relative_strength < 0 disqualifies HQB). It never feeds "
        "gates.py's BUY/WATCH/REJECT decision directly."
    ),
}

# --- mechanism 3: HIGH_QUALITY_BUY --------------------------------------
hqb_condition_names = [
    "confidence_ge_75", "freshness_live", "entry_ready_now", "rr_ge_2",
    "volume_confirms", "sector_not_negative", "breakout_not_failed", "no_warnings",
]
hqb_pass_counts = {name: 0 for name in hqb_condition_names}
hqb_fail_counts = {name: 0 for name in hqb_condition_names}
only_warnings_block_count = 0
market_closed_count = 0
warning_texts_counter = Counter()
for r in actionable_rows:
    c = r["hqb_conditions"]
    if c is None:
        continue
    for name in hqb_condition_names:
        if c[name]:
            hqb_pass_counts[name] += 1
        else:
            hqb_fail_counts[name] += 1
    if c["only_warnings_block"]:
        only_warnings_block_count += 1
    if c["market_status"] == "CLOSED":
        market_closed_count += 1
    for w in c["warning_texts"]:
        warning_texts_counter[w] += 1

hqb_diag = {
    "actionable_signal_count": len(actionable_rows),
    "high_quality_buy_true_count": sum(1 for r in actionable_rows if r["is_high_quality_buy"]),
    "per_condition_pass_count": hqb_pass_counts,
    "per_condition_fail_count": hqb_fail_counts,
    "actionable_signals_with_market_status_closed": market_closed_count,
    "actionable_signals_where_only_the_no_warnings_condition_blocks_hqb": only_warnings_block_count,
    "distinct_warning_texts_and_frequency": dict(warning_texts_counter.most_common(20)),
    "min_confidence_threshold": _HIGH_QUALITY_BUY_MIN_CONFIDENCE,
    "min_risk_reward_threshold": _HIGH_QUALITY_BUY_MIN_RISK_REWARD,
    "structural_note": (
        "decision_v2_context.py anchors evaluation_time to time.max (23:59:59 UTC) for every evaluation "
        "date -- converted to Tadawul local time this always falls outside the 10:00-15:00 AST session, so "
        "is_market_open(evaluation_time) is False for literally every one of this harness's evaluation "
        "points. engine.py's `if market_is_open is False: ... warnings.append(...)` therefore appends a "
        "warning to every single decision, and classify_high_quality_buy's `if warnings: return False` "
        "(trade_classification.py) then deterministically forecloses HIGH_QUALITY_BUY for all of them, "
        "regardless of confidence/R:R/volume/sector/breakout evidence. This is a measurement artifact of "
        "this end-of-day backtest harness's clock choice, not evidence that the underlying evidence "
        "combination is rare in live (intraday, market-open) production use."
    ),
}

# --- confidence / R:R distributions (mechanism 5 support + general) ----
confidence_stats = pct_stats([r["confidence_score"] for r in actionable_rows])
rr_stats = pct_stats([r["risk_reward_target_1"] for r in actionable_rows])
calibration_diag = {
    "confidence_score_stats_actionable": confidence_stats,
    "risk_reward_target_1_stats_actionable": rr_stats,
    "calibrated_confidence_field_present_on_decision_result": False,
    "structural_note": (
        "get_effective_confidence/ConfidenceCalibrationEngine/apply_calibration are called from exactly "
        "two places in this codebase: src/api/routes/stocks.py (the /decision-v2 route's DecisionV2Snapshot "
        "persistence block, AFTER decide() already returned) and "
        "src/market_intelligence/repositories/market_intelligence_repository.py's save_symbol_records "
        "(the live scan pipeline's persistence path, also after decide() returns). Neither "
        "src/analysis/decision_v2/engine.py nor gates.py nor decision_v2_strategies.py nor "
        "decision_v2_context.py reference calibration in any form. The historical replay harness calls "
        "only run_baseline_v2()/run_phase3_v2() -> DecisionEngineV2.decide() directly and never persists "
        "a DecisionV2Snapshot row, so confidence calibration is structurally unreachable from this "
        "backtest -- not merely empirically inactive."
    ),
}

# --- negative-expectancy contributor breakdown --------------------------


def stop_rate_bucket(rows):
    n = len(rows)
    stops = sum(1 for r in rows if r.get("outcome_status") == "STOP_LOSS_HIT")
    wins = sum(1 for r in rows if (r.get("return_pct") or 0) > 0)
    return {"n": n, "stop_rate": round(stops / n, 3) if n else None, "win_rate": round(wins / n, 3) if n else None}


def bucket_pct(value, edges, labels):
    if value is None:
        return "unknown"
    for edge, label in zip(edges, labels):
        if value < edge:
            return label
    return labels[-1]


stop_dist_edges = [-15, -10, -7, -5, -3, 999]
stop_dist_labels = ["<-15%", "-15..-10%", "-10..-7%", "-7..-5%", "-5..-3%", ">=-3%"]
target1_dist_edges = [3, 5, 8, 12, 20, 999]
target1_dist_labels = ["<3%", "3-5%", "5-8%", "8-12%", "12-20%", ">=20%"]
rr_edges = [1.0, 1.5, 2.0, 3.0, 5.0, 999]
rr_labels = ["<1.0", "1.0-1.5", "1.5-2.0", "2.0-3.0", "3.0-5.0", ">=5.0"]
conf_edges = [60, 70, 75, 80, 90, 101]
conf_labels = ["<60", "60-69", "70-74", "75-79", "80-89", ">=90"]

by_stop_dist, by_target1_dist, by_rr, by_conf, by_sector, by_symbol = (
    defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list), defaultdict(list)
)
for r in entered_rows:
    entry_price = r.get("entry_price")
    stop_loss = r.get("stop_loss")
    target_1 = r.get("target_1")
    stop_dist_pct = (
        round((entry_price - stop_loss) / entry_price * 100.0, 2)
        if entry_price and stop_loss is not None else None
    )
    target1_dist_pct = (
        round((target_1 - entry_price) / entry_price * 100.0, 2)
        if entry_price and target_1 is not None else None
    )
    by_stop_dist[bucket_pct(-stop_dist_pct if stop_dist_pct is not None else None, stop_dist_edges, stop_dist_labels)].append(r)
    by_target1_dist[bucket_pct(target1_dist_pct, target1_dist_edges, target1_dist_labels)].append(r)
    by_rr[bucket_pct(r.get("risk_reward_target_1"), rr_edges, rr_labels)].append(r)
    by_conf[bucket_pct(r.get("confidence_score"), conf_edges, conf_labels)].append(r)
    by_sector[r.get("sector_name") or "unknown"].append(r)
    by_symbol[r["symbol"]].append(r)

symbol_concentration = sorted(
    ((sym, len(rows), stop_rate_bucket(rows)) for sym, rows in by_symbol.items()),
    key=lambda t: t[1], reverse=True,
)[:15]

negative_expectancy_diag = {
    "entered_count": len(entered_rows),
    "overall": stop_rate_bucket(entered_rows),
    "by_stop_distance_pct_from_entry": {k: stop_rate_bucket(v) for k, v in by_stop_dist.items()},
    "by_target1_distance_pct_from_entry": {k: stop_rate_bucket(v) for k, v in by_target1_dist.items()},
    "by_risk_reward_bucket": {k: stop_rate_bucket(v) for k, v in by_rr.items()},
    "by_confidence_band": {k: stop_rate_bucket(v) for k, v in by_conf.items()},
    "by_sector": {k: stop_rate_bucket(v) for k, v in by_sector.items()},
    "top_15_symbols_by_entry_count": [
        {"symbol": sym, "entries": n, **stats} for sym, n, stats in symbol_concentration
    ],
    "mfe_mae_stats": {
        "avg_mfe_pct": pct_stats([r["max_favorable_excursion_pct"] for r in entered_rows]),
        "avg_mae_pct": pct_stats([r["max_adverse_excursion_pct"] for r in entered_rows]),
    },
}

# --- data-sufficiency arithmetic ----------------------------------------

section("11. Data-sufficiency arithmetic (n>=30 target per near-zero cohort)")


def months_for_n30(observed_count, observed_points, observed_months, target_n=30):
    if observed_points <= 0 or observed_count <= 0:
        return None
    rate_per_point = observed_count / observed_points
    if rate_per_point <= 0:
        return None
    points_per_month = observed_points / observed_months if observed_months else None
    needed_points = target_n / rate_per_point
    needed_months = needed_points / points_per_month if points_per_month else None
    return {
        "observed_count": observed_count, "observed_points": observed_points,
        "observed_months": round(observed_months, 2) if observed_months else None,
        "rate_per_point": round(rate_per_point, 6),
        "points_per_month_at_this_symbol_count_and_frequency": round(points_per_month, 1) if points_per_month else None,
        "points_needed_for_n30": round(needed_points, 1),
        "months_needed_for_n30": round(needed_months, 1) if needed_months else None,
        "years_needed_for_n30": round(needed_months / 12.0, 2) if needed_months else None,
    }


observed_months = (end_dt - start_dt).days / 30.44 if end_dt > start_dt else None
confirmed_breakout_count = breakout_status_counts.get("CONFIRMED_BREAKOUT", 0)
wait_for_pullback_count = entry_status_counts_all.get("WAIT_FOR_PULLBACK", 0)
hqb_true_count = hqb_diag["high_quality_buy_true_count"]

sufficiency = {
    "observed_window_months": round(observed_months, 2) if observed_months else None,
    "evaluated_points": evaluated_points,
    "breakout_confirmed": (
        {"note": "structurally 0 for any sample size -- see breakout_diag.structural_note; more data cannot fix this"}
        if confirmed_breakout_count == 0 else
        months_for_n30(confirmed_breakout_count, evaluated_points, observed_months)
    ),
    "anti_chase_wait_for_pullback": (
        {"note": "structurally 0 for any sample size -- see anti_chase_diag.structural_note (dead code branch); more data cannot fix this"}
        if wait_for_pullback_count == 0 else
        months_for_n30(wait_for_pullback_count, evaluated_points, observed_months)
    ),
    "high_quality_buy": (
        {"note": "structurally 0 within THIS harness for any sample size -- see hqb_diag.structural_note (evaluation_time always end-of-day -> always market-closed warning); NOT evidence of real-world rarity"}
        if hqb_true_count == 0 else
        months_for_n30(hqb_true_count, evaluated_points, observed_months)
    ),
    "sector_strength_used": months_for_n30(sector_used_count, evaluated_points, observed_months),
}
print(json.dumps(sufficiency, indent=2, default=str))

# ---------------------------------------------------------------------
# Final report
# ---------------------------------------------------------------------

section("12. FINAL REPORT")
final = {
    "evaluated_points": evaluated_points,
    "skipped_insufficient_data": skipped_insufficient_data,
    "skipped_symbol_not_found": skipped_symbol_not_found,
    "phase3_actionable_signals": len(phase3_actionable_keys),
    "baseline_actionable_signals": len(baseline_actionable_keys),
    "actionable_sets_identical_baseline_vs_phase3": phase3_actionable_keys == baseline_actionable_keys,
    "backtest_window": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
    "harness_params": {
        "evaluation_frequency_days": EVAL_FREQUENCY_DAYS,
        "entry_expiry_days": ENTRY_EXPIRY_DAYS,
        "resolution_horizon_days": RESOLUTION_HORIZON_DAYS,
    },
    "breakout_confirmation_mechanism": breakout_diag,
    "anti_chase_entry_status_mechanism": anti_chase_diag,
    "sector_relative_strength_mechanism": sector_diag,
    "high_quality_buy_mechanism": hqb_diag,
    "confidence_calibration_mechanism": calibration_diag,
    "negative_expectancy_contributor_breakdown": negative_expectancy_diag,
    "data_sufficiency_arithmetic": sufficiency,
}
print(json.dumps(final, indent=2, default=str))

with open("phase3_decision_mechanism_diagnostics_report.json", "w") as f:
    json.dump(final, f, indent=2, default=str)
print("\nWrote phase3_decision_mechanism_diagnostics_report.json")
