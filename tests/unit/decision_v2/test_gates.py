"""Unit tests for the 15 Decision Engine V2 publication gates
(src.analysis.decision_v2.gates) -- pure function tests over
`GateInputs`, no I/O, no dependency on TechnicalAnalysisEngine's real
indicator math (that integration is covered separately in
test_engine.py)."""

from src.analysis.decision.types import EntryQuality
from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2.gates import GateInputs, evaluate_decision
from src.analysis.decision_v2.types import Decision
from src.analysis.recommendation.types import Recommendation

TUNING = DecisionV2Tuning()


def _base_buy_inputs(**overrides) -> GateInputs:
    defaults = dict(
        has_technical=True,
        recommendation=Recommendation.BUY,
        direction=1,
        is_synthetic=False,
        data_age_hours=1.0,
        max_age_hours=24.0,
        price=100.0,
        entry_zone_low=97.0,
        entry_zone_high=101.0,
        stop_loss=94.0,
        target_1=110.0,
        risk_reward_ratio=2.0,
        min_risk_reward_ratio=1.0,
        average_traded_value=5_000_000.0,
        min_average_traded_value=1_000_000.0,
        atr_pct=0.02,
        excessive_volatility_pct=0.08,
        market_status_known=True,
        available_sub_score_count=6,
        fundamentals_available=True,
        news_available=True,
        entry_quality=EntryQuality.GOOD,
        price_missed_entry_zone=False,
    )
    defaults.update(overrides)
    return GateInputs(**defaults)


class TestBaselineMappings:
    def test_hold_maps_to_hold(self):
        inputs = _base_buy_inputs(recommendation=Recommendation.HOLD, direction=0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.HOLD

    def test_sell_maps_to_reduce(self):
        inputs = _base_buy_inputs(recommendation=Recommendation.SELL, direction=-1)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REDUCE

    def test_strong_sell_maps_to_exit(self):
        inputs = _base_buy_inputs(recommendation=Recommendation.STRONG_SELL, direction=-1)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.EXIT

    def test_buy_with_everything_passing_is_buy_candidate(self):
        result = evaluate_decision(_base_buy_inputs(), TUNING)
        assert result.decision is Decision.BUY_CANDIDATE

    def test_strong_buy_with_everything_passing_is_strong_buy_candidate(self):
        inputs = _base_buy_inputs(recommendation=Recommendation.STRONG_BUY)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.STRONG_BUY_CANDIDATE


class TestDataAuthenticityAndAvailability:
    def test_synthetic_data_is_rejected_regardless_of_everything_else(self):
        inputs = _base_buy_inputs(is_synthetic=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT
        assert any(g.name == "real_data_source" and not g.passed for g in result.gates)

    def test_missing_technical_data_is_insufficient_data(self):
        inputs = _base_buy_inputs(has_technical=False, recommendation=None, direction=0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA

    def test_no_recommendation_is_insufficient_data(self):
        inputs = _base_buy_inputs(recommendation=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA

    def test_invalid_price_is_insufficient_data(self):
        inputs = _base_buy_inputs(price=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA

    def test_negative_price_is_insufficient_data(self):
        inputs = _base_buy_inputs(price=-5.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.INSUFFICIENT_DATA


class TestStaleData:
    def test_stale_data_downgrades_buy_to_watch_not_reject(self):
        inputs = _base_buy_inputs(data_age_hours=48.0, max_age_hours=24.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH
        assert any("بيانات" in w for w in result.warnings)

    def test_stale_data_does_not_block_hold(self):
        inputs = _base_buy_inputs(
            recommendation=Recommendation.HOLD, direction=0, data_age_hours=48.0, max_age_hours=24.0,
        )
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.HOLD


class TestEntryZoneAndTargetOrdering:
    def test_entry_zone_low_above_high_is_rejected(self):
        inputs = _base_buy_inputs(entry_zone_low=105.0, entry_zone_high=95.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_missing_entry_zone_is_rejected(self):
        inputs = _base_buy_inputs(entry_zone_low=None, entry_zone_high=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_stop_above_entry_zone_low_is_rejected(self):
        inputs = _base_buy_inputs(stop_loss=99.0)  # entry_zone_low=97.0 -- stop must be < 97
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_target_below_entry_zone_high_is_rejected(self):
        inputs = _base_buy_inputs(target_1=100.5)  # entry_zone_high=101.0 -- target must be > 101
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT


class TestMissedEntry:
    def test_price_past_entry_zone_becomes_wait_for_entry(self):
        inputs = _base_buy_inputs(price_missed_entry_zone=True)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WAIT_FOR_ENTRY
        assert any("مطاردة" in w for w in result.warnings)


class TestRiskRewardAndLiquidity:
    def test_risk_reward_below_minimum_is_rejected(self):
        inputs = _base_buy_inputs(risk_reward_ratio=0.5, min_risk_reward_ratio=1.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_missing_risk_reward_is_rejected(self):
        inputs = _base_buy_inputs(risk_reward_ratio=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_liquidity_below_minimum_is_rejected(self):
        inputs = _base_buy_inputs(average_traded_value=100_000.0, min_average_traded_value=1_000_000.0)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.REJECT

    def test_unknown_liquidity_does_not_block(self):
        inputs = _base_buy_inputs(average_traded_value=None)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE


class TestVolatilityAndEvidence:
    def test_excessive_volatility_downgrades_to_watch(self):
        inputs = _base_buy_inputs(atr_pct=0.15, excessive_volatility_pct=0.08)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH

    def test_single_indicator_confidence_downgrades_to_watch(self):
        inputs = _base_buy_inputs(available_sub_score_count=1)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH

    def test_poor_entry_quality_downgrades_to_watch_not_reject(self):
        inputs = _base_buy_inputs(entry_quality=EntryQuality.POOR)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.WATCH


class TestDisclosuresNeverBlock:
    def test_missing_fundamentals_does_not_block_a_valid_buy(self):
        inputs = _base_buy_inputs(fundamentals_available=False)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        assert any("أساسية" in d for d in result.disclosures)

    def test_missing_news_does_not_block_a_valid_buy(self):
        inputs = _base_buy_inputs(news_available=False)
        result = evaluate_decision(inputs, TUNING)
        assert result.decision is Decision.BUY_CANDIDATE
        assert any("إخبارية" in d for d in result.disclosures)
