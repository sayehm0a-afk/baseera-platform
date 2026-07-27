import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import session_service
from src.auth.exceptions import InvalidOrExpiredTokenError
from src.auth.jwt_service import decode_access_token
from src.auth.repository import AuthRepository
from src.core.db.database import Base


def is_redis_available() -> bool:
    try:
        import redis

        r = redis.Redis(host="localhost", port=6379, socket_connect_timeout=1)
        return r.ping()
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not is_redis_available(), reason="Redis not available")


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
def user(session):
    return AuthRepository().create_user(session, "sessiontest@example.com", "hashed")


def test_create_session_returns_valid_access_and_refresh_tokens(session, user):
    pair = session_service.create_session(session, user, device_label="test-device")
    claims = decode_access_token(pair.access_token)
    assert claims["sub"] == str(user.id)
    assert pair.refresh_token  # non-empty raw token


def test_refresh_rotates_the_token(session, user):
    first = session_service.create_session(session, user)
    second = session_service.refresh_session(session, first.refresh_token)

    assert second.refresh_token != first.refresh_token
    # The old token is now revoked and cannot be reused.
    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, first.refresh_token)


def test_reuse_of_rotated_token_revokes_entire_family(session, user):
    first = session_service.create_session(session, user)
    second = session_service.refresh_session(session, first.refresh_token)

    # Presenting the already-rotated-away token again...
    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, first.refresh_token)

    # ...revokes the whole family, so even the *current* valid token
    # from that chain is now dead too.
    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, second.refresh_token)


def test_refresh_unknown_token_rejected(session):
    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, "not-a-real-refresh-token")


def test_revoke_session_prevents_future_refresh(session, user):
    pair = session_service.create_session(session, user)
    session_service.revoke_session(session, pair.refresh_token)

    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, pair.refresh_token)


def test_revoke_all_sessions_for_user(session, user):
    pair1 = session_service.create_session(session, user, device_label="device-1")
    pair2 = session_service.create_session(session, user, device_label="device-2")

    session_service.revoke_all_sessions(session, user.id)

    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, pair1.refresh_token)
    with pytest.raises(InvalidOrExpiredTokenError):
        session_service.refresh_session(session, pair2.refresh_token)


def test_list_sessions_reflects_active_logins(session, user):
    session_service.create_session(session, user, device_label="device-a")
    session_service.create_session(session, user, device_label="device-b")

    sessions = session_service.list_sessions(session, user.id)
    assert len(sessions) == 2
    assert {s.device_label for s in sessions} == {"device-a", "device-b"}
