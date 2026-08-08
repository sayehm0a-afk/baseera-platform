import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth.exceptions import InsufficientPermissionError, SubscriptionRequiredError
from src.auth.rbac import require_active_subscription, require_any_staff_role, require_staff_role
from src.core.db.database import Base
from src.domain.models import StaffRole, SubscriptionPlan, SubscriptionStatus, User
from src.subscriptions.repository import SubscriptionRepository


def _user(is_staff: bool, staff_role: "StaffRole | None") -> User:
    user = User(email="staff@example.com", password_hash="hashed")
    user.is_staff = is_staff
    user.staff_role = staff_role
    return user


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


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


def test_analyst_never_satisfies_a_rank_based_minimum():
    # ANALYST is deliberately outside _ROLE_RANK -- must not silently
    # KeyError, and must never pass a SUPPORT/ADMIN/OWNER gate.
    user = _user(is_staff=True, staff_role=StaffRole.ANALYST)
    with pytest.raises(InsufficientPermissionError):
        require_staff_role(StaffRole.SUPPORT)(current_user=user)
    with pytest.raises(InsufficientPermissionError):
        require_staff_role(StaffRole.ADMIN)(current_user=user)


def test_require_any_staff_role_admits_an_explicitly_listed_role():
    dependency = require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)
    user = _user(is_staff=True, staff_role=StaffRole.ANALYST)
    assert dependency(current_user=user) is user


def test_require_any_staff_role_rejects_an_unlisted_role():
    dependency = require_any_staff_role(StaffRole.ANALYST, StaffRole.ADMIN, StaffRole.OWNER)
    with pytest.raises(InsufficientPermissionError):
        dependency(current_user=_user(is_staff=True, staff_role=StaffRole.SUPPORT))


def test_require_any_staff_role_rejects_non_staff():
    dependency = require_any_staff_role(StaffRole.ANALYST)
    with pytest.raises(InsufficientPermissionError):
        dependency(current_user=_user(is_staff=False, staff_role=None))


def test_analyst_does_not_gain_support_gated_calibration_power():
    # The specific risk this design avoids: inserting ANALYST into the
    # rank ladder above SUPPORT would have silently granted it
    # calibration-activation power. It must not.
    user = _user(is_staff=True, staff_role=StaffRole.ANALYST)
    with pytest.raises(InsufficientPermissionError):
        require_staff_role(StaffRole.SUPPORT)(current_user=user)


def _create_user(session) -> User:
    user = User(email="customer@example.com", password_hash="hashed")
    session.add(user)
    session.commit()
    return user


def test_staff_bypasses_the_subscription_check_entirely(session):
    staff_user = _user(is_staff=True, staff_role=StaffRole.SUPPORT)
    dependency = require_active_subscription()
    # No Subscription row exists at all -- staff must still pass.
    assert dependency(session=session, current_user=staff_user) is staff_user


def test_customer_with_no_subscription_row_is_rejected(session):
    user = _create_user(session)
    dependency = require_active_subscription()
    with pytest.raises(SubscriptionRequiredError):
        dependency(session=session, current_user=user)


def test_customer_with_trialing_subscription_passes(session):
    user = _create_user(session)
    SubscriptionRepository().create_subscription(
        session, user_id=user.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.TRIALING
    )
    dependency = require_active_subscription()
    assert dependency(session=session, current_user=user) is user


def test_customer_with_expired_subscription_is_rejected(session):
    user = _create_user(session)
    SubscriptionRepository().create_subscription(
        session, user_id=user.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.EXPIRED
    )
    dependency = require_active_subscription()
    with pytest.raises(SubscriptionRequiredError):
        dependency(session=session, current_user=user)
