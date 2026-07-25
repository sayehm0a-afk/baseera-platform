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

from src.api.dependencies import get_current_user
from src.auth.exceptions import InsufficientPermissionError
from src.domain.models import StaffRole, User

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
