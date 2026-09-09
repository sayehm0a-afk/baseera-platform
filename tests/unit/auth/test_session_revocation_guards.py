"""Real SQLite/JWT checks; Redis is an explicit in-memory transport double.

These checks target access-token validity, not recommendation generation or
browser authentication. No customer accounts or external services are used.
"""

from datetime import datetime, timedelta, timezone
from unittest.mock import Mock, patch

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.api.dependencies import get_current_user
from src.auth import jwt_service, session_service, token_store
from src.auth.exceptions import UnauthenticatedError
from src.auth.repository import AuthRepository
from src.core.db.database import Base


@pytest.fixture
def db(monkeypatch):
    cache = Mock()
    cache.exists.return_value = 0
    monkeypatch.setattr(token_store, "_client", cache)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_revoking_remote_session_rejects_its_access_but_keeps_other_device(db):
    repo = AuthRepository()
    user = repo.create_user(db, "revocation-test@example.com", "test-only-hash")
    first = session_service.create_session(db, user)
    second = session_service.create_session(db, user)
    session_service.revoke_session(db, first.refresh_token)

    with pytest.raises(UnauthenticatedError):
        get_current_user(access_token=first.access_token, session=db)
    assert get_current_user(access_token=second.access_token, session=db).id == user.id


def test_rotation_preserves_access_validity_until_the_family_is_revoked(db):
    user = AuthRepository().create_user(db, "rotation-test@example.com", "test-only-hash")
    first = session_service.create_session(db, user)
    rotated = session_service.refresh_session(db, first.refresh_token)
    assert get_current_user(access_token=first.access_token, session=db).id == user.id
    session_service.revoke_session(db, rotated.refresh_token)
    for token in (first.access_token, rotated.access_token):
        with pytest.raises(UnauthenticatedError):
            get_current_user(access_token=token, session=db)


def test_new_login_within_revocation_second_is_valid_but_older_token_is_not(db):
    user = AuthRepository().create_user(db, "same-second@example.com", "test-only-hash")
    base = (datetime.now(timezone.utc) - timedelta(seconds=2)).replace(microsecond=0)
    user.tokens_invalid_before = base + timedelta(microseconds=400000)
    db.commit()
    with patch.object(jwt_service, "datetime") as clock:
        clock.now.return_value = base + timedelta(microseconds=200000)
        old = jwt_service.encode_access_token(user.id, False, None)
        clock.now.return_value = base + timedelta(microseconds=600000)
        new = jwt_service.encode_access_token(user.id, False, None)
    with pytest.raises(UnauthenticatedError):
        get_current_user(access_token=old, session=db)
    assert get_current_user(access_token=new, session=db).id == user.id


def test_revocation_using_an_older_rotated_token_still_kills_the_family(db):
    user = AuthRepository().create_user(db, "old-row@example.com", "test-only-hash")
    first = session_service.create_session(db, user)
    second = session_service.refresh_session(db, first.refresh_token)
    session_service.revoke_session(db, first.refresh_token)
    with pytest.raises(UnauthenticatedError):
        get_current_user(access_token=second.access_token, session=db)


def test_failed_rotation_rolls_back_revocation(db, monkeypatch):
    user = AuthRepository().create_user(db, "rollback@example.com", "test-only-hash")
    pair = session_service.create_session(db, user)
    with monkeypatch.context() as context:
        def unavailable(*args, **kwargs):
            raise RuntimeError("test transport failure")
        context.setattr(token_store, "store_refresh_session", unavailable)
        with pytest.raises(RuntimeError):
            session_service.refresh_session(db, pair.refresh_token)
    assert get_current_user(access_token=pair.access_token, session=db).id == user.id
    assert session_service.refresh_session(db, pair.refresh_token).refresh_token


def test_refresh_claim_is_single_use_even_with_a_stale_orm_object(db):
    from src.auth.token_hashing import hash_token

    repo = AuthRepository()
    user = repo.create_user(db, "claim-once@example.com", "test-only-hash")
    pair = session_service.create_session(db, user)
    row = repo.get_user_session_by_jti(db, hash_token(pair.refresh_token))
    assert repo.consume_refresh_session(db, row.id) is True
    # The session's previously read Python object has not been refreshed.
    assert row.revoked_at is None
    assert repo.consume_refresh_session(db, row.id) is False
    db.rollback()
    assert repo.has_active_session_family(db, user.id, row.family_id)
