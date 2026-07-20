"""
Decision Fusion Module

This module implements Decision Fusion, which combines decisions from multiple
sources (debates, votes, rankings) into a final unified decision.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class FusionMethod(Enum):
    """Enumeration for decision fusion methods."""

    WEIGHTED_AVERAGE = "weighted_average"  # Weighted average of inputs
    MAJORITY_VOTING = "majority_voting"  # Majority rule
    CONSENSUS = "consensus"  # Consensus-based
    EXPERT_WEIGHTED = "expert_weighted"  # Expert-weighted combination
    BAYESIAN = "bayesian"  # Bayesian combination


class DecisionSource(Enum):
    """Enumeration for decision sources."""

    DEBATE = "debate"
    VOTING = "voting"
    RANKING = "ranking"
    REFLECTION = "reflection"
    EXTERNAL = "external"


@dataclass
class DecisionInput:
    """Represents a single decision input from a source."""

    input_id: str
    source: DecisionSource
    source_id: str  # ID of the source (debate_id, voting_id, etc.)
    decision: str  # The decision/recommendation
    confidence: float = 1.0  # 0.0 to 1.0
    supporting_data: Dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class FusedDecision:
    """Represents a fused decision."""

    decision_id: str
    final_decision: str
    confidence: float
    supporting_inputs: List[DecisionInput]
    fusion_method: FusionMethod
    reasoning: str
    alternatives: List[Tuple[str, float]] = field(
        default_factory=list
    )  # (decision, score)
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class DecisionFusionConfig:
    """Configuration for Decision Fusion."""

    default_fusion_method: FusionMethod = FusionMethod.WEIGHTED_AVERAGE
    confidence_threshold: float = 0.5  # Minimum confidence for decision
    enable_alternative_ranking: bool = True
    enable_reasoning_generation: bool = True
    max_decisions: int = 1000


class DecisionFusion:
    """
    Decision Fusion for combining multiple decision sources.

    The Decision Fusion is responsible for:
    - Collecting decision inputs from multiple sources
    - Fusing decisions using various methods
    - Generating final decisions with confidence scores
    - Providing reasoning for decisions
    - Ranking alternative decisions
    - Tracking decision history
    """

    def __init__(self, config: Optional[DecisionFusionConfig] = None):
        """
        Initialize the Decision Fusion.

        Args:
            config: DecisionFusionConfig instance for configuring fusion behavior.
                   If None, uses default config.
        """
        self.config = config or DecisionFusionConfig()
        self.decisions: Dict[str, FusedDecision] = {}
        self.decision_history: List[FusedDecision] = []
        self.pending_inputs: Dict[str, List[DecisionInput]] = {}

    def add_input(
        self,
        decision_id: str,
        input_id: str,
        source: DecisionSource,
        source_id: str,
        decision: str,
        confidence: float = 1.0,
        supporting_data: Optional[Dict[str, Any]] = None,
    ) -> Optional[DecisionInput]:
        """
        Add a decision input from a source.

        Args:
            decision_id: The decision ID to add input to
            input_id: Unique identifier for the input
            source: Source of the decision
            source_id: ID of the source
            decision: The decision/recommendation
            confidence: Confidence level (0.0 to 1.0)
            supporting_data: Optional supporting data

        Returns:
            DecisionInput if added successfully, None otherwise
        """
        decision_input = DecisionInput(
            input_id=input_id,
            source=source,
            source_id=source_id,
            decision=decision,
            confidence=max(0.0, min(1.0, confidence)),
            supporting_data=supporting_data or {},
        )

        if decision_id not in self.pending_inputs:
            self.pending_inputs[decision_id] = []

        self.pending_inputs[decision_id].append(decision_input)

        logger.debug(f"Decision input added: {input_id} to {decision_id}")
        return decision_input

    def fuse_decision(
        self,
        decision_id: str,
        method: Optional[FusionMethod] = None,
    ) -> Optional[FusedDecision]:
        """
        Fuse pending decision inputs into a final decision.

        Args:
            decision_id: The decision ID
            method: Optional fusion method (uses default if not provided)

        Returns:
            FusedDecision if fusion successful, None otherwise
        """
        if (
            decision_id not in self.pending_inputs
            or not self.pending_inputs[decision_id]
        ):
            logger.error(f"No inputs for decision {decision_id}", exc_info=True)
            return None

        inputs = self.pending_inputs[decision_id]
        method = method or self.config.default_fusion_method

        # Fuse decisions
        final_decision, confidence = self._fuse_inputs(inputs, method)

        # Check confidence threshold
        if confidence < self.config.confidence_threshold:
            logger.warning(f"Decision confidence below threshold: {confidence}")

        # Generate reasoning
        reasoning = self._generate_reasoning(inputs, final_decision, method)

        # Rank alternatives
        alternatives = []
        if self.config.enable_alternative_ranking:
            alternatives = self._rank_alternatives(inputs)

        # Create fused decision
        fused = FusedDecision(
            decision_id=decision_id,
            final_decision=final_decision,
            confidence=confidence,
            supporting_inputs=inputs,
            fusion_method=method,
            reasoning=reasoning,
            alternatives=alternatives,
        )

        self.decisions[decision_id] = fused
        self.decision_history.append(fused)

        # Clear pending inputs
        del self.pending_inputs[decision_id]

        logger.debug(f"Decision fused: {decision_id}")
        return fused

    def _fuse_inputs(
        self,
        inputs: List[DecisionInput],
        method: FusionMethod,
    ) -> Tuple[str, float]:
        """
        Fuse inputs using the specified method.

        Args:
            inputs: List of decision inputs
            method: Fusion method to use

        Returns:
            Tuple of (final_decision, confidence)
        """
        if not inputs:
            return "NO_DECISION", 0.0

        if method == FusionMethod.WEIGHTED_AVERAGE:
            return self._weighted_average_fusion(inputs)
        elif method == FusionMethod.MAJORITY_VOTING:
            return self._majority_voting_fusion(inputs)
        elif method == FusionMethod.CONSENSUS:
            return self._consensus_fusion(inputs)
        elif method == FusionMethod.EXPERT_WEIGHTED:
            return self._expert_weighted_fusion(inputs)
        elif method == FusionMethod.BAYESIAN:
            return self._bayesian_fusion(inputs)

        return "NO_DECISION", 0.0

    def _weighted_average_fusion(
        self,
        inputs: List[DecisionInput],
    ) -> Tuple[str, float]:
        """Fuse using weighted average."""
        # Group by decision
        decision_scores = {}
        total_confidence = 0.0

        for input_obj in inputs:
            if input_obj.decision not in decision_scores:
                decision_scores[input_obj.decision] = 0.0
            decision_scores[input_obj.decision] += input_obj.confidence
            total_confidence += input_obj.confidence

        if total_confidence == 0:
            return "NO_DECISION", 0.0

        # Find decision with highest score
        final_decision = max(decision_scores, key=decision_scores.get)
        confidence = decision_scores[final_decision] / total_confidence

        return final_decision, confidence

    def _majority_voting_fusion(
        self,
        inputs: List[DecisionInput],
    ) -> Tuple[str, float]:
        """Fuse using majority voting."""
        # Count votes
        decision_counts = {}
        for input_obj in inputs:
            decision_counts[input_obj.decision] = (
                decision_counts.get(input_obj.decision, 0) + 1
            )

        if not decision_counts:
            return "NO_DECISION", 0.0

        # Find decision with most votes
        final_decision = max(decision_counts, key=decision_counts.get)
        confidence = decision_counts[final_decision] / len(inputs)

        return final_decision, confidence

    def _consensus_fusion(
        self,
        inputs: List[DecisionInput],
    ) -> Tuple[str, float]:
        """Fuse using consensus (all must agree)."""
        if not inputs:
            return "NO_DECISION", 0.0

        first_decision = inputs[0].decision
        all_agree = all(input_obj.decision == first_decision for input_obj in inputs)

        if all_agree:
            avg_confidence = sum(input_obj.confidence for input_obj in inputs) / len(
                inputs
            )
            return first_decision, avg_confidence
        else:
            return "NO_CONSENSUS", 0.0

    def _expert_weighted_fusion(
        self,
        inputs: List[DecisionInput],
    ) -> Tuple[str, float]:
        """Fuse using expert-weighted combination."""
        # Assign expert weights based on source type
        expert_weights = {
            DecisionSource.REFLECTION: 0.4,
            DecisionSource.DEBATE: 0.3,
            DecisionSource.VOTING: 0.2,
            DecisionSource.RANKING: 0.1,
            DecisionSource.EXTERNAL: 0.05,
        }

        decision_scores = {}
        total_weight = 0.0

        for input_obj in inputs:
            weight = expert_weights.get(input_obj.source, 0.1)
            weighted_score = input_obj.confidence * weight

            if input_obj.decision not in decision_scores:
                decision_scores[input_obj.decision] = 0.0
            decision_scores[input_obj.decision] += weighted_score
            total_weight += weight

        if total_weight == 0:
            return "NO_DECISION", 0.0

        final_decision = max(decision_scores, key=decision_scores.get)
        confidence = decision_scores[final_decision] / total_weight

        return final_decision, min(1.0, confidence)

    def _bayesian_fusion(
        self,
        inputs: List[DecisionInput],
    ) -> Tuple[str, float]:
        """Fuse using Bayesian combination."""
        # Simple Bayesian approach: combine confidence scores
        decision_posteriors = {}

        for input_obj in inputs:
            if input_obj.decision not in decision_posteriors:
                decision_posteriors[input_obj.decision] = 1.0

            # Update posterior with likelihood
            decision_posteriors[input_obj.decision] *= input_obj.confidence

        if not decision_posteriors:
            return "NO_DECISION", 0.0

        # Normalize posteriors
        total = sum(decision_posteriors.values())
        for decision in decision_posteriors:
            decision_posteriors[decision] /= total

        final_decision = max(decision_posteriors, key=decision_posteriors.get)
        confidence = decision_posteriors[final_decision]

        return final_decision, confidence

    def _generate_reasoning(
        self,
        inputs: List[DecisionInput],
        final_decision: str,
        method: FusionMethod,
    ) -> str:
        """
        Generate reasoning for the fused decision.

        Args:
            inputs: List of decision inputs
            final_decision: The final decision
            method: Fusion method used

        Returns:
            Reasoning string
        """
        reasoning = f"Decision fused using {method.value} method.\n"
        reasoning += f"Final decision: {final_decision}\n"
        reasoning += f"Supporting inputs: {len(inputs)}\n"

        # List supporting inputs
        supporting = [inp for inp in inputs if inp.decision == final_decision]
        reasoning += f"Inputs supporting final decision: {len(supporting)}\n"

        # List conflicting inputs
        conflicting = [inp for inp in inputs if inp.decision != final_decision]
        if conflicting:
            reasoning += f"Conflicting inputs: {len(conflicting)}\n"

        return reasoning

    def _rank_alternatives(
        self,
        inputs: List[DecisionInput],
    ) -> List[Tuple[str, float]]:
        """
        Rank alternative decisions.

        Args:
            inputs: List of decision inputs

        Returns:
            List of (decision, score) tuples sorted by score
        """
        decision_scores = {}

        for input_obj in inputs:
            if input_obj.decision not in decision_scores:
                decision_scores[input_obj.decision] = 0.0
            decision_scores[input_obj.decision] += input_obj.confidence

        # Sort by score
        sorted_alternatives = sorted(
            decision_scores.items(),
            key=lambda x: x[1],
            reverse=True,
        )

        return sorted_alternatives

    def analyze_decision(self, decision_id: str) -> Dict[str, Any]:
        """
        Analyze a fused decision.

        Args:
            decision_id: The decision ID

        Returns:
            Dictionary containing analysis results
        """
        if decision_id not in self.decisions:
            logger.error(f"Decision {decision_id} not found", exc_info=True)
            return {}

        fused = self.decisions[decision_id]
        analysis = {
            "decision_id": decision_id,
            "final_decision": fused.final_decision,
            "confidence": fused.confidence,
            "fusion_method": fused.fusion_method.value,
            "input_count": len(fused.supporting_inputs),
            "source_distribution": {},
            "average_input_confidence": 0.0,
        }

        # Count sources
        for input_obj in fused.supporting_inputs:
            source = input_obj.source.value
            analysis["source_distribution"][source] = (
                analysis["source_distribution"].get(source, 0) + 1
            )

        # Calculate average confidence
        if fused.supporting_inputs:
            avg_conf = sum(inp.confidence for inp in fused.supporting_inputs) / len(
                fused.supporting_inputs
            )
            analysis["average_input_confidence"] = avg_conf

        return analysis

    def get_decision(self, decision_id: str) -> Optional[FusedDecision]:
        """
        Get a fused decision.

        Args:
            decision_id: The decision ID

        Returns:
            FusedDecision if found, None otherwise
        """
        return self.decisions.get(decision_id)

    def get_decision_history(self) -> List[FusedDecision]:
        """
        Get decision history.

        Returns:
            List of fused decisions
        """
        return self.decision_history
