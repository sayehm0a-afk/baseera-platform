"""Telemetry/audit-record construction for Basirah Brain Shadow
decisions.

Deliberately allow-listed: this module stores ONLY input evidence hash,
final structured output, concise disclosed reason codes, provider/model
identity, prompt/schema versions, latency, token usage, validation
result, and a timestamp -- never a raw model transcript, never a hidden
chain-of-thought field, never the full prompt text (which could grow to
contain the entire evidence payload repeatedly and serves no audit
purpose beyond the hash + the final structured decision already
captured). This is the exact, explicit field list the Stage 1 mandate
requires and no more.
"""

import hashlib
import json
from dataclasses import dataclass
from typing import List, Optional

from .provider import BasirahBrainProviderOutcome
from .schemas import BasirahBrainInputV1


def compute_input_hash(brain_input: BasirahBrainInputV1) -> str:
    """SHA-256 of the input's canonical JSON form. Pydantic's
    `model_dump_json` with sorted keys gives a stable, reproducible
    serialization -- the same logical input always hashes identically,
    which is what `service.py`'s idempotency tests rely on."""
    canonical = json.dumps(json.loads(brain_input.model_dump_json()), sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class ShadowTelemetryRecord:
    """The exact, allow-listed field set persisted per Shadow decision --
    see module docstring. Never carries a `chain_of_thought`,
    `raw_prompt`, or similar field by design."""

    input_hash: str
    input_schema_version: str
    output_schema_version: Optional[str]
    model_provider: str
    model_name: str
    prompt_version: str
    latency_ms: float
    prompt_tokens: Optional[int]
    completion_tokens: Optional[int]
    validation_status: str
    reason_codes: List[str]


def build_telemetry_record(
    brain_input: BasirahBrainInputV1,
    outcome: BasirahBrainProviderOutcome,
    prompt_version: str,
    validation_status: str,
    reason_codes: List[str],
) -> ShadowTelemetryRecord:
    return ShadowTelemetryRecord(
        input_hash=compute_input_hash(brain_input),
        input_schema_version=brain_input.schema_version,
        output_schema_version=(outcome.decision.schema_version if outcome.decision else None),
        model_provider=outcome.model_provider,
        model_name=outcome.model_name,
        prompt_version=prompt_version,
        latency_ms=outcome.latency_ms,
        prompt_tokens=outcome.prompt_tokens,
        completion_tokens=outcome.completion_tokens,
        validation_status=validation_status,
        reason_codes=reason_codes,
    )
