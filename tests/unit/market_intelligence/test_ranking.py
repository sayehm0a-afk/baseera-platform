"""Unit tests for RankingEngine."""

from datetime import datetime, timezone

from src.analysis.decision.types import RiskLevel, TimeHorizon
from src.analysis.recommendation.types import Recommendation
from src.market_intelligence.ranking import RankingEngine
from src.market_intelligence.types import ChangeDetectionResult, ChangeEvent, ChangeType, RankingCategory
from tests.unit.market_intelligence._fixtures import make_decision, make_outcome


def test_top_buy_includes_buy_and_strong_buy_sorted_by_final_score():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.BUY, final_score=60.0)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", recommendation=Recommendation.STRONG_BUY, final_score=90.0)),
        make_outcome(symbol="C", decision=make_decision(symbol="C", recommendation=Recommendation.HOLD, final_score=50.0)),
    ]
    rankings = RankingEngine().rank(outcomes)
    entries = rankings[RankingCategory.TOP_BUY].entries
    assert [e.symbol for e in entries] == ["B", "A"]


def test_top_buy_excludes_a_high_score_buy_with_negative_expected_return():
    # Reproduces the 2026-07-30 live scan defect: symbol 1020 (BJAZ)
    # had the highest final_score (70.5) of any BUY but a negative
    # expected return (-0.16%) -- it still reached TOP_BUY #1 because
    # ranking sorted purely by score with no publication gate. A BUY
    # whose own target sits below its entry price must never appear in
    # TOP_BUY, regardless of how high its score is.
    outcomes = [
        make_outcome(symbol="1020", decision=make_decision(
            symbol="1020", recommendation=Recommendation.BUY, final_score=70.5, confidence=63.2,
            target_price=11.86, stop_loss=11.6, expected_return_pct=-0.16,
        )),
        make_outcome(symbol="1140", decision=make_decision(
            symbol="1140", recommendation=Recommendation.BUY, final_score=68.4,
            target_price=24.58, stop_loss=23.68, expected_return_pct=2.23, risk_reward_ratio=2.0,
        )),
    ]
    rankings = RankingEngine().rank(outcomes)
    entries = rankings[RankingCategory.TOP_BUY].entries
    assert [e.symbol for e in entries] == ["1140"]


def test_top_strong_buy_only_includes_strong_buy():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.BUY, confidence=90.0)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", recommendation=Recommendation.STRONG_BUY, confidence=70.0)),
    ]
    rankings = RankingEngine().rank(outcomes)
    assert [e.symbol for e in rankings[RankingCategory.TOP_STRONG_BUY].entries] == ["B"]


def test_lowest_risk_sorted_by_risk_ordinal_then_confidence():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", risk_level=RiskLevel.HIGH, confidence=90.0)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", risk_level=RiskLevel.LOW, confidence=50.0)),
        make_outcome(symbol="C", decision=make_decision(symbol="C", risk_level=RiskLevel.LOW, confidence=80.0)),
    ]
    rankings = RankingEngine().rank(outcomes)
    assert [e.symbol for e in rankings[RankingCategory.LOWEST_RISK].entries] == ["C", "B", "A"]


def test_top_dividend_stocks_requires_dividend_yield():
    outcomes = [
        make_outcome(symbol="A", fundamental_snapshot={"dividend_yield": 0.05}),
        make_outcome(symbol="B", fundamental_snapshot=None),
        make_outcome(symbol="C", fundamental_snapshot={"dividend_yield": 0.08}),
    ]
    rankings = RankingEngine().rank(outcomes)
    assert [e.symbol for e in rankings[RankingCategory.TOP_DIVIDEND_STOCKS].entries] == ["C", "A"]


def test_top_swing_trade_requires_short_term_horizon_and_buy():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.BUY, time_horizon=TimeHorizon.SHORT_TERM, expected_return_pct=3.0)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", recommendation=Recommendation.BUY, time_horizon=TimeHorizon.LONG_TERM, expected_return_pct=10.0)),
    ]
    rankings = RankingEngine().rank(outcomes)
    assert [e.symbol for e in rankings[RankingCategory.TOP_SWING_TRADE].entries] == ["A"]


def test_failed_or_skipped_outcomes_never_appear_in_any_ranking():
    outcomes = [
        make_outcome(symbol="A", success=False, report=None, skipped_reason="insufficient_data"),
        make_outcome(symbol="B", success=True),
    ]
    rankings = RankingEngine().rank(outcomes)
    for ranking_list in rankings.values():
        assert all(e.symbol != "A" for e in ranking_list.entries)


def test_change_dependent_categories_are_empty_without_a_previous_scan():
    outcomes = [make_outcome(symbol="A")]
    rankings = RankingEngine().rank(outcomes, change_result=None)
    for category in (
        RankingCategory.MOST_IMPROVED_TODAY, RankingCategory.MOST_DETERIORATED_TODAY,
        RankingCategory.RECENTLY_UPGRADED, RankingCategory.RECENTLY_DOWNGRADED,
        RankingCategory.NEW_OPPORTUNITIES, RankingCategory.REMOVED_OPPORTUNITIES,
    ):
        assert rankings[category].entries == []


def test_most_improved_and_deteriorated_from_score_change_events():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A")),
        make_outcome(symbol="B", decision=make_decision(symbol="B")),
    ]
    now = datetime.now(timezone.utc)
    change_result = ChangeDetectionResult(
        events=[
            ChangeEvent(symbol="A", change_type=ChangeType.SCORE_CHANGE, previous_value="40.0", new_value="60.0", delta=20.0, detected_at=now),
            ChangeEvent(symbol="B", change_type=ChangeType.SCORE_CHANGE, previous_value="60.0", new_value="40.0", delta=-20.0, detected_at=now),
        ],
        new_symbols=[], removed_symbols=[], previous_scan_run_id=1,
    )
    rankings = RankingEngine().rank(outcomes, change_result)
    assert [e.symbol for e in rankings[RankingCategory.MOST_IMPROVED_TODAY].entries] == ["A"]
    assert [e.symbol for e in rankings[RankingCategory.MOST_DETERIORATED_TODAY].entries] == ["B"]


def test_recently_upgraded_and_downgraded_from_recommendation_change_events():
    outcomes = [
        make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.BUY)),
        make_outcome(symbol="B", decision=make_decision(symbol="B", recommendation=Recommendation.SELL)),
    ]
    now = datetime.now(timezone.utc)
    change_result = ChangeDetectionResult(
        events=[
            ChangeEvent(symbol="A", change_type=ChangeType.RECOMMENDATION_CHANGE, previous_value="HOLD", new_value="BUY", delta=None, detected_at=now),
            ChangeEvent(symbol="B", change_type=ChangeType.RECOMMENDATION_CHANGE, previous_value="HOLD", new_value="SELL", delta=None, detected_at=now),
        ],
        new_symbols=[], removed_symbols=[], previous_scan_run_id=1,
    )
    rankings = RankingEngine().rank(outcomes, change_result)
    assert [e.symbol for e in rankings[RankingCategory.RECENTLY_UPGRADED].entries] == ["A"]
    assert [e.symbol for e in rankings[RankingCategory.RECENTLY_DOWNGRADED].entries] == ["B"]


def test_new_opportunities_includes_a_brand_new_symbol_already_rated_buy():
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.STRONG_BUY))]
    change_result = ChangeDetectionResult(events=[], new_symbols=["A"], removed_symbols=[], previous_scan_run_id=1)

    rankings = RankingEngine().rank(outcomes, change_result)

    assert [e.symbol for e in rankings[RankingCategory.NEW_OPPORTUNITIES].entries] == ["A"]


def test_removed_opportunities_from_a_recommendation_dropping_out_of_buy_territory():
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A", recommendation=Recommendation.HOLD))]
    now = datetime.now(timezone.utc)
    change_result = ChangeDetectionResult(
        events=[
            ChangeEvent(symbol="A", change_type=ChangeType.RECOMMENDATION_CHANGE, previous_value="BUY", new_value="HOLD", delta=None, detected_at=now),
        ],
        new_symbols=[], removed_symbols=[], previous_scan_run_id=1,
    )
    rankings = RankingEngine().rank(outcomes, change_result)
    assert [e.symbol for e in rankings[RankingCategory.REMOVED_OPPORTUNITIES].entries] == ["A"]


def test_all_seventeen_categories_are_always_present():
    rankings = RankingEngine().rank([make_outcome(symbol="A")])
    assert set(rankings.keys()) == set(RankingCategory)
    assert len(RankingCategory) == 17
