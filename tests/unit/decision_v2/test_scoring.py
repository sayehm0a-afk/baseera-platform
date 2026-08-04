import numpy as np
import pandas as pd

from src.analysis.decision_v2.config import DecisionV2Tuning
from src.analysis.decision_v2 import scoring
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine

TUNING = DecisionV2Tuning()


def _make_ohlcv(n=90, seed=1, drift=0.0):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(drift, 1.0, n))
    high = close + np.abs(rng.normal(0, 1, n))
    low = close - np.abs(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def _technical(seed=1, drift=0.0):
    return TechnicalAnalysisEngine().analyze(_make_ohlcv(seed=seed, drift=drift))


class TestTrendScore:
    def test_returns_none_without_technical_data(self):
        assert scoring.trend_score(None, 100.0) is None

    def test_returns_none_without_price(self):
        assert scoring.trend_score(_technical(), None) is None

    def test_score_is_within_bounds(self):
        score = scoring.trend_score(_technical(), 100.0)
        assert score is None or 0.0 <= score <= 100.0


class TestMomentumScore:
    def test_returns_none_without_technical_data(self):
        assert scoring.momentum_score(None) is None

    def test_score_within_bounds(self):
        score = scoring.momentum_score(_technical())
        assert score is None or 0.0 <= score <= 100.0


class TestVolumeScore:
    def test_returns_none_without_technical_data(self):
        assert scoring.volume_score(None) is None

    def test_score_within_bounds(self):
        score = scoring.volume_score(_technical())
        assert score is None or 0.0 <= score <= 100.0


class TestLiquidityScore:
    def test_none_when_average_traded_value_unknown(self):
        assert scoring.liquidity_score(None, 1_000_000.0) is None

    def test_exactly_at_minimum_is_fifty(self):
        assert scoring.liquidity_score(1_000_000.0, 1_000_000.0) == 50.0

    def test_at_three_times_minimum_is_capped_at_100(self):
        assert scoring.liquidity_score(3_000_000.0, 1_000_000.0) == 100.0

    def test_below_minimum_scores_below_fifty(self):
        assert scoring.liquidity_score(500_000.0, 1_000_000.0) < 50.0


class TestVolatilityScore:
    def test_none_when_atr_pct_unknown(self):
        assert scoring.volatility_score(None, TUNING) is None

    def test_sweet_spot_scores_high(self):
        mid = (TUNING.volatility_sweet_spot_low_pct + TUNING.volatility_sweet_spot_high_pct) / 2
        assert scoring.volatility_score(mid, TUNING) == 85.0

    def test_excessive_volatility_scores_low(self):
        score = scoring.volatility_score(TUNING.volatility_excessive_pct * 2, TUNING)
        assert score < 40.0

    def test_too_low_volatility_scores_below_sweet_spot(self):
        score = scoring.volatility_score(TUNING.volatility_sweet_spot_low_pct / 10, TUNING)
        assert score < 85.0


class TestRiskRewardScore:
    def test_none_when_ratio_unknown(self):
        assert scoring.risk_reward_score(None, 1.0) is None

    def test_exactly_at_minimum_is_fifty(self):
        assert scoring.risk_reward_score(1.0, 1.0) == 50.0

    def test_at_three_times_minimum_is_capped(self):
        assert scoring.risk_reward_score(3.0, 1.0) == 100.0

    def test_below_minimum_scores_below_fifty(self):
        assert scoring.risk_reward_score(0.5, 1.0) < 50.0


class TestMarketContextScore:
    def test_open_market_scores_higher_than_closed(self):
        assert scoring.market_context_score(True, True) > scoring.market_context_score(False, True)

    def test_unknown_status_scores_lowest(self):
        assert scoring.market_context_score(None, True) < scoring.market_context_score(False, True)

    def test_known_sector_adds_a_small_bonus(self):
        assert scoring.market_context_score(True, True) > scoring.market_context_score(True, False)


class TestDataQualityScore:
    def test_full_real_fresh_data_scores_high(self):
        score = scoring.data_quality_score(True, True, False, 1.0, 24.0, TUNING)
        assert score == 100.0

    def test_missing_technical_leg_penalized_heavily(self):
        score = scoring.data_quality_score(False, True, False, 1.0, 24.0, TUNING)
        assert score < 100.0

    def test_synthetic_data_scores_zero(self):
        score = scoring.data_quality_score(True, True, True, 1.0, 24.0, TUNING)
        assert score == 0.0

    def test_stale_data_is_capped(self):
        score = scoring.data_quality_score(True, True, False, 48.0, 24.0, TUNING)
        assert score <= TUNING.stale_data_penalty_score


class TestOpportunityQualityScore:
    def test_renormalizes_when_some_sub_scores_are_missing(self):
        sub_all = {
            "trend_score": 80.0, "momentum_score": 80.0, "volume_score": 80.0,
            "liquidity_score": 80.0, "volatility_score": 80.0, "risk_reward_score": 80.0,
            "market_context_score": 80.0, "data_quality_score": 80.0,
        }
        sub_partial = dict(sub_all)
        sub_partial["volume_score"] = None
        # All sub-scores equal -> renormalized weighted average is unaffected by which one is missing.
        assert scoring.opportunity_quality_score(sub_all, TUNING) == scoring.opportunity_quality_score(sub_partial, TUNING)

    def test_all_missing_returns_zero(self):
        sub = {k: None for k in [
            "trend_score", "momentum_score", "volume_score", "liquidity_score",
            "volatility_score", "risk_reward_score", "market_context_score", "data_quality_score",
        ]}
        assert scoring.opportunity_quality_score(sub, TUNING) == 0.0


class TestConflictingIndicators:
    def test_bullish_trend_bearish_momentum_is_flagged(self):
        assert scoring.conflicting_indicators(70.0, 30.0) is not None

    def test_bearish_trend_bullish_momentum_is_flagged(self):
        assert scoring.conflicting_indicators(30.0, 70.0) is not None

    def test_aligned_indicators_are_not_flagged(self):
        assert scoring.conflicting_indicators(70.0, 70.0) is None

    def test_missing_inputs_are_not_flagged(self):
        assert scoring.conflicting_indicators(None, 70.0) is None
