"""Real-PostgreSQL concurrency + family-isolation proof for refresh-
token rotation (src.auth.session_service.refresh_session).

An earlier ad hoc probe (PR #120 review) found that Codex's own test
suite for this fix used only in-memory SQLite via a single shared
connection, which cannot exercise real cross-connection row locking --
the exact race this fix (consume_refresh_session's conditional UPDATE)
exists to close. This module is the permanent, CI-runnable replacement
for that ad hoc script: genuine threads, genuine separate PostgreSQL
connections, threading.Barrier to force real interleaving at the
critical section (never a sleep()-based timing guess), following the
same idiom as tests/integration/test_decision_v2_outcome_concurrency.py.

Two properties are proven here:

1. Concurrency safety: N simultaneous refresh_session() calls presenting
   the SAME raw refresh token must produce exactly one winner (a new
   token pair) and N-1 clean rejections -- never a double-issue, never
   an unhandled exception.

2. Family-scoped isolation: the reuse-detection defense in
   refresh_session() (raised when a refresh token that was already
   rotated away is presented again -- whether via a live race or a
   later replay) must revoke *only* the session family the presented
   token belongs to. A second, independent login for the same user
   (a genuinely different device/browser) must remain fully valid and
   unaffected. This closes a gap in the PR's own earlier description,
   which said this defense "logs the user out everywhere" -- imprecise:
   it revokes one login's family, not every family belonging to the
   user.

No live Postgres is available in the standard CI environment for this
project (see tests/integration/test_migrations.py's own docstring for
the same disclosed limitation) -- these tests skip cleanly (not
silently) when no reachable PostgreSQL + Redis pair is configured, and
run in full wherever both are (this development/audit environment
always has them)."""

import threading

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import session_service
from src.auth.exceptions import InvalidOrExpiredTokenError
from src.core.config.settings import settings
from src.domain.models import User, UserSession


def _postgres_reachable() -> bool:
    if not settings.database_url.startswith("postgresql"):
        return False
    try:
        probe = create_engine(settings.database_url, pool_pre_ping=True)
        with probe.connect():
            pass
        probe.dispose()
        return True
    except Exception:  # noqa: BLE001 -- any connection failure means "skip", not "crash the suite"
        return False


def _redis_reachable() -> bool:
    try:
        import redis

        client = redis.Redis(host=settings.redis_host, port=settings.redis_port, socket_connect_timeout=1)
        return bool(client.ping())
    except Exception:  # noqa: BLE001 -- any connection failure means "skip", not "crash the suite"
        return False


pytestmark = pytest.mark.skipif(
    not (_postgres_reachable() and _redis_reachable()),
    reason="Refresh-rotation concurrency and family-isolation guarantees are exercised against real "
    "PostgreSQL row-level locking and real Redis (token_store) -- SQLite's locking semantics and a "
    "mocked Redis cannot meaningfully prove either property. Skipped, not silently assumed passing, "
    "when either is unreachable.",
)


@pytest.fixture
def engine():
    eng = create_engine(settings.database_url)
    yield eng
    eng.dispose()


@pytest.fixture
def Factory(engine):
    return sessionmaker(bind=engine)


@pytest.fixture
def cleanup(Factory):
    emails = []
    yield emails
    if emails:
        s = Factory()
        user_ids = [u.id for u in s.query(User).filter(User.email.in_(emails)).all()]
        if user_ids:
            s.query(UserSession).filter(UserSession.user_id.in_(user_ids)).delete(synchronize_session=False)
            s.query(User).filter(User.id.in_(user_ids)).delete(synchronize_session=False)
            s.commit()
        s.close()


def _make_user(Factory, email: str) -> int:
    s = Factory()
    user = User(email=email, password_hash="x", is_email_verified=True, is_active=True)
    s.add(user)
    s.commit()
    user_id = user.id
    s.close()
    return user_id


def _create_session_for(Factory, user_id: int, device_label: str):
    s = Factory()
    user = s.query(User).filter_by(id=user_id).one()
    pair = session_service.create_session(s, user, device_label=device_label)
    s.close()
    return pair


class TestConcurrentRefreshRotationSafety:
    """Real threads, real separate PostgreSQL connections, genuine
    interleaving via threading.Barrier (no sleep-based timing guesses)."""

    def _race_same_token(self, Factory, raw_refresh: str, worker_count: int) -> dict:
        barrier = threading.Barrier(worker_count)
        results = {}

        def worker(name):
            session = Factory()
            try:
                barrier.wait()
                pair = session_service.refresh_session(session, raw_refresh)
                results[name] = ("SUCCESS", pair.refresh_token)
            except InvalidOrExpiredTokenError as e:
                results[name] = ("REJECTED", str(e))
            except Exception as exc:  # noqa: BLE001 -- captured for the assertion, not swallowed silently
                session.rollback()
                results[name] = ("EXCEPTION", repr(exc))
            finally:
                session.close()

        threads = [threading.Thread(target=worker, args=(f"W{i}",)) for i in range(worker_count)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert all(not t.is_alive() for t in threads), "a worker thread did not finish within 30s"
        return results

    def test_two_way_race_exactly_one_winner_no_double_issue(self, Factory, cleanup):
        email = "race-2way@example.com"
        cleanup.append(email)
        user_id = _make_user(Factory, email)
        pair = _create_session_for(Factory, user_id, "device-A")

        results = self._race_same_token(Factory, pair.refresh_token, worker_count=2)

        exceptions = {k: v for k, v in results.items() if v[0] == "EXCEPTION"}
        assert not exceptions, f"no worker should raise an uncaught exception: {exceptions}"
        successes = [v for v in results.values() if v[0] == "SUCCESS"]
        rejections = [v for v in results.values() if v[0] == "REJECTED"]
        assert len(successes) == 1, f"exactly one request must win the race, got: {results}"
        assert len(rejections) == 1, f"exactly one request must be cleanly rejected, got: {results}"

    def test_five_way_burst_still_exactly_one_winner(self, Factory, cleanup):
        email = "race-5way@example.com"
        cleanup.append(email)
        user_id = _make_user(Factory, email)
        pair = _create_session_for(Factory, user_id, "device-A")

        results = self._race_same_token(Factory, pair.refresh_token, worker_count=5)

        exceptions = {k: v for k, v in results.items() if v[0] == "EXCEPTION"}
        assert not exceptions, f"no worker should raise an uncaught exception: {exceptions}"
        successes = [v for v in results.values() if v[0] == "SUCCESS"]
        rejections = [v for v in results.values() if v[0] == "REJECTED"]
        assert len(successes) == 1, f"exactly one of 5 concurrent requests must win, got: {results}"
        assert len(rejections) == 4, f"the other 4 must be cleanly rejected, got: {results}"

    def test_repeated_race_reduces_chance_of_a_lucky_ordering_masking_a_gap(self, Factory, cleanup):
        """Same race, run 3 times against fresh users, to reduce the
        chance a single lucky thread-scheduling order masks a real gap
        -- the DB-level guarantee must hold regardless of which
        thread's UPDATE happens to reach Postgres first."""
        for attempt in range(3):
            email = f"race-repeat-{attempt}@example.com"
            cleanup.append(email)
            user_id = _make_user(Factory, email)
            pair = _create_session_for(Factory, user_id, "device-A")

            results = self._race_same_token(Factory, pair.refresh_token, worker_count=2)
            successes = [v for v in results.values() if v[0] == "SUCCESS"]
            assert len(successes) == 1, f"attempt {attempt}: got {results}"


class TestFamilyScopedRevocationIsolation:
    """The reuse-detection defense in refresh_session() must revoke
    *only* the presented token's own session family -- never a
    different, genuinely independent login (another device/browser)
    for the same user."""

    def test_concurrent_race_only_revokes_the_raced_family_a_second_independent_login_is_untouched(
        self, Factory, cleanup
    ):
        email = "race-isolation@example.com"
        cleanup.append(email)
        user_id = _make_user(Factory, email)
        pair_a = _create_session_for(Factory, user_id, "device-A")
        pair_b = _create_session_for(Factory, user_id, "device-B")

        barrier = threading.Barrier(2)
        results = {}

        def worker(name):
            session = Factory()
            try:
                barrier.wait()
                new_pair = session_service.refresh_session(session, pair_a.refresh_token)
                results[name] = ("SUCCESS", new_pair.refresh_token)
            except InvalidOrExpiredTokenError as e:
                results[name] = ("REJECTED", str(e))
            finally:
                session.close()

        threads = [threading.Thread(target=worker, args=(f"W{i}",)) for i in range(2)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)
        assert all(not t.is_alive() for t in threads), "a worker thread did not finish within 30s"

        winners = [v[1] for v in results.values() if v[0] == "SUCCESS"]
        assert len(winners) == 1, f"expected exactly one winner in the race: {results}"
        winner_new_token = winners[0]

        # Device B -- a genuinely different login/family -- must remain
        # completely valid: refreshing it must still succeed.
        verify_b = Factory()
        pair_b_refreshed = session_service.refresh_session(verify_b, pair_b.refresh_token)
        verify_b.close()
        assert pair_b_refreshed.refresh_token

        # Device A's family, by contrast, must now be fully gone --
        # including the winner's own brand-new token from the race.
        verify_a = Factory()
        with pytest.raises(InvalidOrExpiredTokenError):
            session_service.refresh_session(verify_a, winner_new_token)
        verify_a.close()

    def test_sequential_reuse_of_an_already_rotated_token_revokes_only_its_own_family(self, Factory, cleanup):
        """The more common real-world shape of this defense: not a
        live race, but a replay of a refresh token strictly AFTER the
        legitimate client already rotated past it (a stolen token used
        out of band, or a stale client retry)."""
        email = "sequential-reuse@example.com"
        cleanup.append(email)
        user_id = _make_user(Factory, email)
        pair_a = _create_session_for(Factory, user_id, "device-A")
        pair_b = _create_session_for(Factory, user_id, "device-B")

        s1 = Factory()
        rotated = session_service.refresh_session(s1, pair_a.refresh_token)
        s1.close()

        s2 = Factory()
        with pytest.raises(InvalidOrExpiredTokenError, match="already been used"):
            session_service.refresh_session(s2, pair_a.refresh_token)
        s2.close()

        # The replay must have revoked device A's entire family --
        # including the token issued by the legitimate rotation that
        # happened just before it.
        s3 = Factory()
        with pytest.raises(InvalidOrExpiredTokenError):
            session_service.refresh_session(s3, rotated.refresh_token)
        s3.close()

        # Device B -- an unrelated login -- must be completely
        # unaffected by device A's reuse-detection event.
        s4 = Factory()
        pair_b_refreshed = session_service.refresh_session(s4, pair_b.refresh_token)
        s4.close()
        assert pair_b_refreshed.refresh_token
