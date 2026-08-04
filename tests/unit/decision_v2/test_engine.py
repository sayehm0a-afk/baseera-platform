"""Integration tests for DecisionEngineV2 -- constructs a real
TechnicalAnalysisResult (via TechnicalAnalysisEngine, same helper
pattern as tests/unit/analysis/core/test_contracts.py) and a
directly-built `InvestmentDecision` fixture (decoupling these tests
from AIDecisionEngine's own scoring internals, which are already
covered by that engine's own test suite) to exercise the full
DecisionEngineV2.decide() path end to end.
"""

from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd
import pytest

from src.analysis.decision.types import (
    DecisionFactorBreakdown,
    EntryQuality,
    InvestmentDecision,
    PositionSize,
    RiskLevel,
    TimeHorizon,
)
from src.analysis.decision_v2.engine import DecisionEngineV2
from src.analysis.decision_v2.types import Decision, DataFreshnessStatus
from src.analysis.recommendation.types import AnalysisContext, Recommendation
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine


def _make_ohlcv(n=90, seed=1):
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0, 1.0, n))
    high = close + np.abs(rng.normal(0, 1, n))
    low = close - np.abs(rng.normal(0, 1, n))
    open_ = close + rng.normal(0, 0.5, n)
    volume = rng.integers(1_000_000, 5_000_000, n).astype(float)
    index = pd.date_range("2026-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume}, index=index
    )


def _technical():
    return TechnicalAnalysisEngine().analyze(_make_ohlcv())


def _context(price=100.0, technical=None, fundamental=None):
    return AnalysisContext(
        symbol="2222", technical_result=technical if technical is not None else _technical(),
        fundamental_result=fundamental, latest_price=price,
    )


def _buy_decision(price=100.0, target=112.0, stop=94.0) -> InvestmentDecision:
    return InvestmentDecision(
        symbol="2222",
        recommendation=Recommendation.BUY,
        confidence=75.0,
        final_score=68.0,
        target_price=target,
        stop_loss=stop,
        time_horizon=TimeHorizon.SHORT_TERM,
        expected_return_pct=round((target - price) / price * 100, 2),
        risk_level=RiskLevel.MEDIUM,
        position_size=PositionSize.STANDARD,
        reasons=["نمط فني إيجابي عام."],
        breakdown=[DecisionFactorBreakdown(category="Technical Analysis", points=18.0, weight=0.6, confidence=70.0, available=True)],
        signals=[],
        generated_at=datetime.now(timezone.utc),
        entry_quality=EntryQuality.GOOD,
        risk_reward_ratio=round((target - price) / (price - stop), 2),
    )


def _decide(ctx, decision, **overrides):
    kwargs = dict(
        company_name_ar="أرامكو السعودية",
        company_name_en="Saudi Aramco",
        sector="Energy",
        sector_ar="الطاقة",
        is_synthetic=False,
        data_source="SAHMK",
        quote_timestamp=datetime.now(timezone.utc),
        market_status="OPEN",
        market_is_open=True,
        scan_run_id=None,
    )
    kwargs.update(overrides)
    return DecisionEngineV2().decide(ctx, decision, **kwargs)


class TestBuyPath:
    def test_valid_buy_setup_produces_a_buy_like_decision(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.decision in (Decision.BUY_CANDIDATE, Decision.STRONG_BUY_CANDIDATE, Decision.WATCH, Decision.WAIT_FOR_ENTRY)

    def test_entry_zone_is_internally_consistent(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.entry_zone_low is not None:
            assert result.entry_zone_low <= result.entry_zone_high

    def test_stop_below_entry_zone(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.entry_zone_low is not None and result.stop_loss is not None:
            assert result.stop_loss < result.entry_zone_low

    def test_target_above_entry_zone(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.entry_zone_high is not None and result.target_1 is not None:
            assert result.target_1 > result.entry_zone_high

    def test_gates_are_populated_and_transparent(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert len(result.gates) > 0

    def test_analysis_version_and_provenance_are_set(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision(), scan_run_id=42)
        assert result.analysis_version
        assert result.data_source == "SAHMK"
        assert result.scan_run_id == 42
        assert result.decision_timestamp is not None

    def test_arabic_label_matches_decision(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        from src.analysis.decision_v2.types import DECISION_LABELS_AR
        assert result.decision_label_ar == DECISION_LABELS_AR[result.decision]


class TestMissedEntry:
    def test_price_run_past_entry_zone_becomes_wait_for_entry(self):
        # A tight, already-realized rally: price sits well above the
        # target-implying stop-anchored entry zone the InvestmentDecision
        # was computed for.
        ctx = _context(price=130.0)
        decision = _buy_decision(price=100.0, target=112.0, stop=94.0)
        result = _decide(ctx, decision)
        assert result.decision is Decision.WAIT_FOR_ENTRY


class TestHoldAndSellMapping:
    def test_hold_recommendation_has_no_entry_zone(self):
        ctx = _context()
        hold_decision = InvestmentDecision(
            symbol="2222", recommendation=Recommendation.HOLD, confidence=60.0, final_score=50.0,
            target_price=None, stop_loss=None, time_horizon=TimeHorizon.SHORT_TERM,
            expected_return_pct=None, risk_level=RiskLevel.MEDIUM, position_size=PositionSize.NONE,
            reasons=[], breakdown=[], signals=[], generated_at=datetime.now(timezone.utc),
        )
        result = _decide(ctx, hold_decision)
        assert result.decision is Decision.HOLD
        assert result.entry_zone_low is None and result.entry_zone_high is None


class TestClosedMarketAndFreshness:
    def test_closed_market_caps_confidence_and_warns(self):
        ctx = _context()
        result_open = _decide(ctx, _buy_decision(), market_status="OPEN", market_is_open=True)
        result_closed = _decide(ctx, _buy_decision(), market_status="CLOSED", market_is_open=False)
        assert result_closed.confidence_score <= result_open.confidence_score
        assert any("مغلق" in w for w in result_closed.warnings)

    def test_stale_quote_marks_freshness_as_not_live(self):
        ctx = _context()
        old_ts = datetime.now(timezone.utc) - timedelta(hours=72)
        result = _decide(ctx, _buy_decision(), quote_timestamp=old_ts, market_status="CLOSED", market_is_open=False)
        assert result.data_freshness_status != DataFreshnessStatus.LIVE

    def test_synthetic_data_is_flagged_as_unknown_freshness(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision(), is_synthetic=True)
        assert result.data_freshness_status is DataFreshnessStatus.UNKNOWN


class TestInsufficientData:
    def test_no_technical_data_is_insufficient_data(self):
        ctx = AnalysisContext(symbol="9999", technical_result=None, fundamental_result=None, latest_price=None)
        insufficient_decision = InvestmentDecision(
            symbol="9999", recommendation=Recommendation.HOLD, confidence=0.0, final_score=50.0,
            target_price=None, stop_loss=None, time_horizon=TimeHorizon.SHORT_TERM,
            expected_return_pct=None, risk_level=RiskLevel.MEDIUM, position_size=PositionSize.NONE,
            reasons=[], breakdown=[], signals=[], generated_at=datetime.now(timezone.utc),
        )
        # has_technical is derived from context.technical_result, not the recommendation itself
        result = _decide(ctx, insufficient_decision)
        assert result.decision is Decision.INSUFFICIENT_DATA


class TestConfidenceNeverEscapesBounds:
    @pytest.mark.parametrize("market_is_open", [True, False, None])
    def test_confidence_stays_within_0_100(self, market_is_open):
        ctx = _context()
        result = _decide(ctx, _buy_decision(), market_is_open=market_is_open, market_status="OPEN" if market_is_open else "CLOSED")
        assert 0.0 <= result.confidence_score <= 100.0
