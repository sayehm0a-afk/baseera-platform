"""BasirahBrainService.analyze_shadow() persistence tests -- items #15,
16, 17, 18, 19, 22 of the Stage 1 test list (idempotent duplicate
persistence, input hashing reproducibility, no mutation of
DecisionV2Snapshot, no consumer-feed mutation, no recommendation-table
mutation, concurrency safety)."""

import pytest

from src.ai.basirah_brain.providers.mock_provider import (
    MockBasirahBrainProvider,
    hard_gate_override_attempt_response,
    invented_price_levels_response,
)
from src.ai.basirah_brain.service import (
    STATUS_POLICY_VIOLATION_CORRECTED,
    STATUS_PROVIDER_ERROR,
    STATUS_SUCCESS,
    BasirahBrainService,
)
from src.ai.basirah_brain.telemetry import compute_input_hash
from src.analysis.decision_v2.types import Decision
from src.domain.models import BasirahBrainShadowDecision, DecisionV2Snapshot, RadarOpportunity, RecommendationSnapshot

from .conftest import make_decision_result


@pytest.mark.asyncio
async def test_analyze_shadow_persists_a_shadow_row_and_never_touches_production_tables(
    session, session_factory, stock
):
    dr = make_decision_result()
    service = BasirahBrainService(provider=MockBasirahBrainProvider(), session_factory=session_factory)

    result = await service.analyze_shadow(dr, stock)

    assert result.status == STATUS_SUCCESS
    assert result.shadow_record_id is not None

    row = session.query(BasirahBrainShadowDecision).filter_by(id=result.shadow_record_id).one()
    assert row.symbol == "1213"
    assert row.deterministic_decision == "BUY_CANDIDATE"
    assert row.brain_decision == "BUY"
    assert row.status == STATUS_SUCCESS

    # Hard isolation proof: zero rows exist anywhere in every
    # production/consumer-facing table this session's schema includes.
    assert session.query(DecisionV2Snapshot).count() == 0
    assert session.query(RadarOpportunity).count() == 0
    assert session.query(RecommendationSnapshot).count() == 0


@pytest.mark.asyncio
async def test_provider_error_is_recorded_but_never_propagates_a_fabricated_decision(
    session, session_factory, stock
):
    def _malformed(_):
        return "{not json"

    dr = make_decision_result()
    service = BasirahBrainService(
        provider=MockBasirahBrainProvider(response_factory=_malformed), session_factory=session_factory
    )

    result = await service.analyze_shadow(dr, stock)

    assert result.status == STATUS_PROVIDER_ERROR
    assert result.decision is None
    assert result.error_code == "INVALID_JSON"

    row = session.query(BasirahBrainShadowDecision).filter_by(id=result.shadow_record_id).one()
    assert row.status == STATUS_PROVIDER_ERROR
    assert row.brain_decision is None


@pytest.mark.asyncio
async def test_hard_gate_override_attempt_is_persisted_as_policy_violation_corrected(
    session, session_factory, stock
):
    dr = make_decision_result(decision=Decision.REJECT)
    service = BasirahBrainService(
        provider=MockBasirahBrainProvider(response_factory=hard_gate_override_attempt_response),
        session_factory=session_factory,
    )

    result = await service.analyze_shadow(dr, stock)

    assert result.status == STATUS_POLICY_VIOLATION_CORRECTED
    assert result.decision.decision.value == "NO_TRADE"
    row = session.query(BasirahBrainShadowDecision).filter_by(id=result.shadow_record_id).one()
    assert row.status == STATUS_POLICY_VIOLATION_CORRECTED
    assert row.brain_decision == "NO_TRADE"
    assert "POLICY_VIOLATION_HARD_GATE_OVERRIDE_ATTEMPTED" in row.reason_codes


@pytest.mark.asyncio
async def test_input_hashing_is_reproducible_for_identical_inputs(session_factory, stock):
    dr1 = make_decision_result()
    dr2 = make_decision_result()  # identical field values, a second construction

    from src.ai.basirah_brain.evidence_builder import build_input

    hash1 = compute_input_hash(build_input(dr1, stock))
    hash2 = compute_input_hash(build_input(dr2, stock))
    assert hash1 == hash2

    dr3 = make_decision_result(confidence_score=99.0)  # a real, material difference
    hash3 = compute_input_hash(build_input(dr3, stock))
    assert hash3 != hash1


@pytest.mark.asyncio
async def test_duplicate_calls_are_idempotent_in_the_sense_of_never_crashing_or_corrupting(
    session, session_factory, stock
):
    """This table is an insert-only audit log (matching DecisionV2Snapshot's
    own established convention) -- 'idempotent' here means calling
    analyze_shadow() twice with the same DecisionResult produces two
    well-formed, independently-correct rows, never a crash, a corrupted
    row, or a silently dropped one."""
    dr = make_decision_result()
    service = BasirahBrainService(provider=MockBasirahBrainProvider(), session_factory=session_factory)

    result1 = await service.analyze_shadow(dr, stock)
    result2 = await service.analyze_shadow(dr, stock)

    assert result1.shadow_record_id != result2.shadow_record_id
    assert session.query(BasirahBrainShadowDecision).count() == 2
    rows = session.query(BasirahBrainShadowDecision).all()
    assert rows[0].input_hash == rows[1].input_hash  # same logical input, correctly reproducible


@pytest.mark.asyncio
async def test_concurrent_shadow_persistence_does_not_corrupt_or_crash(session, session_factory, stock):
    import asyncio

    dr = make_decision_result()
    service = BasirahBrainService(provider=MockBasirahBrainProvider(), session_factory=session_factory)

    results = await asyncio.gather(*[service.analyze_shadow(dr, stock) for _ in range(5)])

    ids = {r.shadow_record_id for r in results}
    assert len(ids) == 5  # every concurrent call got its own distinct row
    assert session.query(BasirahBrainShadowDecision).count() == 5
    assert all(r.status == STATUS_SUCCESS for r in results)


@pytest.mark.asyncio
async def test_f5_service_level_price_geometry_normalization_is_enforced(session, session_factory, stock):
    """Finding F5 remediation: proves price-geometry normalization
    through the REAL, full `analyze_shadow()` service path -- not just
    the `normalize_price_geometry()` helper in isolation (the original
    test blind spot the pre-merge audit's Negative Control 3 exposed:
    the prior CASE F service test only asserted on decision/status, not
    on the persisted price fields)."""
    dr = make_decision_result(decision=Decision.BUY_CANDIDATE)  # real geometry: 98-101 / 93 / 108-115-122
    service = BasirahBrainService(
        provider=MockBasirahBrainProvider(response_factory=invented_price_levels_response),
        session_factory=session_factory,
    )

    result = await service.analyze_shadow(dr, stock)

    assert result.decision.entry_zone.low == 98.0
    assert result.decision.entry_zone.high == 101.0
    assert result.decision.stop_loss == 93.0
    assert result.decision.targets == [108.0, 115.0, 122.0]
    assert result.decision.holding_horizon.min_days == 10
    assert result.decision.holding_horizon.max_days == 30

    row = session.query(BasirahBrainShadowDecision).filter_by(id=result.shadow_record_id).one()
    persisted = row.raw_structured_output
    assert persisted["entry_zone"] == {"low": 98.0, "high": 101.0}
    assert persisted["stop_loss"] == 93.0
    assert persisted["targets"] == [108.0, 115.0, 122.0]
    # The invented values must not survive anywhere in the persisted record.
    for invented in (1.23, 4.56, 0.01, 7777.0, 8888.0, 9999.0):
        assert invented not in (persisted["targets"] + [persisted["entry_zone"]["low"], persisted["entry_zone"]["high"], persisted["stop_loss"]])
