"""
Unit tests for Decision Fusion
"""

import pytest
from core.autonomous_intelligence_layer.decision_fusion import (
    DecisionFusion,
    DecisionInput,
    FusionMethod,
    DecisionSource,
    DecisionFusionConfig,
)


class TestDecisionFusion:
    """Test cases for DecisionFusion class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.fusion = DecisionFusion()
        self.decision_id = "decision_001"

    def test_decision_fusion_initialization(self):
        """Test that DecisionFusion initializes correctly."""
        assert self.fusion is not None
        assert self.fusion.config is not None
        assert isinstance(self.fusion.config, DecisionFusionConfig)
        assert len(self.fusion.decisions) == 0

    def test_decision_fusion_with_custom_config(self):
        """Test DecisionFusion with custom config."""
        custom_config = DecisionFusionConfig(
            default_fusion_method=FusionMethod.CONSENSUS,
            confidence_threshold=0.8,
        )
        fusion = DecisionFusion(config=custom_config)
        assert fusion.config.default_fusion_method == FusionMethod.CONSENSUS
        assert fusion.config.confidence_threshold == 0.8

    def test_add_input(self):
        """Test adding a decision input."""
        input_obj = self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        assert input_obj is not None
        assert input_obj.decision == "Option A"
        assert input_obj.confidence == 0.9

    def test_add_multiple_inputs(self):
        """Test adding multiple inputs."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option A",
            confidence=0.8,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_003",
            source=DecisionSource.RANKING,
            source_id="ranking_001",
            decision="Option B",
            confidence=0.6,
        )

        assert len(self.fusion.pending_inputs[self.decision_id]) == 3

    def test_fuse_decision_weighted_average(self):
        """Test fusing decision with weighted average method."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option A",
            confidence=0.8,
        )

        fused = self.fusion.fuse_decision(
            decision_id=self.decision_id,
            method=FusionMethod.WEIGHTED_AVERAGE,
        )

        assert fused is not None
        assert fused.final_decision == "Option A"
        assert fused.confidence > 0

    def test_fuse_decision_majority_voting(self):
        """Test fusing decision with majority voting method."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option A",
            confidence=0.8,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_003",
            source=DecisionSource.RANKING,
            source_id="ranking_001",
            decision="Option B",
            confidence=0.6,
        )

        fused = self.fusion.fuse_decision(
            decision_id=self.decision_id,
            method=FusionMethod.MAJORITY_VOTING,
        )

        assert fused is not None
        assert fused.final_decision == "Option A"

    def test_fuse_decision_consensus(self):
        """Test fusing decision with consensus method."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option A",
            confidence=0.8,
        )

        fused = self.fusion.fuse_decision(
            decision_id=self.decision_id,
            method=FusionMethod.CONSENSUS,
        )

        assert fused is not None
        assert fused.final_decision == "Option A"

    def test_fuse_decision_consensus_no_agreement(self):
        """Test consensus fusion when no agreement."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option B",
            confidence=0.8,
        )

        fused = self.fusion.fuse_decision(
            decision_id=self.decision_id,
            method=FusionMethod.CONSENSUS,
        )

        assert fused is not None
        assert fused.final_decision == "NO_CONSENSUS"

    def test_fuse_decision_expert_weighted(self):
        """Test fusing decision with expert-weighted method."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.REFLECTION,
            source_id="reflection_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.8,
        )

        fused = self.fusion.fuse_decision(
            decision_id=self.decision_id,
            method=FusionMethod.EXPERT_WEIGHTED,
        )

        assert fused is not None
        assert fused.final_decision == "Option A"

    def test_fuse_decision_bayesian(self):
        """Test fusing decision with Bayesian method."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option A",
            confidence=0.8,
        )

        fused = self.fusion.fuse_decision(
            decision_id=self.decision_id,
            method=FusionMethod.BAYESIAN,
        )

        assert fused is not None
        assert fused.final_decision == "Option A"

    def test_fuse_decision_no_inputs(self):
        """Test fusing with no inputs."""
        fused = self.fusion.fuse_decision(decision_id=self.decision_id)
        assert fused is None

    def test_confidence_clamping(self):
        """Test that confidence values are clamped."""
        input1 = self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=1.5,
        )

        input2 = self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option B",
            confidence=-0.5,
        )

        assert input1.confidence == 1.0
        assert input2.confidence == 0.0

    def test_analyze_decision(self):
        """Test analyzing a fused decision."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option A",
            confidence=0.8,
        )

        fused = self.fusion.fuse_decision(decision_id=self.decision_id)
        analysis = self.fusion.analyze_decision(self.decision_id)

        assert analysis["decision_id"] == self.decision_id
        assert analysis["final_decision"] == "Option A"
        assert analysis["input_count"] == 2
        assert "source_distribution" in analysis

    def test_get_decision(self):
        """Test retrieving a decision."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.fuse_decision(decision_id=self.decision_id)
        decision = self.fusion.get_decision(self.decision_id)

        assert decision is not None
        assert decision.decision_id == self.decision_id

    def test_get_nonexistent_decision(self):
        """Test retrieving nonexistent decision."""
        decision = self.fusion.get_decision("nonexistent")
        assert decision is None

    def test_decision_history(self):
        """Test decision history tracking."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.fuse_decision(decision_id=self.decision_id)

        history = self.fusion.get_decision_history()
        assert len(history) == 1
        assert history[0].decision_id == self.decision_id

    def test_multiple_decisions(self):
        """Test creating multiple decisions."""
        for i in range(3):
            decision_id = f"decision_{i:03d}"
            self.fusion.add_input(
                decision_id=decision_id,
                input_id=f"input_{i:03d}",
                source=DecisionSource.DEBATE,
                source_id=f"debate_{i:03d}",
                decision="Option A",
                confidence=0.9,
            )
            self.fusion.fuse_decision(decision_id=decision_id)

        assert len(self.fusion.decisions) == 3
        assert len(self.fusion.get_decision_history()) == 3

    def test_alternative_ranking(self):
        """Test alternative decision ranking."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option B",
            confidence=0.6,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_003",
            source=DecisionSource.RANKING,
            source_id="ranking_001",
            decision="Option C",
            confidence=0.4,
        )

        fused = self.fusion.fuse_decision(decision_id=self.decision_id)

        assert len(fused.alternatives) > 0
        # Alternatives should be sorted by score

    def test_reasoning_generation(self):
        """Test reasoning generation for fused decision."""
        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_001",
            source=DecisionSource.DEBATE,
            source_id="debate_001",
            decision="Option A",
            confidence=0.9,
        )

        self.fusion.add_input(
            decision_id=self.decision_id,
            input_id="input_002",
            source=DecisionSource.VOTING,
            source_id="voting_001",
            decision="Option B",
            confidence=0.6,
        )

        fused = self.fusion.fuse_decision(decision_id=self.decision_id)

        assert fused.reasoning is not None
        assert len(fused.reasoning) > 0
        assert "Option A" in fused.reasoning or "weighted_average" in fused.reasoning
