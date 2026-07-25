import pytest

from src.auth.exceptions import InsufficientPermissionError
from src.auth.rbac import require_staff_role
from src.domain.models import StaffRole, User


def _user(is_staff: bool, staff_role: "StaffRole | None") -> User:
    user = User(email="staff@example.com", password_hash="hashed")
    user.is_staff = is_staff
    user.staff_role = staff_role
    return user


def test_non_staff_user_is_rejected():
    dependency = require_staff_role(StaffRole.SUPPORT)
    with pytest.raises(InsufficientPermissionError):
        dependency(current_user=_user(is_staff=False, staff_role=None))


def test_staff_user_with_no_role_set_is_rejected():
    dependency = require_staff_role(StaffRole.SUPPORT)
    with pytest.raises(InsufficientPermissionError):
        dependency(current_user=_user(is_staff=True, staff_role=None))


def test_support_cannot_pass_an_admin_only_gate():
    dependency = require_staff_role(StaffRole.ADMIN)
    with pytest.raises(InsufficientPermissionError):
        dependency(current_user=_user(is_staff=True, staff_role=StaffRole.SUPPORT))


def test_admin_passes_an_admin_gate():
    dependency = require_staff_role(StaffRole.ADMIN)
    user = _user(is_staff=True, staff_role=StaffRole.ADMIN)
    assert dependency(current_user=user) is user


def test_owner_passes_a_support_or_admin_gate():
    user = _user(is_staff=True, staff_role=StaffRole.OWNER)
    assert require_staff_role(StaffRole.SUPPORT)(current_user=user) is user
    assert require_staff_role(StaffRole.ADMIN)(current_user=user) is user
