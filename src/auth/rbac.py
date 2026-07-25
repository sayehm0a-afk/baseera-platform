"""Role-based access control dependency factories.

`get_current_user` (src/api/dependencies.py) already IS "require
authenticated" -- any route depending on it gets a 401 the moment no
valid session exists. `require_authenticated` below is a thin alias so
call sites read consistently with `require_staff_role(...)`.

`require_staff_role` is a factory (not a bare function) because
different admin routes need different minimum roles (e.g. only OWNER
may permanently delete another staff account, while ADMIN/SUPPORT can
both view users) -- the same "parameterized checks are factories"
shape the Phase 10 plan calls for `require_active_subscription()` to
follow once the Subscription model exists (M10.6).

Role ranking is OWNER > ADMIN > SUPPORT, so `require_staff_role
(StaffRole.ADMIN)` also admits an OWNER, but never a SUPPORT.
"""

from typing import Callable

from fastapi import Depends
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.auth.exceptions import InsufficientPermissionError, SubscriptionRequiredError
from src.core.db.database import get_db
from src.domain.models import StaffRole, User
from src.subscriptions import subscription_service

_ROLE_RANK = {StaffRole.SUPPORT: 0, StaffRole.ADMIN: 1, StaffRole.OWNER: 2}


def require_authenticated() -> Callable[..., User]:
    return get_current_user


def require_staff_role(minimum_role: StaffRole) -> Callable[..., User]:
    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.is_staff or current_user.staff_role is None:
            raise InsufficientPermissionError("This action requires staff access.")
        if _ROLE_RANK[current_user.staff_role] < _ROLE_RANK[minimum_role]:
            raise InsufficientPermissionError(f"This action requires at least {minimum_role.value} access.")
        return current_user

    return _dependency


def require_active_subscription() -> Callable[..., User]:
    """Gates a premium feature behind an entitled (trialing/active)
    subscription. Staff bypass entirely (an internal account
    reviewing/support-testing a premium feature is not a customer
    subscription concern) -- this composes with require_staff_role
    exactly like every other per-route dependency in this codebase
    already does, per Phase 10 plan decision 9."""

    def _dependency(
        session: Session = Depends(get_db), current_user: User = Depends(get_current_user)
    ) -> User:
        if current_user.is_staff:
            return current_user
        subscription = subscription_service.get_effective_subscription(session, current_user.id)
        if not subscription_service.is_entitled(subscription):
            raise SubscriptionRequiredError(
                "An active trial or paid subscription is required to use this feature."
            )
        return current_user

    return _dependency
