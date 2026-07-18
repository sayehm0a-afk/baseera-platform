"""
Voting System Module

This module implements the Voting System, which allows agents to vote on decisions,
options, or proposals with various voting mechanisms and aggregation strategies.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class VotingMechanism(Enum):
    """Enumeration for voting mechanisms."""
    SIMPLE_MAJORITY = "simple_majority"  # More than 50%
    ABSOLUTE_MAJORITY = "absolute_majority"  # More than 50% of all voters
    QUALIFIED_MAJORITY = "qualified_majority"  # 2/3 or 3/4 majority
    CONSENSUS = "consensus"  # All or near-all agree
    WEIGHTED = "weighted"  # Votes weighted by agent confidence


class VoteType(Enum):
    """Enumeration for vote types."""
    YES = "yes"
    NO = "no"
    ABSTAIN = "abstain"
    CONDITIONAL = "conditional"


@dataclass
class Vote:
    """Represents a single vote."""
    vote_id: str
    voter_id: str
    proposal_id: str
    vote_type: VoteType
    confidence: float = 1.0  # 0.0 to 1.0
    reasoning: Optional[str] = None
    timestamp: datetime = field(default_factory=datetime.utcnow)
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class Proposal:
    """Represents a proposal to be voted on."""
    proposal_id: str
    title: str
    description: str
    options: List[str]  # Available voting options
    proposer_id: str
    created_at: datetime = field(default_factory=datetime.utcnow)
    deadline: Optional[datetime] = None
    voting_mechanism: VotingMechanism = VotingMechanism.SIMPLE_MAJORITY
    required_majority: float = 0.5  # Percentage required for approval
    votes: List[Vote] = field(default_factory=list)
    is_closed: bool = False
    result: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class VotingConfig:
    """Configuration for Voting System."""
    default_voting_mechanism: VotingMechanism = VotingMechanism.SIMPLE_MAJORITY
    default_required_majority: float = 0.5
    enable_weighted_voting: bool = True
    enable_revoting: bool = False  # Allow voters to change their vote
    enable_abstention: bool = True
    max_proposals: int = 1000
    vote_timeout_seconds: int = 3600  # 1 hour


class VotingSystem:
    """
    Voting System for agent decision-making.

    The Voting System is responsible for:
    - Creating proposals
    - Recording votes
    - Aggregating votes
    - Determining outcomes
    - Tracking voting history
    - Analyzing voting patterns
    """

    def __init__(self, config: Optional[VotingConfig] = None):
        """
        Initialize the Voting System.

        Args:
            config: VotingConfig instance for configuring voting behavior.
                   If None, uses default config.
        """
        self.config = config or VotingConfig()
        self.proposals: Dict[str, Proposal] = {}
        self.voting_history: List[Proposal] = []

    def create_proposal(
        self,
        proposal_id: str,
        title: str,
        description: str,
        options: List[str],
        proposer_id: str,
        voting_mechanism: Optional[VotingMechanism] = None,
        required_majority: Optional[float] = None,
        deadline: Optional[datetime] = None,
    ) -> Optional[Proposal]:
        """
        Create a new proposal.

        Args:
            proposal_id: Unique identifier for the proposal
            title: Title of the proposal
            description: Description of the proposal
            options: List of voting options
            proposer_id: ID of the proposer
            voting_mechanism: Optional voting mechanism (uses default if not provided)
            required_majority: Optional required majority (uses default if not provided)
            deadline: Optional voting deadline

        Returns:
            Proposal if created successfully, None otherwise
        """
        # Check proposal limit
        if len(self.proposals) >= self.config.max_proposals:
            logger.error("Maximum proposals limit reached")
            return None

        proposal = Proposal(
            proposal_id=proposal_id,
            title=title,
            description=description,
            options=options,
            proposer_id=proposer_id,
            voting_mechanism=voting_mechanism or self.config.default_voting_mechanism,
            required_majority=required_majority or self.config.default_required_majority,
            deadline=deadline,
        )

        self.proposals[proposal_id] = proposal
        logger.debug(f"Proposal created: {proposal_id}")
        return proposal

    def cast_vote(
        self,
        vote_id: str,
        voter_id: str,
        proposal_id: str,
        vote_type: VoteType,
        confidence: float = 1.0,
        reasoning: Optional[str] = None,
    ) -> Optional[Vote]:
        """
        Cast a vote on a proposal.

        Args:
            vote_id: Unique identifier for the vote
            voter_id: ID of the voter
            proposal_id: ID of the proposal
            vote_type: Type of vote
            confidence: Confidence level (0.0 to 1.0)
            reasoning: Optional reasoning for the vote

        Returns:
            Vote if cast successfully, None otherwise
        """
        if proposal_id not in self.proposals:
            logger.error(f"Proposal {proposal_id} not found")
            return None

        proposal = self.proposals[proposal_id]

        # Check if proposal is closed
        if proposal.is_closed:
            logger.warning(f"Proposal {proposal_id} is closed")
            return None

        # Check if voter has already voted
        if not self.config.enable_revoting:
            for existing_vote in proposal.votes:
                if existing_vote.voter_id == voter_id:
                    logger.warning(f"Voter {voter_id} has already voted")
                    return None

        # Create vote
        vote = Vote(
            vote_id=vote_id,
            voter_id=voter_id,
            proposal_id=proposal_id,
            vote_type=vote_type,
            confidence=max(0.0, min(1.0, confidence)),
            reasoning=reasoning,
        )

        # Add vote to proposal
        proposal.votes.append(vote)

        logger.debug(f"Vote cast: {vote_id}")
        return vote

    def close_proposal(self, proposal_id: str) -> bool:
        """
        Close a proposal and determine the result.

        Args:
            proposal_id: The proposal ID

        Returns:
            True if proposal closed successfully, False otherwise
        """
        if proposal_id not in self.proposals:
            logger.error(f"Proposal {proposal_id} not found")
            return False

        proposal = self.proposals[proposal_id]
        proposal.is_closed = True

        # Determine result
        result = self._determine_result(proposal)
        proposal.result = result

        # Move to history
        self.voting_history.append(proposal)

        logger.debug(f"Proposal closed: {proposal_id}, Result: {result}")
        return True

    def get_vote_count(self, proposal_id: str) -> Dict[str, int]:
        """
        Get vote counts for a proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            Dictionary with vote type counts
        """
        if proposal_id not in self.proposals:
            logger.error(f"Proposal {proposal_id} not found")
            return {}

        proposal = self.proposals[proposal_id]
        vote_counts = {
            "yes": 0,
            "no": 0,
            "abstain": 0,
            "conditional": 0,
            "total": len(proposal.votes),
        }

        for vote in proposal.votes:
            vote_counts[vote.vote_type.value] += 1

        return vote_counts

    def get_vote_percentage(self, proposal_id: str) -> Dict[str, float]:
        """
        Get vote percentages for a proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            Dictionary with vote type percentages
        """
        vote_counts = self.get_vote_count(proposal_id)
        total = vote_counts.get("total", 0)

        if total == 0:
            return {
                "yes": 0.0,
                "no": 0.0,
                "abstain": 0.0,
                "conditional": 0.0,
            }

        return {
            "yes": (vote_counts["yes"] / total) * 100,
            "no": (vote_counts["no"] / total) * 100,
            "abstain": (vote_counts["abstain"] / total) * 100,
            "conditional": (vote_counts["conditional"] / total) * 100,
        }

    def get_weighted_votes(self, proposal_id: str) -> Dict[str, float]:
        """
        Get weighted vote counts (by confidence).

        Args:
            proposal_id: The proposal ID

        Returns:
            Dictionary with weighted vote counts
        """
        if proposal_id not in self.proposals:
            logger.error(f"Proposal {proposal_id} not found")
            return {}

        proposal = self.proposals[proposal_id]
        weighted_votes = {
            "yes": 0.0,
            "no": 0.0,
            "abstain": 0.0,
            "conditional": 0.0,
        }

        for vote in proposal.votes:
            weighted_votes[vote.vote_type.value] += vote.confidence

        return weighted_votes

    def analyze_voting(self, proposal_id: str) -> Dict[str, Any]:
        """
        Analyze voting results for a proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            Dictionary containing voting analysis
        """
        if proposal_id not in self.proposals:
            logger.error(f"Proposal {proposal_id} not found")
            return {}

        proposal = self.proposals[proposal_id]
        vote_counts = self.get_vote_count(proposal_id)
        vote_percentages = self.get_vote_percentage(proposal_id)
        weighted_votes = self.get_weighted_votes(proposal_id)

        analysis = {
            "proposal_id": proposal_id,
            "title": proposal.title,
            "voting_mechanism": proposal.voting_mechanism.value,
            "vote_counts": vote_counts,
            "vote_percentages": vote_percentages,
            "weighted_votes": weighted_votes,
            "is_closed": proposal.is_closed,
            "result": proposal.result,
            "total_voters": len(set(v.voter_id for v in proposal.votes)),
            "average_confidence": 0.0,
        }

        if proposal.votes:
            avg_confidence = sum(v.confidence for v in proposal.votes) / len(proposal.votes)
            analysis["average_confidence"] = avg_confidence

        return analysis

    def _determine_result(self, proposal: Proposal) -> str:
        """
        Determine the result of a proposal based on votes.

        Args:
            proposal: The proposal to evaluate

        Returns:
            Result string (e.g., "APPROVED", "REJECTED", "INCONCLUSIVE")
        """
        vote_counts = self.get_vote_count(proposal.proposal_id)
        total_votes = vote_counts["total"]

        if total_votes == 0:
            return "NO_VOTES"

        yes_votes = vote_counts["yes"]
        no_votes = vote_counts["no"]
        abstain_votes = vote_counts["abstain"]

        # Calculate voting percentage
        voting_percentage = (yes_votes + no_votes) / total_votes if total_votes > 0 else 0

        # Apply voting mechanism
        if proposal.voting_mechanism == VotingMechanism.SIMPLE_MAJORITY:
            if yes_votes > no_votes:
                return "APPROVED"
            elif no_votes > yes_votes:
                return "REJECTED"
            else:
                return "TIE"

        elif proposal.voting_mechanism == VotingMechanism.ABSOLUTE_MAJORITY:
            if yes_votes > (total_votes * 0.5):
                return "APPROVED"
            else:
                return "REJECTED"

        elif proposal.voting_mechanism == VotingMechanism.QUALIFIED_MAJORITY:
            if yes_votes >= (total_votes * 2 / 3):
                return "APPROVED"
            else:
                return "REJECTED"

        elif proposal.voting_mechanism == VotingMechanism.CONSENSUS:
            if yes_votes == total_votes:
                return "APPROVED"
            else:
                return "REJECTED"

        elif proposal.voting_mechanism == VotingMechanism.WEIGHTED:
            weighted_votes = self.get_weighted_votes(proposal.proposal_id)
            if weighted_votes["yes"] > weighted_votes["no"]:
                return "APPROVED"
            else:
                return "REJECTED"

        return "INCONCLUSIVE"

    def get_proposal(self, proposal_id: str) -> Optional[Proposal]:
        """
        Get a proposal.

        Args:
            proposal_id: The proposal ID

        Returns:
            Proposal if found, None otherwise
        """
        return self.proposals.get(proposal_id)

    def get_voting_history(self) -> List[Proposal]:
        """
        Get voting history.

        Returns:
            List of closed proposals
        """
        return self.voting_history
