"""
Unit tests for Debate Engine
"""

import pytest
from core.autonomous_intelligence_layer.debate_engine import (
    DebateEngine,
    DebateSession,
    Argument,
    ArgumentType,
    DebatePhase,
    DebateConfig,
)


class TestDebateEngine:
    """Test cases for DebateEngine class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.engine = DebateEngine()
        self.session_id = "debate_001"
        self.topic = "Should AI be regulated?"
        self.participants = ["agent_1", "agent_2", "agent_3"]

    def test_debate_engine_initialization(self):
        """Test that DebateEngine initializes correctly."""
        assert self.engine is not None
        assert self.engine.config is not None
        assert isinstance(self.engine.config, DebateConfig)
        assert len(self.engine.sessions) == 0

    def test_debate_engine_with_custom_config(self):
        """Test DebateEngine with custom config."""
        custom_config = DebateConfig(
            max_rounds=5,
            max_arguments_per_round=3,
        )
        engine = DebateEngine(config=custom_config)
        assert engine.config.max_rounds == 5
        assert engine.config.max_arguments_per_round == 3

    def test_create_session(self):
        """Test creating a debate session."""
        session = self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        assert session is not None
        assert session.session_id == self.session_id
        assert session.topic == self.topic
        assert session.participants == self.participants
        assert session.current_phase == DebatePhase.OPENING

    def test_add_argument(self):
        """Test adding an argument to a debate."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        argument = self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_001",
            agent_id="agent_1",
            content="AI regulation is necessary for safety.",
            argument_type=ArgumentType.PRO,
            confidence=0.9,
        )

        assert argument is not None
        assert argument.argument_id == "arg_001"
        assert argument.agent_id == "agent_1"
        assert argument.argument_type == ArgumentType.PRO
        assert argument.confidence == 0.9

    def test_add_multiple_arguments(self):
        """Test adding multiple arguments."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_001",
            agent_id="agent_1",
            content="AI regulation is necessary.",
            argument_type=ArgumentType.PRO,
        )

        self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_002",
            agent_id="agent_2",
            content="Regulation might stifle innovation.",
            argument_type=ArgumentType.CON,
        )

        session = self.engine.get_session(self.session_id)
        assert len(session.rounds) >= 1
        assert len(session.rounds[0].arguments) == 2

    def test_add_argument_to_nonexistent_session(self):
        """Test adding argument to nonexistent session."""
        argument = self.engine.add_argument(
            session_id="nonexistent",
            argument_id="arg_001",
            agent_id="agent_1",
            content="Test argument",
            argument_type=ArgumentType.PRO,
        )

        assert argument is None

    def test_add_argument_with_evidence(self):
        """Test adding argument with supporting evidence."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        evidence = ["Study 1", "Study 2", "Report X"]
        argument = self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_001",
            agent_id="agent_1",
            content="Evidence shows regulation is beneficial.",
            argument_type=ArgumentType.EVIDENCE,
            supporting_evidence=evidence,
        )

        assert argument is not None
        assert argument.supporting_evidence == evidence

    def test_advance_phase(self):
        """Test advancing debate phase."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        session = self.engine.get_session(self.session_id)
        assert session.current_phase == DebatePhase.OPENING

        self.engine.advance_phase(self.session_id, DebatePhase.DISCUSSION)
        session = self.engine.get_session(self.session_id)
        assert session.current_phase == DebatePhase.DISCUSSION

    def test_conclude_debate(self):
        """Test concluding a debate."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        self.engine.advance_phase(self.session_id, DebatePhase.CONCLUDED)
        session = self.engine.get_session(self.session_id)
        assert session.current_phase == DebatePhase.CONCLUDED
        assert session.concluded_at is not None

    def test_detect_consensus_no_arguments(self):
        """Test consensus detection with no arguments."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        consensus_reached, score = self.engine.detect_consensus(self.session_id)
        assert consensus_reached is False
        assert score == 0.0

    def test_detect_consensus_with_agreement(self):
        """Test consensus detection with agreeing arguments."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        # Add mostly pro arguments
        for i in range(4):
            self.engine.add_argument(
                session_id=self.session_id,
                argument_id=f"arg_{i:03d}",
                agent_id=f"agent_{i % 3}",
                content=f"Pro argument {i}",
                argument_type=ArgumentType.PRO,
                confidence=0.9,
            )

        # Add one con argument
        self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_con",
            agent_id="agent_1",
            content="Con argument",
            argument_type=ArgumentType.CON,
            confidence=0.3,
        )

        consensus_reached, score = self.engine.detect_consensus(self.session_id)
        assert consensus_reached is True
        assert score > self.engine.config.consensus_threshold

    def test_analyze_arguments(self):
        """Test analyzing arguments."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_001",
            agent_id="agent_1",
            content="Pro argument",
            argument_type=ArgumentType.PRO,
            confidence=0.9,
        )

        self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_002",
            agent_id="agent_2",
            content="Con argument",
            argument_type=ArgumentType.CON,
            confidence=0.5,
        )

        analysis = self.engine.analyze_arguments(self.session_id)

        assert analysis["session_id"] == self.session_id
        assert analysis["topic"] == self.topic
        assert analysis["total_arguments"] == 2
        assert analysis["average_confidence"] > 0
        assert "pro" in analysis["argument_types"]
        assert "con" in analysis["argument_types"]

    def test_generate_summary(self):
        """Test generating debate summary."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_001",
            agent_id="agent_1",
            content="Pro argument",
            argument_type=ArgumentType.PRO,
        )

        summary = self.engine.generate_summary(self.session_id)

        assert self.topic in summary
        assert "Debate Summary" in summary
        assert "Total Arguments" in summary

    def test_get_session(self):
        """Test retrieving a session."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        session = self.engine.get_session(self.session_id)
        assert session is not None
        assert session.session_id == self.session_id

    def test_get_nonexistent_session(self):
        """Test retrieving nonexistent session."""
        session = self.engine.get_session("nonexistent")
        assert session is None

    def test_debate_history(self):
        """Test debate history tracking."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        self.engine.advance_phase(self.session_id, DebatePhase.CONCLUDED)

        history = self.engine.get_debate_history()
        assert len(history) == 1
        assert history[0].session_id == self.session_id

    def test_confidence_clamping(self):
        """Test that confidence values are clamped."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        arg1 = self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_001",
            agent_id="agent_1",
            content="High confidence",
            argument_type=ArgumentType.PRO,
            confidence=1.5,
        )

        arg2 = self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_002",
            agent_id="agent_2",
            content="Negative confidence",
            argument_type=ArgumentType.CON,
            confidence=-0.5,
        )

        assert arg1.confidence == 1.0
        assert arg2.confidence == 0.0

    def test_argument_with_references(self):
        """Test adding argument with references."""
        self.engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        references = ["https://example.com/study1", "https://example.com/study2"]
        argument = self.engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_001",
            agent_id="agent_1",
            content="Referenced argument",
            argument_type=ArgumentType.PRO,
            references=references,
        )

        assert argument.references == references

    def test_max_rounds_limit(self):
        """Test maximum rounds limit."""
        config = DebateConfig(max_rounds=1, max_arguments_per_round=2)
        engine = DebateEngine(config=config)

        engine.create_session(
            session_id=self.session_id,
            topic=self.topic,
            participants=self.participants,
        )

        # Add arguments up to limit
        for i in range(2):
            engine.add_argument(
                session_id=self.session_id,
                argument_id=f"arg_{i:03d}",
                agent_id="agent_1",
                content=f"Argument {i}",
                argument_type=ArgumentType.PRO,
            )

        # Try to add beyond limit
        result = engine.add_argument(
            session_id=self.session_id,
            argument_id="arg_999",
            agent_id="agent_1",
            content="Beyond limit",
            argument_type=ArgumentType.PRO,
        )

        # Should create a new round or fail
        session = engine.get_session(self.session_id)
        assert len(session.rounds) <= 2
