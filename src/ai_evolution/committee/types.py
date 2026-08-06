"""Shared types for the AI Multi-Agent Investment Committee."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from src.domain.models import AgentStance

# The eight required agent roles, in the mandate's own order -- every
# `AgentVerdict.role` is one of these, and `consensus.py`'s weight
# table is keyed by the same set.
ROLE_TECHNICAL = "technical"
ROLE_FUNDAMENTAL = "fundamental"
ROLE_NEWS = "news"
ROLE_MARKET_SENTIMENT = "market_sentiment"
ROLE_RISK = "risk"
ROLE_LIQUIDITY_VOLUME = "liquidity_volume"
ROLE_MACRO = "macro"
ROLE_PORTFOLIO_ALLOCATION = "portfolio_allocation"


@dataclass(frozen=True)
class AgentVerdict:
    """One committee agent's independent verdict on one live decision.
    `confidence` is 0-100. `evidence` and `rejection_reasons` are lists
    of plain-text strings, each built from a real, already-computed
    field (see agents.py) -- never a fabricated narrative."""

    agent_name: str
    role: str
    stance: AgentStance
    confidence: float
    reasoning: str
    evidence: List[str] = field(default_factory=list)
    rejection_reasons: List[str] = field(default_factory=list)
    used_llm: bool = False


@dataclass(frozen=True)
class RejectedAlternative:
    """One dissenting agent's opinion and why the Consensus Engine's
    weighted vote outweighed it -- never a fabricated critique, only
    the real arithmetic (weight vs. the winning side's total weight)."""

    agent_name: str
    role: str
    stance: AgentStance
    confidence: float
    reasoning: str
    rejection_reason: str


@dataclass(frozen=True)
class ConsensusResult:
    """The Consensus Engine's full output for one committee run."""

    final_decision: str  # "BUY" | "SELL" | "HOLD"
    final_confidence: float

    participant_count: int
    directional_count: int
    agreement_pct: float
    disagreement_pct: float
    disagreement_score: float

    most_optimistic_agent: Optional[str]
    most_optimistic_stance: Optional[str]
    most_conservative_agent: Optional[str]
    most_conservative_stance: Optional[str]

    consensus_reasoning_ar: str
    rejected_alternatives: List[RejectedAlternative]
    weighted_votes: Dict[str, float]

    opinions: List[AgentVerdict] = field(default_factory=list)


def verdict_to_dict(verdict: AgentVerdict) -> Dict[str, Any]:
    """The one place an `AgentVerdict` is flattened for a JSON column
    or an API response -- reused by the orchestrator's persistence and
    by the API schema mapper so both can never silently drift apart."""
    return {
        "agent_name": verdict.agent_name,
        "role": verdict.role,
        "stance": verdict.stance.value,
        "confidence": verdict.confidence,
        "reasoning": verdict.reasoning,
        "evidence": list(verdict.evidence),
        "rejection_reasons": list(verdict.rejection_reasons),
        "used_llm": verdict.used_llm,
    }
