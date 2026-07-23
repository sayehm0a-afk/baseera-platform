import pytest
from src.core.autonomous_intelligence_layer.debate_engine.debate_engine import (
    DebateEngine,
    DebateConfig,
    ArgumentType,
    DebatePhase
)


@pytest.fixture
def debate_engine():
    config = DebateConfig(max_rounds=2, max_arguments_per_round=2, consensus_threshold=0.7)
    return DebateEngine(config)


def test_create_session(debate_engine):
    session = debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    assert session is not None
    assert session.session_id == "s1"
    assert session.topic == "Topic A"
    assert session.participants == ["agent1", "agent2"]
    assert session.current_phase == DebatePhase.OPENING
    assert len(debate_engine.sessions) == 1


def test_add_argument(debate_engine):
    session = debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    arg = debate_engine.add_argument("s1", "arg1", "agent1", "Content 1", ArgumentType.PRO)
    assert arg is not None
    assert arg.argument_id == "arg1"
    assert len(session.rounds) == 1
    assert len(session.rounds[0].arguments) == 1


def test_add_argument_session_not_found(debate_engine):
    arg = debate_engine.add_argument("s_nonexistent", "arg1", "agent1", "Content 1", ArgumentType.PRO)
    assert arg is None


def test_add_argument_concluded_session(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    debate_engine.advance_phase("s1", DebatePhase.CONCLUDED)
    arg = debate_engine.add_argument("s1", "arg1", "agent1", "Content 1", ArgumentType.PRO)
    assert arg is None


def test_add_argument_max_rounds_reached(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    debate_engine.add_argument("s1", "arg1", "agent1", "Content 1", ArgumentType.PRO)
    debate_engine.add_argument("s1", "arg2", "agent2", "Content 2", ArgumentType.CON)
    debate_engine.add_argument("s1", "arg3", "agent1", "Content 3", ArgumentType.PRO)
    debate_engine.add_argument("s1", "arg4", "agent2", "Content 4", ArgumentType.CON)
    # Max rounds is 2, max arguments per round is 2. So 4 arguments fill 2 rounds.
    arg = debate_engine.add_argument("s1", "arg5", "agent1", "Content 5", ArgumentType.PRO)
    assert arg is None


def test_add_argument_max_argument_length(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    long_content = "a" * (debate_engine.config.max_argument_length + 1)
    arg = debate_engine.add_argument("s1", "arg1", "agent1", long_content, ArgumentType.PRO)
    assert arg is None


def test_add_argument_evidence_requirement(debate_engine):
    debate_engine.config.enable_evidence_requirement = True
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    arg = debate_engine.add_argument("s1", "arg1", "agent1", "Content", ArgumentType.EVIDENCE, supporting_evidence=[])
    assert arg is None
    arg = debate_engine.add_argument("s1", "arg2", "agent1", "Content", ArgumentType.EVIDENCE, supporting_evidence=["evidence1"])
    assert arg is not None


def test_advance_phase(debate_engine):
    session = debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    assert debate_engine.advance_phase("s1", DebatePhase.DISCUSSION) is True
    assert session.current_phase == DebatePhase.DISCUSSION
    assert debate_engine.advance_phase("s1", DebatePhase.CONCLUDED) is True
    assert session.current_phase == DebatePhase.CONCLUDED
    assert session.concluded_at is not None
    assert len(debate_engine.debate_history) == 1


def test_advance_phase_session_not_found(debate_engine):
    assert debate_engine.advance_phase("s_nonexistent", DebatePhase.DISCUSSION) is False


def test_detect_consensus_no_arguments(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    consensus, score = debate_engine.detect_consensus("s1")
    assert consensus is False
    assert score == 0.0


def test_detect_consensus_pro_con(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    debate_engine.add_argument("s1", "arg1", "agent1", "Pro 1", ArgumentType.PRO, confidence=0.9)
    debate_engine.add_argument("s1", "arg2", "agent2", "Con 1", ArgumentType.CON, confidence=0.1)
    debate_engine.add_argument("s1", "arg3", "agent1", "Pro 2", ArgumentType.PRO, confidence=0.8)

    consensus, score = debate_engine.detect_consensus("s1")
    assert consensus is False  # 2 pro, 1 con, threshold 0.7 -> 2/3 = 0.66, which is < 0.7
    # The current implementation of detect_consensus only counts pro/con arguments, not confidence for consensus score.
    # Let's adjust the test to reflect the current implementation or adjust the implementation.
    # Based on the code, consensus_score = max_count / total_arguments. So 2/3 = 0.66. If threshold is 0.7, it should be False.
    # Let's re-evaluate the test case or the threshold.
    # With 2 PRO and 1 CON, max_count is 2, total_arguments is 3. score = 2/3 = 0.666...
    # If threshold is 0.7, then consensus_reached should be False.
    assert consensus is False
    assert round(score, 2) == 0.67


def test_detect_consensus_reached(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    debate_engine.add_argument("s1", "arg1", "agent1", "Pro 1", ArgumentType.PRO, confidence=0.9)
    debate_engine.add_argument("s1", "arg2", "agent1", "Pro 2", ArgumentType.PRO, confidence=0.8)
    debate_engine.add_argument("s1", "arg3", "agent2", "Pro 3", ArgumentType.PRO, confidence=0.7)

    consensus, score = debate_engine.detect_consensus("s1")
    assert consensus is True  # 3 pro, 0 con, threshold 0.7 -> 3/3 = 1.0
    assert score == 1.0


def test_analyze_arguments(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    debate_engine.add_argument("s1", "arg1", "agent1", "Pro 1", ArgumentType.PRO, confidence=0.9)
    debate_engine.add_argument("s1", "arg2", "agent2", "Con 1", ArgumentType.CON, confidence=0.1)
    debate_engine.add_argument("s1", "arg3", "agent1", "Pro 2", ArgumentType.PRO, confidence=0.8)

    analysis = debate_engine.analyze_arguments("s1")
    assert analysis["total_arguments"] == 3
    assert analysis["argument_types"][ArgumentType.PRO.value] == 2
    assert analysis["argument_types"][ArgumentType.CON.value] == 1
    assert analysis["agent_contributions"]["agent1"] == 2
    assert analysis["agent_contributions"]["agent2"] == 1
    assert round(analysis["average_confidence"], 2) == round((0.9 + 0.1 + 0.8) / 3, 2)
    assert len(analysis["strongest_arguments"]) > 0
    assert len(analysis["weakest_arguments"]) > 0


def test_generate_summary(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    debate_engine.add_argument("s1", "arg1", "agent1", "Pro 1", ArgumentType.PRO, confidence=0.9)
    debate_engine.add_argument("s1", "arg2", "agent2", "Con 1", ArgumentType.CON, confidence=0.1)

    summary = debate_engine.generate_summary("s1")
    assert "Debate Summary: Topic A" in summary
    assert "Total Arguments: 2" in summary
    assert "Consensus: Not reached" in summary


def test_getters(debate_engine):
    debate_engine.create_session("s1", "Topic A", ["agent1", "agent2"])
    assert debate_engine.get_session("s1") is not None
    assert debate_engine.get_session("nonexistent") is None

    debate_engine.advance_phase("s1", DebatePhase.CONCLUDED)
    assert len(debate_engine.get_debate_history()) == 1
