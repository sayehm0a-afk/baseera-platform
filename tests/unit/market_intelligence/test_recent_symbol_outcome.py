"""Unit tests for src.market_intelligence.recent_symbol_outcome -- the
real, per-symbol recent-failure disclosure for Smart Radar cards.
Same in-memory-sqlite construction pattern as test_sector_reliability.py,
since both modules are read-only disclosures layered on already-tracked
outcome data.
"""

from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import DecisionV2Outcome, DecisionV2OutcomeStatus, DecisionV2Snapshot, Stock
from src.market_intelligence.recent_symbol_outcome import (
    compute_recent_negative_outcome_by_symbol,
    recent_negative_outcome_for_symbol,
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


def _make_stock(session, symbol) -> Stock:
    stock = session.query(Stock).filter_by(symbol=symbol).first()
    if stock is None:
        stock = Stock(symbol=symbol, name_en=f"Stock {symbol}")
        session.add(stock)
        session.commit()
    return stock


def _add_snapshot(session, stock) -> DecisionV2Snapshot:
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id, symbol=stock.symbol, company_name_en=stock.name_en,
        decision="BUY_CANDIDATE", decision_label_ar="شراء",
        confidence_score=Decimal("75"), opportunity_quality_score=Decimal("60"),
        risk_score=Decimal("40"), data_quality_score=Decimal("90"),
        data_freshness_status="LIVE", current_price=Decimal("30.0"),
        entry_zone_low=Decimal("29.5"), entry_zone_high=Decimal("30.2"), stop_loss=Decimal("29.0"),
        market_status="OPEN", decision_timestamp=datetime.now(timezone.utc),
        analysis_version="2.0.0", data_source="SAHMK_REAL",
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def _add_outcome(session, symbol, status, *, evaluated_at=None, return_pct=None):
    stock = _make_stock(session, symbol)
    snapshot = _add_snapshot(session, stock)
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id, symbol=symbol,
        due_at=datetime.now(timezone.utc), status=status, entry_triggered=True,
        evaluated_at=evaluated_at or datetime.now(timezone.utc), return_pct=return_pct,
    )
    session.add(outcome)
    session.commit()
    return outcome


def test_symbol_with_no_outcomes_returns_empty_map(session):
    _make_stock(session, "1830")
    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])
    assert result == {}
    assert recent_negative_outcome_for_symbol(result, "1830") is None


def test_recent_stop_loss_hit_is_disclosed(session):
    _add_outcome(session, "1830", DecisionV2OutcomeStatus.STOP_LOSS_HIT, return_pct=-1.9)

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])

    outcome = recent_negative_outcome_for_symbol(result, "1830")
    assert outcome is not None
    assert outcome.status == "STOP_LOSS_HIT"
    assert "وقف الخسارة" in outcome.label_ar
    assert outcome.return_pct == pytest.approx(-1.9)


def test_recent_invalidated_setup_is_disclosed(session):
    _add_outcome(session, "1830", DecisionV2OutcomeStatus.INVALIDATED)

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])

    outcome = recent_negative_outcome_for_symbol(result, "1830")
    assert outcome is not None
    assert outcome.status == "INVALIDATED"


def test_recent_expired_with_negative_return_is_disclosed(session):
    _add_outcome(session, "1830", DecisionV2OutcomeStatus.EXPIRED, return_pct=-4.2)

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])

    outcome = recent_negative_outcome_for_symbol(result, "1830")
    assert outcome is not None
    assert outcome.status == "EXPIRED"


def test_expired_with_positive_return_is_not_a_failure(session):
    _add_outcome(session, "1830", DecisionV2OutcomeStatus.EXPIRED, return_pct=2.1)

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])

    assert recent_negative_outcome_for_symbol(result, "1830") is None


@pytest.mark.parametrize(
    "status",
    [
        DecisionV2OutcomeStatus.PENDING,
        DecisionV2OutcomeStatus.TARGET_1_HIT,
        DecisionV2OutcomeStatus.TARGET_2_HIT,
        DecisionV2OutcomeStatus.TARGET_3_HIT,
        DecisionV2OutcomeStatus.PARTIAL,
        DecisionV2OutcomeStatus.CANCELLED,
        DecisionV2OutcomeStatus.DATA_UNAVAILABLE,
        DecisionV2OutcomeStatus.ENTRY_NEVER_TRIGGERED,
    ],
)
def test_non_failure_statuses_never_trigger_the_warning(session, status):
    _add_outcome(session, "1830", status)

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])

    assert recent_negative_outcome_for_symbol(result, "1830") is None


def test_outcome_outside_the_lookback_window_is_ignored(session):
    _add_outcome(
        session, "1830", DecisionV2OutcomeStatus.STOP_LOSS_HIT,
        evaluated_at=datetime.now(timezone.utc) - timedelta(days=60),
    )

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"], lookback_days=14)

    assert recent_negative_outcome_for_symbol(result, "1830") is None


def test_only_the_most_recent_qualifying_outcome_is_kept(session):
    _add_outcome(
        session, "1830", DecisionV2OutcomeStatus.STOP_LOSS_HIT,
        evaluated_at=datetime.now(timezone.utc) - timedelta(days=5),
    )
    _add_outcome(
        session, "1830", DecisionV2OutcomeStatus.INVALIDATED,
        evaluated_at=datetime.now(timezone.utc) - timedelta(hours=2),
    )

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])

    outcome = recent_negative_outcome_for_symbol(result, "1830")
    assert outcome.status == "INVALIDATED"


def test_unresolved_pending_outcome_is_never_counted_as_a_failure(session):
    """PENDING rows have no evaluated_at yet -- must never be mistaken
    for a resolved failure."""
    stock = _make_stock(session, "1830")
    snapshot = _add_snapshot(session, stock)
    outcome = DecisionV2Outcome(
        decision_v2_snapshot_id=snapshot.id, symbol="1830",
        due_at=datetime.now(timezone.utc), status=DecisionV2OutcomeStatus.PENDING,
        entry_triggered=False,
    )
    session.add(outcome)
    session.commit()

    result = compute_recent_negative_outcome_by_symbol(session, ["1830"])

    assert recent_negative_outcome_for_symbol(result, "1830") is None


def test_batched_lookup_covers_multiple_symbols_in_one_query(session):
    _add_outcome(session, "1830", DecisionV2OutcomeStatus.STOP_LOSS_HIT)
    _add_outcome(session, "2222", DecisionV2OutcomeStatus.TARGET_1_HIT)

    result = compute_recent_negative_outcome_by_symbol(session, ["1830", "2222", "3092"])

    assert recent_negative_outcome_for_symbol(result, "1830") is not None
    assert recent_negative_outcome_for_symbol(result, "2222") is None
    assert recent_negative_outcome_for_symbol(result, "3092") is None


def test_empty_symbol_list_returns_empty_map_without_querying(session):
    assert compute_recent_negative_outcome_by_symbol(session, []) == {}
