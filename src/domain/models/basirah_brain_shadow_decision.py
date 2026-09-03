"""BasirahBrainShadowDecision: the isolated audit ledger for Stage 1 of
the Basirah Brain AI-analyst layer (see src.ai.basirah_brain).

Deliberately a brand-new, standalone table -- never read by any
consumer-facing route, never joined into RadarOpportunity/ShadowLiveSignal
publication, and never written back into DecisionV2Snapshot. Mirrors the
isolation convention `ShadowLiveSignal` already established for the
recurrent-live-scan Shadow Mode ledger (see that model's own docstring):
while Stage 1 is active, a row here has ZERO effect on anything a real
user sees. `DecisionV2Snapshot` and every existing production decision
path stay byte-for-byte unchanged by this table's existence.

Insert-only, matching `DecisionV2Snapshot`'s own "pure insert-only
request log" convention -- the same symbol may legitimately be analyzed
by the Brain many times (different inputs, different prompt/model
versions), and every one of those Shadow analyses is real evidence worth
keeping, not a duplicate to collapse. No UPDATE, no DELETE from
application code.

`decision_v2_snapshot_id` is nullable and NOT unique (unlike
`ShadowLiveSignal.decision_v2_snapshot_id`): Stage 1's Brain can run
against an in-memory `DecisionResult` that was never itself persisted as
a `DecisionV2Snapshot` row (e.g. a test fixture, or a future caller that
builds the evidence package without first writing an audit snapshot), so
the link is best-effort provenance, not a required relationship.
"""

from datetime import datetime, timezone

from sqlalchemy import JSON, Column, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func

from src.core.db.database import Base


class BasirahBrainShadowDecision(Base):
    __tablename__ = "basirah_brain_shadow_decisions"

    id = Column(Integer, primary_key=True)

    symbol = Column(String(16), nullable=False, index=True)
    stock_id = Column(Integer, ForeignKey("stocks.id"), nullable=False, index=True)

    # Best-effort provenance only -- see module docstring for why this is
    # neither NOT NULL nor unique, unlike ShadowLiveSignal's own FK.
    decision_v2_snapshot_id = Column(
        Integer, ForeignKey("decision_v2_snapshots.id"), nullable=True, index=True
    )

    input_schema_version = Column(String(16), nullable=False)
    output_schema_version = Column(String(16), nullable=True)

    model_provider = Column(String(32), nullable=False)
    model_name = Column(String(64), nullable=False)
    prompt_version = Column(String(16), nullable=False)

    # SHA-256 hex digest of the canonical BasirahBrainInputV1 JSON this
    # decision was computed from -- reproducibility/audit evidence, and
    # the basis for this module's idempotency tests (see service.py).
    input_hash = Column(String(64), nullable=False, index=True)

    deterministic_decision = Column(String(32), nullable=False)
    brain_decision = Column(String(32), nullable=True)
    brain_confidence_score = Column(Numeric(6, 2), nullable=True)
    agreement_status = Column(String(24), nullable=True)

    # JSON list of short, disclosed reason codes (e.g.
    # "POLICY_VIOLATION_HARD_GATE_OVERRIDE_ATTEMPTED") -- never free-form
    # hidden chain-of-thought. See telemetry.py's module docstring for
    # the explicit list of what this table is and is not allowed to store.
    reason_codes = Column(JSON, nullable=True)

    # The full, schema-validated BasirahBrainDecisionV1 the provider
    # returned (after post-generation normalization) -- structured,
    # disclosed fields only (thesis_summary/bull_case/bear_case/etc.),
    # never a raw model transcript or hidden reasoning trace.
    raw_structured_output = Column(JSON, nullable=True)

    latency_ms = Column(Numeric(10, 2), nullable=True)

    # "SUCCESS" | "PROVIDER_ERROR" | "INVALID_OUTPUT" | "POLICY_VIOLATION_CORRECTED"
    status = Column(String(32), nullable=False)
    error_code = Column(String(64), nullable=True)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False,
        default=lambda: datetime.now(timezone.utc),
        server_default=func.now(),
    )

    stock = relationship("Stock")
    snapshot = relationship("DecisionV2Snapshot")

    def __repr__(self) -> str:
        return (
            f"<BasirahBrainShadowDecision symbol={self.symbol!r} "
            f"deterministic={self.deterministic_decision!r} brain={self.brain_decision!r} "
            f"status={self.status!r}>"
        )
