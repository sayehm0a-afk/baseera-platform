"""Unit tests for HistoricalOhlcvExecutionLock (PR #108 P0 concurrency
remediation) -- the Redis SET-NX-PX / Lua-check-and-delete lock that
closes the two reproduced defects: the manual admin route's own
in-flight check was a non-atomic plain SELECT, and the recurring
scheduler's historical_ohlcv tick never consulted any shared exclusion
boundary at all. Mirrors tests/unit/market_intelligence/
test_scheduler_leader_lock.py's own isolation and _FakeRedis/
_BrokenRedis conventions so this module's tests never touch the real,
process-wide shared Redis client singleton by accident.

_FakeRedisWithEval additionally implements eval() by directly
interpreting the one Lua script this lock ever sends
(_RELEASE_SCRIPT) -- an ownership-checked get-then-delete -- so the
fake proves the SAME check-and-delete semantics the real script
provides without needing a real Redis server for these particular
tests. test_historical_ohlcv_lock_real_redis.py (this same directory)
separately exercises the real Lua script against a genuine Redis
instance so the script itself, not just this fake's interpretation of
it, is proven correct at least once.
"""

import pytest

import src.market_data.ingestion.historical_ohlcv_lock as lock_module
import src.market_intelligence.scheduler_leader_lock as leader_lock_module
from src.market_data.ingestion.historical_ohlcv_lock import (
    HISTORICAL_OHLCV_EXECUTION_LOCK_KEY,
    HistoricalOhlcvExecutionLock,
)

_REAL_GET_SHARED_REDIS_CLIENT = leader_lock_module._get_shared_redis_client


@pytest.fixture(autouse=True)
def _no_real_shared_redis_by_default(monkeypatch):
    """Same rationale as test_scheduler_leader_lock.py's identical
    fixture -- HistoricalOhlcvExecutionLock reuses the exact same
    process-wide shared-singleton getter, so without this, a test
    environment that happens to have a real Redis reachable (this
    sandbox does) would let lock state leak across tests/processes
    through the real singleton instead of each test's own isolated
    redis_client= override.

    Patches BOTH the defining module's name (leader_lock_module, in
    case anything calls it via that path) AND historical_ohlcv_lock's
    own module-local binding -- `from ... import _get_shared_redis_
    client` binds a second, independent name in THIS module's globals
    at import time, which patching only the origin module does not
    reach (confirmed: without this second patch, a test asserting
    "fails closed with no Redis" silently passed against redis-server's
    real, actually-running local instance instead of the intended
    fake/None)."""
    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", lambda: None)
    monkeypatch.setattr(lock_module, "_get_shared_redis_client", lambda: None)
    yield


class _FakeRedisWithEval:
    """In-memory stand-in covering exactly the operations
    HistoricalOhlcvExecutionLock uses: set-with-nx-and-px, and eval()
    interpreting the one ownership-checked check-and-delete script this
    lock sends."""

    def __init__(self):
        self._kv: dict = {}

    def set(self, key, value, nx=False, px=None):
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    def get(self, key):
        return self._kv.get(key)

    def eval(self, script, numkeys, key, token):
        # Mirrors _RELEASE_SCRIPT's own semantics exactly: only delete
        # if the current value still matches the caller's token.
        if self._kv.get(key) == token:
            del self._kv[key]
            return 1
        return 0

    def expire_now(self, key):
        """Test-only helper simulating the lock's TTL expiring (e.g. a
        crashed holder never called release())."""
        self._kv.pop(key, None)


class _BrokenRedis:
    def set(self, key, value, nx=False, px=None):
        raise ConnectionError("simulated Redis outage")

    def get(self, key):
        raise ConnectionError("simulated Redis outage")

    def eval(self, script, numkeys, key, token):
        raise ConnectionError("simulated Redis outage")


def test_no_redis_available_fails_closed_not_acquired():
    """The mandate's explicit fail-closed requirement: an execution
    that cannot prove exclusivity must never assume it is safe to
    proceed."""
    lock = HistoricalOhlcvExecutionLock()
    assert lock.acquire(ttl_seconds=3600) is False


def test_first_instance_acquires_an_uncontested_lock():
    redis = _FakeRedisWithEval()
    lock = HistoricalOhlcvExecutionLock(redis_client=redis)
    assert lock.acquire(ttl_seconds=3600) is True


def test_second_instance_cannot_acquire_while_first_holds_it():
    """The core P0 property: two near-simultaneous attempts (any
    combination of manual route / scheduler tick / full-discovery) must
    never both succeed."""
    redis = _FakeRedisWithEval()
    first = HistoricalOhlcvExecutionLock(redis_client=redis)
    second = HistoricalOhlcvExecutionLock(redis_client=redis)

    assert first.acquire(ttl_seconds=3600) is True
    assert second.acquire(ttl_seconds=3600) is False


def test_a_new_instance_can_acquire_after_the_previous_holder_expires():
    """Simulates a crashed holder (killed mid-job, never released) --
    the TTL, not an explicit handoff, is what prevents a historical_
    ohlcv attempt from being permanently blocked forever."""
    redis = _FakeRedisWithEval()
    crashed_holder = HistoricalOhlcvExecutionLock(redis_client=redis)
    assert crashed_holder.acquire(ttl_seconds=3600) is True

    redis.expire_now(HISTORICAL_OHLCV_EXECUTION_LOCK_KEY)

    new_holder = HistoricalOhlcvExecutionLock(redis_client=redis)
    assert new_holder.acquire(ttl_seconds=3600) is True


def test_release_deletes_the_lock_when_this_instance_owns_it():
    redis = _FakeRedisWithEval()
    lock = HistoricalOhlcvExecutionLock(redis_client=redis)
    lock.acquire(ttl_seconds=3600)

    lock.release()

    other = HistoricalOhlcvExecutionLock(redis_client=redis)
    assert other.acquire(ttl_seconds=3600) is True


def test_release_is_ownership_safe_does_not_delete_a_different_owners_lock():
    """The exact property the mandate calls out by name
    ("ownership-aware release," "naive SETNX without ownership-
    validated release" explicitly forbidden): a stale/expired holder's
    release() must never delete a DIFFERENT, currently-valid owner's
    lock -- otherwise a slow releaser could accidentally unblock a
    second concurrent execution while a legitimate first execution is
    still genuinely in progress under a fresh token."""
    redis = _FakeRedisWithEval()
    original = HistoricalOhlcvExecutionLock(redis_client=redis)
    original.acquire(ttl_seconds=3600)

    # Original's lock expired/was otherwise cleared, and a new,
    # legitimate holder has since taken over.
    redis.expire_now(HISTORICAL_OHLCV_EXECUTION_LOCK_KEY)
    new_holder = HistoricalOhlcvExecutionLock(redis_client=redis)
    assert new_holder.acquire(ttl_seconds=3600) is True

    original.release()  # must be a no-op -- must NOT delete new_holder's lock

    challenger = HistoricalOhlcvExecutionLock(redis_client=redis)
    assert challenger.acquire(ttl_seconds=3600) is False  # new_holder's lock is still held


def test_release_with_no_redis_available_does_not_raise():
    lock = HistoricalOhlcvExecutionLock()
    lock.release()  # must be a silent no-op


def test_acquire_degrades_to_not_acquired_on_a_redis_error():
    lock = HistoricalOhlcvExecutionLock(redis_client=_BrokenRedis())
    assert lock.acquire(ttl_seconds=3600) is False


def test_release_swallows_a_redis_error():
    lock = HistoricalOhlcvExecutionLock(redis_client=_BrokenRedis())
    lock.release()  # must not raise


def test_two_instances_get_distinct_tokens():
    a = HistoricalOhlcvExecutionLock()
    b = HistoricalOhlcvExecutionLock()
    assert a.token != b.token


def test_acquire_converts_ttl_seconds_to_at_least_one_millisecond():
    """A caller passing a very small or zero ttl_seconds must never
    send Redis a px=0 (which some Redis builds reject or treat as an
    immediate expiry, defeating the lock before any caller could ever
    observe holding it)."""
    captured = {}

    class _CapturingRedis(_FakeRedisWithEval):
        def set(self, key, value, nx=False, px=None):
            captured["px"] = px
            return super().set(key, value, nx=nx, px=px)

    lock = HistoricalOhlcvExecutionLock(redis_client=_CapturingRedis())
    assert lock.acquire(ttl_seconds=0) is True
    assert captured["px"] >= 1


def test_shared_redis_client_construction_failure_degrades_to_none(monkeypatch):
    """Exercises the REAL _get_shared_redis_client (not this file's
    patched stub, and the exact same singleton SchedulerLeaderLock
    already relies on -- deliberately reused, not duplicated) to prove
    a Redis client construction failure results in acquire()=False,
    not a raised exception."""
    monkeypatch.setattr(leader_lock_module, "_get_shared_redis_client", _REAL_GET_SHARED_REDIS_CLIENT)
    monkeypatch.setattr(lock_module, "_get_shared_redis_client", _REAL_GET_SHARED_REDIS_CLIENT)
    leader_lock_module.reset_shared_redis_client()

    class _BrokenRedisModule:
        class Redis:
            @staticmethod
            def from_url(*args, **kwargs):
                raise ConnectionError("simulated construction failure")

    monkeypatch.setattr(leader_lock_module, "redis_lib", _BrokenRedisModule)

    lock = lock_module.HistoricalOhlcvExecutionLock()
    assert lock.acquire(ttl_seconds=3600) is False

    leader_lock_module.reset_shared_redis_client()
