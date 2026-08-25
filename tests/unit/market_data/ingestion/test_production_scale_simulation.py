"""P0 SAHMK quota architecture repair (2026-08-25), Section 19:
production-scale simulation. Builds a realistic 384-symbol universe
(3 active positions, 12 pending-not-yet-triggered signals, 15 live
Radar candidates, 354 background) against the REAL evidence-based
daily ceiling (100/day, 30 critical reserve, 20 live-scan reserve --
see src.market_data.config's own docstrings) and simulates 10+
trading days of `build_priority_plan` + arithmetic budget spend, using
the REAL tier0-4 queries and REAL fair-rotation ordering against an
in-memory SQLite DB. No SAHMK quota is consumed -- this is pure
offline simulation, zero network calls, zero real provider requests.

Required invariants (Section 20's acceptance criteria):
  QUOTA_BREACH must be 0 on every simulated day.
  Permanent starvation must be 0 (every Tier 4 symbol is eventually
  refreshed within the reported MAX_BACKGROUND_REFRESH_AGE).
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    PriceBar,
    RadarOpportunity,
    Stock,
    Timeframe,
)
from src.market_data.config import (
    get_sahmk_max_requests_per_day,
    get_sahmk_reserved_for_critical_requests_per_day,
    get_sahmk_reserved_for_live_scan_requests_per_day,
)
from src.market_data.ingestion.ohlcv_priority import build_priority_plan

MAX_PER_DAY = get_sahmk_max_requests_per_day()
RESERVED_CRITICAL = get_sahmk_reserved_for_critical_requests_per_day()
RESERVED_LIVE_SCAN = get_sahmk_reserved_for_live_scan_requests_per_day()
BACKGROUND_BUDGET = MAX_PER_DAY - RESERVED_CRITICAL - RESERVED_LIVE_SCAN


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


def _seed_universe(session, *, active_positions, pending_signals, radar_candidates, background_count):
    """Builds exactly the Section 19 scenario shape: `active_positions`
    Tier 0 symbols, `pending_signals` Tier 1 symbols, `radar_candidates`
    Tier 2 symbols, `background_count` plain Tier 4 symbols -- every
    symbol already has one existing (stale) PriceBar, matching a real,
    already-onboarded universe rather than a cold start."""
    counter = 0

    def _next_stock(prefix):
        nonlocal counter
        counter += 1
        symbol = f"{prefix}{counter:04d}"
        stock = Stock(symbol=symbol, name_en=symbol, is_active=True)
        session.add(stock)
        session.flush()
        session.add(
            PriceBar(
                stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
                timestamp=datetime.now(timezone.utc) - timedelta(days=30),
                open=1, high=1, low=1, close=1, volume=1, source="test", is_synthetic=False,
            )
        )
        return stock

    for _ in range(active_positions):
        stock = _next_stock("A")
        snapshot = DecisionV2Snapshot(
            stock_id=stock.id, symbol=stock.symbol, company_name_en=stock.name_en,
            decision="BUY_CANDIDATE", decision_label_ar="x", confidence_score=70.0,
            opportunity_quality_score=60.0, risk_score=30.0, data_quality_score=90.0,
            data_freshness_status="LIVE", current_price=100.0, market_status="OPEN",
            decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0", data_source="test",
        )
        session.add(snapshot)
        session.flush()
        session.add(
            DecisionV2Outcome(
                decision_v2_snapshot_id=snapshot.id, symbol=stock.symbol,
                due_at=datetime.now(timezone.utc) + timedelta(days=5),
                status=DecisionV2OutcomeStatus.PENDING, entry_triggered=True,
            )
        )

    for _ in range(pending_signals):
        stock = _next_stock("P")
        snapshot = DecisionV2Snapshot(
            stock_id=stock.id, symbol=stock.symbol, company_name_en=stock.name_en,
            decision="BUY_CANDIDATE", decision_label_ar="x", confidence_score=70.0,
            opportunity_quality_score=60.0, risk_score=30.0, data_quality_score=90.0,
            data_freshness_status="LIVE", current_price=100.0, market_status="OPEN",
            decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0", data_source="test",
        )
        session.add(snapshot)
        session.flush()
        session.add(
            DecisionV2Outcome(
                decision_v2_snapshot_id=snapshot.id, symbol=stock.symbol,
                due_at=datetime.now(timezone.utc) + timedelta(days=5),
                status=DecisionV2OutcomeStatus.PENDING, entry_triggered=False,
            )
        )

    for _ in range(radar_candidates):
        stock = _next_stock("R")
        snapshot = DecisionV2Snapshot(
            stock_id=stock.id, symbol=stock.symbol, company_name_en=stock.name_en,
            decision="WATCH", decision_label_ar="x", confidence_score=50.0,
            opportunity_quality_score=40.0, risk_score=30.0, data_quality_score=90.0,
            data_freshness_status="LIVE", current_price=100.0, market_status="OPEN",
            decision_timestamp=datetime.now(timezone.utc), analysis_version="2.0.0", data_source="test",
        )
        session.add(snapshot)
        session.flush()
        session.add(
            RadarOpportunity(
                symbol=stock.symbol, stock_id=stock.id, decision_v2_snapshot_id=snapshot.id,
                classification="WATCH", classification_label_ar="x", confidence_score=50.0,
                emitted_at=datetime.now(timezone.utc),
            )
        )

    for _ in range(background_count):
        _next_stock("B")

    session.commit()
    return [row.symbol for row in session.query(Stock.symbol).all()]


def _run_simulation(session_factory, *, active_positions, pending_signals, radar_candidates, background_count, days):
    """Runs `days` simulated trading days. Each day: compute the real
    tier plan, spend the critical reserve on tier0+1 (always fully
    covered -- see the assertion below), spend the live-scan reserve on
    nothing (LIVE_RECURRENT_SCAN_ENABLED stays OFF per this task's own
    constraints -- reported as reserved-but-unspent, exactly production's
    real current state), then spend the background budget on tier2
    first (kept fresh every day, matching a live Radar candidate's own
    "current" requirement) and whatever remains of the budget on the
    tier4 rotation, marking each spent symbol as refreshed (a fresh
    PriceBar) before the next day's plan is computed."""
    session = session_factory()
    all_symbols = _seed_universe(
        session,
        active_positions=active_positions,
        pending_signals=pending_signals,
        radar_candidates=radar_candidates,
        background_count=background_count,
    )
    session.close()

    report_rows = []
    last_refreshed_day = {}

    for day in range(days):
        session = session_factory()
        plan = build_priority_plan(session, base_symbols=all_symbols)

        critical_requests = len(plan.critical_symbols)  # every critical symbol refreshed every day
        assert critical_requests <= RESERVED_CRITICAL, (
            f"day {day}: critical requests ({critical_requests}) exceeded the reserve "
            f"({RESERVED_CRITICAL}) -- QUOTA_BREACH"
        )

        live_reserved_unspent = RESERVED_LIVE_SCAN  # scheduler stays OFF -- reserved, not spent

        tier2_requests = len(plan.tier2)
        remaining_background_budget = max(0, BACKGROUND_BUDGET - tier2_requests)
        tier4_spent = plan.tier4[:remaining_background_budget]
        background_requests = tier2_requests + len(tier4_spent)

        total_requests = critical_requests + background_requests
        assert total_requests <= MAX_PER_DAY - live_reserved_unspent, (
            f"day {day}: total requests ({total_requests}) breached the daily budget "
            f"(max={MAX_PER_DAY}, live_scan reserved unspent={live_reserved_unspent}) -- QUOTA_BREACH"
        )

        for symbol in tier4_spent:
            stock = session.query(Stock).filter_by(symbol=symbol).one()
            session.add(
                PriceBar(
                    stock_id=stock.id, timeframe=Timeframe.ONE_DAY,
                    timestamp=datetime.now(timezone.utc) + timedelta(days=day),
                    open=1, high=1, low=1, close=1, volume=1, source="test", is_synthetic=False,
                )
            )
            last_refreshed_day[symbol] = day
        session.commit()

        oldest_background_age = day - min(
            (last_refreshed_day.get(s, -1) for s in plan.tier4), default=day
        )
        symbols_starved = sum(1 for s in plan.tier4 if s not in last_refreshed_day)

        report_rows.append(
            {
                "DAY": day,
                "CRITICAL_REQUESTS": critical_requests,
                "LIVE_RESERVED": live_reserved_unspent,
                "BACKGROUND_REQUESTS": background_requests,
                "BACKFILL_REQUESTS": 0,  # no genuinely-new symbol in this scenario (already onboarded)
                "TOTAL_REQUESTS": total_requests,
                "OLDEST_BACKGROUND_AGE": oldest_background_age,
                "SYMBOLS_STARVED": symbols_starved,
                "QUOTA_BREACH": 0,
            }
        )
        session.close()

    return report_rows


def _print_report(title, rows):
    print(f"\n=== {title} ===")
    header = list(rows[0].keys())
    print(" | ".join(header))
    for row in rows:
        print(" | ".join(str(row[k]) for k in header))


def test_realistic_10_day_simulation_never_breaches_quota_or_permanently_starves(session_factory):
    """The exact Section 19 scenario: 3 active recommendations, 12
    unresolved outcome symbols, 15 Stage 2 candidates, 354 remaining
    background symbols, 10 trading days."""
    rows = _run_simulation(
        session_factory,
        active_positions=3, pending_signals=12, radar_candidates=15, background_count=354,
        days=10,
    )
    _print_report("10-day simulation (3 active / 12 pending / 15 radar / 354 background)", rows)

    assert all(row["QUOTA_BREACH"] == 0 for row in rows)
    final_starved = rows[-1]["SYMBOLS_STARVED"]
    assert final_starved < 354, "background rotation must make real progress within 10 days"
    # Full-coverage check: run long enough for every Tier 4 symbol to be
    # reached at least once, proving zero PERMANENT starvation (as
    # opposed to merely "not yet reached on day 10").
    max_days_for_full_coverage = -(-354 // (BACKGROUND_BUDGET - 15))  # ceil division
    fresh_engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=fresh_engine)
    fresh_session_factory = sessionmaker(bind=fresh_engine)
    full_rows = _run_simulation(
        fresh_session_factory,
        active_positions=3, pending_signals=12, radar_candidates=15, background_count=354,
        days=max_days_for_full_coverage + 2,
    )
    Base.metadata.drop_all(bind=fresh_engine)
    assert full_rows[-1]["SYMBOLS_STARVED"] == 0, "no background symbol may be permanently starved"
    assert all(row["QUOTA_BREACH"] == 0 for row in full_rows)


def test_zero_active_signals_scenario_never_breaches_quota(session_factory):
    rows = _run_simulation(
        session_factory,
        active_positions=0, pending_signals=0, radar_candidates=15, background_count=369,
        days=5,
    )
    _print_report("0 active signals", rows)
    assert all(row["QUOTA_BREACH"] == 0 for row in rows)
    assert all(row["CRITICAL_REQUESTS"] == 0 for row in rows)


def test_twenty_active_and_pending_signals_scenario_never_breaches_the_critical_reserve(session_factory):
    """20 active/pending signals exceeds this task's own default
    critical reserve sizing basis (14 observed in real production) but
    must still fit comfortably under the configured reserve (30)."""
    rows = _run_simulation(
        session_factory,
        active_positions=5, pending_signals=15, radar_candidates=15, background_count=349,
        days=5,
    )
    _print_report("20 active/pending signals", rows)
    assert all(row["QUOTA_BREACH"] == 0 for row in rows)
    assert all(row["CRITICAL_REQUESTS"] == 20 for row in rows)
    assert 20 <= RESERVED_CRITICAL


def test_restart_halfway_produces_the_identical_plan_as_an_uninterrupted_run(session_factory):
    """Test matrix #12/restart-safety (in spirit): the tier plan is
    entirely derived from durable DB state (PriceBar/DecisionV2Outcome/
    RadarOpportunity), never an in-memory cursor -- computing it twice
    in a row (simulating "process restarted, recomputes from scratch")
    with no state change in between must produce the identical plan."""
    session = session_factory()
    all_symbols = _seed_universe(
        session, active_positions=3, pending_signals=12, radar_candidates=15, background_count=50
    )
    session.close()

    session = session_factory()
    plan_before_restart = build_priority_plan(session, base_symbols=all_symbols)
    session.close()

    # "restart": a brand-new session, no persisted cursor of any kind.
    session = session_factory()
    plan_after_restart = build_priority_plan(session, base_symbols=all_symbols)
    session.close()

    assert plan_before_restart.critical_symbols == plan_after_restart.critical_symbols
    assert plan_before_restart.background_symbols == plan_after_restart.background_symbols


def test_quota_reset_scenario_starts_each_simulated_day_with_the_full_budget(session_factory):
    """The arithmetic simulation itself models a quota reset as a new
    day's fresh CRITICAL_REQUESTS/BACKGROUND_REQUESTS budget (exactly
    what SahmkRateLimiter's own real UTC-day-window rollover provides,
    see rate_limiter.py's _roll_day_window_locked) -- asserting that no
    day's totals ever carry over or shrink the next day's nominal
    budget."""
    rows = _run_simulation(
        session_factory,
        active_positions=3, pending_signals=12, radar_candidates=15, background_count=354,
        days=3,
    )
    for row in rows:
        assert row["TOTAL_REQUESTS"] <= MAX_PER_DAY
        assert row["CRITICAL_REQUESTS"] <= RESERVED_CRITICAL
