"""Unit tests for the SAHMK live-verification classification logic
(scripts/sahmk_live_diagnosis.py).

Pure decision-tree tests only -- local sample status codes/exceptions,
no network, no live SAHMK call. The one real, unmocked verification
lives in scripts/verify_sahmk_live.py, run only by
.github/workflows/sahmk-live-verification.yml on manual dispatch; this
file must never import or exercise that network path.

`scripts/` is not an installed package, so it is added to `sys.path`
here the same way `scripts/run_retention_cleanup.py` already inserts
the repo root for its own imports.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent.parent))

import pytest  # noqa: E402

from scripts.sahmk_live_diagnosis import (  # noqa: E402
    CONCLUSIVE_DIAGNOSES,
    DIAGNOSIS_MEANINGS,
    Diagnosis,
    LayerAResult,
    LayerBOutcome,
    LayerCOutcome,
    LayerDOutcome,
    LayerOutcomes,
    classify_layer_b,
    determine_final_diagnosis,
)


class TestClassifyLayerB:
    def test_200_with_price_is_ok(self):
        assert (
            classify_layer_b(status_code=200, network_error=False, is_json=True, has_required_fields=True)
            == LayerBOutcome.OK
        )

    def test_200_without_json_is_contract_mismatch(self):
        assert (
            classify_layer_b(status_code=200, network_error=False, is_json=False, has_required_fields=False)
            == LayerBOutcome.CONTRACT_MISMATCH
        )

    def test_200_json_missing_price_is_contract_mismatch(self):
        assert (
            classify_layer_b(status_code=200, network_error=False, is_json=True, has_required_fields=False)
            == LayerBOutcome.CONTRACT_MISMATCH
        )

    def test_401_is_key_invalid(self):
        assert (
            classify_layer_b(status_code=401, network_error=False, is_json=False, has_required_fields=False)
            == LayerBOutcome.KEY_INVALID
        )

    def test_403_is_plan_restricted(self):
        assert (
            classify_layer_b(status_code=403, network_error=False, is_json=False, has_required_fields=False)
            == LayerBOutcome.PLAN_RESTRICTED
        )

    def test_429_is_rate_limited(self):
        assert (
            classify_layer_b(status_code=429, network_error=False, is_json=False, has_required_fields=False)
            == LayerBOutcome.RATE_LIMITED
        )

    @pytest.mark.parametrize("status", [500, 502, 503, 599])
    def test_5xx_is_server_error(self, status):
        assert (
            classify_layer_b(status_code=status, network_error=False, is_json=False, has_required_fields=False)
            == LayerBOutcome.SERVER_ERROR
        )

    def test_network_error_overrides_any_status(self):
        assert (
            classify_layer_b(status_code=200, network_error=True, is_json=True, has_required_fields=True)
            == LayerBOutcome.NETWORK_BLOCKED
        )

    def test_no_status_code_is_network_blocked(self):
        assert (
            classify_layer_b(status_code=None, network_error=True, is_json=False, has_required_fields=False)
            == LayerBOutcome.NETWORK_BLOCKED
        )

    def test_unmapped_status_is_contract_mismatch(self):
        # e.g. a 3xx redirect this integration has no documented mapping for.
        assert (
            classify_layer_b(status_code=302, network_error=False, is_json=False, has_required_fields=False)
            == LayerBOutcome.CONTRACT_MISMATCH
        )


class TestDetermineFinalDiagnosis:
    def test_layer_a_network_blocked_short_circuits_everything(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.NETWORK_BLOCKED,
            layer_b=LayerBOutcome.OK,
            layer_c=LayerCOutcome.OK,
            layer_d=LayerDOutcome.OK,
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_NETWORK_BLOCKED

    def test_layer_b_network_blocked(self):
        outcomes = LayerOutcomes(layer_a=LayerAResult.OK, layer_b=LayerBOutcome.NETWORK_BLOCKED)
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_NETWORK_BLOCKED

    def test_layer_b_key_invalid(self):
        outcomes = LayerOutcomes(layer_a=LayerAResult.OK, layer_b=LayerBOutcome.KEY_INVALID)
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_KEY_INVALID

    def test_layer_b_plan_restricted(self):
        outcomes = LayerOutcomes(layer_a=LayerAResult.OK, layer_b=LayerBOutcome.PLAN_RESTRICTED)
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_PLAN_RESTRICTION

    @pytest.mark.parametrize(
        "layer_b_outcome",
        [LayerBOutcome.RATE_LIMITED, LayerBOutcome.SERVER_ERROR, LayerBOutcome.CONTRACT_MISMATCH],
    )
    def test_layer_b_edge_cases_are_inconclusive_not_forced_into_another_category(self, layer_b_outcome):
        outcomes = LayerOutcomes(layer_a=LayerAResult.OK, layer_b=layer_b_outcome)
        assert determine_final_diagnosis(outcomes) == Diagnosis.INCONCLUSIVE

    def test_layer_b_ok_layer_c_not_run_is_connection_confirmed(self):
        outcomes = LayerOutcomes(layer_a=LayerAResult.OK, layer_b=LayerBOutcome.OK)
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_CONNECTION_CONFIRMED

    def test_layer_c_client_error_is_basirah_client_broken(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.OK, layer_b=LayerBOutcome.OK, layer_c=LayerCOutcome.CLIENT_ERROR
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.BASIRAH_CLIENT_BROKEN

    def test_layer_c_parser_error_is_basirah_parser_mismatch(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.OK, layer_b=LayerBOutcome.OK, layer_c=LayerCOutcome.PARSER_ERROR
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.BASIRAH_PARSER_MISMATCH

    def test_layer_c_ok_layer_d_not_run_is_connection_confirmed(self):
        outcomes = LayerOutcomes(layer_a=LayerAResult.OK, layer_b=LayerBOutcome.OK, layer_c=LayerCOutcome.OK)
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_CONNECTION_CONFIRMED

    def test_layer_d_plan_restricted_is_entitlement_not_bug(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.OK,
            layer_b=LayerBOutcome.OK,
            layer_c=LayerCOutcome.OK,
            layer_d=LayerDOutcome.PLAN_RESTRICTED,
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_PLAN_RESTRICTION

    def test_layer_d_network_blocked(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.OK,
            layer_b=LayerBOutcome.OK,
            layer_c=LayerCOutcome.OK,
            layer_d=LayerDOutcome.NETWORK_BLOCKED,
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.SAHMK_NETWORK_BLOCKED

    def test_layer_d_parser_error(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.OK,
            layer_b=LayerBOutcome.OK,
            layer_c=LayerCOutcome.OK,
            layer_d=LayerDOutcome.PARSER_ERROR,
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.BASIRAH_PARSER_MISMATCH

    def test_layer_d_pipeline_error(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.OK,
            layer_b=LayerBOutcome.OK,
            layer_c=LayerCOutcome.OK,
            layer_d=LayerDOutcome.PIPELINE_ERROR,
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.BASIRAH_PIPELINE_BROKEN

    def test_full_success_path(self):
        outcomes = LayerOutcomes(
            layer_a=LayerAResult.OK,
            layer_b=LayerBOutcome.OK,
            layer_c=LayerCOutcome.OK,
            layer_d=LayerDOutcome.OK,
        )
        assert determine_final_diagnosis(outcomes) == Diagnosis.FULL_END_TO_END_SUCCESS

    def test_every_diagnosis_has_a_meaning_string(self):
        for d in Diagnosis:
            assert d in DIAGNOSIS_MEANINGS
            assert isinstance(DIAGNOSIS_MEANINGS[d], str)
            assert len(DIAGNOSIS_MEANINGS[d]) > 0

    def test_inconclusive_is_the_only_non_conclusive_diagnosis(self):
        assert Diagnosis.INCONCLUSIVE not in CONCLUSIVE_DIAGNOSES
        assert len(CONCLUSIVE_DIAGNOSES) == len(list(Diagnosis)) - 1
        for d in Diagnosis:
            if d is not Diagnosis.INCONCLUSIVE:
                assert d in CONCLUSIVE_DIAGNOSES


class TestDiagnosisEnumMatchesTaskSpec:
    """Locks the exact 8 required diagnosis codes so a future refactor
    can't silently rename/drop one of them."""

    REQUIRED_CODES = {
        "SAHMK_CONNECTION_CONFIRMED",
        "SAHMK_KEY_INVALID",
        "SAHMK_PLAN_RESTRICTION",
        "SAHMK_NETWORK_BLOCKED",
        "BASIRAH_CLIENT_BROKEN",
        "BASIRAH_PARSER_MISMATCH",
        "BASIRAH_PIPELINE_BROKEN",
        "FULL_END_TO_END_SUCCESS",
    }

    def test_all_required_codes_present(self):
        actual = {d.value for d in Diagnosis}
        assert self.REQUIRED_CODES.issubset(actual)

    def test_only_one_extension_beyond_the_required_8(self):
        actual = {d.value for d in Diagnosis}
        extra = actual - self.REQUIRED_CODES
        assert extra == {"INCONCLUSIVE"}
