"""Structural conformance tests: ExpertResult satisfies AnalysisOutput
and CouncilResult satisfies AnalysisEngineResult, without either
importing src.analysis.core.contracts -- the same proof
tests/unit/analysis/core/test_contracts.py already establishes for
IndicatorOutput/TechnicalAnalysisResult and
tests/unit/analysis/composite/test_types.py establishes for
CompositeFactorOutput/CompositeResult.
"""

from datetime import datetime, timezone

import pytest

from src.analysis.composite.types import DataCompleteness, Freshness
from src.analysis.core.contracts import AnalysisEngineResult, AnalysisOutput
from src.analysis.experts.types import Council, CouncilResult, EvidenceItem, ExpertDirection, ExpertResult


def _make_expert_result(expert_id="technical.trend", score=0.6, confidence=0.7):
    return ExpertResult(
        expert_id=expert_id,
        expert_name="Trend Expert",
        council=Council.TECHNICAL,
        domain="trend",
        symbol="1111",
        as_of=datetime(2026, 1, 1, tzinfo=timezone.utc),
        direction=ExpertDirection.BULLISH,
        normalized_score=score,
        confidence=confidence,
        completeness=DataCompleteness.COMPLETE,
        freshness=Freshness.FRESH,
        evidence=(EvidenceItem("ema_20", 12.0, "trend.ema_above_sma_is_bullish", 1.0),),
        contributing_metrics=("ema_20", "sma_20"),
        rule_ids=("trend.ema_above_sma_is_bullish",),
        warnings=(),
        conflicts=(),
        limitations=(),
        version="1.0.0",
        metadata={},
    )


def test_expert_result_satisfies_analysis_output():
    result = _make_expert_result()
    assert isinstance(result, AnalysisOutput)
    assert result.name == result.expert_id
    assert result.category == Council.TECHNICAL
    assert result.value == result.normalized_score
    assert result.latest() == result.normalized_score


def test_expert_result_name_is_expert_id():
    # AnalysisOutput.name has no dedicated field on ExpertResult (per
    # BEIF Section 4) -- expert_id serves as `name` structurally, since
    # ExpertResult has no separate `name` attribute; this test locks
    # that convention in.
    result = _make_expert_result(expert_id="technical.momentum")
    assert result.expert_id == "technical.momentum"


def test_council_result_satisfies_analysis_engine_result():
    expert = _make_expert_result()
    result = CouncilResult(council=Council.TECHNICAL, experts={expert.expert_id: expert})

    assert isinstance(result, AnalysisEngineResult)
    assert result.get("technical.trend") is expert
    assert result.latest_snapshot() == {"technical.trend": expert.normalized_score}


def test_council_result_get_raises_key_error_for_unknown_expert():
    result = CouncilResult(council=Council.TECHNICAL, experts={})
    with pytest.raises(KeyError):
        result.get("does_not_exist")


def test_council_result_latest_snapshot_empty_when_no_experts():
    result = CouncilResult(council=Council.TECHNICAL, experts={})
    assert result.latest_snapshot() == {}


def test_expert_result_insufficient_completeness_has_none_score():
    result = _make_expert_result(score=None, confidence=0.0)
    assert result.latest() is None
    assert result.value is None
