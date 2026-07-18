"""
Unit tests for Learning Engine
"""

import pytest
from core.autonomous_intelligence_layer.learning_engine import (
    LearningEngine,
    LearningType,
    LearningEngineConfig,
)


class TestLearningEngine:
    """Test cases for LearningEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = LearningEngine()

    def test_learning_engine_initialization(self):
        """Test that LearningEngine initializes correctly."""
        assert self.engine is not None
        assert self.engine.config is not None
        assert isinstance(self.engine.config, LearningEngineConfig)

    def test_learning_engine_with_custom_config(self):
        """Test LearningEngine with custom config."""
        custom_config = LearningEngineConfig(
            enable_pattern_recognition=False,
            min_pattern_confidence=0.8,
        )
        engine = LearningEngine(config=custom_config)
        assert engine.config.min_pattern_confidence == 0.8

    def test_record_experience(self):
        """Test recording an experience."""
        experience = self.engine.record_experience(
            experience_id="exp_001",
            experience_type="task_execution",
            input_data={"task": "process_data"},
            output_data={"result": "success"},
            outcome="SUCCESS",
        )

        assert experience is not None
        assert experience.outcome == "SUCCESS"

    def test_record_multiple_experiences(self):
        """Test recording multiple experiences."""
        for i in range(5):
            self.engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS" if i % 2 == 0 else "FAILURE",
            )

        assert len(self.engine.experiences) == 5

    def test_discover_pattern(self):
        """Test discovering a pattern."""
        pattern = self.engine.discover_pattern(
            pattern_id="pat_001",
            pattern_type="execution_pattern",
            pattern_data={"condition": "high_load", "action": "scale_up"},
            confidence=0.85,
        )

        assert pattern is not None
        assert pattern.confidence == 0.85

    def test_discover_pattern_low_confidence(self):
        """Test discovering pattern with low confidence."""
        pattern = self.engine.discover_pattern(
            pattern_id="pat_001",
            pattern_type="execution_pattern",
            pattern_data={"condition": "high_load"},
            confidence=0.5,  # Below threshold
        )

        assert pattern is None

    def test_learn_from_experiences(self):
        """Test learning from experiences."""
        # Record experiences
        for i in range(10):
            self.engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS" if i < 7 else "FAILURE",
            )

        # Discover patterns
        self.engine.discover_pattern(
            pattern_id="pat_001",
            pattern_type="execution_pattern",
            pattern_data={"condition": "high_load"},
            confidence=0.9,
        )

        result = self.engine.learn_from_experiences(
            learning_id="learn_001",
            learning_type=LearningType.SUPERVISED,
        )

        assert result is not None
        assert result.improvement_metrics["success_rate"] == 0.7

    def test_get_experience(self):
        """Test retrieving an experience."""
        self.engine.record_experience(
            experience_id="exp_001",
            experience_type="task_execution",
            input_data={"task": "process_data"},
            output_data={"result": "success"},
            outcome="SUCCESS",
        )

        experience = self.engine.get_experience("exp_001")
        assert experience is not None
        assert experience.outcome == "SUCCESS"

    def test_get_pattern(self):
        """Test retrieving a pattern."""
        self.engine.discover_pattern(
            pattern_id="pat_001",
            pattern_type="execution_pattern",
            pattern_data={"condition": "high_load"},
            confidence=0.9,
        )

        pattern = self.engine.get_pattern("pat_001")
        assert pattern is not None

    def test_get_learning_result(self):
        """Test retrieving a learning result."""
        self.engine.record_experience(
            experience_id="exp_001",
            experience_type="task_execution",
            input_data={"task": "process_data"},
            output_data={"result": "success"},
            outcome="SUCCESS",
        )

        self.engine.learn_from_experiences(
            learning_id="learn_001",
            learning_type=LearningType.SUPERVISED,
        )

        result = self.engine.get_learning_result("learn_001")
        assert result is not None

    def test_get_experience_history(self):
        """Test getting experience history."""
        for i in range(5):
            self.engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS",
            )

        history = self.engine.get_experience_history()
        assert len(history) == 5

    def test_get_successful_experiences(self):
        """Test getting successful experiences."""
        for i in range(10):
            self.engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS" if i < 7 else "FAILURE",
            )

        successful = self.engine.get_successful_experiences()
        assert len(successful) == 7

    def test_get_failed_experiences(self):
        """Test getting failed experiences."""
        for i in range(10):
            self.engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS" if i < 7 else "FAILURE",
            )

        failed = self.engine.get_failed_experiences()
        assert len(failed) == 3

    def test_get_high_confidence_patterns(self):
        """Test getting high confidence patterns."""
        for i in range(5):
            confidence = 0.6 + i * 0.1
            self.engine.discover_pattern(
                pattern_id=f"pat_{i:03d}",
                pattern_type="execution_pattern",
                pattern_data={"condition": f"condition_{i}"},
                confidence=confidence,
            )

        high_conf = self.engine.get_high_confidence_patterns()
        assert len(high_conf) > 0

    def test_get_success_rate(self):
        """Test getting success rate."""
        for i in range(10):
            self.engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS" if i < 7 else "FAILURE",
            )

        success_rate = self.engine.get_success_rate()
        assert success_rate == 0.7

    def test_recommend_strategy(self):
        """Test recommending a strategy."""
        self.engine.discover_pattern(
            pattern_id="pat_001",
            pattern_type="execution_pattern",
            pattern_data={"condition": "high_load", "action": "scale_up"},
            confidence=0.9,
        )

        recommendation = self.engine.recommend_strategy()
        assert recommendation is not None
        assert recommendation["pattern_id"] == "pat_001"

    def test_recommend_strategy_no_patterns(self):
        """Test recommending strategy with no patterns."""
        recommendation = self.engine.recommend_strategy()
        assert recommendation is None

    def test_multiple_learning_types(self):
        """Test different learning types."""
        learning_types = [
            LearningType.SUPERVISED,
            LearningType.UNSUPERVISED,
            LearningType.REINFORCEMENT,
            LearningType.TRANSFER,
        ]

        for i, learning_type in enumerate(learning_types):
            self.engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS",
            )

            result = self.engine.learn_from_experiences(
                learning_id=f"learn_{i:03d}",
                learning_type=learning_type,
            )

            assert result is not None
            assert result.learning_type == learning_type

    def test_experience_limit(self):
        """Test experience limit enforcement."""
        config = LearningEngineConfig(max_experiences=5)
        engine = LearningEngine(config=config)

        for i in range(5):
            result = engine.record_experience(
                experience_id=f"exp_{i:03d}",
                experience_type="task_execution",
                input_data={"task": f"task_{i}"},
                output_data={"result": "success"},
                outcome="SUCCESS",
            )
            assert result is not None

        # Should fail when limit reached
        result = engine.record_experience(
            experience_id="exp_005",
            experience_type="task_execution",
            input_data={"task": "task_5"},
            output_data={"result": "success"},
            outcome="SUCCESS",
        )
        assert result is None
