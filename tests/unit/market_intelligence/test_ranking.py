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


def test_highest_expected_return_excludes_a_publication_gate_rejection():
    # Phase 2D: HIGHEST_EXPECTED_RETURN previously had no is_publishable
    # check at all -- a BUY with a positive expected_return_pct but a
    # non-positive risk/reward (rejected by the gate) could still top
    # this list purely on the raw return number.
    outcomes = [
        make_outcome(symbol="GOOD", decision=make_decision(
            symbol="GOOD", recommendation=Recommendation.BUY, expected_return_pct=4.0,
        )),
        make_outcome(symbol="SYNTHETIC", is_synthetic=True, decision=make_decision(
            symbol="SYNTHETIC", recommendation=Recommendation.BUY, expected_return_pct=20.0,
        )),
    ]
    rankings = RankingEngine().rank(outcomes)
    entries = rankings[RankingCategory.HIGHEST_EXPECTED_RETURN].entries
    assert [e.symbol for e in entries] == ["GOOD"]


def test_lowest_risk_excludes_a_publication_gate_rejection():
    outcomes = [
        make_outcome(symbol="GOOD", decision=make_decision(symbol="GOOD", risk_level=RiskLevel.LOW)),
        make_outcome(symbol="SYNTHETIC", is_synthetic=True, decision=make_decision(
            symbol="SYNTHETIC", risk_level=RiskLevel.LOW,
        )),
    ]
    rankings = RankingEngine().rank(outcomes)
    entries = rankings[RankingCategory.LOWEST_RISK].entries
    assert [e.symbol for e in entries] == ["GOOD"]


def test_top_dividend_stocks_excludes_a_publication_gate_rejection():
    outcomes = [
        make_outcome(symbol="GOOD", fundamental_snapshot={"dividend_yield": 0.05}),
        make_outcome(symbol="SYNTHETIC", is_synthetic=True, fundamental_snapshot={"dividend_yield": 0.09}),
    ]
    rankings = RankingEngine().rank(outcomes)
    entries = rankings[RankingCategory.TOP_DIVIDEND_STOCKS].entries
    assert [e.symbol for e in entries] == ["GOOD"]


def test_most_bullish_and_most_bearish_exclude_publication_gate_rejections():
    outcomes = [
        make_outcome(symbol="GOOD_BULL", decision=make_decision(symbol="GOOD_BULL", final_score=80.0)),
        make_outcome(symbol="SYNTHETIC_BULL", is_synthetic=True, decision=make_decision(
            symbol="SYNTHETIC_BULL", final_score=95.0,
        )),
        make_outcome(symbol="GOOD_BEAR", decision=make_decision(
            symbol="GOOD_BEAR", recommendation=Recommendation.SELL, final_score=20.0, expected_return_pct=-3.0,
        )),
        make_outcome(symbol="SYNTHETIC_BEAR", is_synthetic=True, decision=make_decision(
            symbol="SYNTHETIC_BEAR", recommendation=Recommendation.SELL, final_score=5.0, expected_return_pct=-9.0,
        )),
    ]
    rankings = RankingEngine().rank(outcomes)
    # Synthetic-data outcomes are excluded from both lists regardless of
    # score; among the two real outcomes, MOST_BULLISH still sorts by
    # final_score descending and MOST_BEARISH ascending (this gate only
    # removes gate-rejected symbols, it does not filter by direction).
    assert [e.symbol for e in rankings[RankingCategory.MOST_BULLISH].entries] == ["GOOD_BULL", "GOOD_BEAR"]
    assert [e.symbol for e in rankings[RankingCategory.MOST_BEARISH].entries] == ["GOOD_BEAR", "GOOD_BULL"]


def test_zero_price_outcome_is_excluded_from_every_ranking_category_not_just_gated_ones():
    # Reproduces a real 2026-08-03 full-universe scan defect: symbol
    # 2210 had no technical leg (0 OHLCV rows) but a valid fundamental
    # leg, so scanner.py's _scan_one() correctly marked it success=True
    # with latest_price=0.0 -- and it reached MOST_BEARISH unfiltered,
    # since only the publication-gated "opportunity" categories
    # (TOP_BUY etc.) checked price validity, not _successful() itself.
    outcomes = [
        make_outcome(symbol="2210", latest_price=0.0, decision=make_decision(
            symbol="2210", recommendation=Recommendation.SELL, final_score=26.0, confidence=8.2,
            target_price=None, stop_loss=None, expected_return_pct=None,
        )),
        make_outcome(symbol="B", latest_price=50.0, decision=make_decision(
            symbol="B", recommendation=Recommendation.SELL, final_score=40.0, confidence=70.0,
        )),
    ]
    rankings = RankingEngine().rank(outcomes)
    for category, ranking_list in rankings.items():
        symbols = [e.symbol for e in ranking_list.entries]
        assert "2210" not in symbols, f"zero-price symbol 2210 leaked into {category}"


def test_calibrated_confidences_excludes_a_below_threshold_symbol_from_gated_categories():
    # Recommendation-engine hardening: a symbol whose raw confidence
    # looks fine but whose real calibrated success probability is below
    # get_min_calibrated_success_probability() (default 0.35) must be
    # excluded from every is_publishable()-gated category, not just
    # written-but-ignored on the historical RecommendationSnapshot.
    outcomes = [
        make_outcome(symbol="LOW_CAL", decision=make_decision(symbol="LOW_CAL", final_score=90.0, confidence=95.0)),
        make_outcome(symbol="HIGH_CAL", decision=make_decision(symbol="HIGH_CAL", final_score=60.0, confidence=70.0)),
    ]
    calibrated_confidences = {"LOW_CAL": 0.10, "HIGH_CAL": 0.80}

    rankings = RankingEngine().rank(outcomes, calibrated_confidences=calibrated_confidences)

    assert [e.symbol for e in rankings[RankingCategory.TOP_BUY].entries] == ["HIGH_CAL"]
    assert [e.symbol for e in rankings[RankingCategory.MOST_BULLISH].entries] == ["HIGH_CAL"]
    # HIGHEST_CONFIDENCE is deliberately never gated (a diagnostic view,
    # not an "opportunity") -- both symbols must still appear there,
    # proving the exclusion above is the calibration gate specifically.
    assert {e.symbol for e in rankings[RankingCategory.HIGHEST_CONFIDENCE].entries} == {"LOW_CAL", "HIGH_CAL"}


def test_generated_at_defaults_to_now_when_not_supplied():
    # Backward compatibility: existing callers (e.g. RebalanceEngine)
    # that never pass generated_at must keep getting "now", unchanged.
    before = datetime.now(timezone.utc)
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A"))]
    rankings = RankingEngine().rank(outcomes)
    after = datetime.now(timezone.utc)
    for ranking_list in rankings.values():
        assert before <= ranking_list.generated_at <= after


def test_generated_at_uses_the_real_supplied_timestamp_not_read_time():
    # Production freshness fix (2026-08-23): a caller with a real scan
    # timestamp (e.g. src.api.routes.market's `run.finished_at`) must
    # see that exact timestamp reflected in every RankingList, not the
    # moment rank() happened to be called -- this is what makes
    # /opportunities' and /rankings' `generated_at` field honestly
    # report how old the underlying scan actually is instead of always
    # claiming "just now".
    real_scan_timestamp = datetime(2026, 8, 20, 10, 0, tzinfo=timezone.utc)  # three days before "now" in this run
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A"))]
    rankings = RankingEngine().rank(outcomes, generated_at=real_scan_timestamp)
    for ranking_list in rankings.values():
        assert ranking_list.generated_at == real_scan_timestamp
        assert ranking_list.generated_at != datetime.now(timezone.utc)


def test_no_calibrated_confidences_argument_behaves_exactly_as_before():
    # Backward compatibility: omitting calibrated_confidences entirely
    # (every existing caller before this hardening pass) must produce
    # the same NOT_EVALUATED-not-FAIL behavior as passing an empty dict.
    outcomes = [make_outcome(symbol="A", decision=make_decision(symbol="A"))]
    without_arg = RankingEngine().rank(outcomes)
    with_empty_dict = RankingEngine().rank(outcomes, calibrated_confidences={})
    for category in RankingCategory:
        assert (
            [e.symbol for e in without_arg[category].entries] == [e.symbol for e in with_empty_dict[category].entries]
        )
