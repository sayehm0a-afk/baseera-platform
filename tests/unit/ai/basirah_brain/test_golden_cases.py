"""Deterministic golden analyst fixtures (Stage 1 mandate, CASE A-F) --
each pins a realistic combination of deterministic-engine evidence to
an expected Brain outcome family, run through the full
`BasirahBrainService.analyze_shadow()` path with the deterministic
`MockBasirahBrainProvider`.

These are fixture/plumbing tests, not a claim that the mock provider's
simple rule-based logic *is* real analyst reasoning -- they prove the
safety pipeline (hard-gate ceiling, price-geometry normalization,
persistence) behaves correctly across the full range of deterministic-
engine states a real provider will eventually be asked to reason over.
"""

import pytest

from src.analysis.decision_v2.types import DataFreshnessStatus, Decision, GateOutcome, GateStatus
from src.ai.basirah_brain.providers.mock_provider import (
    MockBasirahBrainProvider,
    hard_gate_override_attempt_response,
)
from src.ai.basirah_brain.service import BasirahBrainService

from .conftest import make_decision_result


async def _run(dr, stock, session_factory, response_factory=None):
    service = BasirahBrainService(
        provider=MockBasirahBrainProvider(response_factory=response_factory), session_factory=session_factory
    )
    return await service.analyze_shadow(dr, stock)


@pytest.mark.asyncio
async def test_case_a_strong_clean_setup_may_buy_or_wait(session_factory, stock):
    """Strong trend, healthy liquidity, good RR, not extended, clean data."""
    dr = make_decision_result(
        decision=Decision.STRONG_BUY_CANDIDATE,
        confidence_score=85.0,
        data_freshness_status=DataFreshnessStatus.LIVE,
        liquidity_quality_ar="ممتازة",
    )
    result = await _run(dr, stock, session_factory)
    assert result.decision.brain_decision in {"BUY", "WAIT_FOR_ENTRY"}


@pytest.mark.asyncio
async def test_case_b_overextended_near_resistance_never_buys(session_factory, stock):
    """Strong score but price already overextended -- the deterministic
    engine itself classifies this as WAIT_FOR_ENTRY (anti-chase), so the
    Brain's ceiling never includes BUY."""
    dr = make_decision_result(decision=Decision.WAIT_FOR_ENTRY, confidence_score=75.0)
    result = await _run(dr, stock, session_factory)
    assert result.decision.brain_decision != "BUY"
    assert result.decision.brain_decision in {"WAIT_FOR_ENTRY", "WATCH", "NO_TRADE"}


@pytest.mark.asyncio
async def test_case_c_positive_technicals_but_stale_data_forces_no_trade(session_factory, stock):
    """Positive technicals, but stale price data must block any BUY."""
    dr = make_decision_result(
        decision=Decision.BUY_CANDIDATE,
        confidence_score=80.0,
        data_freshness_status=DataFreshnessStatus.STALE,
    )
    result = await _run(dr, stock, session_factory)
    assert result.decision.brain_decision == "NO_TRADE"


@pytest.mark.asyncio
async def test_case_d_great_chart_but_poor_liquidity_forces_no_trade(session_factory, stock):
    """Poor liquidity is a hard REJECT gate in the deterministic engine
    -- no chart quality can override it."""
    dr = make_decision_result(
        decision=Decision.REJECT,
        confidence_score=15.0,
        gates=[GateOutcome(name="liquidity", status=GateStatus.FAIL, detail="below floor", blocking=True)],
    )
    result = await _run(dr, stock, session_factory)
    assert result.decision.brain_decision == "NO_TRADE"


@pytest.mark.asyncio
async def test_case_e_mixed_evidence_watches_or_declines(session_factory, stock):
    """Mixed/conflicting technical evidence -- deterministic WATCH."""
    dr = make_decision_result(decision=Decision.WATCH, confidence_score=50.0)
    result = await _run(dr, stock, session_factory)
    assert result.decision.brain_decision in {"WATCH", "NO_TRADE"}


@pytest.mark.asyncio
async def test_case_f_hard_reject_llm_attempts_buy_is_forced_to_no_trade(session_factory, stock):
    """Deterministic hard reject, but a misbehaving provider attempts
    BUY with invented price levels -- the post-validator must force
    NO_TRADE and log the policy violation."""
    dr = make_decision_result(decision=Decision.REJECT, confidence_score=10.0)
    result = await _run(dr, stock, session_factory, response_factory=hard_gate_override_attempt_response)
    assert result.decision.brain_decision == "NO_TRADE"
    assert "POLICY_VIOLATION_HARD_GATE_OVERRIDE_ATTEMPTED" in result.reason_codes
