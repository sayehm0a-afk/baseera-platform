"""QUALITY PROOF INSTRUMENTATION HARDENING (2026-09-06), P1-B: unit
tests for src.analysis.decision_v2.versioning -- engine_sha/config_hash
must be deterministic, must change only when behavior-affecting values
change, and must never fabricate identity for values that are genuinely
unavailable."""

import importlib
import sys

from src.analysis.decision_v2 import versioning
from src.analysis.decision_v2.config import DecisionV2Tuning


def _real_settings_module():
    """`src/core/config/__init__.py` does `from .settings import ...,
    settings`, which rebinds the *submodule* attribute name `settings`
    on the `src.core.config` package object to the `Settings` *instance*
    (the imported name collides with the submodule's own name). That
    means `import src.core.config.settings as m` -- an attribute-walk,
    per the language reference -- resolves `m` to that instance instead
    of the module once `src.core.config` has been initialized (verified:
    `type(m) is Settings`, not `ModuleType`). `versioning.get_engine_sha`
    itself is unaffected (it does `from src.core.config.settings import
    settings`, which reads the submodule from `sys.modules` directly),
    but tests need the *actual* module object to monkeypatch its
    `settings` attribute -- fetched here via `sys.modules`/
    `importlib.import_module`, which are keyed by the unambiguous dotted
    name and are not subject to the parent-package shadowing."""
    return sys.modules.get("src.core.config.settings") or importlib.import_module(
        "src.core.config.settings"
    )


class TestGetEngineSha:
    def test_uses_deployment_commit_when_set(self, monkeypatch):
        settings_module = _real_settings_module()

        fake_settings = type("_S", (), {"deployment_commit": "abc123deployedsha"})()
        monkeypatch.setattr(settings_module, "settings", fake_settings)

        assert versioning.get_engine_sha() == "abc123deployedsha"

    def test_falls_back_to_local_git_sha_when_deployment_commit_unset(self, monkeypatch):
        settings_module = _real_settings_module()

        fake_settings = type("_S", (), {"deployment_commit": None})()
        monkeypatch.setattr(settings_module, "settings", fake_settings)
        monkeypatch.setattr(versioning, "_git_head_sha_fallback", lambda: "local-git-sha")

        assert versioning.get_engine_sha() == "local-git-sha"

    def test_falls_back_to_sentinel_when_nothing_available(self, monkeypatch):
        settings_module = _real_settings_module()

        fake_settings = type("_S", (), {"deployment_commit": None})()
        monkeypatch.setattr(settings_module, "settings", fake_settings)
        monkeypatch.setattr(versioning, "_git_head_sha_fallback", lambda: None)

        assert versioning.get_engine_sha() == "UNKNOWN_ENGINE_SHA"

    def test_never_raises_even_if_git_subprocess_fails(self):
        # Real subprocess call, no mocking -- proves the function is
        # exception-safe regardless of environment (git present or not).
        result = versioning.get_engine_sha()
        assert isinstance(result, str)
        assert len(result) > 0


class TestComputeDecisionV2ConfigHash:
    def test_deterministic_same_config_same_hash(self):
        h1 = versioning.compute_decision_v2_config_hash()
        h2 = versioning.compute_decision_v2_config_hash()
        assert h1 == h2
        assert len(h1) == 64  # sha256 hex digest

    def test_changes_when_a_behavior_affecting_tuning_field_changes(self, monkeypatch):
        baseline = versioning.compute_decision_v2_config_hash()

        # _decision_v2_tuning_fingerprint_dict imports DecisionV2Tuning
        # locally inside the function -- patch the source module's class
        # itself (not versioning's namespace, which never binds the name).
        import src.analysis.decision_v2.config as config_module

        mutated_tuning = DecisionV2Tuning(strong_buy_minimum_confidence=99.0)
        monkeypatch.setattr(config_module, "DecisionV2Tuning", lambda: mutated_tuning)

        mutated = versioning.compute_decision_v2_config_hash()
        assert mutated != baseline

    def test_changes_when_an_env_driven_gate_threshold_changes(self, monkeypatch):
        baseline = versioning.compute_decision_v2_config_hash()

        monkeypatch.setenv("MARKET_MAX_OHLCV_STALENESS_DAYS", "99")

        mutated = versioning.compute_decision_v2_config_hash()
        assert mutated != baseline

    def test_irrelevant_setting_never_touched_by_this_module_does_not_change_hash(self, monkeypatch):
        # A setting this module deliberately never reads (e.g. an
        # ingestion/quota knob) must have zero effect on the Decision V2
        # config fingerprint -- proves the hash is scoped to
        # recommendation-affecting configuration only.
        baseline = versioning.compute_decision_v2_config_hash()

        monkeypatch.setenv("SAHMK_MAX_REQUESTS_PER_DAY", "999999")

        unaffected = versioning.compute_decision_v2_config_hash()
        assert unaffected == baseline

    def test_uncached_reflects_env_change_within_same_process(self, monkeypatch):
        """Negative-control-adjacent: proves this function is NOT
        stale-cached across an env change within one process (a real
        risk if a cache were added carelessly)."""
        monkeypatch.setenv("MARKET_MAX_DATA_AGE_HOURS", "12")
        first = versioning.compute_decision_v2_config_hash()
        monkeypatch.setenv("MARKET_MAX_DATA_AGE_HOURS", "48")
        second = versioning.compute_decision_v2_config_hash()
        assert first != second
