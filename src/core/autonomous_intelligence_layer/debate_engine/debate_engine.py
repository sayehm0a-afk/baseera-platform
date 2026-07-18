"""
Debate Engine Module

This module implements the Debate Engine, which facilitates multi-agent discussions
and arguments to explore different perspectives on complex problems.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class ArgumentType(Enum):
    """Enumeration for argument types."""
    PRO = "pro"  # Supporting argument
    CON = "con"  # Opposing argument
    NEUTRAL = "neutral"  # Neutral perspective
    CLARIFICATION = "clarification"  # Clarifying question or statement
    EVIDENCE = "evidence"  # Supporting evidence


class DebatePhase(Enum):
    """Enumeration for debate phases."""
    OPENING = "opening"  # Initial arguments
    DISCUSSION = "discussion"  # Back and forth discussion
    REBUTTAL = "rebuttal"  # Counter arguments
    CLOSING = "closing"  # Final statements
    CONCLUDED = "concluded"  # Debate ended


@dataclass
class Argument:
    """Represents a single argument in a debate."""
    argument_id: str
    agent_id: str
    content: str
    argument_type: ArgumentType
    timestamp: datetime = field(default_factory=datetime.utcnow)
    confidence: float = 1.0  # 0.0 to 1.0
    supporting_evidence: List[str] = field(default_factory=list)
    references: List[str] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DebateRound:
    """Represents a single round in a debate."""
    round_id: str
    round_number: int
    phase: DebatePhase
    arguments: List[Argument] = field(default_factory=list)
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DebateSession:
    """Represents a complete debate session."""
    session_id: str
    topic: str
    participants: List[str]  # Agent IDs
    rounds: List[DebateRound] = field(default_factory=list)
    current_phase: DebatePhase = DebatePhase.OPENING
    created_at: datetime = field(default_factory=datetime.utcnow)
    concluded_at: Optional[datetime] = None
    consensus_reached: bool = False
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DebateConfig:
    """Configuration for Debate Engine."""
    max_rounds: int = 10
    max_arguments_per_round: int = 5
    max_argument_length: int = 5000
    enable_evidence_requirement: bool = True
    enable_consensus_detection: bool = True
    consensus_threshold: float = 0.7  # Threshold for consensus
    timeout_seconds: int = 3600  # 1 hour


class DebateEngine:
    """
    Debate Engine for facilitating multi-agent discussions.
    
    The Debate Engine is responsible for:
    - Managing debate sessions and rounds
    - Recording arguments from different agents
    - Tracking debate phases
    - Detecting consensus
    - Analyzing argument strength
    - Generating debate summaries
    """

    def __init__(self, config: Optional[DebateConfig] = None):
        """
        Initialize the Debate Engine.
        
        Args:
            config: DebateConfig instance for configuring debate behavior.
                   If None, uses default config.
        """
        self.config = config or DebateConfig()
        self.sessions: Dict[str, DebateSession] = {}
        self.debate_history: List[DebateSession] = []

    def create_session(
        self,
        session_id: str,
        topic: str,
        participants: List[str],
    ) -> DebateSession:
        """
        Create a new debate session.
        
        Args:
            session_id: Unique identifier for the session
            topic: The topic to debate
            participants: List of agent IDs participating
            
        Returns:
            DebateSession representing the new session
        """
        session = DebateSession(
            session_id=session_id,
            topic=topic,
            participants=participants,
        )

        self.sessions[session_id] = session
        logger.debug(f"Debate session created: {session_id}")
        return session

    def add_argument(
        self,
        session_id: str,
        argument_id: str,
        agent_id: str,
        content: str,
        argument_type: ArgumentType,
        confidence: float = 1.0,
        supporting_evidence: Optional[List[str]] = None,
        references: Optional[List[str]] = None,
    ) -> Optional[Argument]:
        """
        Add an argument to a debate session.
        
        Args:
            session_id: The session ID
            argument_id: Unique identifier for the argument
            agent_id: ID of the agent providing the argument
            content: The argument content
            argument_type: Type of argument
            confidence: Confidence level (0.0 to 1.0)
            supporting_evidence: Optional supporting evidence
            references: Optional references
            
        Returns:
            Argument if added successfully, None otherwise
        """
        if session_id not in self.sessions:
            logger.error(f"Session {session_id} not found")
            return None

        session = self.sessions[session_id]

        # Check if session is concluded
        if session.current_phase == DebatePhase.CONCLUDED:
            logger.warning(f"Cannot add argument to concluded session {session_id}")
            return None

        # Check round limit
        if len(session.rounds) >= self.config.max_rounds:
            logger.warning(f"Maximum rounds reached for session {session_id}")
            return None

        # Create argument
        argument = Argument(
            argument_id=argument_id,
            agent_id=agent_id,
            content=content,
            argument_type=argument_type,
            confidence=max(0.0, min(1.0, confidence)),
            supporting_evidence=supporting_evidence or [],
            references=references or [],
        )

        # Validate argument
        if not self._validate_argument(argument):
            logger.warning(f"Argument validation failed: {argument_id}")
            return None

        # Get or create current round
        if not session.rounds or len(session.rounds[-1].arguments) >= self.config.max_arguments_per_round:
            round_number = len(session.rounds) + 1
            new_round = DebateRound(
                round_id=f"{session_id}_round_{round_number}",
                round_number=round_number,
                phase=session.current_phase,
            )
            session.rounds.append(new_round)

        # Add argument to current round
        current_round = session.rounds[-1]
        current_round.arguments.append(argument)

        logger.debug(f"Argument added to session {session_id}: {argument_id}")
        return argument

    def advance_phase(self, session_id: str, new_phase: DebatePhase) -> bool:
        """
        Advance the debate to the next phase.
        
        Args:
            session_id: The session ID
            new_phase: The new phase
            
        Returns:
            True if phase advanced successfully, False otherwise
        """
        if session_id not in self.sessions:
            logger.error(f"Session {session_id} not found")
            return False

        session = self.sessions[session_id]
        session.current_phase = new_phase

        if new_phase == DebatePhase.CONCLUDED:
            session.concluded_at = datetime.utcnow()
            self.debate_history.append(session)

        logger.debug(f"Debate phase advanced: {session_id} -> {new_phase.value}")
        return True

    def detect_consensus(self, session_id: str) -> Tuple[bool, float]:
        """
        Detect if consensus has been reached.
        
        Args:
            session_id: The session ID
            
        Returns:
            Tuple of (consensus_reached, consensus_score)
        """
        if session_id not in self.sessions:
            logger.error(f"Session {session_id} not found")
            return False, 0.0

        session = self.sessions[session_id]

        if not session.rounds:
            return False, 0.0

        # Analyze arguments to detect consensus
        pro_count = 0
        con_count = 0
        total_confidence = 0.0

        for round_obj in session.rounds:
            for argument in round_obj.arguments:
                if argument.argument_type == ArgumentType.PRO:
                    pro_count += 1
                    total_confidence += argument.confidence
                elif argument.argument_type == ArgumentType.CON:
                    con_count += 1
                    total_confidence += argument.confidence

        total_arguments = pro_count + con_count
        if total_arguments == 0:
            return False, 0.0

        # Calculate consensus score
        max_count = max(pro_count, con_count)
        consensus_score = max_count / total_arguments

        # Check if consensus threshold is met
        consensus_reached = consensus_score >= self.config.consensus_threshold

        logger.debug(
            f"Consensus detection for {session_id}: "
            f"score={consensus_score:.2f}, reached={consensus_reached}"
        )

        return consensus_reached, consensus_score

    def analyze_arguments(self, session_id: str) -> Dict[str, Any]:
        """
        Analyze arguments in a debate session.
        
        Args:
            session_id: The session ID
            
        Returns:
            Dictionary containing analysis results
        """
        if session_id not in self.sessions:
            logger.error(f"Session {session_id} not found")
            return {}

        session = self.sessions[session_id]
        analysis = {
            "session_id": session_id,
            "topic": session.topic,
            "total_rounds": len(session.rounds),
            "total_arguments": 0,
            "argument_types": {},
            "agent_contributions": {},
            "average_confidence": 0.0,
            "strongest_arguments": [],
            "weakest_arguments": [],
        }

        all_arguments = []
        total_confidence = 0.0

        for round_obj in session.rounds:
            for argument in round_obj.arguments:
                all_arguments.append(argument)
                total_confidence += argument.confidence

                # Count argument types
                arg_type = argument.argument_type.value
                analysis["argument_types"][arg_type] = analysis["argument_types"].get(arg_type, 0) + 1

                # Count agent contributions
                agent_id = argument.agent_id
                analysis["agent_contributions"][agent_id] = analysis["agent_contributions"].get(agent_id, 0) + 1

        analysis["total_arguments"] = len(all_arguments)

        if all_arguments:
            analysis["average_confidence"] = total_confidence / len(all_arguments)

            # Find strongest and weakest arguments
            sorted_args = sorted(all_arguments, key=lambda a: a.confidence, reverse=True)
            analysis["strongest_arguments"] = [
                {
                    "id": arg.argument_id,
                    "agent": arg.agent_id,
                    "type": arg.argument_type.value,
                    "confidence": arg.confidence,
                }
                for arg in sorted_args[:3]
            ]
            analysis["weakest_arguments"] = [
                {
                    "id": arg.argument_id,
                    "agent": arg.agent_id,
                    "type": arg.argument_type.value,
                    "confidence": arg.confidence,
                }
                for arg in sorted_args[-3:]
            ]

        return analysis

    def generate_summary(self, session_id: str) -> str:
        """
        Generate a summary of the debate.
        
        Args:
            session_id: The session ID
            
        Returns:
            Summary string
        """
        if session_id not in self.sessions:
            logger.error(f"Session {session_id} not found")
            return ""

        session = self.sessions[session_id]
        analysis = self.analyze_arguments(session_id)

        summary = f"""
Debate Summary: {session.topic}
{'=' * 50}

Total Rounds: {analysis['total_rounds']}
Total Arguments: {analysis['total_arguments']}
Average Confidence: {analysis['average_confidence']:.2f}

Argument Distribution:
{chr(10).join(f"  - {k}: {v}" for k, v in analysis['argument_types'].items())}

Agent Contributions:
{chr(10).join(f"  - {k}: {v}" for k, v in analysis['agent_contributions'].items())}

Consensus: {'Reached' if session.consensus_reached else 'Not reached'}
Current Phase: {session.current_phase.value}
"""
        return summary

    def _validate_argument(self, argument: Argument) -> bool:
        """
        Validate an argument.
        
        Args:
            argument: The argument to validate
            
        Returns:
            True if valid, False otherwise
        """
        # Check content length
        if len(argument.content) > self.config.max_argument_length:
            logger.warning(f"Argument content exceeds maximum length: {argument.argument_id}")
            return False

        # Check evidence requirement
        if self.config.enable_evidence_requirement:
            if argument.argument_type == ArgumentType.EVIDENCE and not argument.supporting_evidence:
                logger.warning(f"Evidence argument missing supporting evidence: {argument.argument_id}")
                return False

        return True

    def get_session(self, session_id: str) -> Optional[DebateSession]:
        """
        Get a debate session.
        
        Args:
            session_id: The session ID
            
        Returns:
            DebateSession if found, None otherwise
        """
        return self.sessions.get(session_id)

    def get_debate_history(self) -> List[DebateSession]:
        """
        Get the debate history.
        
        Returns:
            List of concluded debate sessions
        """
        return self.debate_history
