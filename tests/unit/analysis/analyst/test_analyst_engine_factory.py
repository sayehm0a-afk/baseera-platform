"""Unit tests for get_analyst_engine()/get_llm_adapter() -- the one
place production code decides whether Analyst Framework narration uses
a real LLM. No real OpenAI call in any test; OPENAI_API_KEY is
explicitly unset or set to a syntactically-valid-looking placeholder,
never a real credential."""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.analyst.analyst_engine_factory import get_analyst_engine, get_llm_adapter
from src.core.db.database import Base


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


class TestGetLlmAdapter:
    def test_returns_none_when_no_api_key_is_configured(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        assert get_llm_adapter() is None

    def test_returns_a_real_adapter_when_an_api_key_is_configured(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        adapter = get_llm_adapter()
        assert adapter is not None
        assert adapter.name == "openai"


class TestGetAnalystEngine:
    def test_pipeline_has_no_llm_adapter_when_unconfigured(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        engine = get_analyst_engine(_session())
        assert engine._pipeline._llm_adapter is None

    def test_pipeline_has_a_real_adapter_when_configured(self, monkeypatch):
        monkeypatch.setenv("OPENAI_API_KEY", "sk-test-not-a-real-key")
        engine = get_analyst_engine(_session())
        assert engine._pipeline._llm_adapter is not None
        assert engine._pipeline._llm_adapter.name == "openai"

    def test_pipeline_is_given_the_session_for_ai_request_recording(self, monkeypatch):
        monkeypatch.delenv("OPENAI_API_KEY", raising=False)
        session = _session()
        engine = get_analyst_engine(session)
        assert engine._pipeline._session is session
