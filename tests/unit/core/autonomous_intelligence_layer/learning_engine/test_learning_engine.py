import pytest
from datetime import datetime
from src.core.autonomous_intelligence_layer.learning_engine.learning_engine import (
    LearningType, Experience, LearningPattern, LearningResult, LearningEngineConfig, LearningEngine
)

# Test LearningType Enum


def test_learning_type_enum():
    assert LearningType.SUPERVISED.value == "supervised"
    assert LearningType.UNSUPERVISED.value == "unsupervised"
    assert LearningType.REINFORCEMENT.value == "reinforcement"
    assert LearningType.TRANSFER.value == "transfer"

# Test Experience dataclass


def test_experience_dataclass():
    exp = Experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    assert exp.experience_id == "exp1"
    assert exp.experience_type == "type1"
    assert exp.input_data == {"in": 1}
    assert exp.output_data == {"out": 1}
    assert exp.outcome == "SUCCESS"
    assert isinstance(exp.timestamp, datetime)
    assert exp.metadata == {}

# Test LearningPattern dataclass


def test_learning_pattern_dataclass():
    pattern = LearningPattern("pat1", "typeA", {"data": "X"}, 0.9, 5)
    assert pattern.pattern_id == "pat1"
    assert pattern.pattern_type == "typeA"
    assert pattern.pattern_data == {"data": "X"}
    assert pattern.confidence == 0.9
    assert pattern.occurrences == 5
    assert isinstance(pattern.timestamp, datetime)
    assert pattern.metadata == {}

# Test LearningResult dataclass


def test_learning_result_dataclass():
    result = LearningResult("res1", LearningType.SUPERVISED, ["pat1"], {"metric": 0.8})
    assert result.learning_id == "res1"
    assert result.learning_type == LearningType.SUPERVISED
    assert result.patterns_discovered == ["pat1"]
    assert result.improvement_metrics == {"metric": 0.8}
    assert isinstance(result.timestamp, datetime)
    assert result.metadata == {}

# Test LearningEngineConfig dataclass


def test_learning_engine_config_dataclass():
    config = LearningEngineConfig()
    assert config.enable_pattern_recognition is True
    assert config.min_pattern_confidence == 0.7
    assert config.max_experiences == 100000
    assert config.max_patterns == 10000

# Test LearningEngine class


@pytest.fixture
def learning_engine():
    return LearningEngine()


def test_learning_engine_init(learning_engine):
    assert isinstance(learning_engine.config, LearningEngineConfig)
    assert learning_engine.experiences == {}
    assert learning_engine.patterns == {}
    assert learning_engine.learning_results == {}
    assert learning_engine.experience_history == []


def test_learning_engine_init_with_custom_config():
    custom_config = LearningEngineConfig(min_pattern_confidence=0.9, max_experiences=10)
    engine = LearningEngine(config=custom_config)
    assert engine.config.min_pattern_confidence == 0.9
    assert engine.config.max_experiences == 10


def test_record_experience(learning_engine):
    exp = learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    assert exp is not None
    assert "exp1" in learning_engine.experiences
    assert learning_engine.experiences["exp1"] == exp
    assert learning_engine.experience_history == [exp]


def test_record_experience_max_limit(learning_engine):
    learning_engine.config.max_experiences = 1
    learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    exp2 = learning_engine.record_experience("exp2", "type2", {"in": 2}, {"out": 2}, "FAILURE")
    assert exp2 is None
    assert len(learning_engine.experiences) == 1


def test_discover_pattern(learning_engine):
    pattern = learning_engine.discover_pattern("pat1", "typeA", {"data": "X"}, 0.8)
    assert pattern is not None
    assert "pat1" in learning_engine.patterns
    assert learning_engine.patterns["pat1"] == pattern


def test_discover_pattern_below_confidence_threshold(learning_engine):
    pattern = learning_engine.discover_pattern("pat2", "typeB", {"data": "Y"}, 0.6)
    assert pattern is None
    assert "pat2" not in learning_engine.patterns


def test_discover_pattern_max_limit(learning_engine):
    learning_engine.config.max_patterns = 1
    learning_engine.discover_pattern("pat1", "typeA", {"data": "X"}, 0.8)
    pattern2 = learning_engine.discover_pattern("pat2", "typeB", {"data": "Y"}, 0.9)
    assert pattern2 is None
    assert len(learning_engine.patterns) == 1


def test_learn_from_experiences_no_experiences(learning_engine):
    result = learning_engine.learn_from_experiences("learn1", LearningType.SUPERVISED)
    assert result is None


def test_learn_from_experiences_success(learning_engine):
    learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    learning_engine.record_experience("exp2", "type1", {"in": 2}, {"out": 2}, "SUCCESS")
    learning_engine.discover_pattern("pat1", "typeA", {"data": "X"}, 0.8)

    result = learning_engine.learn_from_experiences("learn1", LearningType.SUPERVISED)
    assert result is not None
    assert "learn1" in learning_engine.learning_results
    assert result.learning_type == LearningType.SUPERVISED
    assert result.patterns_discovered == ["pat1"]
    assert result.improvement_metrics["success_rate"] == 1.0
    assert result.improvement_metrics["successful_experiences"] == 2
    assert result.improvement_metrics["failed_experiences"] == 0
    assert result.improvement_metrics["total_experiences"] == 2


def test_learn_from_experiences_failure(learning_engine):
    learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "FAILURE")
    learning_engine.record_experience("exp2", "type1", {"in": 2}, {"out": 2}, "PARTIAL")

    result = learning_engine.learn_from_experiences("learn1", LearningType.SUPERVISED)
    assert result is not None
    assert result.improvement_metrics["success_rate"] == 0.0
    assert result.improvement_metrics["successful_experiences"] == 0
    assert result.improvement_metrics["failed_experiences"] == 1
    assert result.improvement_metrics["total_experiences"] == 2


def test_get_experience(learning_engine):
    exp = learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    retrieved_exp = learning_engine.get_experience("exp1")
    assert retrieved_exp == exp
    assert learning_engine.get_experience("non_existent") is None


def test_get_pattern(learning_engine):
    pattern = learning_engine.discover_pattern("pat1", "typeA", {"data": "X"}, 0.8)
    retrieved_pattern = learning_engine.get_pattern("pat1")
    assert retrieved_pattern == pattern
    assert learning_engine.get_pattern("non_existent") is None


def test_get_learning_result(learning_engine):
    learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    result = learning_engine.learn_from_experiences("learn1", LearningType.SUPERVISED)
    retrieved_result = learning_engine.get_learning_result("learn1")
    assert retrieved_result == result
    assert learning_engine.get_learning_result("non_existent") is None


def test_get_experience_history(learning_engine):
    exp1 = learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    exp2 = learning_engine.record_experience("exp2", "type2", {"in": 2}, {"out": 2}, "FAILURE")
    assert learning_engine.get_experience_history() == [exp1, exp2]


def test_get_successful_experiences(learning_engine):
    exp1 = learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    learning_engine.record_experience("exp2", "type2", {"in": 2}, {"out": 2}, "FAILURE")
    exp3 = learning_engine.record_experience("exp3", "type3", {"in": 3}, {"out": 3}, "SUCCESS")
    assert learning_engine.get_successful_experiences() == [exp1, exp3]


def test_get_failed_experiences(learning_engine):
    learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    exp2 = learning_engine.record_experience("exp2", "type2", {"in": 2}, {"out": 2}, "FAILURE")
    exp3 = learning_engine.record_experience("exp3", "type3", {"in": 3}, {"out": 3}, "PARTIAL")
    assert learning_engine.get_failed_experiences() == [exp2]


def test_get_high_confidence_patterns(learning_engine):
    learning_engine.discover_pattern("pat1", "typeA", {"data": "X"}, 0.8)
    learning_engine.discover_pattern("pat2", "typeB", {"data": "Y"}, 0.6)  # Below threshold
    pat3 = learning_engine.discover_pattern("pat3", "typeC", {"data": "Z"}, 0.9)
    assert learning_engine.get_high_confidence_patterns() == [learning_engine.patterns["pat1"], pat3]


def test_get_success_rate(learning_engine):
    learning_engine.record_experience("exp1", "type1", {"in": 1}, {"out": 1}, "SUCCESS")
    learning_engine.record_experience("exp2", "type2", {"in": 2}, {"out": 2}, "FAILURE")
    assert learning_engine.get_success_rate() == 0.5


def test_get_success_rate_no_experiences(learning_engine):
    assert learning_engine.get_success_rate() == 0.0


def test_recommend_strategy(learning_engine):
    learning_engine.discover_pattern("pat1", "typeA", {"data": "X"}, 0.8)
    learning_engine.discover_pattern("pat2", "typeB", {"data": "Y"}, 0.95)
    learning_engine.discover_pattern("pat3", "typeC", {"data": "Z"}, 0.7)

    recommendation = learning_engine.recommend_strategy()
    assert recommendation is not None
    assert recommendation["pattern_id"] == "pat2"
    assert recommendation["confidence"] == 0.95


def test_recommend_strategy_no_patterns(learning_engine):
    recommendation = learning_engine.recommend_strategy()
    assert recommendation is None
