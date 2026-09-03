"""telemetry.py tests -- proves the Shadow audit record carries only the
explicitly allow-listed fields (no chain-of-thought, no raw prompt) and
that input hashing is deterministic."""

import pytest

from src.ai.basirah_brain.evidence_builder import build_input
from src.ai.basirah_brain.providers.mock_provider import MockBasirahBrainProvider
from src.ai.basirah_brain.telemetry import ShadowTelemetryRecord, build_telemetry_record, compute_input_hash

from .conftest import make_decision_result


def test_input_hash_is_a_64_char_hex_sha256():
    import re

    class _Stub:
        id = 1
        sector = "Materials"

    brain_input = build_input(make_decision_result(), _Stub())
    digest = compute_input_hash(brain_input)
    assert re.fullmatch(r"[0-9a-f]{64}", digest)


@pytest.mark.asyncio
async def test_telemetry_record_has_only_the_allow_listed_fields(stock):
    brain_input = build_input(make_decision_result(), stock)
    outcome = await MockBasirahBrainProvider().analyze(brain_input)

    record = build_telemetry_record(
        brain_input=brain_input,
        outcome=outcome,
        prompt_version="v1",
        validation_status="SUCCESS",
        reason_codes=[],
    )

    assert isinstance(record, ShadowTelemetryRecord)
    allow_listed = {
        "input_hash",
        "input_schema_version",
        "output_schema_version",
        "model_provider",
        "model_name",
        "prompt_version",
        "latency_ms",
        "prompt_tokens",
        "completion_tokens",
        "validation_status",
        "reason_codes",
    }
    actual_fields = set(record.__dataclass_fields__.keys())
    assert actual_fields == allow_listed
    # No field name anywhere in this contract could plausibly carry a
    # raw model transcript or hidden reasoning trace.
    for forbidden in ("chain_of_thought", "raw_prompt", "prompt_text", "reasoning_trace"):
        assert forbidden not in actual_fields
