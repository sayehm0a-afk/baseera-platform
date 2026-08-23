"""Integration tests for DecisionEngineV2 -- constructs a real
TechnicalAnalysisResult (via TechnicalAnalysisEngine, same helper
pattern as tests/unit/analysis/core/test_contracts.py) and a
directly-built `InvestmentDecision` fixture (decoupling these tests
from AIDecisionEngine's own scoring internals, which are already
covered by that engine's own test suite) to exercise the full
DecisionEngineV2.decide() path end to end.
"""

from datetime import date, datetime, timedelta, timezone

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
from src.analysis.decision_v2.types import DECISION_LABELS_AR, Decision, DataFreshnessStatus
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.fundamental.types import FundamentalFacts
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


def _context(price=100.0, technical=None, fundamental=None, extra=None):
    return AnalysisContext(
        symbol="2222", technical_result=technical if technical is not None else _technical(),
        fundamental_result=fundamental, latest_price=price, extra=extra or {},
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
    def test_price_moderately_past_entry_zone_becomes_wait_for_entry(self):
        """Mild overrun (not severe) -- exact prior WAIT_FOR_ENTRY
        behavior, unaffected by the severity gate."""
        ctx = _context(price=103.25)
        decision = _buy_decision(price=100.0, target=112.0, stop=94.0)
        result = _decide(ctx, decision)
        assert result.decision is Decision.WAIT_FOR_ENTRY

    def test_severely_extended_price_becomes_watch_not_wait_for_entry(self):
        """A genuinely severe overrun (price ran to 130 vs. a ~103
        entry zone) now moves to Decision.WATCH -- a real decision
        consequence for the already-computed severity signal, replacing
        the old behavior where this stayed the coarser WAIT_FOR_ENTRY
        indefinitely. Verified against the real engine (not a
        hand-constructed GateInputs) at price=130.0 -- empirically
        confirmed severely_missed before writing this assertion."""
        ctx = _context(price=130.0)
        decision = _buy_decision(price=100.0, target=112.0, stop=94.0)
        result = _decide(ctx, decision)
        assert result.decision is Decision.WATCH

    def test_severely_extended_price_never_produces_reject_exit_or_reduce(self):
        """Severe anti-chase must never imply a SELL-like/invalidated-
        setup decision -- this is a bullish overrun, not a broken
        trade."""
        ctx = _context(price=130.0)
        decision = _buy_decision(price=100.0, target=112.0, stop=94.0)
        result = _decide(ctx, decision)
        assert result.decision not in (Decision.REJECT, Decision.EXIT, Decision.REDUCE)

    def test_valid_entry_is_ready_now(self):
        """A price still inside its own entry zone is READY_NOW,
        unaffected by the anti-chase gate."""
        from src.analysis.decision_v2.types import EntryStatus
        ctx = _context(price=100.0)
        decision = _buy_decision(price=100.0, target=112.0, stop=94.0)
        result = _decide(ctx, decision)
        assert result.decision in (Decision.BUY_CANDIDATE, Decision.STRONG_BUY_CANDIDATE)
        assert result.entry_status is EntryStatus.READY_NOW


class TestSevereAntiChaseGeometryAndDownstreamConsistency:
    def test_stop_and_target_unchanged_between_mild_and_severe(self):
        """The new severity gate only changes the Decision, never
        stop_loss/target_1 -- both are echoed straight through from
        investment_decision.stop_loss/target_price regardless of price
        or severity, never recomputed after evaluate_decision() runs.
        (entry_zone_low/high are deliberately NOT compared here --
        structure.compute_entry_zone anchors the zone to the current
        price/ATR by design, so it legitimately differs between two
        different prices; that is pre-existing, unrelated behavior, not
        a side effect of this gate -- see
        TestFailedBreakoutGate.test_geometry_and_confidence_unchanged_by_failed_breakout_gate
        for the correct same-price comparison proving the new gates
        introduce zero geometry side effects.)"""
        mild = _decide(_context(price=103.25), _buy_decision(price=100.0, target=112.0, stop=94.0))
        severe = _decide(_context(price=130.0), _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert mild.decision is Decision.WAIT_FOR_ENTRY
        assert severe.decision is Decision.WATCH
        assert mild.stop_loss == severe.stop_loss == 94.0
        assert mild.target_1 == severe.target_1 == 112.0
        assert mild.confidence_score == severe.confidence_score

    def test_existing_holder_never_receives_exit_guidance_from_severe_overrun(self):
        """src.api.routes.portfolio's _HOLDER_GUIDANCE_MAP (unchanged by
        this gate) must map the Decision this engine now returns for a
        severe overrun (Decision.WATCH) to continued-monitoring
        guidance, never EXIT -- this is the concrete evidence the prior
        architecture review used to reject REJECT as the terminal state
        for this case."""
        from src.api.routes.portfolio import _HOLDER_GUIDANCE_MAP, _holder_guidance_from_decision

        severe = _decide(_context(price=130.0), _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert severe.decision is Decision.WATCH
        guidance = _holder_guidance_from_decision(severe.decision.value)
        assert guidance is not None
        code, label_ar = guidance
        assert code == "WATCH"
        assert code != "EXIT"
        assert _HOLDER_GUIDANCE_MAP["WATCH"][0] == "WATCH"
        assert _HOLDER_GUIDANCE_MAP["REJECT"][0] == "EXIT"  # unchanged, confirms REJECT was correctly avoided


class TestFailedBreakoutGate:
    """FAILED_BREAKOUT downgrades an otherwise-actionable BUY-like
    decision to WATCH. Every other breakout_status value, including the
    safe default NOT_APPLICABLE, is unaffected."""

    def test_failed_breakout_downgrades_buy_candidate_to_watch(self):
        ctx = _context(price=100.0, extra={"breakout_confirmation": {"status": "FAILED_BREAKOUT"}})
        result = _decide(ctx, _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert result.decision is Decision.WATCH
        gate = next(g for g in result.gates if g.name == "breakout_not_failed")
        assert gate.status.value == "FAIL"

    def test_geometry_and_confidence_unchanged_by_failed_breakout_gate(self):
        """The new gate only changes the Decision, never entry zone,
        stop, targets, or confidence -- verified against the identical
        inputs with and without the FAILED_BREAKOUT signal."""
        baseline = _decide(_context(price=100.0), _buy_decision(price=100.0, target=112.0, stop=94.0))
        with_failed_breakout = _decide(
            _context(price=100.0, extra={"breakout_confirmation": {"status": "FAILED_BREAKOUT"}}),
            _buy_decision(price=100.0, target=112.0, stop=94.0),
        )
        assert baseline.decision is Decision.BUY_CANDIDATE
        assert with_failed_breakout.decision is Decision.WATCH
        assert baseline.entry_zone_low == with_failed_breakout.entry_zone_low
        assert baseline.entry_zone_high == with_failed_breakout.entry_zone_high
        assert baseline.stop_loss == with_failed_breakout.stop_loss
        assert baseline.target_1 == with_failed_breakout.target_1
        assert baseline.target_2 == with_failed_breakout.target_2
        assert baseline.target_3 == with_failed_breakout.target_3
        assert baseline.confidence_score == with_failed_breakout.confidence_score
        assert baseline.risk_reward_target_1 == with_failed_breakout.risk_reward_target_1

    def test_not_applicable_default_is_byte_identical_to_pre_repair(self):
        """Omitting breakout_confirmation entirely (every caller before
        this gate existed) is unaffected."""
        with_default = _decide(_context(price=100.0, extra={}), _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert with_default.decision is Decision.BUY_CANDIDATE

    def test_confirmed_breakout_unaffected(self):
        ctx = _context(price=100.0, extra={"breakout_confirmation": {"status": "CONFIRMED_BREAKOUT"}})
        result = _decide(ctx, _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert result.decision is Decision.BUY_CANDIDATE

    def test_early_breakout_unaffected(self):
        ctx = _context(price=100.0, extra={"breakout_confirmation": {"status": "EARLY_BREAKOUT"}})
        result = _decide(ctx, _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert result.decision is Decision.BUY_CANDIDATE

    def test_unconfirmed_breakout_unaffected(self):
        ctx = _context(price=100.0, extra={"breakout_confirmation": {"status": "UNCONFIRMED_BREAKOUT"}})
        result = _decide(ctx, _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert result.decision is Decision.BUY_CANDIDATE

    def test_sequence_unverified_unaffected(self):
        ctx = _context(price=100.0, extra={"breakout_confirmation": {"status": "SEQUENCE_UNVERIFIED"}})
        result = _decide(ctx, _buy_decision(price=100.0, target=112.0, stop=94.0))
        assert result.decision is Decision.BUY_CANDIDATE

    def test_failed_breakout_does_not_affect_hold_sell_reduce_exit(self):
        extra = {"breakout_confirmation": {"status": "FAILED_BREAKOUT"}}

        def _sell_side_decision(recommendation):
            return InvestmentDecision(
                symbol="2222", recommendation=recommendation, confidence=60.0, final_score=30.0,
                target_price=90.0, stop_loss=105.0, time_horizon=TimeHorizon.SHORT_TERM,
                expected_return_pct=-10.0, risk_level=RiskLevel.MEDIUM, position_size=PositionSize.NONE,
                reasons=[], breakdown=[], signals=[], generated_at=datetime.now(timezone.utc),
            )

        hold_decision = InvestmentDecision(
            symbol="2222", recommendation=Recommendation.HOLD, confidence=60.0, final_score=50.0,
            target_price=None, stop_loss=None, time_horizon=TimeHorizon.SHORT_TERM,
            expected_return_pct=None, risk_level=RiskLevel.MEDIUM, position_size=PositionSize.NONE,
            reasons=[], breakdown=[], signals=[], generated_at=datetime.now(timezone.utc),
        )
        assert _decide(_context(price=100.0, extra=extra), hold_decision).decision is Decision.HOLD
        assert _decide(
            _context(price=100.0, extra=extra), _sell_side_decision(Recommendation.SELL)
        ).decision is Decision.REDUCE
        assert _decide(
            _context(price=100.0, extra=extra), _sell_side_decision(Recommendation.STRONG_SELL)
        ).decision is Decision.EXIT


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

    def test_confidence_stays_within_bounds_under_multiple_stacked_caps(self):
        """Phase 2I: closed market + a very stale quote + synthetic
        (fabricated) data all cap confidence independently -- stacked
        together, the combined penalty must still clamp into [0, 100],
        never go negative or NaN, no matter how many caps compound."""
        ctx = _context(fundamental=None)
        old_ts = datetime.now(timezone.utc) - timedelta(hours=72)
        result = _decide(
            ctx, _buy_decision(),
            market_status="CLOSED", market_is_open=False,
            quote_timestamp=old_ts, is_synthetic=True,
        )
        assert 0.0 <= result.confidence_score <= 100.0
        assert result.confidence_score == result.confidence_score  # not NaN


class TestPhase2ACanonicalFields:
    """Phase 2A: the canonical stock-intelligence extension fields --
    trade classification, price plan, support/resistance, liquidity/
    accumulation, confidence breakdown, and Arabic reasoning. Every
    assertion here is about internal consistency (does the derived
    field agree with the primitive fields it was built from), never
    about the exact numeric value of an indicator on synthetic OHLCV
    data.
    """

    def test_is_real_data_reflects_is_synthetic(self):
        ctx = _context()
        real = _decide(ctx, _buy_decision(), is_synthetic=False)
        synthetic = _decide(ctx, _buy_decision(), is_synthetic=True)
        unknown = _decide(ctx, _buy_decision(), is_synthetic=None)
        assert real.is_real_data is True
        assert synthetic.is_real_data is False
        assert unknown.is_real_data is False

    def test_confidence_breakdown_aliases_the_matching_sub_scores(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.technical_confidence == result.sub_scores.trend_score
        assert result.momentum_confidence == result.sub_scores.momentum_score
        assert result.liquidity_confidence == result.sub_scores.liquidity_score
        assert result.market_context_confidence == result.sub_scores.market_context_score
        assert result.data_quality_confidence == result.sub_scores.data_quality_score

    def test_trade_type_is_only_assigned_when_a_holding_period_exists(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.expected_holding_period_min_days is not None:
            assert result.trade_type is not None
            assert result.trade_type_label_ar != "غير محدد"

    def test_entry_status_is_ready_now_only_for_buy_like_decisions(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.decision in (Decision.STRONG_BUY_CANDIDATE, Decision.BUY_CANDIDATE):
            assert result.entry_status.value == "READY_NOW"
            assert result.entry_status_label_ar == "مناسب الآن"

    def test_entry_status_never_assigns_the_unimplemented_breakout_state(self):
        """Section E's CONDITIONAL_ON_BREAKOUT is defined for API
        compatibility but requires a real breakout-pattern detector
        (deferred to Phase 2F) -- must never be assigned today."""
        for seed in range(1, 6):
            ctx = _context(technical=TechnicalAnalysisEngine().analyze(_make_ohlcv(seed=seed)))
            result = _decide(ctx, _buy_decision())
            assert result.entry_status.value != "CONDITIONAL_ON_BREAKOUT"

    def test_best_entry_price_is_within_the_entry_zone_when_present(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.best_entry_price is not None and result.entry_zone_low is not None:
            assert result.entry_zone_low <= result.best_entry_price <= result.entry_zone_high

    def test_risk_level_and_entry_quality_labels_are_populated_arabic_text(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.risk_level == "MEDIUM"
        assert result.risk_level_label_ar == "متوسطة"
        assert result.entry_quality == "GOOD"
        assert result.entry_quality_label_ar == "جيدة"

    def test_invalidation_price_matches_the_stop_loss(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.invalidation_price == result.stop_loss

    def test_estimated_days_to_target_are_non_negative_when_present(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        for days in (result.estimated_days_target_1, result.estimated_days_target_2, result.estimated_days_target_3):
            if days is not None:
                assert days >= 0

    def test_nearest_support_never_exceeds_price_and_nearest_resistance_never_below_it(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.nearest_support is not None and result.current_price is not None:
            assert result.nearest_support <= result.current_price
        if result.nearest_resistance is not None and result.current_price is not None:
            assert result.nearest_resistance >= result.current_price

    def test_major_support_is_never_closer_to_price_than_nearest_support(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        if result.major_support is not None and result.nearest_support is not None:
            assert result.major_support <= result.nearest_support

    def test_breakout_and_breakdown_levels_alias_nearest_resistance_and_support(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.breakout_level == result.nearest_resistance
        assert result.breakdown_level == result.nearest_support

    def test_relative_volume_is_real_only_when_a_quote_volume_and_average_are_both_available(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        # This test's AnalysisContext.extra has no "quote" leg -- current_volume
        # must stay honestly absent, never fabricated.
        assert result.current_volume is None
        assert result.relative_volume is None

    def test_accumulation_score_aliases_the_volume_sub_score(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.accumulation_score == result.sub_scores.volume_score

    def test_technical_evidence_bundle_is_populated_when_technical_data_exists(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert isinstance(result.technical_evidence, dict)
        assert len(result.technical_evidence) > 0
        assert "rsi_14" in result.technical_evidence

    def test_technical_evidence_bundle_is_empty_without_technical_data(self):
        ctx = AnalysisContext(symbol="9999", technical_result=None, fundamental_result=None, latest_price=None)
        insufficient_decision = InvestmentDecision(
            symbol="9999", recommendation=Recommendation.HOLD, confidence=0.0, final_score=50.0,
            target_price=None, stop_loss=None, time_horizon=TimeHorizon.SHORT_TERM,
            expected_return_pct=None, risk_level=RiskLevel.MEDIUM, position_size=PositionSize.NONE,
            reasons=[], breakdown=[], signals=[], generated_at=datetime.now(timezone.utc),
        )
        result = _decide(ctx, insufficient_decision)
        assert result.technical_evidence == {}

    def test_decision_summary_contains_the_decision_label_and_confidence(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.decision_label_ar in result.decision_summary_ar
        assert result.trade_type_label_ar in result.decision_summary_ar or result.trade_type_label_ar == "غير محدد"

    def test_why_now_and_why_not_stronger_are_never_empty(self):
        ctx = _context()
        result = _decide(ctx, _buy_decision())
        assert result.why_now_ar != ""
        assert result.why_not_stronger_ar != ""

    def test_decision_labels_use_the_canonical_phase2a_taxonomy(self):
        assert DECISION_LABELS_AR[Decision.STRONG_BUY_CANDIDATE] == "شراء قوي"
        assert DECISION_LABELS_AR[Decision.BUY_CANDIDATE] == "شراء"
        assert DECISION_LABELS_AR[Decision.WAIT_FOR_ENTRY] == "انتظار"
        assert DECISION_LABELS_AR[Decision.WATCH] == "مراقبة"
        assert DECISION_LABELS_AR[Decision.HOLD] == "احتفاظ"
        assert DECISION_LABELS_AR[Decision.REDUCE] == "تخفيف"
        assert DECISION_LABELS_AR[Decision.EXIT] == "خروج"
        assert DECISION_LABELS_AR[Decision.REJECT] == "رفض التوصية"
        assert DECISION_LABELS_AR[Decision.INSUFFICIENT_DATA] == "بيانات غير كافية"


def _fundamental_facts(**overrides) -> FundamentalFacts:
    defaults = dict(
        stock_id=1, period_type="annual", fiscal_period_end=date(2024, 12, 31),
        revenue=1000.0, gross_profit=400.0, net_income=150.0, total_assets=3000.0,
        total_liabilities=1200.0, total_equity=1800.0, current_assets=700.0,
        current_liabilities=400.0, inventory=100.0, cash_and_equivalents=200.0,
        total_debt=500.0, shares_outstanding=500, eps=0.3, dividend_per_share=0.1,
    )
    defaults.update(overrides)
    return FundamentalFacts(**defaults)


class TestFundamentalSummaryWiring:
    def test_no_fundamental_result_yields_the_not_available_default(self):
        ctx = _context(fundamental=None)
        result = _decide(ctx, _buy_decision())
        assert all(v is None for v in result.fundamental_summary.values())
        assert "غير متوفرة" in result.fundamental_summary_ar

    def test_real_fundamental_result_populates_real_ratios_not_fabricated(self):
        fundamental = FundamentalAnalysisEngine().analyze(
            _fundamental_facts(),
            prior_facts=_fundamental_facts(
                fiscal_period_end=date(2023, 12, 31), revenue=800.0, net_income=100.0, eps=0.2
            ),
            market_price=15.0,
        )
        ctx = _context(fundamental=fundamental)
        result = _decide(ctx, _buy_decision())
        assert result.fundamental_summary["revenue_growth"] == pytest.approx(fundamental.revenue_growth)
        assert result.fundamental_summary["return_on_equity"] == pytest.approx(fundamental.return_on_equity)
        assert result.fundamental_summary["price_to_earnings"] == pytest.approx(fundamental.price_to_earnings)
        assert result.fundamental_summary_ar != ""


class TestNewsImpactWiring:
    def test_no_news_sentiment_extra_yields_no_relevant_news(self):
        ctx = _context(extra={})
        result = _decide(ctx, _buy_decision())
        assert result.news_impact == "NO_RELEVANT_NEWS"

    def test_real_news_sentiment_extra_is_classified_not_fabricated(self):
        ctx = _context(extra={"news_sentiment": {"sentiment_score": 0.5, "article_count": 4}})
        result = _decide(ctx, _buy_decision())
        assert result.news_impact == "POSITIVE"
        assert "4" in result.news_impact_summary_ar

    def test_negative_news_sentiment_is_classified_negative(self):
        ctx = _context(extra={"news_sentiment": {"sentiment_score": -0.5, "article_count": 2}})
        result = _decide(ctx, _buy_decision())
        assert result.news_impact == "NEGATIVE"
