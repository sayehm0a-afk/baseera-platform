"""Schemas for the staff-gated AI Multi-Agent Investment Committee
dashboard -- GET /api/v1/admin/investment-committee/*. Every field is
a direct read of `CommitteeConsensus`/`CommitteeAgentOpinion` rows
(see src.ai_evolution.committee), never a re-derived estimate.
"""

from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel


class CommitteeSessionSummaryOut(BaseModel):
    """One row of the committee timeline -- one consensus session."""

    session_id: int
    decision_v2_snapshot_id: int
    symbol: str
    company_name_ar: Optional[str] = None
    decision: str
    decision_label_ar: str
    final_decision: str
    final_confidence: float
    agreement_pct: float
    disagreement_pct: float
    disagreement_score: float
    most_optimistic_agent: Optional[str] = None
    most_conservative_agent: Optional[str] = None
    created_at: datetime


class CommitteeSessionListOut(BaseModel):
    generated_at: datetime
    total_sessions: int
    sessions: List[CommitteeSessionSummaryOut]


class CommitteeAgentOpinionDetailOut(BaseModel):
    agent_name: str
    role: str
    stance: str
    confidence: float
    reasoning: str
    evidence: List[str] = []
    rejection_reasons: List[str] = []
    used_llm: bool = False


class RejectedAlternativeDetailOut(BaseModel):
    agent_name: str
    role: str
    stance: str
    confidence: float
    reasoning: str
    rejection_reason: str


class CommitteeSessionDetailOut(BaseModel):
    """Full detail for one committee session -- the professional
    dashboard's agent cards, votes, evidence, and consensus reasoning
    all come from this one response."""

    session_id: int
    decision_v2_snapshot_id: int
    symbol: str
    company_name_ar: Optional[str] = None
    decision: str
    decision_label_ar: str
    decision_timestamp: datetime

    final_decision: str
    final_confidence: float
    participant_count: int
    directional_count: int
    agreement_pct: float
    disagreement_pct: float
    disagreement_score: float
    most_optimistic_agent: Optional[str] = None
    most_optimistic_stance: Optional[str] = None
    most_conservative_agent: Optional[str] = None
    most_conservative_stance: Optional[str] = None
    consensus_reasoning_ar: str
    weighted_votes: Dict[str, float] = {}
    rejected_alternatives: List[RejectedAlternativeDetailOut] = []
    opinions: List[CommitteeAgentOpinionDetailOut] = []
    created_at: datetime


class CommitteeStatsOut(BaseModel):
    """Aggregate committee statistics over a time window -- how often
    the committee agrees with itself, how often each agent is the most
    optimistic/conservative, and the overall final-decision mix."""

    generated_at: datetime
    window_hours: int
    total_sessions: int
    average_agreement_pct: Optional[float] = None
    average_disagreement_score: Optional[float] = None
    final_decision_distribution: Dict[str, int] = {}
    most_optimistic_agent_counts: Dict[str, int] = {}
    most_conservative_agent_counts: Dict[str, int] = {}
