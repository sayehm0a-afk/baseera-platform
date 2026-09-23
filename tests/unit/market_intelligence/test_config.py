"""Unit tests for src.market_intelligence.config's Basirah Radar V2 /
Stage 1 getters -- mirrors tests/unit/decision_v2/test_config.py's own
weight-sum-to-one convention, since Stage 1's ranking_score is built the
same way (a DecisionV2Tuning instance whose weights come from these
getters, see stage1_local_scan.py::_score_symbol)."""

import os
from unittest import mock

from src.market_intelligence import config


def test_stage1_ranking_weights_sum_to_one_at_default():
    total = (
        config.get_stage1_trend_weight()
        + config.get_stage1_momentum_weight()
        + config.get_stage1_volume_weight()
        + config.get_stage1_liquidity_weight()
        + config.get_stage1_volatility_weight()
        + config.get_stage1_risk_reward_weight()
    )
    assert round(total, 6) == 1.0


def test_stage1_getters_read_env_at_call_time_not_import_time():
    """Matches this module's own established convention (every other
    getter in market_intelligence/config.py reads os.getenv at call
    time) -- lets tests monkeypatch per-test without reloading the
    module."""
    with mock.patch.dict(os.environ, {"RADAR_STAGE1_TRENDING_ADX_THRESHOLD": "40.0"}):
        assert config.get_stage1_trending_adx_threshold() == 40.0
    assert config.get_stage1_trending_adx_threshold() == 25.0


def test_stage1_threshold_defaults_match_documented_values():
    assert config.get_stage1_abnormal_volume_ratio() == 2.0
    assert config.get_stage1_trending_adx_threshold() == 25.0
    assert config.get_stage1_rsi_oversold() == 30.0
    assert config.get_stage1_rsi_overbought() == 70.0
    assert config.get_stage1_min_dollar_volume_sar() == 100_000.0
    assert config.get_stage1_atr_reward_multiple() == 2.0
    assert config.get_stage1_atr_risk_multiple() == 1.0
    assert config.get_radar_stage2_candidate_cap() == 15


def test_market_risk_breadth_window_runs_default_and_env_override():
    """2026-09-23 fix: default 5, reads os.getenv at call time like every
    other getter in this module."""
    assert config.get_market_risk_breadth_window_runs() == 5
    with mock.patch.dict(os.environ, {"MARKET_RISK_BREADTH_WINDOW_RUNS": "10"}):
        assert config.get_market_risk_breadth_window_runs() == 10
    assert config.get_market_risk_breadth_window_runs() == 5


def test_min_calibrated_success_probability_default_is_60_percent():
    """2026-09-17 explicit product decision: lowered from 0.70 (raised
    2026-09-16 from 0.35, which filtered out nothing) after real
    production evidence the next trading day showed 0.70 published zero
    BUY/SELL candidates all day against a real calibrated-confidence
    distribution clustering at 54-61%. 0.60 is the real middle ground:
    a genuinely raised bar over 0.35, while still letting the upper end
    of that real distribution publish."""
    assert config.get_min_calibrated_success_probability() == 0.60


def test_min_calibrated_success_probability_reads_env_at_call_time():
    with mock.patch.dict(os.environ, {"MARKET_MIN_CALIBRATED_SUCCESS_PROBABILITY": "0.5"}):
        assert config.get_min_calibrated_success_probability() == 0.5
    assert config.get_min_calibrated_success_probability() == 0.60
