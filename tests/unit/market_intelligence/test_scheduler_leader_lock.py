"""Unit tests for SchedulerLeaderLock -- the Redis SETNX-with-TTL
leader lease added to close the 2026-08-13 SAHMK quota-exhaustion
incident's second root cause (all 4 Gunicorn workers running the
market-scan loop concurrently and redundantly). Mirrors
tests/unit/market_data/sahmk/test_rate_limiter.py's own isolation and
_FakeRedis patterns so this module's tests never touch a real,
process-wide shared Redis client.
"""

import pytest

import src.market_intelligence.scheduler_leader_lock as leader_lock_module
from src.market_intelligence.scheduler_leader_lock import SchedulerLeaderLock

# Captured before the autouse fixture below patches the module
# attribute of the same name -- mirrors test_rate_limiter.py's own
# _REAL_GET_SHARED_REDIS_CLIENT capture, for the one test that needs
# the real construction-failure-handling code path.
_REAL_GET_SHARED_REDIS_CLIENT = leader_lock_module._get_shared_redis_client


@pytest.fixture(autouse=True)
def _no_real_shared_redis_by_default(monkeypatch):
    """Every test in this file must be isolated from any real Redis --
    a test environment that actually provisions Redis (CI does; this
    repo's local dev sandbox does not) would otherwise let leadership
    state leak across tests through the process-wide shared singleton
    (the same one production uses). Tests that need real cross-
    instance sharing behavior pass their own _FakeRedis via
    redis_client= (SchedulerLeaderLock._redis() prefers that override
    over this patched singleton), so they are unaffected."""
    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)
    yield


class _FakeRedis:
    """In-memory stand-in for redis.Redis, covering exactly the
    operations SchedulerLeaderLock uses (get/set-with-nx-and-px,
    pexpire, delete) -- enough to prove real cross-instance leadership
    handoff (two SchedulerLeaderLock objects given the *same*
    _FakeRedis instance) without a real Redis server."""

    def __init__(self):
        self._kv: dict = {}

    def get(self, key):
        return self._kv.get(key)

    def set(self, key, value, nx=False, px=None):
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    def pexpire(self, key, ttl_ms):
        return key in self._kv

    def delete(self, key):
        self._kv.pop(key, None)

    def expire_now(self, key):
        """Test-only helper simulating a lease TTL expiring (e.g. the
        previous leader's process crashed without releasing) -- no
        real Redis client offers this; it stands in for the passage of
        time a real PX expiry would cause."""
        self._kv.pop(key, None)


class _BrokenRedis:
    """Every operation raises, standing in for a Redis connection that
    is reachable at client-construction time but fails on each real
    call (a network blip mid-request) -- must degrade to "not leader,"
    never raise out of try_acquire_or_renew/release."""

    def get(self, key):
        raise ConnectionError("simulated Redis outage")

    def set(self, key, value, nx=False, px=None):
        raise ConnectionError("simulated Redis outage")

    def pexpire(self, key, ttl_ms):
        raise ConnectionError("simulated Redis outage")

    def delete(self, key):
        raise ConnectionError("simulated Redis outage")


def test_no_redis_available_fails_closed_not_leader():
    """redis_client=None with the shared singleton patched to None
    (this file's default) -- try_acquire_or_renew must return False,
    never assume leadership just because it cannot prove otherwise."""
    lock = SchedulerLeaderLock()
    assert lock.try_acquire_or_renew(lease_seconds=30) is False


def test_first_instance_acquires_an_uncontested_lease():
    redis = _FakeRedis()
    lock = SchedulerLeaderLock(redis_client=redis)
    assert lock.try_acquire_or_renew(lease_seconds=30) is True


def test_second_instance_cannot_acquire_while_first_holds_the_lease():
    redis = _FakeRedis()
    leader = SchedulerLeaderLock(redis_client=redis)
    challenger = SchedulerLeaderLock(redis_client=redis)

    assert leader.try_acquire_or_renew(lease_seconds=30) is True
    assert challenger.try_acquire_or_renew(lease_seconds=30) is False


def test_current_holder_renews_instead_of_losing_the_lease():
    redis = _FakeRedis()
    leader = SchedulerLeaderLock(redis_client=redis)

    assert leader.try_acquire_or_renew(lease_seconds=30) is True
    # Second tick, same process, same token -- must renew (True), not
    # attempt a fresh SETNX (which would harmlessly no-op anyway, but
    # renewal is the intended code path).
    assert leader.try_acquire_or_renew(lease_seconds=30) is True


def test_a_new_instance_can_acquire_after_the_previous_leader_expires():
    """Simulates the previous leader's process crashing without
    calling release() -- the lease's own TTL is what prevents
    permanent lock-out, not an explicit handoff."""
    redis = _FakeRedis()
    crashed_leader = SchedulerLeaderLock(redis_client=redis)
    assert crashed_leader.try_acquire_or_renew(lease_seconds=30) is True

    redis.expire_now("basirah:scheduler:market_intelligence:leader")

    new_leader = SchedulerLeaderLock(redis_client=redis)
    assert new_leader.try_acquire_or_renew(lease_seconds=30) is True


def test_release_deletes_the_lease_when_this_instance_owns_it():
    redis = _FakeRedis()
    lock = SchedulerLeaderLock(redis_client=redis)
    lock.try_acquire_or_renew(lease_seconds=30)

    lock.release()

    other = SchedulerLeaderLock(redis_client=redis)
    assert other.try_acquire_or_renew(lease_seconds=30) is True


def test_release_is_a_noop_when_this_instance_does_not_own_the_lease():
    """A worker that lost its lease (e.g. a long GC pause let the TTL
    expire and someone else took over) must not delete the new
    leader's lease out from under it."""
    redis = _FakeRedis()
    original = SchedulerLeaderLock(redis_client=redis)
    original.try_acquire_or_renew(lease_seconds=30)

    redis.expire_now("basirah:scheduler:market_intelligence:leader")
    new_leader = SchedulerLeaderLock(redis_client=redis)
    new_leader.try_acquire_or_renew(lease_seconds=30)

    original.release()  # must not delete new_leader's lease

    yet_another = SchedulerLeaderLock(redis_client=redis)
    assert yet_another.try_acquire_or_renew(lease_seconds=30) is False


def test_release_with_no_redis_available_does_not_raise():
    lock = SchedulerLeaderLock()
    lock.release()  # must be a silent no-op, not an AttributeError on a None client


def test_acquire_degrades_to_not_leader_on_a_redis_error():
    lock = SchedulerLeaderLock(redis_client=_BrokenRedis())
    assert lock.try_acquire_or_renew(lease_seconds=30) is False


def test_release_swallows_a_redis_error():
    lock = SchedulerLeaderLock(redis_client=_BrokenRedis())
    lock.release()  # must not raise


def test_two_instances_get_distinct_tokens():
    a = SchedulerLeaderLock()
    b = SchedulerLeaderLock()
    assert a.token != b.token


def test_shared_redis_client_construction_failure_degrades_to_none(monkeypatch):
    """Exercises the REAL _get_shared_redis_client (not this file's
    patched stub) to prove a Redis client construction failure is
    caught and results in `None`, not a raised exception -- a worker
    with a broken Redis DSN must fail closed (never scan) rather than
    crash the scheduler's loop."""
    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", _REAL_GET_SHARED_REDIS_CLIENT)
    leader_lock_module.reset_shared_redis_client()

    class _BrokenRedisModule:
        class Redis:
            @staticmethod
            def from_url(*args, **kwargs):
                raise ConnectionError("simulated construction failure")

    monkeypatch.setattr(leader_lock_module, "redis_lib", _BrokenRedisModule)

    lock = SchedulerLeaderLock()
    assert lock.try_acquire_or_renew(lease_seconds=30) is False

    leader_lock_module.reset_shared_redis_client()
