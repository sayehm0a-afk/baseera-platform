from src.analysis.decision_v2.config import DecisionV2Tuning


def test_sub_score_weights_sum_to_one():
    tuning = DecisionV2Tuning()
    total = (
        tuning.trend_weight
        + tuning.momentum_weight
        + tuning.volume_weight
        + tuning.liquidity_weight
        + tuning.volatility_weight
        + tuning.risk_reward_weight
        + tuning.market_context_weight
        + tuning.data_quality_weight
    )
    assert round(total, 6) == 1.0
