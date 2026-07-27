from src.analysis.analyst.config import (
    get_analyst_llm_model_name,
    get_analyst_llm_timeout_seconds,
    is_analyst_llm_narration_enabled,
)


class TestGetAnalystLlmModelName:
    def test_defaults_to_gpt_4o_mini(self, monkeypatch):
        monkeypatch.delenv("ANALYST_LLM_MODEL", raising=False)
        assert get_analyst_llm_model_name() == "gpt-4o-mini"

    def test_reads_env_override(self, monkeypatch):
        monkeypatch.setenv("ANALYST_LLM_MODEL", "gpt-4-turbo")
        assert get_analyst_llm_model_name() == "gpt-4-turbo"


class TestGetAnalystLlmTimeoutSeconds:
    def test_defaults_to_12_seconds(self, monkeypatch):
        monkeypatch.delenv("ANALYST_LLM_TIMEOUT_SECONDS", raising=False)
        assert get_analyst_llm_timeout_seconds() == 12.0

    def test_reads_env_override(self, monkeypatch):
        monkeypatch.setenv("ANALYST_LLM_TIMEOUT_SECONDS", "5")
        assert get_analyst_llm_timeout_seconds() == 5.0


class TestIsAnalystLlmNarrationEnabled:
    def test_false_when_no_api_key_is_configured(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert is_analyst_llm_narration_enabled() is False

    def test_true_when_an_api_key_is_configured(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        assert is_analyst_llm_narration_enabled() is True
