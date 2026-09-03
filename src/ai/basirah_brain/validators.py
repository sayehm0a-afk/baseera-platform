"""Post-generation safety validation -- the layer that must never trust
a provider's raw output blindly (Stage 1's non-negotiable safety
principle). Applied corrections, in the fixed order
`apply_all_safety_corrections` runs them:

1. `enforce_hard_gate_policy` -- the Brain can never be more aggressive
   than the deterministic engine's own classification tier allows. A
   BUY attempted against a non-actionable deterministic decision is
   force-corrected to NO_TRADE and logged as a policy violation, never
   silently allowed through.

2. `enforce_data_quality_gate` (pre-merge hardening audit, Finding F1) --
   independent, code-level defense-in-depth: the Brain can never emit an
   actionable BUY when the input evidence itself is flagged synthetic or
   non-fresh, regardless of what the deterministic tier or the provider
   claims. This does NOT invent a second freshness definition -- it
   consumes exactly the same authoritative `DataFreshnessStatus`-derived
   signal (`data_quality.stale_flags`/`is_synthetic`,
   `price_context.data_freshness_status`) evidence_builder.py already
   populates from the real `DecisionResult`, mirroring gates.py's own
   precedence (synthetic is the harsher check, matching gates.py's
   `is_synthetic -> REJECT`; non-fresh is the softer one, matching
   gates.py's `is_stale -> WATCH`). Never trusted to the LLM.

3. `validate_evidence_grounding` (Finding F2) -- every `key_evidence[]`
   citation must reference a real path that exists in the schema of
   `BasirahBrainInputV1`; an invalid/fabricated `source_field` is
   removed (not a hard fail-closed -- see its own docstring for why) and
   `data_quality.sufficient` is downgraded to `False`.

4. `sanitize_reason_codes` (Finding F3) -- `reason_codes` are checked
   against a controlled vocabulary (the fixed set of codes this module
   itself emits, plus a curated set of legitimate provider-facing
   codes); anything else is mapped to a single safe generic value, never
   allowed to become an arbitrary, attacker-influenced "authoritative"
   identifier.

5. `normalize_price_geometry` -- Stage 1's AI is not permitted to
   redesign numerical trade geometry. Entry zone, stop loss, targets,
   and holding horizon are always overwritten with the deterministic
   engine's own already-computed values, regardless of what the
   provider returned for them, so no invented price level can ever
   reach a persisted Shadow record as if it were real. Always applied
   last, since whatever the final decision ends up being, its price
   geometry must always be the deterministic engine's.

All are applied unconditionally by `service.py` after schema validation,
before persistence -- never optional, never skippable by a caller.
"""

import re
from typing import Any, FrozenSet, List, Tuple

from pydantic import BaseModel as _PydanticBaseModel

from .schemas import (
    AgreementStatus,
    BasirahBrainDecisionV1,
    BasirahBrainInputV1,
    BrainDataQualityIn,
    BrainDecision,
    BrainEntryZone,
    BrainExistingEngineEvidence,
    BrainHoldingHorizon,
)

REASON_HARD_GATE_OVERRIDE_ATTEMPTED = "POLICY_VIOLATION_HARD_GATE_OVERRIDE_ATTEMPTED"
REASON_PRICE_GEOMETRY_NORMALIZED = "PRICE_GEOMETRY_NORMALIZED_TO_DETERMINISTIC_ENGINE"
REASON_DATA_QUALITY_GATE_ENFORCED = "POLICY_VIOLATION_DATA_QUALITY_GATE_ENFORCED"
REASON_EVIDENCE_CITATION_REMOVED = "EVIDENCE_CITATION_INVALID_REMOVED"
REASON_UNVALIDATED_CODE_REPLACED = "OTHER_UNVALIDATED_REASON"

_BUY_FAMILY = frozenset({"STRONG_BUY_CANDIDATE", "BUY_CANDIDATE"})
_WATCH_FAMILY = frozenset({"WAIT_FOR_ENTRY", "WATCH"})
# Everything else -- HOLD, REDUCE, EXIT, REJECT, INSUFFICIENT_DATA, and
# any future/unrecognized value -- is treated as the most restrictive
# tier by default (fail-safe: an unknown deterministic decision must
# never be interpreted as permissive).

# The authoritative "fresh" value -- reused verbatim from
# src.analysis.decision_v2.types.DataFreshnessStatus.LIVE.value (not
# re-imported to keep this module free of a decision_v2 dependency
# beyond the DecisionResult type already used elsewhere; the value is a
# stable, long-established string constant in that enum).
_FRESH_STATUS_VALUE = "LIVE"

# F3: the fixed set of codes this module itself ever emits, always
# allowed verbatim (never replaced) since they are never
# attacker-influenced.
_SYSTEM_REASON_CODES = frozenset(
    {
        REASON_HARD_GATE_OVERRIDE_ATTEMPTED,
        REASON_PRICE_GEOMETRY_NORMALIZED,
        REASON_DATA_QUALITY_GATE_ENFORCED,
        REASON_EVIDENCE_CITATION_REMOVED,
    }
)

# F3: a curated, closed vocabulary of legitimate provider-facing reason
# codes -- the system prompt (prompts.py) instructs the model to choose
# from exactly this set. Anything the model returns outside
# (_SYSTEM_REASON_CODES | _ALLOWED_PROVIDER_REASON_CODES) is replaced
# with REASON_UNVALIDATED_CODE_REPLACED, never persisted verbatim as an
# "authoritative" identifier.
ALLOWED_PROVIDER_REASON_CODES = frozenset(
    {
        "STRONG_TREND_CONFIRMATION",
        "WEAK_TREND",
        "MOMENTUM_EXHAUSTED",
        "NEAR_RESISTANCE",
        "NEAR_SUPPORT",
        "POOR_LIQUIDITY",
        "CONFLICTING_INDICATORS",
        "INSUFFICIENT_EVIDENCE",
        "UNFAVORABLE_MARKET_REGIME",
        "NEWS_RISK",
        "STALE_DATA_CONCERN",
        "SYNTHETIC_DATA_CONCERN",
        "GOOD_RISK_REWARD",
        "POOR_RISK_REWARD",
        "SECTOR_WEAKNESS",
        "SECTOR_STRENGTH",
        "BREAKOUT_CONFIRMED",
        "BREAKOUT_FAILED",
        "OVEREXTENDED_PRICE",
        "HEALTHY_VOLUME",
    }
)

_MAX_REASON_CODES = 10


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


def enforce_data_quality_gate(
    data_quality: BrainDataQualityIn, freshness_status: str, decision: BasirahBrainDecisionV1
) -> Tuple[BasirahBrainDecisionV1, bool]:
    """Finding F1 remediation: independent, code-level defense-in-depth
    against stale/synthetic data producing an actionable BUY. This is
    NOT a second freshness definition -- `data_quality.is_synthetic`/
    `stale_flags` and `freshness_status` are exactly the authoritative
    signal evidence_builder.py already derives from the real
    `DecisionResult.is_real_data`/`data_freshness_status`, checked
    twice (both the derived flag list AND the raw status string) so a
    future caller that populates one but not the other consistently
    still cannot slip an unfresh input past this gate -- fail-safe, not
    optimistic, on any ambiguity.

    Mirrors gates.py's own real precedence rather than inventing a new
    one: synthetic data is the harsher case (gates.py:
    `is_synthetic -> REJECT`), capped at NO_TRADE; non-fresh data is the
    softer case (gates.py: `is_stale -> WATCH`), capped at
    {WATCH, NO_TRADE}. A missing/unrecognized freshness value (anything
    other than the exact authoritative "LIVE" string) is treated as
    non-fresh, never as an implicit pass."""
    is_synthetic = bool(data_quality.is_synthetic)
    is_fresh = (not data_quality.stale_flags) and (freshness_status == _FRESH_STATUS_VALUE)

    if is_synthetic:
        ceiling = frozenset({BrainDecision.NO_TRADE})
    elif not is_fresh:
        ceiling = frozenset({BrainDecision.WATCH, BrainDecision.NO_TRADE})
    else:
        return decision, False

    if decision.decision in ceiling:
        return decision, False

    reason_codes = list(decision.reason_codes) + [REASON_DATA_QUALITY_GATE_ENFORCED]
    corrected = decision.model_copy(
        update={
            "decision": BrainDecision.NO_TRADE,
            "brain_decision": BrainDecision.NO_TRADE.value,
            "agreement_with_deterministic_engine": AgreementStatus.MORE_CONSERVATIVE,
            "reason_codes": reason_codes,
        }
    )
    return corrected, True


def _collect_valid_schema_paths(model_cls: Any, prefix: str = "") -> set:
    """Recursively walks a pydantic model CLASS's own field definitions
    (not an instance) to build the set of dotted paths a `source_field`
    citation may legitimately reference -- using the class/schema means
    a field that is legitimately `None` on a given input is still a
    valid citation target, not just whichever keys happen to be
    populated. Descends into nested `BaseModel` subclasses and into the
    item type of `List[SomeModel]` fields (so e.g.
    'existing_engine.gate_outcomes.name' is valid without an index)."""
    paths = set()
    model_fields = getattr(model_cls, "model_fields", None)
    if model_fields is None:
        return paths
    for field_name, field_info in model_fields.items():
        full_path = f"{prefix}{field_name}"
        paths.add(full_path)
        annotation = field_info.annotation
        inner = annotation
        # Unwrap Optional[...]/List[...] to find a nested BaseModel, if any.
        args = getattr(inner, "__args__", None)
        candidates = [inner] + (list(args) if args else [])
        for candidate in candidates:
            if isinstance(candidate, type) and issubclass(candidate, _PydanticBaseModel):
                paths |= _collect_valid_schema_paths(candidate, prefix=f"{full_path}.")
    return paths


def validate_evidence_grounding(
    brain_input: BasirahBrainInputV1, decision: BasirahBrainDecisionV1
) -> Tuple[BasirahBrainDecisionV1, bool]:
    """Finding F2 remediation: every `key_evidence[].source_field` must
    reference a real path in `BasirahBrainInputV1`'s own schema.
    Chosen behavior (per the remediation mandate's option B): remove
    invalid citations and mark `data_quality.sufficient = False`, rather
    than hard-failing the whole response. Rationale: a bad citation is
    an evidence-traceability/observability defect, not a trading-safety
    one -- `key_evidence` has zero causal effect on `decision`/price
    geometry (both are governed independently by
    `enforce_hard_gate_policy`/`enforce_data_quality_gate`/
    `normalize_price_geometry`), so discarding an otherwise safety-
    correct, more-conservative-or-equal decision over one bad citation
    would throw away real signal for no safety benefit. Downgrading
    `sufficient` keeps the degradation visible and honest rather than
    silent."""
    valid_paths = _collect_valid_schema_paths(BasirahBrainInputV1)

    def _is_valid(source_field: str) -> bool:
        # Strip array-index notation ("technical.support_levels[0]" ->
        # "technical.support_levels") before matching against the
        # schema-derived path set, which is index-free by construction.
        normalized = re.sub(r"\[\d+\]", "", source_field)
        return normalized in valid_paths

    kept = [item for item in decision.key_evidence if _is_valid(item.source_field)]
    removed_count = len(decision.key_evidence) - len(kept)
    if removed_count == 0:
        return decision, False

    reason_codes = list(decision.reason_codes) + [REASON_EVIDENCE_CITATION_REMOVED]
    new_data_quality = decision.data_quality.model_copy(update={"sufficient": False})
    corrected = decision.model_copy(
        update={
            "key_evidence": kept,
            "data_quality": new_data_quality,
            "reason_codes": reason_codes,
        }
    )
    return corrected, True


def sanitize_reason_codes(decision: BasirahBrainDecisionV1) -> Tuple[BasirahBrainDecisionV1, bool]:
    """Finding F3 remediation: `reason_codes` are checked against a
    closed vocabulary (`_SYSTEM_REASON_CODES | ALLOWED_PROVIDER_REASON_
    CODES`). Any code outside it -- including empty strings, prompt-
    injected text, or a model-invented identifier -- is replaced with
    the single generic `REASON_UNVALIDATED_CODE_REPLACED` value, never
    persisted verbatim as if it were an authoritative, system-recognized
    code. Also dedupes (preserving order) and caps the list at
    `_MAX_REASON_CODES` entries -- an excessive count is truncated, not
    rejected outright."""
    allowed = _SYSTEM_REASON_CODES | ALLOWED_PROVIDER_REASON_CODES
    sanitized: List[str] = []
    for code in decision.reason_codes:
        normalized = code if code in allowed else REASON_UNVALIDATED_CODE_REPLACED
        if normalized not in sanitized:  # dedupe, preserve order
            sanitized.append(normalized)
    sanitized = sanitized[:_MAX_REASON_CODES]  # cap an excessive count, don't reject outright

    if sanitized == list(decision.reason_codes):
        return decision, False
    corrected = decision.model_copy(update={"reason_codes": sanitized})
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
    brain_input: BasirahBrainInputV1, decision: BasirahBrainDecisionV1
) -> Tuple[BasirahBrainDecisionV1, List[str]]:
    """Applies every correction in the fixed, required order and returns
    the final decision plus a plain-English list of what was corrected,
    for logging:

    1. enforce_hard_gate_policy   -- classification-tier ceiling
    2. enforce_data_quality_gate  -- Finding F1: independent stale/synthetic ceiling
    3. validate_evidence_grounding -- Finding F2: drop fabricated source_field citations
    4. sanitize_reason_codes      -- Finding F3: controlled vocabulary
    5. normalize_price_geometry   -- always last: whatever the final decision is,
                                      its price geometry must always be the
                                      deterministic engine's own values.

    Order 1-2 matters (both may force NO_TRADE; running them before 5
    ensures a corrected-to-NO_TRADE decision still gets its price
    geometry normalized rather than left as whatever the rejected
    attempt proposed). Order 3-4 vs 1-2 is independent (evidence/reason
    hygiene doesn't affect the decision ceiling), kept after for
    readability of the notes list.
    """
    engine = brain_input.existing_engine
    deterministic_decision = engine.deterministic_decision
    notes: List[str] = []

    decision, gate_violated = enforce_hard_gate_policy(deterministic_decision, decision)
    if gate_violated:
        notes.append(
            f"Corrected brain_decision to NO_TRADE: deterministic engine returned "
            f"'{deterministic_decision}', which does not permit the provider's attempted decision."
        )

    decision, quality_violated = enforce_data_quality_gate(
        brain_input.data_quality, brain_input.price_context.data_freshness_status, decision
    )
    if quality_violated:
        notes.append(
            "Corrected brain_decision to NO_TRADE: input evidence was flagged synthetic or non-fresh, "
            "which never permits an actionable BUY regardless of the deterministic tier or provider output."
        )

    decision, evidence_changed = validate_evidence_grounding(brain_input, decision)
    if evidence_changed:
        notes.append("Removed one or more key_evidence citations whose source_field did not match real input evidence.")

    decision, codes_changed = sanitize_reason_codes(decision)
    if codes_changed:
        notes.append("Sanitized reason_codes against the controlled vocabulary.")

    decision, price_changed = normalize_price_geometry(engine, decision)
    if price_changed:
        notes.append("Normalized entry_zone/stop_loss/targets/holding_horizon to deterministic engine values.")

    return decision, notes
