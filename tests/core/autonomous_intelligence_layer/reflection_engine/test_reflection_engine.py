"""
Unit tests for Reflection Engine
"""

import pytest
from datetime import datetime
from core.autonomous_intelligence_layer.reflection_engine import (
    ReflectionEngine,
    ReflectionResult,
    ReflectionPolicy,
    ReflectionScoreLevel,
)


class TestReflectionEngine:
    """Test cases for ReflectionEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = ReflectionEngine()
        self.task_id = "test_task_001"
        self.objective = "Analyze the financial market"
        self.agent_output = "The market is bullish. However, there are concerns."

    def test_reflection_engine_initialization(self):
        """Test that ReflectionEngine initializes correctly."""
        assert self.engine is not None
        assert self.engine.policy is not None
        assert isinstance(self.engine.policy, ReflectionPolicy)
        assert len(self.engine.reflection_history) == 0

    def test_reflection_engine_with_custom_policy(self):
        """Test ReflectionEngine with custom policy."""
        custom_policy = ReflectionPolicy(
            contradiction_weight=0.5,
            hallucination_weight=0.3,
            min_score_threshold=0.6,
        )
        engine = ReflectionEngine(policy=custom_policy)
        assert engine.policy.contradiction_weight == 0.5
        assert engine.policy.hallucination_weight == 0.3
        assert engine.policy.min_score_threshold == 0.6

    def test_evaluate_output_basic(self):
        """Test basic evaluation of agent output."""
        result = self.engine.evaluate(
            task_id=self.task_id,
            agent_output=self.agent_output,
            objective=self.objective,
        )

        assert isinstance(result, ReflectionResult)
        assert result.task_id == self.task_id
        assert 0.0 <= result.reflection_score <= 1.0
        assert isinstance(result.score_level, ReflectionScoreLevel)
        assert isinstance(result.recommendations, list)

    def test_evaluate_output_with_acceptance_criteria(self):
        """Test evaluation with acceptance criteria."""
        criteria = [
            "Output should be concise",
            "Output should address the objective",
        ]
        result = self.engine.evaluate(
            task_id=self.task_id,
            agent_output=self.agent_output,
            objective=self.objective,
            acceptance_criteria=criteria,
        )

        assert result.metadata["acceptance_criteria"] == criteria

    def test_reflection_score_calculation(self):
        """Test reflection score calculation."""
        # Test with no issues
        score = self.engine._calculate_reflection_score([], [], [], [])
        assert score == 1.0

        # Test with one contradiction
        score = self.engine._calculate_reflection_score(
            contradictions=["Issue 1"],
            hallucinations=[],
            missing_evidence=[],
            weak_reasoning=[],
        )
        expected_penalty = 1 * self.engine.policy.contradiction_weight
        expected_score = max(0.0, min(1.0, 1.0 - expected_penalty))
        assert score == expected_score

    def test_score_level_determination(self):
        """Test score level determination."""
        assert self.engine._determine_score_level(0.95) == ReflectionScoreLevel.EXCELLENT
        assert self.engine._determine_score_level(0.8) == ReflectionScoreLevel.GOOD
        assert self.engine._determine_score_level(0.6) == ReflectionScoreLevel.ACCEPTABLE
        assert self.engine._determine_score_level(0.3) == ReflectionScoreLevel.POOR

    def test_contradiction_detection(self):
        """Test contradiction detection."""
        output_with_contradiction = "The market is bullish but however it is bearish"
        contradictions = self.engine._detect_contradictions(output_with_contradiction)
        assert len(contradictions) > 0

    def test_evidence_validation(self):
        """Test evidence validation."""
        short_output = "Yes"
        missing_evidence = self.engine._validate_evidence(short_output)
        assert len(missing_evidence) > 0

    def test_reasoning_validation(self):
        """Test reasoning validation."""
        output_not_addressing_objective = "The weather is nice today"
        weak_reasoning = self.engine._validate_reasoning(
            output_not_addressing_objective,
            self.objective,
        )
        assert len(weak_reasoning) > 0

    def test_reflection_history_recording(self):
        """Test that reflection results are recorded in history."""
        self.engine.evaluate(
            task_id=self.task_id,
            agent_output=self.agent_output,
            objective=self.objective,
        )

        history = self.engine.get_reflection_history()
        assert len(history) == 1
        assert history[0].task_id == self.task_id

    def test_reflection_history_filtering(self):
        """Test filtering reflection history by task ID."""
        task_id_1 = "task_001"
        task_id_2 = "task_002"

        self.engine.evaluate(
            task_id=task_id_1,
            agent_output=self.agent_output,
            objective=self.objective,
        )
        self.engine.evaluate(
            task_id=task_id_2,
            agent_output=self.agent_output,
            objective=self.objective,
        )

        history_1 = self.engine.get_reflection_history(task_id=task_id_1)
        assert len(history_1) == 1
        assert history_1[0].task_id == task_id_1

    def test_max_reflection_iterations_limit(self):
        """Test that reflection stops at max iterations."""
        policy = ReflectionPolicy(max_reflection_iterations=2)
        engine = ReflectionEngine(policy=policy)

        task_id = "test_task_iteration"

        # First evaluation
        result1 = engine.evaluate(
            task_id=task_id,
            agent_output=self.agent_output,
            objective=self.objective,
        )
        assert result1.reflection_score >= 0.0

        # Second evaluation
        result2 = engine.evaluate(
            task_id=task_id,
            agent_output=self.agent_output,
            objective=self.objective,
        )
        assert result2.reflection_score >= 0.0

        # Third evaluation should hit the limit
        result3 = engine.evaluate(
            task_id=task_id,
            agent_output=self.agent_output,
            objective=self.objective,
        )
        # Should return default result when max iterations reached
        assert "Max reflection iterations reached" in result3.recommendations[0]

    def test_reset_reflection_count(self):
        """Test resetting reflection iteration count."""
        task_id = "test_task_reset"
        self.engine.reflection_iteration_count[task_id] = 5

        self.engine.reset_reflection_count(task_id)
        assert self.engine.reflection_iteration_count[task_id] == 0

    def test_reflection_result_structure(self):
        """Test the structure of ReflectionResult."""
        result = self.engine.evaluate(
            task_id=self.task_id,
            agent_output=self.agent_output,
            objective=self.objective,
        )

        assert hasattr(result, "reflection_id")
        assert hasattr(result, "task_id")
        assert hasattr(result, "reflection_score")
        assert hasattr(result, "score_level")
        assert hasattr(result, "contradictions")
        assert hasattr(result, "hallucinations")
        assert hasattr(result, "missing_evidence")
        assert hasattr(result, "weak_reasoning")
        assert hasattr(result, "recommendations")
        assert hasattr(result, "timestamp")
        assert hasattr(result, "metadata")

    def test_recommendations_generation(self):
        """Test generation of recommendations."""
        recommendations = self.engine._generate_recommendations(
            contradictions=["Issue 1"],
            hallucinations=["Issue 2"],
            missing_evidence=["Issue 3"],
            weak_reasoning=["Issue 4"],
        )

        assert len(recommendations) >= 4
        assert any("contradiction" in rec.lower() or "logical" in rec.lower() for rec in recommendations)
        assert any("hallucination" in rec.lower() or "verify" in rec.lower() for rec in recommendations)
        assert any("evidence" in rec.lower() for rec in recommendations)
        assert any("reasoning" in rec.lower() or "logical" in rec.lower() for rec in recommendations)

    def test_recommendations_when_no_issues(self):
        """Test recommendations when no issues are detected."""
        recommendations = self.engine._generate_recommendations([], [], [], [])

        assert len(recommendations) == 1
        assert "quality standards" in recommendations[0].lower()
