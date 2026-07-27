"""Unit tests for MarketSnapshotBuilder."""

from datetime import datetime, timezone

from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.market_snapshot import MarketSnapshotBuilder
from src.market_intelligence.types import ChangeDetectionResult, ChangeEvent, ChangeType, SectorSummary
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


def _sector(sector, average_final_score):
    return SectorSummary(
        sector=sector, symbol_count=1, average_confidence=70.0, average_final_score=average_final_score,
        average_expected_return_pct=5.0, average_technical_score=60.0, average_fundamental_score=60.0,
        buy_count=1, sell_count=0, hold_count=0, breadth=1.0, momentum=None,
    )


def test_buy_sell_counts_and_bull_bear_ratio():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.BUY)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", recommendation=Recommendation.BUY)),
        make_outcome(symbol="C", decision=make_decision(symbol="C", recommendation=Recommendation.SELL)),
    ]
    snapshot = MarketSnapshotBuilder().build(outcomes, [])
    assert snapshot.buy_signal_count == 2
    assert snapshot.sell_signal_count == 1
    assert snapshot.bull_bear_ratio == 2.0


def test_bull_bear_ratio_is_none_with_no_sell_signals():
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.BUY))]
    snapshot = MarketSnapshotBuilder().build(outcomes, [])
    assert snapshot.bull_bear_ratio is None


def test_average_recommendation_score_is_centered_on_hold():
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.STRONG_BUY))]
    snapshot = MarketSnapshotBuilder().build(outcomes, [])
    assert snapshot.average_recommendation_score == 2.0  # STRONG_BUY is +2 from HOLD


def test_strongest_and_weakest_sectors_reused_from_sector_analyzer():
    sectors = [_sector("Energy", 90.0), _sector("Banks", 10.0)]
    snapshot = MarketSnapshotBuilder().build([], sectors)
    assert "Energy" in snapshot.strongest_sectors
    assert "Banks" in snapshot.weakest_sectors


def test_most_important_changes_sorted_by_absolute_delta():
    now = datetime.now(timezone.utc)
    change_result = ChangeDetectionResult(
        events=[
            ChangeEvent(symbol="A", change_type=ChangeType.SCORE_CHANGE, previous_value="40", new_value="45", delta=5.0, detected_at=now),
            ChangeEvent(symbol="B", change_type=ChangeType.SCORE_CHANGE, previous_value="40", new_value="10", delta=-30.0, detected_at=now),
        ],
        new_symbols=[], removed_symbols=[], previous_scan_run_id=1,
    )
    snapshot = MarketSnapshotBuilder().build([], [], change_result)
    assert snapshot.most_important_changes[0].symbol == "B"


def test_empty_scan_produces_honest_nones():
    snapshot = MarketSnapshotBuilder().build([], [])
    assert snapshot.symbols_scanned == 0
    assert snapshot.average_confidence is None
    assert snapshot.average_recommendation_score is None
    assert snapshot.bull_bear_ratio is None
