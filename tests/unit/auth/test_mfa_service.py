"""Unit tests for src.auth.mfa_service -- the business rules behind
optional staff TOTP 2FA (governance audit 2026-09-11, item 7)."""

import datetime

import pyotp
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import mfa_service
from src.auth.exceptions import (
    InvalidCredentialsError,
    InvalidMfaCodeError,
    MfaAlreadyEnabledError,
    MfaNotEnabledError,
    MfaSetupNotStartedError,
)
from src.auth.password_hashing import hash_password
from src.core.db.database import Base
from src.domain.models import MfaBackupCode, StaffRole, User

_PASSWORD = "a-real-strong-password1"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def owner(session):
    user = User(
        email="owner@example.com",
        password_hash=hash_password(_PASSWORD),
        is_staff=True,
        staff_role=StaffRole.OWNER,
        is_email_verified=True,
    )
    session.add(user)
    session.commit()
    return user


def _current_code(secret: str) -> str:
    return pyotp.TOTP(secret).now()


def _code_at_offset(secret: str, offset: int) -> str:
    """A code for a step `offset` ticks away from now -- still within
    verify_totp_code's own +/-1 step drift window when offset is -1, 0,
    or 1, but a DIFFERENT step than `_current_code`'s (offset 0), so
    tests can exercise the replay guard without waiting 30 real
    seconds for the step to actually advance."""
    return pyotp.TOTP(secret).at(datetime.datetime.now(), offset)


def test_start_enrollment_stores_a_pending_secret_without_enabling_mfa(session, owner):
    secret, uri = mfa_service.start_enrollment(session, owner)
    assert owner.mfa_enabled is False
    assert owner.mfa_pending_secret_encrypted is not None
    assert uri.startswith("otpauth://totp/")
    pyotp.TOTP(secret)  # a real, usable secret was returned


def test_start_enrollment_rejects_an_already_enabled_account(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    with pytest.raises(MfaAlreadyEnabledError):
        mfa_service.start_enrollment(session, owner)


def test_start_enrollment_overwrites_a_stale_unconfirmed_pending_secret(session, owner):
    secret_a, _ = mfa_service.start_enrollment(session, owner)
    secret_b, _ = mfa_service.start_enrollment(session, owner)
    assert secret_a != secret_b
    # Only the second secret's code should now activate the account.
    mfa_service.confirm_enrollment(session, owner, _current_code(secret_b))
    assert owner.mfa_enabled is True


def test_confirm_enrollment_without_setup_raises(session, owner):
    with pytest.raises(MfaSetupNotStartedError):
        mfa_service.confirm_enrollment(session, owner, "123456")


def test_confirm_enrollment_with_wrong_code_does_not_enable_mfa(session, owner):
    mfa_service.start_enrollment(session, owner)
    with pytest.raises(InvalidMfaCodeError):
        mfa_service.confirm_enrollment(session, owner, "000000")
    assert owner.mfa_enabled is False
    # A failed activation attempt must never destroy the still-valid
    # pending enrollment -- the user should be able to just retry.
    assert owner.mfa_pending_secret_encrypted is not None


def test_confirm_enrollment_with_correct_code_activates_and_returns_backup_codes(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    backup_codes = mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    assert owner.mfa_enabled is True
    assert owner.mfa_pending_secret_encrypted is None
    assert owner.mfa_secret_encrypted is not None
    assert len(backup_codes) == 10
    assert session.query(MfaBackupCode).filter_by(user_id=owner.id).count() == 10


def test_verify_login_code_accepts_a_real_totp_code(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    # confirm_enrollment consumes offset -1's step; login uses offset 0's
    # step (a later, distinct step) so this isn't itself a replay case.
    mfa_service.confirm_enrollment(session, owner, _code_at_offset(secret, -1))

    assert mfa_service.verify_login_code(session, owner, _code_at_offset(secret, 0)) is True


def test_verify_login_code_rejects_replay_of_the_confirmation_code(session, owner):
    # 2026-09-16 audit finding: a code is valid for +/-1 step (~90s), but
    # nothing previously stopped the exact same code from being accepted
    # twice within that window -- once to confirm enrollment, then again
    # immediately for login.
    secret, _ = mfa_service.start_enrollment(session, owner)
    code = _current_code(secret)
    mfa_service.confirm_enrollment(session, owner, code)

    assert mfa_service.verify_login_code(session, owner, code) is False


def test_verify_login_code_rejects_replay_of_a_previously_accepted_login_code(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    mfa_service.confirm_enrollment(session, owner, _code_at_offset(secret, -1))

    login_code = _code_at_offset(secret, 0)
    assert mfa_service.verify_login_code(session, owner, login_code) is True
    # Still within its own +/-1 step window, but already used -- must
    # not be accepted a second time.
    assert mfa_service.verify_login_code(session, owner, login_code) is False


def test_verify_login_code_accepts_a_later_step_after_a_previous_login(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    mfa_service.confirm_enrollment(session, owner, _code_at_offset(secret, -1))

    assert mfa_service.verify_login_code(session, owner, _code_at_offset(secret, 0)) is True
    assert mfa_service.verify_login_code(session, owner, _code_at_offset(secret, 1)) is True


def test_verify_login_code_rejects_a_wrong_code(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    assert mfa_service.verify_login_code(session, owner, "000000") is False


def test_verify_login_code_accepts_a_backup_code_exactly_once(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    backup_codes = mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    code = backup_codes[0]
    assert mfa_service.verify_login_code(session, owner, code) is True
    assert mfa_service.verify_login_code(session, owner, code) is False


def test_verify_login_code_marks_only_the_matched_code_used(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    backup_codes = mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    mfa_service.verify_login_code(session, owner, backup_codes[0])

    unused = {c.code_hash for c in session.query(MfaBackupCode).filter_by(user_id=owner.id, used_at=None)}
    assert len(unused) == 9
    assert mfa_service.verify_login_code(session, owner, backup_codes[1]) is True


def test_disable_mfa_requires_correct_password(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    with pytest.raises(InvalidCredentialsError):
        mfa_service.disable_mfa(session, owner, "wrong-password")
    assert owner.mfa_enabled is True


def test_disable_mfa_clears_secret_and_backup_codes(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    mfa_service.disable_mfa(session, owner, _PASSWORD)

    assert owner.mfa_enabled is False
    assert owner.mfa_secret_encrypted is None
    assert owner.mfa_enabled_at is None
    assert session.query(MfaBackupCode).filter_by(user_id=owner.id).count() == 0


def test_disable_mfa_on_a_not_enabled_account_raises(session, owner):
    with pytest.raises(MfaNotEnabledError):
        mfa_service.disable_mfa(session, owner, _PASSWORD)


def test_regenerate_backup_codes_requires_correct_password(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    with pytest.raises(InvalidCredentialsError):
        mfa_service.regenerate_backup_codes(session, owner, "wrong-password")


def test_regenerate_backup_codes_on_a_not_enabled_account_raises(session, owner):
    with pytest.raises(MfaNotEnabledError):
        mfa_service.regenerate_backup_codes(session, owner, _PASSWORD)


def test_regenerate_backup_codes_invalidates_the_old_set(session, owner):
    secret, _ = mfa_service.start_enrollment(session, owner)
    old_codes = mfa_service.confirm_enrollment(session, owner, _current_code(secret))

    new_codes = mfa_service.regenerate_backup_codes(session, owner, _PASSWORD)

    assert set(new_codes) != set(old_codes)
    assert mfa_service.verify_login_code(session, owner, old_codes[0]) is False
    assert mfa_service.verify_login_code(session, owner, new_codes[0]) is True
