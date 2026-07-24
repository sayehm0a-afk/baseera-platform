"""Unit tests for src.analysis.core.bootstrap -- the composition root."""

from src.analysis.core.bootstrap import register_default_engines
from src.analysis.core.registry import DEFAULT_ENGINE_REGISTRY
from src.analysis.fundamental.fundamental_analysis_engine import FundamentalAnalysisEngine
from src.analysis.technical_analysis_engine import TechnicalAnalysisEngine


def test_both_default_engines_are_registered():
    names = {spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs()}
    assert "technical_analysis" in names
    assert "fundamental_analysis" in names


def test_technical_engine_factory_produces_a_technical_analysis_engine():
    spec = DEFAULT_ENGINE_REGISTRY.get("technical_analysis")
    engine = spec.engine_factory()
    assert isinstance(engine, TechnicalAnalysisEngine)


def test_fundamental_engine_factory_produces_a_fundamental_analysis_engine():
    spec = DEFAULT_ENGINE_REGISTRY.get("fundamental_analysis")
    engine = spec.engine_factory()
    assert isinstance(engine, FundamentalAnalysisEngine)


def test_register_default_engines_is_idempotent():
    # A true duplicate .register() call would raise ValueError --
    # register_default_engines() must guard against that so calling it
    # more than once (e.g. from multiple test modules importing this
    # module) never raises.
    register_default_engines()
    register_default_engines()

    names = [spec.name for spec in DEFAULT_ENGINE_REGISTRY.all_specs()]
    assert names.count("technical_analysis") == 1
    assert names.count("fundamental_analysis") == 1
