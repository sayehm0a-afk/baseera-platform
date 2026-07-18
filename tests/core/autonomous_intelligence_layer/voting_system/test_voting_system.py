"""
Unit tests for Voting System
"""

import pytest
from datetime import datetime, timedelta
from core.autonomous_intelligence_layer.voting_system import (
    VotingSystem,
    Proposal,
    Vote,
    VotingMechanism,
    VoteType,
    VotingConfig,
)


class TestVotingSystem:
    """Test cases for VotingSystem class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.system = VotingSystem()
        self.proposal_id = "proposal_001"
        self.title = "Should we increase budget?"
        self.description = "Discussion on budget increase"
        self.options = ["Yes", "No", "Abstain"]
        self.proposer_id = "agent_1"

    def test_voting_system_initialization(self):
        """Test that VotingSystem initializes correctly."""
        assert self.system is not None
        assert self.system.config is not None
        assert isinstance(self.system.config, VotingConfig)
        assert len(self.system.proposals) == 0

    def test_voting_system_with_custom_config(self):
        """Test VotingSystem with custom config."""
        custom_config = VotingConfig(
            default_voting_mechanism=VotingMechanism.QUALIFIED_MAJORITY,
            default_required_majority=0.67,
        )
        system = VotingSystem(config=custom_config)
        assert system.config.default_voting_mechanism == VotingMechanism.QUALIFIED_MAJORITY
        assert system.config.default_required_majority == 0.67

    def test_create_proposal(self):
        """Test creating a proposal."""
        proposal = self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        assert proposal is not None
        assert proposal.proposal_id == self.proposal_id
        assert proposal.title == self.title
        assert proposal.proposer_id == self.proposer_id
        assert proposal.is_closed is False

    def test_create_proposal_with_custom_mechanism(self):
        """Test creating proposal with custom voting mechanism."""
        proposal = self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
            voting_mechanism=VotingMechanism.CONSENSUS,
            required_majority=1.0,
        )

        assert proposal.voting_mechanism == VotingMechanism.CONSENSUS
        assert proposal.required_majority == 1.0

    def test_cast_vote(self):
        """Test casting a vote."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        vote = self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
            confidence=0.9,
            reasoning="I support this proposal",
        )

        assert vote is not None
        assert vote.voter_id == "agent_2"
        assert vote.vote_type == VoteType.YES
        assert vote.confidence == 0.9

    def test_cast_multiple_votes(self):
        """Test casting multiple votes."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )

        self.system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
        )

        self.system.cast_vote(
            vote_id="vote_003",
            voter_id="agent_3",
            proposal_id=self.proposal_id,
            vote_type=VoteType.ABSTAIN,
        )

        proposal = self.system.get_proposal(self.proposal_id)
        assert len(proposal.votes) == 3

    def test_cast_vote_on_nonexistent_proposal(self):
        """Test casting vote on nonexistent proposal."""
        vote = self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id="nonexistent",
            vote_type=VoteType.YES,
        )

        assert vote is None

    def test_prevent_duplicate_voting(self):
        """Test preventing duplicate voting."""
        config = VotingConfig(enable_revoting=False)
        system = VotingSystem(config=config)

        system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        # First vote
        vote1 = system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )
        assert vote1 is not None

        # Second vote from same voter
        vote2 = system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
        )
        assert vote2 is None

    def test_allow_revoting(self):
        """Test allowing revoting."""
        config = VotingConfig(enable_revoting=True)
        system = VotingSystem(config=config)

        system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        # First vote
        vote1 = system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )
        assert vote1 is not None

        # Second vote from same voter (should be allowed)
        vote2 = system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
        )
        assert vote2 is not None

    def test_close_proposal(self):
        """Test closing a proposal."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )

        result = self.system.close_proposal(self.proposal_id)
        assert result is True

        proposal = self.system.get_proposal(self.proposal_id)
        assert proposal.is_closed is True
        assert proposal.result is not None

    def test_get_vote_count(self):
        """Test getting vote counts."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )
        self.system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )
        self.system.cast_vote(
            vote_id="vote_003",
            voter_id="agent_3",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
        )

        vote_counts = self.system.get_vote_count(self.proposal_id)
        assert vote_counts["yes"] == 2
        assert vote_counts["no"] == 1
        assert vote_counts["total"] == 3

    def test_get_vote_percentage(self):
        """Test getting vote percentages."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )
        self.system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
        )

        percentages = self.system.get_vote_percentage(self.proposal_id)
        assert percentages["yes"] == 50.0
        assert percentages["no"] == 50.0

    def test_get_weighted_votes(self):
        """Test getting weighted votes."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
            confidence=0.9,
        )
        self.system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
            confidence=0.5,
        )

        weighted_votes = self.system.get_weighted_votes(self.proposal_id)
        assert weighted_votes["yes"] == 0.9
        assert weighted_votes["no"] == 0.5

    def test_simple_majority_approval(self):
        """Test simple majority voting mechanism."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
            voting_mechanism=VotingMechanism.SIMPLE_MAJORITY,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )
        self.system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
        )
        self.system.cast_vote(
            vote_id="vote_003",
            voter_id="agent_3",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )

        self.system.close_proposal(self.proposal_id)
        proposal = self.system.get_proposal(self.proposal_id)
        assert proposal.result == "APPROVED"

    def test_analyze_voting(self):
        """Test analyzing voting results."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
            confidence=0.9,
        )
        self.system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
            confidence=0.7,
        )

        analysis = self.system.analyze_voting(self.proposal_id)
        assert analysis["proposal_id"] == self.proposal_id
        assert analysis["total_voters"] == 2
        assert analysis["average_confidence"] > 0

    def test_voting_history(self):
        """Test voting history tracking."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
        )

        self.system.close_proposal(self.proposal_id)

        history = self.system.get_voting_history()
        assert len(history) == 1
        assert history[0].proposal_id == self.proposal_id

    def test_confidence_clamping(self):
        """Test that confidence values are clamped."""
        self.system.create_proposal(
            proposal_id=self.proposal_id,
            title=self.title,
            description=self.description,
            options=self.options,
            proposer_id=self.proposer_id,
        )

        vote1 = self.system.cast_vote(
            vote_id="vote_001",
            voter_id="agent_1",
            proposal_id=self.proposal_id,
            vote_type=VoteType.YES,
            confidence=1.5,
        )

        vote2 = self.system.cast_vote(
            vote_id="vote_002",
            voter_id="agent_2",
            proposal_id=self.proposal_id,
            vote_type=VoteType.NO,
            confidence=-0.5,
        )

        assert vote1.confidence == 1.0
        assert vote2.confidence == 0.0
