"""Unit tests for publication_gate.py -- the missing "is this actually
publishable" step that let symbol 1020 reach TOP_BUY #1 in the
2026-07-30 live scan purely by having the highest final_score, despite
a negative expected return."""

from src.analysis.decision.types import EntryQuality, PositionSize, Recommendation
from src.analysis.recommendation.types import AnalysisContext
from src.market_intelligence.publication_gate import evaluate_publication, is_publishable
from src.market_intelligence.types import GateStatus, PublicationStatus
from tests.unit.market_intelligence._fixtures import make_breakdown, make_decision, make_outcome


def make_context(**extra) -> AnalysisContext:
    return AnalysisContext(symbol="2222", extra=extra)


def test_a_healthy_buy_is_published():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- strict real-data mode: synthetic data can never be published -----


def test_synthetic_data_is_hard_rejected_regardless_of_how_good_it_looks():
    """An otherwise-perfect BUY (strong return, healthy risk/reward)
    must still be rejected outright if it came from a synthetic
    provider -- no other gate's merit can override this."""
    outcome = make_outcome(
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=8.0, risk_reward_ratio=3.0),
        is_synthetic=True, data_source="DEV_SYNTHETIC",
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    data_source_gate = next(g for g in evaluation.gates if g.name == "real_data_source")
    assert data_source_gate.status is GateStatus.FAIL
    assert not is_publishable(outcome)


def test_confirmed_real_sahmk_data_passes_the_data_source_gate():
    outcome = make_outcome(
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
        is_synthetic=False, data_source="SAHMK_REAL",
    )
    evaluation = evaluate_publication(outcome)
    data_source_gate = next(g for g in evaluation.gates if g.name == "real_data_source")
    assert data_source_gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_untracked_data_source_is_not_evaluated_not_hard_blocked():
    """Backward compatibility: outcomes built before is_synthetic
    existed (is_synthetic=None, the make_outcome default) must not be
    retroactively rejected -- NOT_EVALUATED, same convention as the
    sector/benchmark gates."""
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    assert outcome.is_synthetic is None
    evaluation = evaluate_publication(outcome)
    data_source_gate = next(g for g in evaluation.gates if g.name == "real_data_source")
    assert data_source_gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED
    assert is_publishable(outcome)


def test_reproduces_1020_a_buy_with_negative_expected_return_is_rejected():
    # Symbol 1020 (BJAZ), 2026-07-30 live scan: BUY, price 11.88, target
    # 11.86, expected_return_pct -0.16% -- ranked TOP_BUY #1 by score
    # alone. The gate must reject this outright, regardless of score.
    outcome = make_outcome(decision=make_decision(
        symbol="1020", recommendation=Recommendation.BUY, final_score=70.5, confidence=63.2,
        target_price=11.86, stop_loss=11.6, expected_return_pct=-0.16,
    ))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    risk_reward_gate = next(g for g in evaluation.gates if g.name == "risk_reward")
    assert risk_reward_gate.status is GateStatus.FAIL
    assert not is_publishable(outcome)


def test_a_sell_with_non_negative_expected_return_is_rejected():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.SELL, expected_return_pct=0.5))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED


def test_risk_reward_below_minimum_threshold_is_rejected():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=1.0, risk_reward_ratio=0.5))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    risk_reward_gate = next(g for g in evaluation.gates if g.name == "risk_reward")
    assert risk_reward_gate.status is GateStatus.FAIL


def test_missing_risk_reward_ratio_is_not_evaluated_not_rejected():
    # No stop distance to compute risk/reward from -- honestly
    # NOT_EVALUATED, not silently treated as PASS or FAIL.
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=None))
    evaluation = evaluate_publication(outcome)
    risk_reward_gate = next(g for g in evaluation.gates if g.name == "risk_reward")
    assert risk_reward_gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_poor_entry_quality_downgrades_to_watch_only_not_rejected():
    outcome = make_outcome(decision=make_decision(
        recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0,
        entry_quality=EntryQuality.POOR,
    ))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.WATCH_ONLY


def test_hold_is_published_without_risk_reward_or_entry_quality_gating():
    # AIDecisionEngine always computes targets/stop/expected-return
    # regardless of recommendation (see _compute_price_targets), so a
    # real HOLD still carries these fields -- what must differ is that
    # HOLD proposes no trade, so risk/reward and entry quality are
    # never evaluated against it.
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.HOLD, expected_return_pct=-1.0, risk_reward_ratio=None))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.PUBLISHED
    risk_reward_gate = next(g for g in evaluation.gates if g.name == "risk_reward")
    assert risk_reward_gate.status is GateStatus.NOT_EVALUATED


def test_unsuccessful_outcome_is_insufficient_data():
    outcome = make_outcome(success=False, report=None, skipped_reason="insufficient_data")
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.INSUFFICIENT_DATA
    assert not is_publishable(outcome)


def test_missing_price_is_rejected():
    outcome = make_outcome(latest_price=None, decision=make_decision(recommendation=Recommendation.BUY))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    price_gate = next(g for g in evaluation.gates if g.name == "price_validity")
    assert price_gate.status is GateStatus.FAIL


def test_missing_sector_is_not_evaluated_and_never_blocks_publication():
    outcome = make_outcome(sector=None, decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    sector_gate = next(g for g in evaluation.gates if g.name == "sector_data")
    assert sector_gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED
    assert any("sector" in d for d in evaluation.disclosures)


def test_illiquid_stock_is_rejected():
    # price=100, volume_sma_20=1000 -> average traded value ~100,000 SAR/day,
    # well below the default 1,000,000 SAR/day minimum.
    outcome = make_outcome(
        latest_price=100.0, technical_snapshot={"volume_sma_20": 1000.0},
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    liquidity_gate = next(g for g in evaluation.gates if g.name == "liquidity")
    assert liquidity_gate.status is GateStatus.FAIL


def test_liquid_stock_passes_the_liquidity_gate():
    # price=100, volume_sma_20=50000 -> average traded value ~5,000,000 SAR/day.
    outcome = make_outcome(
        latest_price=100.0, technical_snapshot={"volume_sma_20": 50000.0},
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    liquidity_gate = next(g for g in evaluation.gates if g.name == "liquidity")
    assert liquidity_gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_missing_volume_data_is_not_evaluated_not_rejected():
    outcome = make_outcome(
        latest_price=100.0, technical_snapshot=None,
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    liquidity_gate = next(g for g in evaluation.gates if g.name == "liquidity")
    assert liquidity_gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_benchmark_data_is_always_not_evaluated_and_disclosed():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    benchmark_gate = next(g for g in evaluation.gates if g.name == "benchmark_data")
    assert benchmark_gate.status is GateStatus.NOT_EVALUATED
    assert any("TASI" in d for d in evaluation.disclosures)


# --- minimum candles ------------------------------------------------------


def test_insufficient_candle_history_is_rejected():
    outcome = make_outcome(
        context=make_context(bars_used=20),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "min_candles")
    assert gate.status is GateStatus.FAIL


def test_sufficient_candle_history_passes():
    outcome = make_outcome(
        context=make_context(bars_used=120),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "min_candles")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_untracked_bar_count_is_not_evaluated_not_blocked():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "min_candles")
    assert gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- OHLCV staleness (distinct from the scan/quote freshness gate above) --
# The production incident this closes: a live quote is always fetched
# fresh (see context_builder.build_analysis_context), so the
# data_freshness gate above can PASS even while historical_ohlcv
# ingestion has been quota-deferred for days -- this is the gate that
# actually catches technical indicators resting on stale bar history.


def test_stale_ohlcv_history_is_rejected():
    outcome = make_outcome(
        context=make_context(ohlcv_latest_bar_age_days=12.0),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "ohlcv_staleness")
    assert gate.status is GateStatus.FAIL


def test_fresh_ohlcv_history_passes():
    outcome = make_outcome(
        context=make_context(ohlcv_latest_bar_age_days=1.0),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "ohlcv_staleness")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_untracked_ohlcv_age_is_not_evaluated_not_blocked():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "ohlcv_staleness")
    assert gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- suspension ------------------------------------------------------------


def test_likely_suspended_symbol_is_rejected():
    outcome = make_outcome(
        context=make_context(likely_suspended=True),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "suspension")
    assert gate.status is GateStatus.FAIL


def test_normal_trading_activity_passes_the_suspension_gate():
    outcome = make_outcome(
        context=make_context(likely_suspended=False),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "suspension")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- abnormal spread ---------------------------------------------------


def test_wide_bid_ask_spread_is_rejected():
    # bid=100, ask=104 -> 4% spread, above the default 3% maximum.
    outcome = make_outcome(
        context=make_context(quote={"bid": 100.0, "ask": 104.0}),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "abnormal_spread")
    assert gate.status is GateStatus.FAIL


def test_tight_bid_ask_spread_passes():
    # bid=100, ask=100.5 -> 0.5% spread.
    outcome = make_outcome(
        context=make_context(quote={"bid": 100.0, "ask": 100.5}),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "abnormal_spread")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_missing_bid_ask_is_not_evaluated_not_blocked():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "abnormal_spread")
    assert gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- position sizing ---------------------------------------------------


def test_no_viable_position_size_is_rejected():
    outcome = make_outcome(decision=make_decision(
        recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0,
        position_size=PositionSize.NONE,
    ))
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "position_sizing")
    assert gate.status is GateStatus.FAIL


def test_a_real_position_size_passes():
    outcome = make_outcome(decision=make_decision(
        recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0,
        position_size=PositionSize.STANDARD,
    ))
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "position_sizing")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- news conflict -------------------------------------------------------


def test_buy_with_strongly_negative_news_sentiment_is_rejected():
    outcome = make_outcome(
        context=make_context(news_sentiment={"sentiment_score": -0.8, "article_count": 4}),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "news_conflict")
    assert gate.status is GateStatus.FAIL


def test_sell_with_strongly_positive_news_sentiment_is_rejected():
    outcome = make_outcome(
        context=make_context(news_sentiment={"sentiment_score": 0.8, "article_count": 4}),
        decision=make_decision(recommendation=Recommendation.SELL, expected_return_pct=-5.0),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "news_conflict")
    assert gate.status is GateStatus.FAIL


def test_buy_with_positive_news_sentiment_passes():
    outcome = make_outcome(
        context=make_context(news_sentiment={"sentiment_score": 0.6, "article_count": 4}),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "news_conflict")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_negative_sentiment_with_too_few_articles_is_not_evaluated():
    # A single negative headline should not be enough to reject a BUY.
    outcome = make_outcome(
        context=make_context(news_sentiment={"sentiment_score": -0.9, "article_count": 1}),
        decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0),
    )
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "news_conflict")
    assert gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_no_analyzed_news_is_not_evaluated_not_blocked():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "news_conflict")
    assert gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- fundamental conflict -----------------------------------------------


def test_buy_with_bearish_fundamentals_is_rejected():
    outcome = make_outcome(
        decision=make_decision(
            recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0,
            breakdown=[make_breakdown("Fundamental Analysis", points=-25.0)],
        ),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "fundamental_conflict")
    assert gate.status is GateStatus.FAIL


def test_sell_with_bullish_fundamentals_is_rejected():
    outcome = make_outcome(
        decision=make_decision(
            recommendation=Recommendation.SELL, expected_return_pct=-5.0,
            breakdown=[make_breakdown("Fundamental Analysis", points=25.0)],
        ),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "fundamental_conflict")
    assert gate.status is GateStatus.FAIL


def test_buy_with_bullish_fundamentals_passes():
    outcome = make_outcome(
        decision=make_decision(
            recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0,
            breakdown=[make_breakdown("Fundamental Analysis", points=20.0)],
        ),
    )
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "fundamental_conflict")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_no_fundamental_score_is_not_evaluated_not_blocked():
    outcome = make_outcome(decision=make_decision(
        recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0,
        breakdown=[make_breakdown("Technical Analysis", available=True)],
    ))
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "fundamental_conflict")
    assert gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- confidence calibration -----------------------------------------------


def test_low_calibrated_probability_is_rejected():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome, calibrated_success_probability=0.10)
    assert evaluation.status is PublicationStatus.REJECTED
    gate = next(g for g in evaluation.gates if g.name == "confidence_calibration")
    assert gate.status is GateStatus.FAIL


def test_healthy_calibrated_probability_passes():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome, calibrated_success_probability=0.75)
    gate = next(g for g in evaluation.gates if g.name == "confidence_calibration")
    assert gate.status is GateStatus.PASS
    assert evaluation.status is PublicationStatus.PUBLISHED


def test_no_calibration_supplied_is_not_evaluated_not_blocked():
    outcome = make_outcome(decision=make_decision(recommendation=Recommendation.BUY, expected_return_pct=5.0, risk_reward_ratio=2.0))
    evaluation = evaluate_publication(outcome)
    gate = next(g for g in evaluation.gates if g.name == "confidence_calibration")
    assert gate.status is GateStatus.NOT_EVALUATED
    assert evaluation.status is PublicationStatus.PUBLISHED


# --- HOLD is never gated by any of the new actionable-only gates ----------


def test_hold_is_never_gated_by_the_new_actionable_only_gates():
    outcome = make_outcome(
        context=make_context(quote={"bid": 100.0, "ask": 110.0}, news_sentiment={"sentiment_score": -0.9, "article_count": 5}),
        decision=make_decision(
            recommendation=Recommendation.HOLD, expected_return_pct=-1.0, risk_reward_ratio=None,
            position_size=PositionSize.NONE,
        ),
    )
    evaluation = evaluate_publication(outcome)
    assert evaluation.status is PublicationStatus.PUBLISHED
    for name in ("abnormal_spread", "position_sizing", "news_conflict", "fundamental_conflict", "confidence_calibration"):
        gate = next(g for g in evaluation.gates if g.name == name)
        assert gate.status is GateStatus.NOT_EVALUATED, f"{name} should not be evaluated for a HOLD"
