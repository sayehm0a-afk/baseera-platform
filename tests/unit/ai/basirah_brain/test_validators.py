"""Post-generation safety validator tests -- items #5, 6, 7, 8 (hard
reject cannot be overridden, deterministic BUY may be downgraded,
deterministic BUY + aligned evidence may agree, invented AI price
levels are rejected/normalized)."""

from src.ai.basirah_brain.schemas import (
    AgreementStatus,
    BasirahBrainDecisionV1,
    BrainDataQualityOut,
    BrainDecision,
    BrainEntryZone,
    BrainExistingEngineEvidence,
    BrainHoldingHorizon,
    BrainRiskLevel,
    ConfidenceLabel,
)
from src.ai.basirah_brain.validators import (
    REASON_HARD_GATE_OVERRIDE_ATTEMPTED,
    REASON_PRICE_GEOMETRY_NORMALIZED,
    apply_all_safety_corrections,
    decision_ceiling,
    enforce_hard_gate_policy,
    normalize_price_geometry,
)


def _engine(**overrides) -> BrainExistingEngineEvidence:
    base = dict(
        deterministic_decision="BUY_CANDIDATE",
        deterministic_confidence_score=68.0,
        entry_zone_low=98.0,
        entry_zone_high=101.0,
        stop_loss=93.0,
        target_1=108.0,
        target_2=115.0,
        target_3=122.0,
        holding_horizon_min_days=10,
        holding_horizon_max_days=30,
    )
    base.update(overrides)
    return BrainExistingEngineEvidence(**base)


def _decision(decision: BrainDecision, **overrides) -> BasirahBrainDecisionV1:
    base = dict(
        decision=decision,
        confidence_score=90.0,
        confidence_label=ConfidenceLabel.HIGH,
        entry_zone=BrainEntryZone(low=999.0, high=1000.0),
        stop_loss=950.0,
        targets=[1010.0, 1020.0, 1030.0],
        holding_horizon=BrainHoldingHorizon(min_days=1, max_days=2),
        risk_level=BrainRiskLevel.LOW,
        thesis_summary="test",
        data_quality=BrainDataQualityOut(sufficient=True),
        agreement_with_deterministic_engine=AgreementStatus.AGREE,
        deterministic_decision="BUY_CANDIDATE",
        brain_decision=decision.value,
    )
    base.update(overrides)
    return BasirahBrainDecisionV1(**base)


def test_decision_ceiling_buy_family_allows_full_range():
    ceiling = decision_ceiling("BUY_CANDIDATE")
    assert ceiling == {BrainDecision.BUY, BrainDecision.WAIT_FOR_ENTRY, BrainDecision.WATCH, BrainDecision.NO_TRADE}


def test_decision_ceiling_watch_family_never_allows_buy():
    ceiling = decision_ceiling("WATCH")
    assert BrainDecision.BUY not in ceiling
    assert ceiling == {BrainDecision.WAIT_FOR_ENTRY, BrainDecision.WATCH, BrainDecision.NO_TRADE}


def test_decision_ceiling_hard_reject_family_only_allows_no_trade():
    for deterministic in ("REJECT", "INSUFFICIENT_DATA", "HOLD", "REDUCE", "EXIT", "SOMETHING_UNKNOWN"):
        assert decision_ceiling(deterministic) == {BrainDecision.NO_TRADE}


def test_hard_reject_cannot_be_overridden_to_buy():
    attempted_buy = _decision(BrainDecision.BUY)
    corrected, violated = enforce_hard_gate_policy("REJECT", attempted_buy)
    assert violated is True
    assert corrected.decision is BrainDecision.NO_TRADE
    assert REASON_HARD_GATE_OVERRIDE_ATTEMPTED in corrected.reason_codes


def test_deterministic_buy_may_be_downgraded_by_brain():
    conservative = _decision(BrainDecision.NO_TRADE)
    corrected, violated = enforce_hard_gate_policy("BUY_CANDIDATE", conservative)
    assert violated is False
    assert corrected.decision is BrainDecision.NO_TRADE


def test_deterministic_buy_with_aligned_evidence_can_agree():
    agree = _decision(BrainDecision.BUY)
    corrected, violated = enforce_hard_gate_policy("BUY_CANDIDATE", agree)
    assert violated is False
    assert corrected.decision is BrainDecision.BUY


def test_invented_price_levels_are_normalized_away():
    engine = _engine()
    invented = _decision(BrainDecision.BUY)  # entry_zone/stop/targets are invented (999-1030 range)
    assert invented.entry_zone.low == 999.0  # sanity: fixture really is "invented"

    corrected, changed = normalize_price_geometry(engine, invented)
    assert changed is True
    assert corrected.entry_zone == BrainEntryZone(low=98.0, high=101.0)
    assert corrected.stop_loss == 93.0
    assert corrected.targets == [108.0, 115.0, 122.0]
    assert REASON_PRICE_GEOMETRY_NORMALIZED in corrected.reason_codes


def test_matching_price_levels_are_not_flagged_as_changed():
    engine = _engine()
    already_correct = _decision(
        BrainDecision.BUY,
        entry_zone=BrainEntryZone(low=98.0, high=101.0),
        stop_loss=93.0,
        targets=[108.0, 115.0, 122.0],
        holding_horizon=BrainHoldingHorizon(min_days=10, max_days=30),
    )
    corrected, changed = normalize_price_geometry(engine, already_correct)
    assert changed is False
    assert REASON_PRICE_GEOMETRY_NORMALIZED not in corrected.reason_codes


def test_apply_all_safety_corrections_case_f_hard_reject_plus_invented_prices():
    """CASE F: deterministic hard reject but the provider attempts BUY
    with invented price levels -- the combined pipeline must force
    NO_TRADE AND normalize price geometry, both logged."""
    engine = _engine(deterministic_decision="REJECT", entry_zone_low=None, entry_zone_high=None, stop_loss=None)
    misbehaving = _decision(BrainDecision.BUY, deterministic_decision="REJECT")

    corrected, notes = apply_all_safety_corrections("REJECT", engine, misbehaving)

    assert corrected.decision is BrainDecision.NO_TRADE
    assert REASON_HARD_GATE_OVERRIDE_ATTEMPTED in corrected.reason_codes
    assert corrected.entry_zone == BrainEntryZone(low=None, high=None)
    assert corrected.stop_loss is None
    assert len(notes) == 2
