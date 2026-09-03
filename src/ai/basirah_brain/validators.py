"""Post-generation safety validation -- the layer that must never trust
a provider's raw output blindly (Stage 1's non-negotiable safety
principle). Two independent, always-applied corrections:

1. `enforce_hard_gate_policy` -- the Brain can never be more aggressive
   than the deterministic engine's own classification tier allows. A
   BUY attempted against a non-actionable deterministic decision is
   force-corrected to NO_TRADE and logged as a policy violation, never
   silently allowed through.

2. `normalize_price_geometry` -- Stage 1's AI is not permitted to
   redesign numerical trade geometry. Entry zone, stop loss, targets,
   and holding horizon are always overwritten with the deterministic
   engine's own already-computed values, regardless of what the
   provider returned for them, so no invented price level can ever
   reach a persisted Shadow record as if it were real.

Both are applied unconditionally by `service.py` after schema
validation, before persistence -- never optional, never skippable by a
caller.
"""

from typing import FrozenSet, List, Tuple

from .schemas import (
    AgreementStatus,
    BasirahBrainDecisionV1,
    BrainDecision,
    BrainEntryZone,
    BrainExistingEngineEvidence,
    BrainHoldingHorizon,
)

REASON_HARD_GATE_OVERRIDE_ATTEMPTED = "POLICY_VIOLATION_HARD_GATE_OVERRIDE_ATTEMPTED"
REASON_PRICE_GEOMETRY_NORMALIZED = "PRICE_GEOMETRY_NORMALIZED_TO_DETERMINISTIC_ENGINE"

_BUY_FAMILY = frozenset({"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"})
_WATCH_FAMILY = frozenset({"WAIT_FOR_ENTRY", "WATCH"})
# Everything else -- HOLD, REDUCE, EXIT, REJECT, INSUFFICIENT_DATA, and
# any future/unrecognized value -- is treated as the most restrictive
# tier by default (fail-safe: an unknown deterministic decision must
# never be interpreted as permissive).


def decision_ceiling(deterministic_decision: str) -> FrozenSet[BrainDecision]:
    """The maximum set of Brain decisions permitted given the
    deterministic engine's own classification. Never allows BUY unless
    the deterministic tier itself is actionable BUY-family."""
    if deterministic_decision in _BUY_FAMILY:
        return frozenset(
            {BrainDecision.BUY, BrainDecision.WAIT_FOR_ENTRY, BrainDecision.WATCH, BrainDecision.NO_TRADE}
        )
    if deterministic_decision in _WATCH_FAMILY:
        return frozenset({BrainDecision.WAIT_FOR_ENTRY, BrainDecision.WATCH, BrainDecision.NO_TRADE})
    return frozenset({BrainDecision.NO_TRADE})


def enforce_hard_gate_policy(
    deterministic_decision: str, decision: BasirahBrainDecisionV1
) -> Tuple[BasirahBrainDecisionV1, bool]:
    """Returns (possibly-corrected decision, violated). `violated=True`
    means the provider attempted a decision outside its allowed ceiling
    and was forcibly corrected to NO_TRADE -- the caller must log this,
    never silently accept the original value."""
    allowed = decision_ceiling(deterministic_decision)
    if decision.decision in allowed:
        return decision, False

    reason_codes = list(decision.reason_codes) + [REASON_HARD_GATE_OVERRIDE_ATTEMPTED]
    corrected = decision.model_copy(
        update={
            "decision": BrainDecision.NO_TRADE,
            "brain_decision": BrainDecision.NO_TRADE.value,
            "agreement_with_deterministic_engine": AgreementStatus.MORE_CONSERVATIVE,
            "reason_codes": reason_codes,
        }
    )
    return corrected, True


def normalize_price_geometry(
    engine: BrainExistingEngineEvidence, decision: BasirahBrainDecisionV1
) -> Tuple[BasirahBrainDecisionV1, bool]:
    """Unconditionally overwrites entry/stop/targets/holding_horizon with
    the deterministic engine's own already-computed values -- Stage 1's
    Brain is never trusted to originate a price level. Returns
    (corrected decision, changed) so the caller can log a reason code
    only when the provider's own numbers actually differed."""
    engine_entry = BrainEntryZone(low=engine.entry_zone_low, high=engine.entry_zone_high)
    engine_targets = [t for t in (engine.target_1, engine.target_2, engine.target_3) if t is not None]
    engine_horizon = BrainHoldingHorizon(
        min_days=engine.holding_horizon_min_days, max_days=engine.holding_horizon_max_days
    )

    changed = (
        decision.entry_zone != engine_entry
        or decision.stop_loss != engine.stop_loss
        or list(decision.targets) != engine_targets
        or decision.holding_horizon != engine_horizon
    )

    reason_codes = list(decision.reason_codes)
    if changed:
        reason_codes.append(REASON_PRICE_GEOMETRY_NORMALIZED)

    corrected = decision.model_copy(
        update={
            "entry_zone": engine_entry,
            "stop_loss": engine.stop_loss,
            "targets": engine_targets,
            "holding_horizon": engine_horizon,
            "reason_codes": reason_codes,
        }
    )
    return corrected, changed


def apply_all_safety_corrections(
    deterministic_decision: str, engine: BrainExistingEngineEvidence, decision: BasirahBrainDecisionV1
) -> Tuple[BasirahBrainDecisionV1, List[str]]:
    """Applies both corrections in the fixed, required order (hard-gate
    policy first, since a corrected-to-NO_TRADE decision must still have
    its price geometry normalized rather than left as whatever the
    rejected attempt proposed) and returns the final decision plus a
    plain-English list of what was corrected, for logging."""
    notes: List[str] = []

    decision, gate_violated = enforce_hard_gate_policy(deterministic_decision, decision)
    if gate_violated:
        notes.append(
            f"Corrected brain_decision to NO_TRADE: deterministic engine returned "
            f"'{deterministic_decision}', which does not permit the provider's attempted decision."
        )

    decision, price_changed = normalize_price_geometry(engine, decision)
    if price_changed:
        notes.append("Normalized entry_zone/stop_loss/targets/holding_horizon to deterministic engine values.")

    return decision, notes
