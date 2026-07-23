import pytest
from src.core.autonomous_intelligence_layer.decision_fusion.decision_fusion import (
    DecisionFusion,
    DecisionSource,
    FusionMethod
)


@pytest.fixture
def decision_fusion_system():
    return DecisionFusion()


def test_add_input(decision_fusion_system):
    input_obj = decision_fusion_system.add_input(
        "d1", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8
    )
    assert input_obj is not None
    assert input_obj.input_id == "i1"
    assert input_obj.decision == "Option A"
    assert len(decision_fusion_system.pending_inputs["d1"]) == 1


def test_fuse_decision_weighted_average(decision_fusion_system):
    decision_fusion_system.add_input("d1", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.add_input("d1", "i2", DecisionSource.VOTING, "vote1", "Option A", 0.9)
    decision_fusion_system.add_input("d1", "i3", DecisionSource.RANKING, "rank1", "Option B", 0.7)

    fused_decision = decision_fusion_system.fuse_decision("d1", FusionMethod.WEIGHTED_AVERAGE)
    assert fused_decision is not None
    assert fused_decision.final_decision == "Option A"
    assert fused_decision.confidence == pytest.approx((0.8 + 0.9) / (0.8 + 0.9 + 0.7))
    assert len(decision_fusion_system.decisions) == 1
    assert "d1" not in decision_fusion_system.pending_inputs


def test_fuse_decision_majority_voting(decision_fusion_system):
    decision_fusion_system.add_input("d2", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.add_input("d2", "i2", DecisionSource.VOTING, "vote1", "Option A", 0.9)
    decision_fusion_system.add_input("d2", "i3", DecisionSource.RANKING, "rank1", "Option B", 0.7)

    fused_decision = decision_fusion_system.fuse_decision("d2", FusionMethod.MAJORITY_VOTING)
    assert fused_decision is not None
    assert fused_decision.final_decision == "Option A"
    assert fused_decision.confidence == pytest.approx(2 / 3)


def test_fuse_decision_consensus(decision_fusion_system):
    decision_fusion_system.add_input("d3", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.add_input("d3", "i2", DecisionSource.VOTING, "vote1", "Option A", 0.9)

    fused_decision = decision_fusion_system.fuse_decision("d3", FusionMethod.CONSENSUS)
    assert fused_decision is not None
    assert fused_decision.final_decision == "Option A"
    assert fused_decision.confidence == pytest.approx((0.8 + 0.9) / 2)


def test_fuse_decision_no_consensus(decision_fusion_system):
    decision_fusion_system.add_input("d4", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.add_input("d4", "i2", DecisionSource.VOTING, "vote1", "Option B", 0.9)

    fused_decision = decision_fusion_system.fuse_decision("d4", FusionMethod.CONSENSUS)
    assert fused_decision is not None
    assert fused_decision.final_decision == "NO_CONSENSUS"
    assert fused_decision.confidence == 0.0


def test_fuse_decision_expert_weighted(decision_fusion_system):
    decision_fusion_system.add_input("d5", "i1", DecisionSource.REFLECTION, "ref1", "Option A", 0.9)
    decision_fusion_system.add_input("d5", "i2", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.add_input("d5", "i3", DecisionSource.VOTING, "vote1", "Option B", 0.7)

    fused_decision = decision_fusion_system.fuse_decision("d5", FusionMethod.EXPERT_WEIGHTED)
    assert fused_decision is not None
    assert fused_decision.final_decision == "Option A"
    # Weights: Reflection 0.4, Debate 0.3, Voting 0.2
    # Option A: (0.9 * 0.4) + (0.8 * 0.3) = 0.36 + 0.24 = 0.6
    # Option B: (0.7 * 0.2) = 0.14
    # Total weight: 0.4 + 0.3 + 0.2 = 0.9
    assert fused_decision.confidence == pytest.approx(0.6 / 0.9)


def test_fuse_decision_bayesian(decision_fusion_system):
    decision_fusion_system.add_input("d6", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.add_input("d6", "i2", DecisionSource.VOTING, "vote1", "Option A", 0.9)
    decision_fusion_system.add_input("d6", "i3", DecisionSource.RANKING, "rank1", "Option B", 0.7)

    fused_decision = decision_fusion_system.fuse_decision("d6", FusionMethod.BAYESIAN)
    assert fused_decision is not None
    assert fused_decision.final_decision == "Option A"
    # Option A: 0.8 * 0.9 = 0.72
    # Option B: 0.7
    # Total: 0.72 + 0.7 = 1.42
    # Confidence A: 0.72 / 1.42 = 0.507
    assert fused_decision.confidence == pytest.approx(0.72 / (0.72 + 0.7))


def test_analyze_decision(decision_fusion_system):
    decision_fusion_system.add_input("d1", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.add_input("d1", "i2", DecisionSource.VOTING, "vote1", "Option A", 0.9)
    decision_fusion_system.add_input("d1", "i3", DecisionSource.RANKING, "rank1", "Option B", 0.7)
    decision_fusion_system.fuse_decision("d1", FusionMethod.WEIGHTED_AVERAGE)

    analysis = decision_fusion_system.analyze_decision("d1")
    assert analysis["decision_id"] == "d1"
    assert analysis["final_decision"] == "Option A"
    assert analysis["confidence"] == pytest.approx((0.8 + 0.9) / (0.8 + 0.9 + 0.7))
    assert analysis["fusion_method"] == "weighted_average"
    assert analysis["input_count"] == 3
    assert analysis["source_distribution"] == {"debate": 1, "voting": 1, "ranking": 1}
    assert analysis["average_input_confidence"] == pytest.approx((0.8 + 0.9 + 0.7) / 3)


def test_getters(decision_fusion_system):
    decision_fusion_system.add_input("d1", "i1", DecisionSource.DEBATE, "debate1", "Option A", 0.8)
    decision_fusion_system.fuse_decision("d1", FusionMethod.WEIGHTED_AVERAGE)

    assert decision_fusion_system.get_decision("d1") is not None
    assert decision_fusion_system.get_decision("nonexistent") is None
    assert len(decision_fusion_system.get_decision_history()) == 1
