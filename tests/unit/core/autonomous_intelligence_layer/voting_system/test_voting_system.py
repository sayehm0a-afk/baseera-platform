import pytest
from datetime import datetime, timedelta, UTC
from src.core.autonomous_intelligence_layer.voting_system.voting_system import (
    VotingSystem,
    VotingConfig,
    VotingMechanism,
    VoteType,
    Proposal,
    Vote
)


@pytest.fixture
def voting_system():
    return VotingSystem()


def test_create_proposal(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    assert proposal is not None
    assert proposal.proposal_id == "p1"
    assert proposal.title == "Test Proposal"
    assert proposal.proposer_id == "agent1"
    assert len(voting_system.proposals) == 1


def test_create_proposal_max_limit():
    config = VotingConfig(max_proposals=1)
    system = VotingSystem(config)
    system.create_proposal("p1", "Test Proposal", "Description", ["A"], "agent1")
    proposal = system.create_proposal("p2", "Test Proposal 2", "Description", ["B"], "agent2")
    assert proposal is None
    assert len(system.proposals) == 1


def test_cast_vote(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    vote = voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES)
    assert vote is not None
    assert vote.vote_id == "v1"
    assert vote.voter_id == "voter1"
    assert vote.proposal_id == "p1"
    assert vote.vote_type == VoteType.YES
    assert len(proposal.votes) == 1


def test_cast_vote_proposal_not_found(voting_system):
    vote = voting_system.cast_vote("v1", "voter1", "p_nonexistent", VoteType.YES)
    assert vote is None


def test_cast_vote_proposal_closed(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    voting_system.close_proposal("p1")
    vote = voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES)
    assert vote is None


def test_cast_vote_no_revoting(voting_system):
    voting_system.config.enable_revoting = False
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES)
    vote = voting_system.cast_vote("v2", "voter1", "p1", VoteType.NO)
    assert vote is None


def test_close_proposal_simple_majority(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES)
    voting_system.cast_vote("v2", "voter2", "p1", VoteType.YES)
    voting_system.cast_vote("v3", "voter3", "p1", VoteType.NO)

    assert voting_system.close_proposal("p1") is True
    assert proposal.is_closed is True
    assert proposal.result == "APPROVED"
    assert len(voting_system.voting_history) == 1


def test_close_proposal_absolute_majority(voting_system):
    proposal = voting_system.create_proposal(
        "p2", "Test Proposal", "Description", ["Option A", "Option B"], "agent1",
        voting_mechanism=VotingMechanism.ABSOLUTE_MAJORITY
    )
    voting_system.cast_vote("v1", "voter1", "p2", VoteType.YES)
    voting_system.cast_vote("v2", "voter2", "p2", VoteType.YES)
    voting_system.cast_vote("v3", "voter3", "p2", VoteType.NO)
    voting_system.cast_vote("v4", "voter4", "p2", VoteType.ABSTAIN)

    assert voting_system.close_proposal("p2") is True
    assert proposal.is_closed is True
    assert proposal.result == "REJECTED" # 2/4 = 0.5, not > 0.5


def test_close_proposal_qualified_majority(voting_system):
    proposal = voting_system.create_proposal(
        "p3", "Test Proposal", "Description", ["Option A", "Option B"], "agent1",
        voting_mechanism=VotingMechanism.QUALIFIED_MAJORITY
    )
    voting_system.cast_vote("v1", "voter1", "p3", VoteType.YES)
    voting_system.cast_vote("v2", "voter2", "p3", VoteType.YES)
    voting_system.cast_vote("v3", "voter3", "p3", VoteType.YES)
    voting_system.cast_vote("v4", "voter4", "p3", VoteType.NO)

    assert voting_system.close_proposal("p3") is True
    assert proposal.is_closed is True
    assert proposal.result == "APPROVED" # 3/4 = 0.75, which is >= 2/3


def test_close_proposal_consensus(voting_system):
    proposal = voting_system.create_proposal(
        "p4", "Test Proposal", "Description", ["Option A", "Option B"], "agent1",
        voting_mechanism=VotingMechanism.CONSENSUS
    )
    voting_system.cast_vote("v1", "voter1", "p4", VoteType.YES)
    voting_system.cast_vote("v2", "voter2", "p4", VoteType.YES)
    voting_system.cast_vote("v3", "voter3", "p4", VoteType.YES)

    assert voting_system.close_proposal("p4") is True
    assert proposal.is_closed is True
    assert proposal.result == "APPROVED"


def test_close_proposal_weighted(voting_system):
    voting_system.config.enable_weighted_voting = True
    proposal = voting_system.create_proposal(
        "p5", "Test Proposal", "Description", ["Option A", "Option B"], "agent1",
        voting_mechanism=VotingMechanism.WEIGHTED
    )
    voting_system.cast_vote("v1", "voter1", "p5", VoteType.YES, confidence=0.9)
    voting_system.cast_vote("v2", "voter2", "p5", VoteType.NO, confidence=0.8)

    assert voting_system.close_proposal("p5") is True
    assert proposal.is_closed is True
    assert proposal.result == "APPROVED"


def test_get_vote_count(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES)
    voting_system.cast_vote("v2", "voter2", "p1", VoteType.YES)
    voting_system.cast_vote("v3", "voter3", "p1", VoteType.NO)
    voting_system.cast_vote("v4", "voter4", "p1", VoteType.ABSTAIN)

    counts = voting_system.get_vote_count("p1")
    assert counts["yes"] == 2
    assert counts["no"] == 1
    assert counts["abstain"] == 1
    assert counts["total"] == 4


def test_get_vote_percentage(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES)
    voting_system.cast_vote("v2", "voter2", "p1", VoteType.YES)
    voting_system.cast_vote("v3", "voter3", "p1", VoteType.NO)
    voting_system.cast_vote("v4", "voter4", "p1", VoteType.ABSTAIN)

    percentages = voting_system.get_vote_percentage("p1")
    assert percentages["yes"] == 50.0
    assert percentages["no"] == 25.0
    assert percentages["abstain"] == 25.0


def test_get_weighted_votes(voting_system):
    voting_system.config.enable_weighted_voting = True
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES, confidence=0.9)
    voting_system.cast_vote("v2", "voter2", "p1", VoteType.NO, confidence=0.8)
    voting_system.cast_vote("v3", "voter3", "p1", VoteType.YES, confidence=0.7)

    weighted_votes = voting_system.get_weighted_votes("p1")
    assert weighted_votes["yes"] == pytest.approx(1.6) # 0.9 + 0.7
    assert weighted_votes["no"] == 0.8


def test_analyze_voting(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    voting_system.cast_vote("v1", "voter1", "p1", VoteType.YES, confidence=0.9)
    voting_system.cast_vote("v2", "voter2", "p1", VoteType.YES, confidence=0.8)
    voting_system.cast_vote("v3", "voter3", "p1", VoteType.NO, confidence=0.7)

    analysis = voting_system.analyze_voting("p1")
    assert analysis["proposal_id"] == "p1"
    assert analysis["vote_counts"]["yes"] == 2
    assert analysis["vote_percentages"]["yes"] == pytest.approx(66.66, rel=1e-2)
    assert analysis["weighted_votes"]["yes"] == pytest.approx(1.7)
    assert analysis["total_voters"] == 3
    assert analysis["average_confidence"] == pytest.approx((0.9 + 0.8 + 0.7) / 3, rel=1e-2)


def test_getters(voting_system):
    proposal = voting_system.create_proposal(
        "p1", "Test Proposal", "Description", ["Option A", "Option B"], "agent1"
    )
    assert voting_system.get_proposal("p1") is not None
    assert voting_system.get_proposal("nonexistent") is None

    voting_system.close_proposal("p1")
    assert len(voting_system.get_voting_history()) == 1
