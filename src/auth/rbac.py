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
StaffRole.ANALYST is NOT part of this ladder -- `require_staff_role`
never admits it (see `_ROLE_RANK`); routes that should be
ANALYST-accessible use `require_any_staff_role` instead, which checks
exact role membership, not rank. See docs/ADMIN_AND_RBAC.md for the
full per-role permission matrix.
"""

from typing import Callable, Iterable

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
        # .get(..., -1): a role outside the ladder entirely (ANALYST)
        # must never satisfy any rank-based minimum, not crash with a
        # KeyError -- see the module docstring and require_any_staff_role.
        if _ROLE_RANK.get(current_user.staff_role, -1) < _ROLE_RANK[minimum_role]:
            raise InsufficientPermissionError(f"This action requires at least {minimum_role.value} access.")
        return current_user

    return _dependency


def require_any_staff_role(*roles: StaffRole) -> Callable[..., User]:
    """Exact-membership check, deliberately independent of `_ROLE_RANK`
    -- for StaffRole.ANALYST, which is not part of the OWNER > ADMIN >
    SUPPORT ladder at all (see StaffRole's docstring). A route using
    this still admits ADMIN/OWNER when they're listed explicitly (as
    every ANALYST-accessible read-only intelligence route does), but
    an ANALYST account gains exactly the routes that list it and
    nothing more -- no accidental inheritance of SUPPORT's calibration-
    activation power or ADMIN's user/billing management the way
    inserting ANALYST into the rank ladder would silently create."""

    allowed: Iterable[StaffRole] = roles

    def _dependency(current_user: User = Depends(get_current_user)) -> User:
        if not current_user.is_staff or current_user.staff_role is None:
            raise InsufficientPermissionError("This action requires staff access.")
        if current_user.staff_role not in allowed:
            raise InsufficientPermissionError("This action requires a different staff role.")
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
