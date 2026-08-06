"""The Consensus Engine: turns eight independent `AgentVerdict`s into
one weighted-vote decision, an agreement/disagreement read, and a
grounded Arabic explanation of why the consensus was reached and why
dissenting opinions were outweighed.

Every number here is arithmetic over the real `stance`/`confidence`
values the eight committee agents already computed -- no LLM call, no
fabricated score. `_ROLE_WEIGHT` is the one disclosed judgment call
(which expertise counts more toward the final vote): Risk/Technical/
Fundamental carry the most weight (the three legs Decision Engine V2's
own scoring already treats as primary), Macro the least (it is
UNAVAILABLE by design absent a real data source, so it never
meaningfully swings a vote), matching the same "reuse the concept,
disclose the choice" discipline the rest of Decision Engine V2 follows
(e.g. `wrapper_agents.py`'s Quant-to-Momentum mapping).
"""

import math
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple

from src.ai_evolution.committee.types import ConsensusResult, RejectedAlternative, AgentVerdict
from src.domain.models import AgentStance

_ROLE_WEIGHT: Dict[str, float] = {
    "technical": 1.2,
    "fundamental": 1.2,
    "risk": 1.3,
    "liquidity_volume": 1.0,
    "news": 0.9,
    "market_sentiment": 0.8,
    "portfolio_allocation": 0.8,
    "macro": 0.5,
}
_DEFAULT_ROLE_WEIGHT = 1.0

_STANCE_VALUE = {AgentStance.BULLISH: 1.0, AgentStance.NEUTRAL: 0.0, AgentStance.BEARISH: -1.0}

_DECISION_LABELS_AR = {"BUY": "شراء", "SELL": "بيع", "HOLD": "احتفاظ/حياد"}


def _role_weight(role: str) -> float:
    return _ROLE_WEIGHT.get(role, _DEFAULT_ROLE_WEIGHT)


def _signed_vote(verdict: AgentVerdict) -> float:
    """0.0 for NEUTRAL/UNAVAILABLE (no directional vote cast); ±(role
    weight × confidence fraction) for BULLISH/BEARISH."""
    if verdict.stance not in (AgentStance.BULLISH, AgentStance.BEARISH):
        return 0.0
    magnitude = _role_weight(verdict.role) * (verdict.confidence / 100.0)
    return magnitude if verdict.stance is AgentStance.BULLISH else -magnitude


def _weighted_average_confidence(verdicts: List[AgentVerdict]) -> float:
    if not verdicts:
        return 0.0
    total_weight = sum(_role_weight(v.role) for v in verdicts)
    if total_weight <= 0:
        return sum(v.confidence for v in verdicts) / len(verdicts)
    return sum(v.confidence * _role_weight(v.role) for v in verdicts) / total_weight


def _most_optimistic_and_conservative(
    opinionated: List[AgentVerdict],
) -> Tuple[Optional[AgentVerdict], Optional[AgentVerdict]]:
    if not opinionated:
        return None, None
    ranked = sorted(opinionated, key=lambda v: _STANCE_VALUE[v.stance] * (v.confidence / 100.0))
    return ranked[-1], ranked[0]


def _majority_stance(opinionated: List[AgentVerdict], net_vote: float) -> Optional[AgentStance]:
    if not opinionated:
        return None
    directional = [v for v in opinionated if v.stance is not AgentStance.NEUTRAL]
    if directional:
        return AgentStance.BULLISH if net_vote >= 0 else AgentStance.BEARISH
    return AgentStance.NEUTRAL


def build_consensus(symbol: str, opinions: List[AgentVerdict]) -> ConsensusResult:
    """Builds the full weighted-vote consensus for one committee run.
    `symbol` is used only in the Arabic reasoning text, never in the
    arithmetic."""
    participant_count = len(opinions)
    opinionated = [v for v in opinions if v.stance is not AgentStance.UNAVAILABLE]
    directional = [v for v in opinionated if v.stance is not AgentStance.NEUTRAL]
    directional_count = len(directional)

    weighted_votes: Dict[str, float] = OrderedDict((v.agent_name, round(_signed_vote(v), 4)) for v in opinions)
    net_vote = sum(weighted_votes.values())

    if directional_count == 0:
        final_decision = "HOLD"
    elif net_vote > 1e-9:
        final_decision = "BUY"
    elif net_vote < -1e-9:
        final_decision = "SELL"
    else:
        final_decision = "HOLD"

    winning_stance = {"BUY": AgentStance.BULLISH, "SELL": AgentStance.BEARISH}.get(final_decision)
    if winning_stance is not None:
        agreeing = [v for v in directional if v.stance is winning_stance]
        dissenting = [v for v in directional if v.stance is not winning_stance]
    else:
        agreeing = [v for v in opinionated if v.stance is AgentStance.NEUTRAL] or opinionated
        dissenting = directional  # every directional opinion is a live disagreement when the vote is a tie/HOLD

    final_confidence = round(_weighted_average_confidence(agreeing), 2)

    majority_stance = _majority_stance(opinionated, net_vote)
    if opinionated and majority_stance is not None:
        matching = [v for v in opinionated if v.stance is majority_stance]
        agreement_pct = round(len(matching) / len(opinionated) * 100.0, 2)
    else:
        agreement_pct = 0.0
    disagreement_pct = round(100.0 - agreement_pct, 2)

    if len(opinionated) >= 2:
        values = [_STANCE_VALUE[v.stance] * v.confidence for v in opinionated]
        mean = sum(values) / len(values)
        variance = sum((x - mean) ** 2 for x in values) / len(values)
        disagreement_score = round(min(100.0, math.sqrt(variance)), 2)
    else:
        disagreement_score = 0.0

    most_optimistic, most_conservative = _most_optimistic_and_conservative(opinionated)

    rejected_alternatives = [
        RejectedAlternative(
            agent_name=v.agent_name, role=v.role, stance=v.stance, confidence=v.confidence, reasoning=v.reasoning,
            rejection_reason=(
                f"تم ترجيح الرأي الأغلب لأن وزنه المرجح الإجمالي يفوق الوزن المرجح لهذا الرأي "
                f"({abs(_signed_vote(v)):.2f})."
            ),
        )
        for v in dissenting
    ]

    consensus_reasoning_ar = _build_reasoning_ar(
        symbol=symbol, final_decision=final_decision, final_confidence=final_confidence,
        agreement_pct=agreement_pct, most_optimistic=most_optimistic, most_conservative=most_conservative,
        rejected_alternatives=rejected_alternatives, opinionated_count=len(opinionated),
    )

    return ConsensusResult(
        final_decision=final_decision, final_confidence=final_confidence,
        participant_count=participant_count, directional_count=directional_count,
        agreement_pct=agreement_pct, disagreement_pct=disagreement_pct, disagreement_score=disagreement_score,
        most_optimistic_agent=most_optimistic.agent_name if most_optimistic else None,
        most_optimistic_stance=most_optimistic.stance.value if most_optimistic else None,
        most_conservative_agent=most_conservative.agent_name if most_conservative else None,
        most_conservative_stance=most_conservative.stance.value if most_conservative else None,
        consensus_reasoning_ar=consensus_reasoning_ar,
        rejected_alternatives=rejected_alternatives, weighted_votes=weighted_votes, opinions=list(opinions),
    )


def _build_reasoning_ar(
    symbol: str, final_decision: str, final_confidence: float, agreement_pct: float,
    most_optimistic: Optional[AgentVerdict], most_conservative: Optional[AgentVerdict],
    rejected_alternatives: List[RejectedAlternative], opinionated_count: int,
) -> str:
    if opinionated_count == 0:
        return f"لم تتمكن لجنة الاستثمار من تكوين رأي حول {symbol} لعدم توفر بيانات كافية لدى أي محلل."

    decision_ar = _DECISION_LABELS_AR.get(final_decision, final_decision)
    parts = [
        f"توصلت لجنة الاستثمار إلى توافق بنسبة {agreement_pct:.0f}% حول قرار ({decision_ar}) لسهم {symbol} "
        f"بثقة إجمالية {final_confidence:.0f}%."
    ]
    if most_optimistic is not None:
        parts.append(f"كان {most_optimistic.agent_name} الأكثر تفاؤلًا ({most_optimistic.stance.value}).")
    if most_conservative is not None and most_conservative.agent_name != (
        most_optimistic.agent_name if most_optimistic else None
    ):
        parts.append(f"وكان {most_conservative.agent_name} الأكثر تحفظًا ({most_conservative.stance.value}).")
    if rejected_alternatives:
        names = "، ".join(r.agent_name for r in rejected_alternatives)
        parts.append(f"عارض الرأي الأغلب كل من: {names}، إلا أن ثقلهم المرجح لم يكفِ لتغيير القرار النهائي.")
    else:
        parts.append("لم يسجَّل اعتراض جوهري من أي محلل مشارك على القرار النهائي.")
    return " ".join(parts)
