"""Integration tests for POST /api/v1/radar/scan-now -- the on-demand
consumer scan mandate (2026-09-11).

This route is a thin wrapper: authentication/subscription gating (the
same `require_active_subscription()` every other consumer radar route
uses), a per-user Redis cooldown (the new usage cap the mandate asked
for), then delegation to the already-tested `run_radar_v2_cycle` /
`run_one_bounded_background_cycle` pipeline (fully covered by
test_radar_v2_route.py). These tests therefore focus on what is new
here -- auth, cooldown claim/reuse/per-user isolation, fail-closed
behavior on a Redis error, and correct response mapping -- with
`run_radar_v2_cycle` itself mocked so they do not re-prove the
underlying scan pipeline's own already-tested behavior.
"""

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

import pytest

import main
from src.api.dependencies import get_current_user
from src.domain.models import Subscription, SubscriptionPlan, SubscriptionStatus, User

_SCAN_NOW_ROUTE = "/api/v1/radar/scan-now"


@pytest.fixture
def customer(db_session) -> User:
    user = User(email="customer@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(user)
    db_session.commit()
    return user


@pytest.fixture
def subscribed_customer(db_session, customer) -> User:
    future = datetime.now(timezone.utc) + timedelta(days=14)
    db_session.add(
        Subscription(
            user_id=customer.id,
            plan=SubscriptionPlan.TRIAL,
            status=SubscriptionStatus.TRIALING,
            trial_ends_at=future,
            current_period_start=datetime.now(timezone.utc),
            current_period_end=future,
        )
    )
    db_session.commit()
    return customer


def _as(user: User) -> None:
    main.app.dependency_overrides[get_current_user] = lambda: user


@dataclass
class _FakeCycleResult:
    stage2_executed: bool
    stage2_stop_reason: Optional[str] = None
    opportunities_emitted: List[object] = field(default_factory=list)


class _FakeRedis:
    """In-memory stand-in for redis.Redis, covering exactly the
    operations the scan-now route uses (set-with-nx-and-ex, ttl) --
    same convention as test_scheduler_leader_lock.py's own _FakeRedis."""

    def __init__(self):
        self._kv: dict = {}

    def set(self, key, value, nx=False, ex=None):
        if nx and key in self._kv:
            return None
        self._kv[key] = value
        return True

    def ttl(self, key):
        return 900 if key in self._kv else -2


class _BrokenRedis:
    def set(self, key, value, nx=False, ex=None):
        raise ConnectionError("simulated Redis outage")

    def ttl(self, key):
        raise ConnectionError("simulated Redis outage")


@pytest.fixture
def fake_redis(monkeypatch):
    redis_double = _FakeRedis()
    monkeypatch.setattr("src.api.routes.radar.get_redis_client", lambda: redis_double)
    return redis_double


@pytest.fixture
def broken_redis(monkeypatch):
    monkeypatch.setattr("src.api.routes.radar.get_redis_client", lambda: _BrokenRedis())


@pytest.fixture
def mocked_cycle(monkeypatch):
    """Patches run_radar_v2_cycle to a controllable async fake --
    returns a mutable holder so a test can set the result it wants."""
    holder = {"result": _FakeCycleResult(stage2_executed=True, opportunities_emitted=[object(), object()])}
    calls = []

    async def _fake_run_radar_v2_cycle(session, stage2_runner):
        calls.append(stage2_runner)
        return holder["result"]

    monkeypatch.setattr("src.api.routes.radar.run_radar_v2_cycle", _fake_run_radar_v2_cycle)
    return holder, calls


# --- authorization ----------------------------------------------------


def test_anonymous_caller_is_rejected(client):
    response = client.post(_SCAN_NOW_ROUTE)
    assert response.status_code == 401


def test_authenticated_caller_with_no_subscription_is_rejected(client, customer, fake_redis):
    _as(customer)
    response = client.post(_SCAN_NOW_ROUTE)
    assert response.status_code == 402


# --- cooldown -----------------------------------------------------------


def test_first_call_claims_the_cooldown_and_runs_the_cycle(
    client, subscribed_customer, fake_redis, mocked_cycle
):
    _as(subscribed_customer)
    response = client.post(_SCAN_NOW_ROUTE)
    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is True
    assert body["stop_reason"] is None
    assert body["opportunities_emitted_count"] == 2

    holder, calls = mocked_cycle
    assert len(calls) == 1  # the cycle actually ran


def test_second_call_within_the_cooldown_is_refused_without_running_the_cycle(
    client, subscribed_customer, fake_redis, mocked_cycle
):
    _as(subscribed_customer)
    first = client.post(_SCAN_NOW_ROUTE)
    assert first.status_code == 200

    second = client.post(_SCAN_NOW_ROUTE)
    assert second.status_code == 200
    body = second.json()
    assert body["executed"] is False
    assert body["stop_reason"] == "cooldown_active"
    assert body["retry_after_seconds"] == 900

    holder, calls = mocked_cycle
    assert len(calls) == 1  # the second call never reached the cycle at all


def test_cooldown_is_charged_even_when_the_cycle_declines_to_run(
    client, subscribed_customer, fake_redis, mocked_cycle
):
    """A claimed slot is spent regardless of whether the underlying
    cycle actually executes (e.g. background_quota_low/scan_in_progress)
    -- those attempts still cost a real leader-lock CAS and DB/Redis
    health probes, so this route's own docstring is explicit that the
    cooldown protects against that load too, not only against a
    successful run."""
    holder, _calls = mocked_cycle
    holder["result"] = _FakeCycleResult(stage2_executed=False, stage2_stop_reason="background_quota_low")

    _as(subscribed_customer)
    first = client.post(_SCAN_NOW_ROUTE)
    assert first.status_code == 200
    assert first.json()["executed"] is False
    assert first.json()["stop_reason"] == "background_quota_low"

    second = client.post(_SCAN_NOW_ROUTE)
    assert second.json()["stop_reason"] == "cooldown_active"


def test_cooldown_is_isolated_per_user(client, db_session, subscribed_customer, fake_redis, mocked_cycle):
    other = User(email="other@example.com", password_hash="hashed", is_email_verified=True)
    db_session.add(other)
    db_session.commit()
    db_session.add(
        Subscription(
            user_id=other.id, plan=SubscriptionPlan.TRIAL, status=SubscriptionStatus.TRIALING,
            trial_ends_at=datetime.now(timezone.utc) + timedelta(days=14),
            current_period_start=datetime.now(timezone.utc),
            current_period_end=datetime.now(timezone.utc) + timedelta(days=14),
        )
    )
    db_session.commit()

    _as(subscribed_customer)
    first = client.post(_SCAN_NOW_ROUTE)
    assert first.json()["executed"] is True

    _as(other)
    second = client.post(_SCAN_NOW_ROUTE)
    assert second.json()["executed"] is True  # a different user's own first call, not blocked by the first user's cooldown

    holder, calls = mocked_cycle
    assert len(calls) == 2


def test_redis_failure_fails_closed_without_running_the_cycle(
    client, subscribed_customer, broken_redis, mocked_cycle
):
    _as(subscribed_customer)
    response = client.post(_SCAN_NOW_ROUTE)
    assert response.status_code == 200
    body = response.json()
    assert body["executed"] is False
    assert body["stop_reason"] == "redis_unavailable"

    holder, calls = mocked_cycle
    assert len(calls) == 0  # never reached the cycle at all
