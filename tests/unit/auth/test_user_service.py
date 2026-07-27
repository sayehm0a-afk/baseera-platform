import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import user_service
from src.auth.exceptions import (
    AccountHasBillingHistoryError,
    AccountLockedError,
    AccountSuspendedError,
    EmailAlreadyRegisteredError,
    EmailNotVerifiedError,
    InvalidCredentialsError,
    StaffAccountSelfDeletionError,
)
from src.auth.password_hashing import hash_password
from src.auth.repository import AuthRepository
from src.core.db.database import Base
from src.core.monitoring.prometheus_metrics import get_metrics
from src.domain.models import EmailVerificationToken, Subscription, SubscriptionPlan, SubscriptionStatus, User


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_register_creates_unverified_user(session):
    user = user_service.register(session, "New.User@Example.com", "s3cret-password")
    assert user.email == "new.user@example.com"  # normalized
    assert user.is_email_verified is False


def test_register_issues_a_verification_token(session):
    user = user_service.register(session, "verify-me@example.com", "s3cret-password")
    # Can't know the raw token (never persisted), but a row must exist.
    assert session.query(EmailVerificationToken).filter_by(user_id=user.id).count() == 1


def test_register_provisions_a_trial_subscription(session):
    user = user_service.register(session, "trial-me@example.com", "s3cret-password")
    subscription = session.query(Subscription).filter_by(user_id=user.id).one()
    assert subscription.plan == SubscriptionPlan.TRIAL
    assert subscription.status == SubscriptionStatus.TRIALING
    assert subscription.trial_ends_at is not None


def test_register_rejects_duplicate_email(session):
    user_service.register(session, "dup@example.com", "s3cret-password")
    with pytest.raises(EmailAlreadyRegisteredError):
        user_service.register(session, "dup@example.com", "another-password")


def test_register_email_is_case_insensitive_for_duplicates(session):
    user_service.register(session, "Case@Example.com", "s3cret-password")
    with pytest.raises(EmailAlreadyRegisteredError):
        user_service.register(session, "case@example.com", "another-password")


def test_authenticate_rejects_wrong_password(session):
    user_service.register(session, "auth1@example.com", "correct-password")
    with pytest.raises(InvalidCredentialsError):
        user_service.authenticate(session, "auth1@example.com", "wrong-password")


def test_authenticate_rejects_unknown_email(session):
    with pytest.raises(InvalidCredentialsError):
        user_service.authenticate(session, "nobody@example.com", "whatever")


def test_authenticate_rejects_unverified_email(session):
    user_service.register(session, "unverified@example.com", "correct-password")
    with pytest.raises(EmailNotVerifiedError):
        user_service.authenticate(session, "unverified@example.com", "correct-password")


def test_authenticate_rejects_suspended_account(session):
    repo = AuthRepository()
    user = user_service.register(session, "suspended@example.com", "correct-password")
    repo.set_email_verified(session, user.id)
    repo.set_is_active(session, user.id, False)

    with pytest.raises(AccountSuspendedError):
        user_service.authenticate(session, "suspended@example.com", "correct-password")


def test_authenticate_succeeds_when_verified_and_active(session):
    repo = AuthRepository()
    user_service.register(session, "verified@example.com", "correct-password")
    repo.set_email_verified(session, repo.get_user_by_email(session, "verified@example.com").id)

    authenticated = user_service.authenticate(session, "verified@example.com", "correct-password")
    assert authenticated.email == "verified@example.com"
    assert authenticated.last_login_at is not None


def test_register_increments_the_registrations_counter(session):
    metrics = get_metrics()
    before = metrics.registrations_total._value.get()
    user_service.register(session, "metrics-register@example.com", "s3cret-password")
    assert metrics.registrations_total._value.get() == before + 1


def test_authenticate_increments_the_login_success_counter(session):
    repo = AuthRepository()
    user_service.register(session, "metrics-login-success@example.com", "correct-password")
    repo.set_email_verified(session, repo.get_user_by_email(session, "metrics-login-success@example.com").id)

    metrics = get_metrics()
    before = metrics.logins_total.labels(status="success")._value.get()
    user_service.authenticate(session, "metrics-login-success@example.com", "correct-password")
    assert metrics.logins_total.labels(status="success")._value.get() == before + 1


def test_authenticate_increments_the_login_failure_counter(session):
    metrics = get_metrics()
    before = metrics.logins_total.labels(status="failure")._value.get()
    with pytest.raises(InvalidCredentialsError):
        user_service.authenticate(session, "nobody-metrics@example.com", "whatever")
    assert metrics.logins_total.labels(status="failure")._value.get() == before + 1


# --- Account lockout (Phase 13, P13.3) --------------------------------------


def _verified_user(session, email, password="correct-password"):
    repo = AuthRepository()
    user_service.register(session, email, password)
    user = repo.get_user_by_email(session, email)
    repo.set_email_verified(session, user.id)
    return user


def test_repeated_wrong_passwords_lock_the_account(session, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "login_lockout_max_attempts", 3)
    _verified_user(session, "lockout@example.com")

    for _ in range(3):
        with pytest.raises(InvalidCredentialsError):
            user_service.authenticate(session, "lockout@example.com", "wrong-password")

    # The 4th attempt -- even with the *correct* password -- is rejected
    # because the account is now locked, not because of the password.
    with pytest.raises(AccountLockedError):
        user_service.authenticate(session, "lockout@example.com", "correct-password")


def test_lockout_clears_after_a_successful_login_resets_the_counter(session, monkeypatch):
    from src.core.config import settings

    monkeypatch.setattr(settings, "login_lockout_max_attempts", 3)
    _verified_user(session, "reset-lockout@example.com")

    for _ in range(2):  # one below the threshold
        with pytest.raises(InvalidCredentialsError):
            user_service.authenticate(session, "reset-lockout@example.com", "wrong-password")

    user_service.authenticate(session, "reset-lockout@example.com", "correct-password")

    repo = AuthRepository()
    user = repo.get_user_by_email(session, "reset-lockout@example.com")
    assert user.failed_login_attempts == 0
    assert user.locked_until is None


def test_locked_account_stays_locked_until_the_lockout_window_passes(session, monkeypatch):
    from datetime import datetime, timedelta, timezone

    from src.core.config import settings

    monkeypatch.setattr(settings, "login_lockout_max_attempts", 1)
    user = _verified_user(session, "expired-lockout@example.com")

    with pytest.raises(InvalidCredentialsError):
        user_service.authenticate(session, "expired-lockout@example.com", "wrong-password")

    repo = AuthRepository()
    assert repo.get_user_by_email(session, "expired-lockout@example.com").locked_until is not None

    # Simulate the lockout window having already elapsed.
    session.query(type(user)).filter_by(id=user.id).update(
        {"locked_until": datetime.now(timezone.utc) - timedelta(minutes=1)}
    )
    session.commit()

    authenticated = user_service.authenticate(session, "expired-lockout@example.com", "correct-password")
    assert authenticated.email == "expired-lockout@example.com"


def test_authenticate_takes_a_real_password_verification_pass_for_an_unknown_email(session, monkeypatch):
    """Regression guard for the user-enumeration timing fix: `verify_password`
    must be called even when no user was found, not short-circuited away --
    otherwise an unknown email responds measurably faster than a known one
    with a wrong password, which is itself an enumeration oracle."""
    calls = []
    real_verify = user_service.verify_password

    def _spy(password, password_hash):
        calls.append(password_hash)
        return real_verify(password, password_hash)

    monkeypatch.setattr(user_service, "verify_password", _spy)

    with pytest.raises(InvalidCredentialsError):
        user_service.authenticate(session, "definitely-nobody@example.com", "whatever")

    assert calls == [user_service._DUMMY_PASSWORD_HASH]


# --- delete_own_account (Phase 13 P13.6) --------------------------------


def test_delete_own_account_rejects_the_wrong_password(session):
    user = User(email="deleteme@example.com", password_hash=hash_password("correct-password"))
    session.add(user)
    session.commit()

    with pytest.raises(InvalidCredentialsError):
        user_service.delete_own_account(session, user, "wrong-password")

    assert AuthRepository().get_user_by_email(session, "deleteme@example.com") is not None


def test_delete_own_account_removes_the_user_row_on_correct_password(session):
    user = User(email="deleteme@example.com", password_hash=hash_password("correct-password"))
    session.add(user)
    session.commit()
    user_id = user.id

    user_service.delete_own_account(session, user, "correct-password")

    assert AuthRepository().get_user_by_id(session, user_id) is None


def test_delete_own_account_raises_a_customer_facing_error_when_billing_history_blocks_it(session, monkeypatch):
    from sqlalchemy.exc import IntegrityError

    user = User(email="deleteme@example.com", password_hash=hash_password("correct-password"))
    session.add(user)
    session.commit()

    def _raise_integrity_error(*args, **kwargs):
        raise IntegrityError("statement", {}, Exception("FK violation"))

    monkeypatch.setattr(user_service._repository, "delete_user", _raise_integrity_error)

    with pytest.raises(AccountHasBillingHistoryError):
        user_service.delete_own_account(session, user, "correct-password")


def test_delete_own_account_blocks_a_staff_account_regardless_of_password(session):
    staff_user = User(email="staff-self-delete@example.com", password_hash=hash_password("correct-password"), is_staff=True)
    session.add(staff_user)
    session.commit()

    with pytest.raises(StaffAccountSelfDeletionError):
        user_service.delete_own_account(session, staff_user, "correct-password")

    assert AuthRepository().get_user_by_email(session, "staff-self-delete@example.com") is not None
