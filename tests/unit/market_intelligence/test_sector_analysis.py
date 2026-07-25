"""Unit tests for SectorAnalyzer."""

from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.sector_analysis import SectorAnalyzer
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


def test_groups_by_sector_and_computes_averages():
    outcomes = [
        make_outcome(symbol="A", sector="Energy", decision=make_decision(symbol="A", final_score=60.0, confidence=80.0)),
        make_outcome(symbol="B", sector="Energy", decision=make_decision(symbol="B", final_score=80.0, confidence=90.0)),
        make_outcome(symbol="C", sector="Banks", decision=make_decision(symbol="C", final_score=40.0, confidence=50.0)),
    ]
    summaries = {s.sector: s for s in SectorAnalyzer().analyze(outcomes)}

    assert summaries["Energy"].symbol_count == 2
    assert summaries["Energy"].average_final_score == 70.0
    assert summaries["Banks"].symbol_count == 1
    assert summaries["Banks"].average_final_score == 40.0


def test_unclassified_bucket_for_missing_sector():
    outcomes = [make_outcome(symbol="A", sector=None)]
    summaries = SectorAnalyzer().analyze(outcomes)
    assert summaries[0].sector == "Unclassified"


def test_buy_sell_hold_counts_and_breadth():
    outcomes = [
        make_outcome(symbol="A", sector="Energy", decision=make_decision(symbol="A", recommendation=Recommendation.BUY)),
        make_outcome(symbol="B", sector="Energy", decision=make_decision(symbol="B", recommendation=Recommendation.SELL)),
        make_outcome(symbol="C", sector="Energy", decision=make_decision(symbol="C", recommendation=Recommendation.HOLD)),
        make_outcome(symbol="D", sector="Energy", decision=make_decision(symbol="D", recommendation=Recommendation.HOLD)),
    ]
    summary = SectorAnalyzer().analyze(outcomes)[0]
    assert summary.buy_count == 1
    assert summary.sell_count == 1
    assert summary.hold_count == 2
    assert summary.breadth == 0.25


def test_skipped_and_failed_outcomes_excluded_from_averages():
    outcomes = [
        make_outcome(symbol="A", sector="Energy", decision=make_decision(symbol="A", final_score=80.0)),
        make_outcome(symbol="B", sector="Energy", success=False, report=None, skipped_reason="insufficient_data"),
    ]
    summary = SectorAnalyzer().analyze(outcomes)[0]
    assert summary.symbol_count == 1
    assert summary.average_final_score == 80.0


def test_momentum_is_none_without_a_previous_scan():
    outcomes = [make_outcome(symbol="A", sector="Energy")]
    summary = SectorAnalyzer().analyze(outcomes)[0]
    assert summary.momentum is None


def test_momentum_is_the_delta_against_the_previous_scan():
    outcomes = [make_outcome(symbol="A", sector="Energy", decision=make_decision(symbol="A", final_score=70.0))]
    summary = SectorAnalyzer().analyze(outcomes, previous_summaries={"Energy": 55.0})[0]
    assert summary.momentum == 15.0


def test_strongest_and_weakest_sectors():
    outcomes = [
        make_outcome(symbol="A", sector="Energy", decision=make_decision(symbol="A", final_score=90.0)),
        make_outcome(symbol="B", sector="Banks", decision=make_decision(symbol="B", final_score=20.0)),
    ]
    summaries = SectorAnalyzer().analyze(outcomes)
    strongest, weakest = SectorAnalyzer.strongest_and_weakest(summaries, top_n=1)
    assert strongest == ["Energy"]
    assert weakest == ["Banks"]


def test_rotation_splits_by_momentum_sign():
    outcomes_in = [make_outcome(symbol="A", sector="Energy", decision=make_decision(symbol="A", final_score=80.0))]
    outcomes_out = [make_outcome(symbol="B", sector="Banks", decision=make_decision(symbol="B", final_score=20.0))]
    summaries = SectorAnalyzer().analyze(
        outcomes_in + outcomes_out, previous_summaries={"Energy": 50.0, "Banks": 60.0}
    )
    rotating_in, rotating_out = SectorAnalyzer.rotation(summaries)
    assert [s.sector for s in rotating_in][:1] == ["Energy"]
    assert [s.sector for s in rotating_out][:1] == ["Banks"]
