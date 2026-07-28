"""Shared types for the E7 agent panel."""

from dataclasses import dataclass

from src.domain.models import AgentStance


@dataclass(frozen=True)
class AgentOpinionResult:
    """One agent's opinion on one recommendation -- the panel-internal
    shape every agent produces, before it's persisted as an
    `AgentOpinion` row."""

    agent_name: str
    stance: AgentStance
    confidence: float  # 0-100
    reasoning: str
    used_llm: bool = False
