"""
Reflection Engine Module

This module implements the Reflection Engine, which is responsible for evaluating
agent outputs, identifying gaps and inconsistencies, and providing recommendations
for improvement.
"""

from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, UTC
from enum import Enum
import logging


logger = logging.getLogger(__name__)


class ReflectionScoreLevel(Enum):
    """Enumeration for reflection score levels."""
    EXCELLENT = "excellent"  # Score >= 0.9
    GOOD = "good"  # Score >= 0.7 and < 0.9
    ACCEPTABLE = "acceptable"  # Score >= 0.5 and < 0.7
    POOR = "poor"  # Score < 0.5


@dataclass
class ReflectionResult:
    """Represents the result of a reflection evaluation."""
    reflection_id: str
    task_id: str
    reflection_score: float  # 0.0 to 1.0
    score_level: ReflectionScoreLevel
    contradictions: List[str] = field(default_factory=list)
    hallucinations: List[str] = field(default_factory=list)
    missing_evidence: List[str] = field(default_factory=list)
    weak_reasoning: List[str] = field(default_factory=list)
    recommendations: List[str] = field(default_factory=list)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class ReflectionPolicy:
    """Configuration for reflection evaluation."""
    contradiction_weight: float = 0.3
    hallucination_weight: float = 0.3
    missing_evidence_weight: float = 0.2
    weak_reasoning_weight: float = 0.2
    min_score_threshold: float = 0.5  # Minimum acceptable score
    max_reflection_iterations: int = 3  # Prevent infinite reflection loops
    enable_contradiction_detection: bool = True
    enable_hallucination_detection: bool = True
    enable_evidence_validation: bool = True
    enable_reasoning_validation: bool = True


class ReflectionEngine:
    """
    Reflection Engine for evaluating and improving agent outputs.
    
    The Reflection Engine is responsible for:
    - Reviewing agent outputs and plans
    - Comparing results against objectives and acceptance criteria
    - Detecting contradictions, hallucinations, missing evidence, and weak reasoning
    - Producing reflection scores
    - Generating improvement recommendations
    - Preventing infinite reflection loops
    - Recording reflection history
    """

    def __init__(self, policy: Optional[ReflectionPolicy] = None):
        """
        Initialize the Reflection Engine.
        
        Args:
            policy: ReflectionPolicy instance for configuring reflection behavior.
                   If None, uses default policy.
        """
        self.policy = policy or ReflectionPolicy()
        self.reflection_history: List[ReflectionResult] = []
        self.reflection_iteration_count: Dict[str, int] = {}

    def evaluate(
        self,
        task_id: str,
        agent_output: str,
        objective: str,
        acceptance_criteria: Optional[List[str]] = None,
        context: Optional[Dict[str, Any]] = None,
    ) -> ReflectionResult:
        """
        Evaluate an agent's output against objectives and acceptance criteria.
        
        Args:
            task_id: Unique identifier for the task being evaluated
            agent_output: The output produced by the agent
            objective: The high-level objective the agent was trying to achieve
            acceptance_criteria: List of criteria that the output should meet
            context: Additional context for the evaluation
            
        Returns:
            ReflectionResult containing the evaluation results
        """
        reflection_id = f"reflection_{task_id}_{datetime.now(UTC).timestamp()}"
        
        # Check for infinite reflection loops
        iteration_count = self.reflection_iteration_count.get(task_id, 0)
        if iteration_count >= self.policy.max_reflection_iterations:
            logger.warning(
                f"Maximum reflection iterations reached for task {task_id}. "
                f"Stopping reflection to prevent infinite loops."
            )
            return self._create_default_reflection_result(reflection_id, task_id)

        # Detect issues
        contradictions = []
        hallucinations = []
        missing_evidence = []
        weak_reasoning = []

        if self.policy.enable_contradiction_detection:
            contradictions = self._detect_contradictions(agent_output, context)

        if self.policy.enable_hallucination_detection:
            hallucinations = self._detect_hallucinations(agent_output, context)

        if self.policy.enable_evidence_validation:
            missing_evidence = self._validate_evidence(agent_output, context)

        if self.policy.enable_reasoning_validation:
            weak_reasoning = self._validate_reasoning(agent_output, objective, context)

        # Calculate reflection score
        reflection_score = self._calculate_reflection_score(
            contradictions,
            hallucinations,
            missing_evidence,
            weak_reasoning,
        )

        # Determine score level
        score_level = self._determine_score_level(reflection_score)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            contradictions,
            hallucinations,
            missing_evidence,
            weak_reasoning,
        )

        # Create reflection result
        result = ReflectionResult(
            reflection_id=reflection_id,
            task_id=task_id,
            reflection_score=reflection_score,
            score_level=score_level,
            contradictions=contradictions,
            hallucinations=hallucinations,
            missing_evidence=missing_evidence,
            weak_reasoning=weak_reasoning,
            recommendations=recommendations,
            metadata={
                "objective": objective,
                "acceptance_criteria": acceptance_criteria,
            },
        )

        # Record reflection
        self.reflection_history.append(result)
        self.reflection_iteration_count[task_id] = iteration_count + 1

        logger.info(
            f"Reflection completed for task {task_id}. "
            f"Score: {reflection_score:.2f}, Level: {score_level.value}"
        )

        return result

    def _detect_contradictions(
        self,
        agent_output: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Detect contradictions in the agent output.
        
        Args:
            agent_output: The output to analyze
            context: Additional context
            
        Returns:
            List of detected contradictions
        """
        contradictions = []
        # Placeholder implementation - in production, this would use NLP techniques
        # to detect logical contradictions in the output
        if "but" in agent_output.lower() and "however" in agent_output.lower():
            contradictions.append("Potential logical contradiction detected")
        return contradictions

    def _detect_hallucinations(
        self,
        agent_output: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Detect hallucinations in the agent output.
        
        Args:
            agent_output: The output to analyze
            context: Additional context
            
        Returns:
            List of detected hallucinations
        """
        hallucinations = []
        # Placeholder implementation - in production, this would verify claims
        # against known facts and context
        if context and "verified_facts" in context:
            verified_facts = context["verified_facts"]
            # Check if output contains claims not in verified facts
            # This is a simplified check
            pass
        return hallucinations

    def _validate_evidence(
        self,
        agent_output: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Validate evidence in the agent output.
        
        Args:
            agent_output: The output to analyze
            context: Additional context
            
        Returns:
            List of missing or weak evidence
        """
        missing_evidence = []
        # Placeholder implementation - in production, this would check if
        # claims are properly supported by evidence
        if len(agent_output) < 100:
            missing_evidence.append("Output is too short; may lack sufficient evidence")
        return missing_evidence

    def _validate_reasoning(
        self,
        agent_output: str,
        objective: str,
        context: Optional[Dict[str, Any]] = None,
    ) -> List[str]:
        """
        Validate reasoning in the agent output.
        
        Args:
            agent_output: The output to analyze
            objective: The objective the agent was trying to achieve
            context: Additional context
            
        Returns:
            List of weak reasoning issues
        """
        weak_reasoning = []
        # Placeholder implementation - in production, this would analyze
        # the logical flow and reasoning in the output
        if objective and objective.lower() not in agent_output.lower():
            weak_reasoning.append("Output does not directly address the objective")
        return weak_reasoning

    def _calculate_reflection_score(
        self,
        contradictions: List[str],
        hallucinations: List[str],
        missing_evidence: List[str],
        weak_reasoning: List[str],
    ) -> float:
        """
        Calculate the overall reflection score.
        
        Args:
            contradictions: List of detected contradictions
            hallucinations: List of detected hallucinations
            missing_evidence: List of missing evidence
            weak_reasoning: List of weak reasoning issues
            
        Returns:
            Reflection score between 0.0 and 1.0
        """
        # Calculate penalties
        contradiction_penalty = len(contradictions) * self.policy.contradiction_weight
        hallucination_penalty = len(hallucinations) * self.policy.hallucination_weight
        evidence_penalty = len(missing_evidence) * self.policy.missing_evidence_weight
        reasoning_penalty = len(weak_reasoning) * self.policy.weak_reasoning_weight

        total_penalty = (
            contradiction_penalty
            + hallucination_penalty
            + evidence_penalty
            + reasoning_penalty
        )

        # Calculate score (1.0 - total_penalty, clamped to 0.0-1.0)
        score = max(0.0, min(1.0, 1.0 - total_penalty))
        return score

    def _determine_score_level(self, score: float) -> ReflectionScoreLevel:
        """
        Determine the score level based on the score value.
        
        Args:
            score: The reflection score
            
        Returns:
            ReflectionScoreLevel
        """
        if score >= 0.9:
            return ReflectionScoreLevel.EXCELLENT
        elif score >= 0.7:
            return ReflectionScoreLevel.GOOD
        elif score >= 0.5:
            return ReflectionScoreLevel.ACCEPTABLE
        else:
            return ReflectionScoreLevel.POOR

    def _generate_recommendations(
        self,
        contradictions: List[str],
        hallucinations: List[str],
        missing_evidence: List[str],
        weak_reasoning: List[str],
    ) -> List[str]:
        """
        Generate recommendations for improvement.
        
        Args:
            contradictions: List of detected contradictions
            hallucinations: List of detected hallucinations
            missing_evidence: List of missing evidence
            weak_reasoning: List of weak reasoning issues
            
        Returns:
            List of recommendations
        """
        recommendations = []

        if contradictions:
            recommendations.append("Review and resolve logical contradictions in the output")

        if hallucinations:
            recommendations.append("Verify claims against known facts and context")

        if missing_evidence:
            recommendations.append("Provide more supporting evidence for claims")

        if weak_reasoning:
            recommendations.append("Improve logical reasoning and argumentation")

        if not recommendations:
            recommendations.append("Output appears to meet quality standards")

        return recommendations

    def _create_default_reflection_result(
        self,
        reflection_id: str,
        task_id: str,
    ) -> ReflectionResult:
        """
        Create a default reflection result when max iterations are reached.
        
        Args:
            reflection_id: Unique identifier for the reflection
            task_id: Unique identifier for the task
            
        Returns:
            ReflectionResult with default values
        """
        return ReflectionResult(
            reflection_id=reflection_id,
            task_id=task_id,
            reflection_score=0.5,
            score_level=ReflectionScoreLevel.ACCEPTABLE,
            contradictions=[],
            hallucinations=[],
            missing_evidence=[],
            weak_reasoning=[],
            recommendations=["Max reflection iterations reached. Manual review recommended."],
        )

    def get_reflection_history(self, task_id: Optional[str] = None) -> List[ReflectionResult]:
        """
        Retrieve reflection history.
        
        Args:
            task_id: Optional task ID to filter results
            
        Returns:
            List of ReflectionResult objects
        """
        if task_id:
            return [r for r in self.reflection_history if r.task_id == task_id]
        return self.reflection_history

    def reset_reflection_count(self, task_id: str) -> None:
        """
        Reset the reflection iteration count for a task.
        
        Args:
            task_id: The task ID to reset
        """
        self.reflection_iteration_count[task_id] = 0
