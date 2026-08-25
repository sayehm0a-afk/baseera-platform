"""Unit tests for src.market_data.ingestion.ohlcv_priority -- the P0
SAHMK quota architecture repair's tiered refresh + fair rotation
logic. In-memory SQLite, no live DB/network."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import (
    DecisionV2Outcome,
    DecisionV2OutcomeStatus,
    DecisionV2Snapshot,
    MarketScanRun,
    MarketScanStatus,
    PriceBar,
    RadarOpportunity,
    Stock,
    Timeframe,
)
from src.market_data.ingestion.ohlcv_priority import (
    OhlcvPriorityPlan,
    build_priority_plan,
    estimate_max_background_refresh_age_days,
    tier0_active_position_symbols,
    tier1_pending_entry_symbols,
    tier2_live_radar_candidate_symbols,
    tier3_last_scan_universe_symbols,
)


@pytest.fixture
def session_factory():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    yield factory
    Base.metadata.drop_all(bind=engine)


def _stock(session, symbol, is_active=True):
    stock = Stock(symbol=symbol, name_en=symbol, is_active=is_active)
    session.add(stock)
    session.flush()
    return stock


def _snapshot(session, stock, decision="BUY_CANDIDATE", scan_run_id=None):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision=decision,
        decision_label_ar="x",
        confidence_score=70.0,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=100.0,
        market_status="OPEN",
        decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0",
        data_source="test",
        scan_run_id=scan_run_id,
    )
    session.add(snapshot)
    session.flush()
    return snapshot


def _outcome(session, snapshot, symbol, entry_triggered=False, status=DecisionV2OutcomeStatus.PENDING):
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id,
        symbol=symbol,
        due_at=datetime.now(timezone.utc) + timedelta(days=5),
        status=status,
        entry_triggered=entry_triggered,
    )
    session.add(outcome)
    session.flush()
    return outcome


def _bar(session, stock, days_ago):
    session.add(
        PriceBar(
            stock_id=stock.id,
            timeframe=Timeframe.ONE_DAY,
            timestamp=datetime.now(timezone.utc) - timedelta(days=days_ago),
            open=1, high=1, low=1, close=1, volume=1,
            source="test", is_synthetic=False,
        )
    )
    session.flush()


# --- Tier 0 / Tier 1 -----------------------------------------------------


def test_tier0_is_entry_triggered_pending_outcomes_only(session_factory):
    session = session_factory()
    triggered_stock = _stock(session, "1010")
    untriggered_stock = _stock(session, "2020")
    _outcome(session, _snapshot(session, triggered_stock), "1010", entry_triggered=True)
    _outcome(session, _snapshot(session, untriggered_stock), "2020", entry_triggered=False)
    session.commit()

    assert tier0_active_position_symbols(session) == ["1010"]
    assert tier1_pending_entry_symbols(session) == ["2020"]


def test_resolved_outcomes_are_excluded_from_tier0_and_tier1(session_factory):
    """Test matrix (Forward Test integrity, in spirit): once an
    outcome resolves (TARGET_1_HIT etc.), the symbol drops out of both
    critical tiers -- resolved history is never re-protected as if it
    were still an open signal."""
    session = session_factory()
    stock = _stock(session, "3030")
    _outcome(
        session, _snapshot(session, stock), "3030",
        entry_triggered=True, status=DecisionV2OutcomeStatus.TARGET_1_HIT,
    )
    session.commit()

    assert tier0_active_position_symbols(session) == []
    assert tier1_pending_entry_symbols(session) == []


# --- Tier 2 / Tier 3 -------------------------------------------------------


def test_tier2_is_only_non_superseded_radar_opportunities(session_factory):
    session = session_factory()
    live_stock = _stock(session, "4040")
    superseded_stock = _stock(session, "5050")
    live_snapshot = _snapshot(session, live_stock)
    superseded_snapshot = _snapshot(session, superseded_stock)
    live_opp = RadarOpportunity(
        symbol="4040", stock_id=live_stock.id, decision_v2_snapshot_id=live_snapshot.id,
        classification="BUY_CANDIDATE", classification_label_ar="x", confidence_score=70.0,
        emitted_at=datetime.now(timezone.utc),
    )
    session.add(live_opp)
    session.flush()
    superseded_opp = RadarOpportunity(
        symbol="5050", stock_id=superseded_stock.id, decision_v2_snapshot_id=superseded_snapshot.id,
        classification="BUY_CANDIDATE", classification_label_ar="x", confidence_score=70.0,
        emitted_at=datetime.now(timezone.utc), superseded_by_id=None,
    )
    session.add(superseded_opp)
    session.flush()
    superseded_opp.superseded_by_id = live_opp.id  # supersede it after both exist
    session.commit()

    assert tier2_live_radar_candidate_symbols(session) == ["4040"]


def test_tier3_is_the_most_recent_successful_scan_run_universe(session_factory):
    session = session_factory()
    old_stock = _stock(session, "6060")
    new_stock = _stock(session, "7070")
    old_run = MarketScanRun(status=MarketScanStatus.SUCCESS, symbols_requested=1)
    session.add(old_run)
    session.flush()
    _snapshot(session, old_stock, scan_run_id=old_run.id)
    new_run = MarketScanRun(status=MarketScanStatus.SUCCESS, symbols_requested=1)
    session.add(new_run)
    session.flush()
    _snapshot(session, new_stock, scan_run_id=new_run.id)
    session.commit()

    assert tier3_last_scan_universe_symbols(session) == ["7070"]


def test_tier3_ignores_failed_scan_runs(session_factory):
    session = session_factory()
    stock = _stock(session, "8080")
    failed_run = MarketScanRun(status=MarketScanStatus.FAILED, symbols_requested=1)
    session.add(failed_run)
    session.flush()
    _snapshot(session, stock, scan_run_id=failed_run.id)
    session.commit()

    assert tier3_last_scan_universe_symbols(session) == []


# --- build_priority_plan: dedup + tier precedence --------------------------


def test_plan_places_a_symbol_in_only_its_highest_tier(session_factory):
    """Test matrix #3: a symbol appearing in multiple tiers is counted
    exactly once, in its highest tier only."""
    session = session_factory()
    stock = _stock(session, "9090")
    snapshot = _snapshot(session, stock)
    _outcome(session, snapshot, "9090", entry_triggered=True)  # tier 0
    session.add(
        RadarOpportunity(
            symbol="9090", stock_id=stock.id, decision_v2_snapshot_id=snapshot.id,
            classification="BUY_CANDIDATE", classification_label_ar="x", confidence_score=70.0,
            emitted_at=datetime.now(timezone.utc),
        )
    )  # also tier 2 -- must not duplicate
    session.commit()

    plan = build_priority_plan(session, base_symbols=["9090"])

    assert plan.tier0 == ["9090"]
    assert plan.tier1 == []
    assert plan.tier2 == []  # excluded -- already claimed by tier 0
    assert plan.critical_symbols == ["9090"]
    assert plan.background_symbols == []


def test_plan_handles_zero_critical_symbols(session_factory):
    """Test matrix #4: an empty critical tier is not an error -- the
    background tier is computed normally."""
    session = session_factory()
    _stock(session, "1111")
    session.commit()

    plan = build_priority_plan(session, base_symbols=["1111"])

    assert plan.critical_symbols == []
    assert plan.background_symbols == ["1111"]


def test_plan_protects_an_inactive_stock_with_an_unresolved_outcome(session_factory):
    """Test matrix #5: a symbol dropped from the general active-Stock
    universe (base_symbols) still appears in the critical tier if it
    has an unresolved outcome -- base_symbols membership is irrelevant
    to tier 0/1 eligibility."""
    session = session_factory()
    stock = _stock(session, "2222", is_active=False)
    _outcome(session, _snapshot(session, stock), "2222", entry_triggered=False)
    session.commit()

    # base_symbols deliberately does NOT include "2222" (it's inactive).
    plan = build_priority_plan(session, base_symbols=[])

    assert "2222" in plan.critical_symbols


def test_plan_dedup_is_stable_when_base_symbols_has_duplicates(session_factory):
    session = session_factory()
    _stock(session, "3333")
    session.commit()

    plan = build_priority_plan(session, base_symbols=["3333", "3333", "3333"])

    assert plan.background_symbols == ["3333"]


# --- fair rotation (Tier 4) --------------------------------------------------


def test_never_ingested_symbols_sort_before_symbols_with_a_bar(session_factory):
    session = session_factory()
    fresh_stock = _stock(session, "4444")
    _bar(session, fresh_stock, days_ago=0)
    never_ingested_stock = _stock(session, "5555")
    session.commit()

    plan = build_priority_plan(session, base_symbols=["4444", "5555"])

    assert plan.tier4 == ["5555", "4444"], "never-ingested symbols must sort first (oldest possible)"


def test_rotation_orders_oldest_bar_first_tie_broken_by_symbol(session_factory):
    session = session_factory()
    old = _stock(session, "6060")
    _bar(session, old, days_ago=10)
    mid = _stock(session, "7070")
    _bar(session, mid, days_ago=5)
    newer = _stock(session, "8080")
    _bar(session, newer, days_ago=1)
    session.commit()

    plan = build_priority_plan(session, base_symbols=["8080", "6060", "7070"])

    assert plan.tier4 == ["6060", "7070", "8080"]


def test_rotation_advances_a_symbol_once_it_is_refreshed(session_factory):
    """Test matrix #19: after a symbol at the front of the rotation
    receives a fresh bar, it moves to the back on the next planning
    pass -- proving the rotation actually advances instead of sticking."""
    session = session_factory()
    a = _stock(session, "9091")
    _bar(session, a, days_ago=10)
    b = _stock(session, "9092")
    _bar(session, b, days_ago=5)
    session.commit()

    first_plan = build_priority_plan(session, base_symbols=["9091", "9092"])
    assert first_plan.tier4 == ["9091", "9092"]

    # "9091" gets refreshed (simulates a completed ingestion request).
    _bar(session, a, days_ago=0)
    session.commit()

    second_plan = build_priority_plan(session, base_symbols=["9091", "9092"])
    assert second_plan.tier4 == ["9092", "9091"], "the just-refreshed symbol must move to the back"


def test_no_permanent_starvation_across_many_rotation_passes(session_factory):
    """Test matrix #20: simulates N days of a fixed per-day background
    budget against a background universe -- every symbol must
    eventually be refreshed; none is stuck at the tail forever."""
    session = session_factory()
    symbols = [f"S{i:03d}" for i in range(50)]
    for symbol in symbols:
        _stock(session, symbol)
    session.commit()

    budget_per_day = 7
    last_refreshed_day = {symbol: -1 for symbol in symbols}
    max_days = 20  # ceil(50 / 7) == 8, generous headroom
    for day in range(max_days):
        plan = build_priority_plan(session, base_symbols=symbols)
        for symbol in plan.tier4[:budget_per_day]:
            stock = session.query(Stock).filter_by(symbol=symbol).one()
            _bar(session, stock, days_ago=-day)  # "today" for this simulated day
            last_refreshed_day[symbol] = day
        session.commit()

    never_refreshed = [s for s, d in last_refreshed_day.items() if d == -1]
    assert never_refreshed == [], f"permanently starved symbols: {never_refreshed}"


def test_estimate_max_background_refresh_age_days():
    assert estimate_max_background_refresh_age_days(354, 50) == pytest.approx(7.08, abs=0.01)
    assert estimate_max_background_refresh_age_days(0, 50) == 0.0
    assert estimate_max_background_refresh_age_days(100, 0) is None
