"""GET /api/v1/subscriptions/me -- lets an authenticated user see
their own trial/subscription state (trial countdown, plan, status),
reading through subscription_service.get_effective_subscription so a
stale TRIALING row is lazily downgraded to EXPIRED before being shown,
never displaying a status that's already technically wrong.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.api.exceptions import APIError
from src.api.schemas.subscriptions import SubscriptionOut
from src.core.db.database import get_db
from src.domain.models import User
from src.subscriptions import subscription_service

router = APIRouter(prefix="/api/v1/subscriptions", tags=["subscriptions"])


class SubscriptionNotFoundError(APIError):
    """No Subscription row exists for this user -- should not happen
    for a normally-registered account (registration always provisions
    a trial), so this signals a data-integrity gap rather than a
    normal "not yet" state."""

    status_code = 404
    code = "subscription_not_found"


@router.get("/me", response_model=SubscriptionOut)
def get_my_subscription(
    session: Session = Depends(get_db), current_user: User = Depends(get_current_user)
) -> SubscriptionOut:
    subscription = subscription_service.get_effective_subscription(session, current_user.id)
    if subscription is None:
        raise SubscriptionNotFoundError(f"No subscription found for user {current_user.id}.")
    return SubscriptionOut.model_validate(subscription)
