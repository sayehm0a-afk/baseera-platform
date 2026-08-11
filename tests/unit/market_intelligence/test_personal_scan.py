"""Unit tests for src.market_intelligence.personal_scan -- the
"امسح السوق الآن" read path. Constructs DecisionV2Snapshot rows
directly (no real scan/provider involved) so uniqueness/ranking/
staleness behavior can be tested precisely and cheaply.
"""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import DecisionV2Snapshot, MarketScanRun, MarketScanStatus, Stock
from src.market_intelligence.personal_scan import (
    FRESHNESS_AGING,
    FRESHNESS_FRESH,
    FRESHNESS_NO_SCAN,
    FRESHNESS_STALE,
    select_top_opportunities,
)


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def _make_run(session, finished_at) -> MarketScanRun:
    run = MarketScanRun(
        status=MarketScanStatus.SUCCESS, symbols_requested=1, symbols_succeeded=1,
        symbols_skipped=0, symbols_failed=0, started_at=finished_at, finished_at=finished_at,
    )
    session.add(run)
    session.commit()
    return run


def _make_stock(session, symbol) -> Stock:
    stock = Stock(symbol=symbol, name_en=f"Stock {symbol}")
    session.add(stock)
    session.commit()
    return stock


def _add_snapshot(
    session, run, symbol, *, decision="BUY_CANDIDATE", opportunity_quality_score=70.0,
    confidence_score=75.0, risk_score=40.0, entry_status="READY_NOW",
    risk_reward_target_1=None, news_impact=None, volume_confirms_decision=None,
    abnormal_volume=None, market_risk_entry_permitted=None, why_not_buy_reasons=None,
    current_price=30.0, invalidation_price=None,
):
    stock = session.query(Stock).filter_by(symbol=symbol).first() or _make_stock(session, symbol)
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id, symbol=symbol, company_name_en=f"Company {symbol}",
        decision=decision, decision_label_ar="شراء",
        confidence_score=confidence_score, opportunity_quality_score=opportunity_quality_score,
        risk_score=risk_score, data_quality_score=90.0, data_freshness_status="LIVE",
        current_price=current_price, market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0", data_source="SAHMK_REAL", scan_run_id=run.id,
        entry_status=entry_status, risk_reward_target_1=risk_reward_target_1, news_impact=news_impact,
        volume_confirms_decision=volume_confirms_decision, abnormal_volume=abnormal_volume,
        market_risk_entry_permitted=market_risk_entry_permitted, why_not_buy_reasons=why_not_buy_reasons,
        invalidation_price=invalidation_price,
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def test_returns_unique_symbols_even_when_a_symbol_has_multiple_rows_for_the_same_run(session):
    """Regression: DecisionV2Snapshot is an insert-only request log --
    the same symbol can legitimately have more than one row for the
    same scan_run_id (e.g. the scan wrote one, then a user opened the
    stock page and /decision-v2 wrote another). The personal endpoint
    must never show the same stock twice."""
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "1111", opportunity_quality_score=60.0)
    _add_snapshot(session, run, "1111", opportunity_quality_score=80.0)  # newer, higher score
    _add_snapshot(session, run, "2222", opportunity_quality_score=50.0)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    symbols = [c.symbol for c in result.candidates]
    assert symbols == sorted(symbols)  # no assertion on order here, just...
    assert len(symbols) == len(set(symbols)), f"duplicate symbol in {symbols}"
    assert set(symbols) == {"1111", "2222"}
    # The kept "1111" row must be the most recent (highest id) one, not
    # an arbitrary/first one.
    kept = next(c for c in result.candidates if c.symbol == "1111")
    assert float(kept.opportunity_quality_score) == 80.0


def test_caps_at_max_results_even_with_many_qualifying_candidates(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    for i in range(12):
        _add_snapshot(session, run, f"{1000 + i}", opportunity_quality_score=50.0 + i)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert len(result.candidates) == 5


def test_ranks_by_decision_priority_then_quality_score(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "3001", decision="WAIT_FOR_ENTRY", opportunity_quality_score=95.0)
    _add_snapshot(session, run, "3002", decision="STRONG_BUY_CANDIDATE", opportunity_quality_score=60.0)
    _add_snapshot(session, run, "3003", decision="BUY_CANDIDATE", opportunity_quality_score=90.0)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    # STRONG_BUY_CANDIDATE outranks BUY_CANDIDATE outranks WAIT_FOR_ENTRY
    # regardless of raw quality score -- decision priority is primary.
    assert [c.symbol for c in result.candidates] == ["3002", "3003", "3001"]


def test_excludes_non_opportunity_decisions(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "4001", decision="HOLD", opportunity_quality_score=99.0)
    _add_snapshot(session, run, "4002", decision="REJECT", opportunity_quality_score=99.0)
    _add_snapshot(session, run, "4003", decision="INSUFFICIENT_DATA", opportunity_quality_score=99.0)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert result.candidates == []
    assert result.is_stale is False  # a real, fresh scan was checked -- it just had nothing to offer


def test_returns_no_candidates_and_no_stale_flag_when_nothing_qualifies(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)  # no snapshots at all

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert result.candidates == []
    assert result.is_stale is False


def test_stale_scan_returns_no_candidates_and_is_stale_true(session):
    now = datetime.now(timezone.utc)
    old_run = _make_run(session, now - timedelta(hours=48))  # default threshold is 24h
    _add_snapshot(session, old_run, "5001", opportunity_quality_score=99.0)

    result = select_top_opportunities(session, old_run, max_results=5, now=now)

    assert result.candidates == []
    assert result.is_stale is True
    assert result.data_age_hours > 24.0


def test_no_scan_run_at_all_is_stale_not_a_crash(session):
    result = select_top_opportunities(session, None, max_results=5)

    assert result.candidates == []
    assert result.is_stale is True
    assert result.data_age_hours is None


# --- CONT Phase 6: four-state freshness disclosure ---------------------------


def test_freshness_state_is_no_scan_when_no_run_exists(session):
    result = select_top_opportunities(session, None, max_results=5)

    assert result.freshness_state == FRESHNESS_NO_SCAN
    assert result.freshness_label_ar


def test_freshness_state_is_fresh_well_within_the_max_age(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now - timedelta(hours=1))
    _add_snapshot(session, run, "1111")

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert result.is_stale is False
    assert result.freshness_state == FRESHNESS_FRESH
    assert result.freshness_label_ar


def test_freshness_state_is_aging_past_the_halfway_point_but_still_within_max_age(session):
    now = datetime.now(timezone.utc)
    # Default max_data_age_hours is 24h -- 15h is past the 12h halfway
    # point but still well under the 24h staleness cutoff.
    run = _make_run(session, now - timedelta(hours=15))
    _add_snapshot(session, run, "1111")

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert result.is_stale is False
    assert result.freshness_state == FRESHNESS_AGING
    assert result.candidates  # aging data is still usable, unlike stale
    assert result.freshness_label_ar


def test_freshness_state_is_stale_past_the_max_age(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now - timedelta(hours=30))
    _add_snapshot(session, run, "1111")

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert result.is_stale is True
    assert result.freshness_state == FRESHNESS_STALE
    assert result.candidates == []
    assert result.freshness_label_ar


# --- CONT Phase 4: composite-score ranking factors ---------------------------


def test_entry_readiness_breaks_a_tie_between_equal_quality_candidates(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "5001", entry_status="WAIT_FOR_PULLBACK")
    _add_snapshot(session, run, "5002", entry_status="READY_NOW")

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["5002", "5001"]


def test_higher_risk_reward_ranks_above_otherwise_identical_candidate(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "6001", risk_reward_target_1=1.0)
    _add_snapshot(session, run, "6002", risk_reward_target_1=4.0)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["6002", "6001"]


def test_negative_news_impact_ranks_below_positive_at_equal_quality(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "7001", news_impact="NEGATIVE")
    _add_snapshot(session, run, "7002", news_impact="POSITIVE")
    _add_snapshot(session, run, "7003", news_impact=None)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["7002", "7003", "7001"]


def test_abnormal_volume_ranks_below_volume_confirmed_at_equal_quality(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "8001", abnormal_volume=True)
    _add_snapshot(session, run, "8002", volume_confirms_decision=True)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["8002", "8001"]


def test_market_risk_entry_not_permitted_is_penalized(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "9001", market_risk_entry_permitted=False)
    _add_snapshot(session, run, "9002", market_risk_entry_permitted=True)

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["9002", "9001"]


def test_contradictory_evidence_reasons_lower_the_rank(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "1101", why_not_buy_reasons=["سيولة ضعيفة", "تقلب مرتفع"])
    _add_snapshot(session, run, "1102", why_not_buy_reasons=[])

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["1102", "1101"]


def test_candidate_close_to_invalidation_price_is_penalized(session):
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(session, run, "1201", current_price=30.0, invalidation_price=29.7)  # 1% away -- tight
    _add_snapshot(session, run, "1202", current_price=30.0, invalidation_price=25.0)  # far from invalidation

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["1202", "1201"]


def test_decision_priority_still_dominates_every_composite_score_factor(session):
    """The richer composite score must never override the hard business
    rule that STRONG_BUY_CANDIDATE > BUY_CANDIDATE > WAIT_FOR_ENTRY,
    however favorable the losing candidate's other signals are."""
    now = datetime.now(timezone.utc)
    run = _make_run(session, now)
    _add_snapshot(
        session, run, "1301", decision="WAIT_FOR_ENTRY", opportunity_quality_score=99.0,
        risk_reward_target_1=5.0, news_impact="POSITIVE", volume_confirms_decision=True,
    )
    _add_snapshot(
        session, run, "1302", decision="STRONG_BUY_CANDIDATE", opportunity_quality_score=1.0,
        risk_reward_target_1=None, news_impact="NEGATIVE", abnormal_volume=True,
    )

    result = select_top_opportunities(session, run, max_results=5, now=now)

    assert [c.symbol for c in result.candidates] == ["1302", "1301"]
