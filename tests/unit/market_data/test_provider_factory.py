"""Unit tests for src.market_data.provider_factory -- the network-aware
auto-selection logic. SahmkMarketDataProvider is replaced with a fake so
no network call is ever made; these tests only exercise the selection
policy (env var overrides, connectivity/auth outcomes, caching)."""

import asyncio

import pytest

from src.market_data import provider_factory
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkRequestError


class _FakeSahmkProvider:
    """Stands in for SahmkMarketDataProvider in provider_factory tests."""

    instances = []

    def __init__(self, *args, **kwargs):
        self.disconnected = False
        _FakeSahmkProvider.instances.append(self)

    async def authenticate(self):
        raise NotImplementedError  # each test overrides this on the instance

    async def check_connectivity(self):
        raise NotImplementedError  # each test overrides this on the instance

    async def disconnect(self):
        self.disconnected = True


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_factory.reset_provider_cache()
    _FakeSahmkProvider.instances.clear()
    monkeypatch.setattr(provider_factory, "SahmkMarketDataProvider", _FakeSahmkProvider)
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.1")
    # 1 attempt, no retry: these tests exercise the *fallback* behavior
    # on an unreachable/timed-out probe, not the retry mechanics
    # themselves -- see test_provider_connectivity_retry.py for those.
    monkeypatch.setenv("SAHMK_PROBE_MAX_ATTEMPTS", "1")
    monkeypatch.setenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60")
    # Near-instant so tests can observe a genuine-kind-change disconnect
    # without a real 90s wait -- see the grace-delay tests below.
    monkeypatch.setenv("MARKET_DATA_PROVIDER_DISCONNECT_GRACE_SECONDS", "0")
    yield
    provider_factory.reset_provider_cache()


@pytest.mark.asyncio
async def test_forced_dev_returns_dev_provider_even_with_credentials(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert provider_factory.get_last_selected_provider_kind() == "dev"
    assert _FakeSahmkProvider.instances == []


@pytest.mark.asyncio
async def test_auto_without_credentials_returns_dev_provider():
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert provider_factory.get_last_selected_provider_kind() == "dev"


@pytest.mark.asyncio
async def test_forced_sahmk_without_credentials_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)


@pytest.mark.asyncio
async def test_auto_with_credentials_and_reachable_sahmk_returns_sahmk_provider(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, _FakeSahmkProvider)
    assert provider_factory.get_last_selected_provider_kind() == "sahmk"


@pytest.mark.asyncio
async def test_auto_with_credentials_but_rejected_key_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_bad")

    async def _rejected():
        return False

    _FakeSahmkProvider.check_connectivity = lambda self: _rejected()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert _FakeSahmkProvider.instances[0].disconnected is True


@pytest.mark.asyncio
async def test_auto_with_credentials_but_unreachable_host_falls_back_to_dev(monkeypatch):
    """This is the exact scenario the network-restricted sandbox produces:
    a configured key, but the host cannot be reached."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _network_error():
        raise SahmkRequestError("Network error calling SAHMK API: connection refused")

    _FakeSahmkProvider.check_connectivity = lambda self: _network_error()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)
    assert provider_factory.get_last_selected_provider_kind() == "dev"


@pytest.mark.asyncio
async def test_auto_with_credentials_probe_timeout_falls_back_to_dev(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _hangs():
        await asyncio.sleep(10)
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _hangs()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)


@pytest.mark.asyncio
async def test_selection_is_cached_across_calls(monkeypatch):
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()

    await provider_factory.get_market_data_provider()
    await provider_factory.get_market_data_provider()
    assert len(_FakeSahmkProvider.instances) == 1  # second call served from cache


@pytest.mark.asyncio
async def test_force_refresh_bypasses_cache(monkeypatch):
    """force_refresh must skip the cached-selection short-circuit and
    genuinely re-verify reachability -- but, per the concurrency fix
    below, that re-verification reuses the existing healthy instance
    rather than always constructing a new one. Observed here via a real
    check_connectivity() call count, not instance count."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    call_count = 0

    async def _ok(_self):
        nonlocal call_count
        call_count += 1
        return True

    _FakeSahmkProvider.check_connectivity = _ok

    await provider_factory.get_market_data_provider()
    await provider_factory.get_market_data_provider(force_refresh=True)
    assert call_count == 2  # both calls genuinely re-probed, unlike a cache hit
    assert len(_FakeSahmkProvider.instances) == 1  # reused, not recreated


@pytest.mark.asyncio
async def test_get_last_selected_provider_kind_none_before_any_selection():
    assert provider_factory.get_last_selected_provider_kind() is None


# --- regression: aiohttp ClientSession concurrency bug (superseded
# providers being closed out from under a still-in-flight caller) ---
#
# Production evidence (two independent audit runs) traced a recurring
# `AssertionError: assert self._connector is not None` inside aiohttp,
# surfaced as "Circuit breaker operation failed in CLOSED state", to
# get_market_data_provider() closing the outgoing provider's session
# synchronously on every cache refresh -- even when SAHMK stayed
# healthy across the refresh. The SAHMK rate limiter routinely stalls
# the ingestion scheduler's per-symbol loop for up to ~60s between
# requests, easily outliving the default 60s cache window, so a loop
# that fetched the provider moments before a refresh would have its
# live session pulled out from under it mid-iteration. These tests
# lock in the fix: reuse across refreshes when the kind is unchanged,
# and a grace-delayed (not synchronous) disconnect when it does change.


@pytest.mark.asyncio
async def test_force_refresh_reuses_the_same_instance_when_sahmk_stays_healthy(monkeypatch):
    """The core fix: a refresh must not construct a new provider (and
    therefore must not disconnect the old one's live session) when
    SAHMK is still reachable -- the steady-state case a long-running
    caller's loop needs to stay safe across."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()

    first = await provider_factory.get_market_data_provider()
    second = await provider_factory.get_market_data_provider(force_refresh=True)

    assert first is second
    assert len(_FakeSahmkProvider.instances) == 1
    assert first.disconnected is False


@pytest.mark.asyncio
async def test_repeated_healthy_refreshes_never_create_a_new_instance_or_disconnect(monkeypatch):
    """Extends the single-refresh case to several refreshes in a row --
    as long as SAHMK stays healthy, the exact same instance must be
    reused every time, never disconnected."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()

    for _ in range(5):
        await provider_factory.get_market_data_provider(force_refresh=True)

    assert len(_FakeSahmkProvider.instances) == 1
    assert _FakeSahmkProvider.instances[0].disconnected is False


@pytest.mark.asyncio
async def test_kind_change_still_eventually_disconnects_the_superseded_provider(monkeypatch):
    """When SAHMK genuinely becomes unreachable mid-run (a real kind
    change, sahmk -> dev), the superseded provider must still end up
    disconnected -- just not synchronously inside the swap, so a
    straggling concurrent caller isn't cut off mid-request. The grace
    delay is patched to ~0 in the _reset fixture so the background task
    resolves within this test without a real wait."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()
    sahmk_provider = await provider_factory.get_market_data_provider()
    assert sahmk_provider.disconnected is False

    async def _now_unreachable():
        raise SahmkRequestError("Network error calling SAHMK API: connection refused")

    _FakeSahmkProvider.check_connectivity = lambda self: _now_unreachable()
    dev_provider = await provider_factory.get_market_data_provider(force_refresh=True)

    assert isinstance(dev_provider, DevMarketDataProvider)
    # Not disconnected synchronously as part of the swap itself --
    # this is the exact behavior that used to race a concurrent caller.
    assert sahmk_provider.disconnected is False

    # But it does still happen, once the (near-zero) grace delay elapses.
    await asyncio.sleep(0.05)
    assert sahmk_provider.disconnected is True


@pytest.mark.asyncio
async def test_a_provider_still_mid_request_survives_a_concurrent_kind_change(monkeypatch):
    """End-to-end reproduction of the original bug scenario: a caller
    holds the sahmk provider and is mid-"request" (simulated by an
    event it controls) when a concurrent refresh discovers SAHMK is now
    unreachable and swaps to dev. Before the fix, disconnect() ran
    synchronously and the held provider's session was already torn
    down; after the fix, the held provider must remain usable
    (disconnected is False) for the duration of the in-flight call."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()
    held_provider = await provider_factory.get_market_data_provider()

    request_started = asyncio.Event()
    release_request = asyncio.Event()

    async def _simulated_in_flight_request():
        request_started.set()
        await release_request.wait()
        # If disconnect() had already run synchronously against this
        # same instance, a real SahmkClient would raise here trying to
        # use its closed session -- the fake models that as still not
        # being disconnected.
        assert held_provider.disconnected is False

    request_task = asyncio.ensure_future(_simulated_in_flight_request())
    await request_started.wait()

    async def _now_unreachable():
        raise SahmkRequestError("Network error calling SAHMK API: connection refused")

    _FakeSahmkProvider.check_connectivity = lambda self: _now_unreachable()
    await provider_factory.get_market_data_provider(force_refresh=True)

    # The swap has happened, but the held provider must still be alive
    # for the caller that's mid-request against it.
    assert held_provider.disconnected is False

    release_request.set()
    await request_task


@pytest.mark.asyncio
async def test_cache_hit_does_not_disconnect_the_still_current_provider(monkeypatch):
    """A cache *hit* (no reselection) must never disconnect anything --
    only an actual replacement should."""
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()

    provider = await provider_factory.get_market_data_provider()
    same_provider = await provider_factory.get_market_data_provider()

    assert provider is same_provider
    assert provider.disconnected is False


@pytest.mark.asyncio
async def test_switching_from_dev_to_sahmk_does_not_attempt_to_disconnect_dev_incorrectly(
    monkeypatch,
):
    """DevMarketDataProvider.disconnect() is a plain, always-safe no-op
    -- this just confirms transitioning across provider *kinds* (not
    just repeated sahmk selections) goes through the same disconnect
    path without raising."""
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    dev_provider = await provider_factory.get_market_data_provider()

    monkeypatch.setenv("MARKET_DATA_PROVIDER", "sahmk")
    monkeypatch.setenv("SAHMK_API_KEY", "shmk_live_x")

    async def _ok():
        return True

    _FakeSahmkProvider.check_connectivity = lambda self: _ok()

    sahmk_provider = await provider_factory.get_market_data_provider(force_refresh=True)

    assert isinstance(sahmk_provider, _FakeSahmkProvider)
    # dev_provider.disconnect() runs (without raising) after the grace
    # delay (patched to ~0 in _reset) as part of the dev->sahmk
    # transition; DevMarketDataProvider marks itself unhealthy once
    # disconnected.
    await asyncio.sleep(0.05)
    from src.market_data.providers.market_data_provider import ProviderHealth

    assert await dev_provider.health_check() == ProviderHealth.UNHEALTHY
