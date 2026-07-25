"""record_ai_request(): persists one AIRequest row -- what the Admin
Dashboard's "view AI usage" (Phase 10) reads from. A plain function,
not a class: there is exactly one thing to do and no state to hold,
and every call site already has a Session in hand.
"""

from typing import Optional

from sqlalchemy.orm import Session

from src.domain.models import AIRequest, AIRequestStatus


def record_ai_request(
    session: Session,
    *,
    feature: str,
    status: AIRequestStatus,
    user_id: Optional[int] = None,
    symbol: Optional[str] = None,
    model: Optional[str] = None,
    prompt_tokens: Optional[int] = None,
    completion_tokens: Optional[int] = None,
    total_tokens: Optional[int] = None,
    latency_ms: Optional[float] = None,
    error_message: Optional[str] = None,
    estimated_cost_usd: Optional[float] = None,
) -> AIRequest:
    request = AIRequest(
        user_id=user_id,
        feature=feature,
        symbol=symbol,
        model=model,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
        total_tokens=total_tokens,
        latency_ms=latency_ms,
        status=status,
        error_message=error_message,
        estimated_cost_usd=estimated_cost_usd,
    )
    session.add(request)
    session.commit()
    return request
