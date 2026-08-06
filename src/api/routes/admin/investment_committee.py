"""GET /api/v1/admin/investment-committee/* -- staff-only professional
dashboard over the AI Multi-Agent Investment Committee's real,
persisted output (`CommitteeConsensus`/`CommitteeAgentOpinion`, see
src.ai_evolution.committee). Every field here is a direct read of
those rows -- no re-computation, no fabricated statistic.
"""

import logging
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from src.api.schemas.investment_committee import (
    CommitteeAgentOpinionDetailOut,
    CommitteeSessionDetailOut,
    CommitteeSessionListOut,
    CommitteeSessionSummaryOut,
    CommitteeStatsOut,
    RejectedAlternativeDetailOut,
)
from src.auth.rbac import require_staff_role
from src.core.db.database import get_db
from src.domain.models import CommitteeAgentOpinion, CommitteeConsensus, DecisionV2Snapshot, StaffRole, User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/admin/investment-committee", tags=["admin"])


def _session_summary(consensus: CommitteeConsensus, snapshot: DecisionV2Snapshot) -> CommitteeSessionSummaryOut:
    return CommitteeSessionSummaryOut(
        session_id=consensus.id,
        decision_v2_snapshot_id=consensus.decision_v2_snapshot_id,
        symbol=snapshot.symbol,
        company_name_ar=snapshot.company_name_ar,
        decision=snapshot.decision,
        decision_label_ar=snapshot.decision_label_ar,
        final_decision=consensus.final_decision,
        final_confidence=float(consensus.final_confidence),
        agreement_pct=float(consensus.agreement_pct),
        disagreement_pct=float(consensus.disagreement_pct),
        disagreement_score=float(consensus.disagreement_score),
        most_optimistic_agent=consensus.most_optimistic_agent,
        most_conservative_agent=consensus.most_conservative_agent,
        created_at=consensus.created_at,
    )


@router.get("/sessions", response_model=CommitteeSessionListOut)
async def list_committee_sessions(
    symbol: Optional[str] = Query(None),
    limit: int = Query(20, ge=1, le=100),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> CommitteeSessionListOut:
    """The committee timeline -- most recent consensus sessions first,
    optionally filtered to one symbol."""
    query = session.query(CommitteeConsensus, DecisionV2Snapshot).join(
        DecisionV2Snapshot, CommitteeConsensus.decision_v2_snapshot_id == DecisionV2Snapshot.id
    )
    if symbol:
        query = query.filter(DecisionV2Snapshot.symbol == symbol)
    rows = query.order_by(CommitteeConsensus.created_at.desc()).limit(limit).all()

    return CommitteeSessionListOut(
        generated_at=datetime.now(timezone.utc),
        total_sessions=len(rows),
        sessions=[_session_summary(consensus, snapshot) for consensus, snapshot in rows],
    )


@router.get("/sessions/{session_id}", response_model=CommitteeSessionDetailOut)
async def get_committee_session(
    session_id: int,
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> CommitteeSessionDetailOut:
    """Full detail for one committee session -- agent cards, votes,
    evidence, and the consensus explanation, all sourced from the
    real persisted rows for this decision."""
    row = (
        session.query(CommitteeConsensus, DecisionV2Snapshot)
        .join(DecisionV2Snapshot, CommitteeConsensus.decision_v2_snapshot_id == DecisionV2Snapshot.id)
        .filter(CommitteeConsensus.id == session_id)
        .first()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Committee session not found.")
    consensus, snapshot = row

    opinions = (
        session.query(CommitteeAgentOpinion)
        .filter(CommitteeAgentOpinion.decision_v2_snapshot_id == consensus.decision_v2_snapshot_id)
        .order_by(CommitteeAgentOpinion.id.asc())
        .all()
    )

    return CommitteeSessionDetailOut(
        session_id=consensus.id,
        decision_v2_snapshot_id=consensus.decision_v2_snapshot_id,
        symbol=snapshot.symbol,
        company_name_ar=snapshot.company_name_ar,
        decision=snapshot.decision,
        decision_label_ar=snapshot.decision_label_ar,
        decision_timestamp=snapshot.decision_timestamp,
        final_decision=consensus.final_decision,
        final_confidence=float(consensus.final_confidence),
        participant_count=consensus.participant_count,
        directional_count=consensus.directional_count,
        agreement_pct=float(consensus.agreement_pct),
        disagreement_pct=float(consensus.disagreement_pct),
        disagreement_score=float(consensus.disagreement_score),
        most_optimistic_agent=consensus.most_optimistic_agent,
        most_optimistic_stance=consensus.most_optimistic_stance,
        most_conservative_agent=consensus.most_conservative_agent,
        most_conservative_stance=consensus.most_conservative_stance,
        consensus_reasoning_ar=consensus.consensus_reasoning_ar,
        weighted_votes={k: float(v) for k, v in (consensus.weighted_votes or {}).items()},
        rejected_alternatives=[
            RejectedAlternativeDetailOut(**item) for item in (consensus.rejected_alternatives or [])
        ],
        opinions=[
            CommitteeAgentOpinionDetailOut(
                agent_name=op.agent_name, role=op.agent_role, stance=op.stance.value,
                confidence=float(op.confidence) if op.confidence is not None else 0.0,
                reasoning=op.reasoning, evidence=op.evidence or [], rejection_reasons=op.rejection_reasons or [],
                used_llm=op.used_llm,
            )
            for op in opinions
        ],
        created_at=consensus.created_at,
    )


@router.get("/stats", response_model=CommitteeStatsOut)
async def get_committee_stats(
    within_hours: int = Query(72, ge=1, le=24 * 30),
    session: Session = Depends(get_db),
    _current_user: User = Depends(require_staff_role(StaffRole.ADMIN)),
) -> CommitteeStatsOut:
    """Aggregate committee behavior over a time window -- real SQL
    over `committee_sessions`, never an estimate."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=within_hours)
    rows = (
        session.query(CommitteeConsensus)
        .filter(CommitteeConsensus.created_at >= cutoff)
        .all()
    )

    decision_counter: Counter = Counter()
    optimistic_counter: Counter = Counter()
    conservative_counter: Counter = Counter()
    agreement_sum = 0.0
    disagreement_score_sum = 0.0

    for row in rows:
        decision_counter[row.final_decision] += 1
        if row.most_optimistic_agent:
            optimistic_counter[row.most_optimistic_agent] += 1
        if row.most_conservative_agent:
            conservative_counter[row.most_conservative_agent] += 1
        agreement_sum += float(row.agreement_pct)
        disagreement_score_sum += float(row.disagreement_score)

    total = len(rows)
    return CommitteeStatsOut(
        generated_at=datetime.now(timezone.utc),
        window_hours=within_hours,
        total_sessions=total,
        average_agreement_pct=round(agreement_sum / total, 2) if total else None,
        average_disagreement_score=round(disagreement_score_sum / total, 2) if total else None,
        final_decision_distribution=dict(decision_counter),
        most_optimistic_agent_counts=dict(optimistic_counter),
        most_conservative_agent_counts=dict(conservative_counter),
    )
