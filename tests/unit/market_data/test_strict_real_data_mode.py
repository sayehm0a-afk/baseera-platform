"""Unit tests for strict real-data mode (STRICT_REAL_DATA/
ALLOW_SYNTHETIC_DATA) -- the production guarantee that Basirah never
silently substitutes synthetic data for real SAHMK data. Reuses the
same fake-provider pattern as test_provider_factory.py so no network
call is ever made.
"""

import asyncio

import pytest

from src.market_data import config as market_data_config
from src.market_data import fundamental_provider_factory, provider_factory
from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider
from src.market_data.sahmk.exceptions import SahmkAuthenticationError, SahmkRateLimitError, SahmkRequestError
from src.market_data.strict_mode import StrictRealDataUnavailableError

_SECRET_MARKER = "shmk_live_do_not_leak_9f8e7d6c"


class _FakeSahmkProvider:
    instances = []

    def __init__(self, *args, **kwargs):
        self.disconnected = False
        _FakeSahmkProvider.instances.append(self)

    async def authenticate(self):
        raise NotImplementedError

    async def disconnect(self):
        self.disconnected = True


class _FakeSahmkFundamentalProvider(_FakeSahmkProvider):
    pass


@pytest.fixture(autouse=True)
def _reset(monkeypatch):
    provider_factory.reset_provider_cache()
    fundamental_provider_factory.reset_fundamental_provider_cache()
    _FakeSahmkProvider.instances.clear()
    monkeypatch.setattr(provider_factory, "SahmkMarketDataProvider", _FakeSahmkProvider)
    monkeypatch.setattr(fundamental_provider_factory, "SahmkFundamentalDataProvider", _FakeSahmkFundamentalProvider)
    monkeypatch.delenv("MARKET_DATA_PROVIDER", raising=False)
    monkeypatch.delenv("SAHMK_API_KEY", raising=False)
    monkeypatch.delenv("STRICT_REAL_DATA", raising=False)
    monkeypatch.delenv("ALLOW_SYNTHETIC_DATA", raising=False)
    monkeypatch.setenv("SAHMK_PROBE_TIMEOUT_SECONDS", "0.1")
    monkeypatch.setenv("MARKET_DATA_PROVIDER_CACHE_SECONDS", "60")
    yield
    provider_factory.reset_provider_cache()
    fundamental_provider_factory.reset_fundamental_provider_cache()


# --- config layer -----------------------------------------------------


def test_strict_mode_off_by_default():
    assert market_data_config.is_strict_real_data_enabled() is False
    assert market_data_config.is_synthetic_data_allowed() is True


def test_strict_real_data_true_enables_strict_mode(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    assert market_data_config.is_strict_real_data_enabled() is True
    assert market_data_config.is_synthetic_data_allowed() is False


def test_allow_synthetic_data_false_disallows_synthetic_without_strict_mode(monkeypatch):
    monkeypatch.setenv("ALLOW_SYNTHETIC_DATA", "false")
    assert market_data_config.is_strict_real_data_enabled() is False
    assert market_data_config.is_synthetic_data_allowed() is False


def test_strict_mode_overrides_an_explicit_allow_synthetic_true(monkeypatch):
    """Strict mode is the absolute switch -- ALLOW_SYNTHETIC_DATA=true
    cannot re-permit synthetic data once STRICT_REAL_DATA=true."""
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("ALLOW_SYNTHETIC_DATA", "true")
    assert market_data_config.is_synthetic_data_allowed() is False


# --- test 1: missing key blocks strict-mode provider selection --------


@pytest.mark.asyncio
async def test_strict_mode_missing_key_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    with pytest.raises(StrictRealDataUnavailableError, match="SAHMK_API_KEY is not configured"):
        await provider_factory.get_market_data_provider()
    assert _FakeSahmkProvider.instances == []


@pytest.mark.asyncio
async def test_strict_mode_missing_key_blocks_fundamental_provider_too(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    with pytest.raises(StrictRealDataUnavailableError, match="SAHMK_API_KEY is not configured"):
        await fundamental_provider_factory.get_fundamental_data_provider()


# --- test 2/3: invalid key / 401 blocks the scan -----------------------


@pytest.mark.asyncio
async def test_strict_mode_rejected_key_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _rejected():
        return False

    _FakeSahmkProvider.authenticate = lambda self: _rejected()

    with pytest.raises(StrictRealDataUnavailableError, match="authentication check did not succeed"):
        await provider_factory.get_market_data_provider()
    assert _FakeSahmkProvider.instances[0].disconnected is True


@pytest.mark.asyncio
async def test_strict_mode_401_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _unauthorized():
        raise SahmkAuthenticationError("401 Unauthorized", status_code=401)

    _FakeSahmkProvider.authenticate = lambda self: _unauthorized()

    with pytest.raises(StrictRealDataUnavailableError):
        await provider_factory.get_market_data_provider()


# --- test 4: timeout blocks the scan -----------------------------------


@pytest.mark.asyncio
async def test_strict_mode_timeout_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _hangs():
        await asyncio.sleep(10)
        return True

    _FakeSahmkProvider.authenticate = lambda self: _hangs()

    with pytest.raises(StrictRealDataUnavailableError, match="timed out"):
        await provider_factory.get_market_data_provider()


# --- test 5: rate limiting does not activate synthetic fallback --------


@pytest.mark.asyncio
async def test_strict_mode_rate_limit_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _rate_limited():
        raise SahmkRateLimitError("429 rate limited", status_code=429)

    _FakeSahmkProvider.authenticate = lambda self: _rate_limited()

    with pytest.raises(StrictRealDataUnavailableError):
        await provider_factory.get_market_data_provider()
    # Never a DevMarketDataProvider anywhere -- the raise happened
    # instead of a fallback, not after one.
    assert provider_factory.get_last_selected_provider_kind() is None


# --- test 6: general SAHMK outage does not activate synthetic fallback -


@pytest.mark.asyncio
async def test_strict_mode_network_error_raises_instead_of_falling_back(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _network_error():
        raise SahmkRequestError("Network error calling SAHMK API: connection refused")

    _FakeSahmkProvider.authenticate = lambda self: _network_error()

    with pytest.raises(StrictRealDataUnavailableError):
        await provider_factory.get_market_data_provider()


@pytest.mark.asyncio
async def test_strict_mode_explicit_dev_override_still_raises(monkeypatch):
    """STRICT_REAL_DATA=true is an absolute switch -- even an explicit
    MARKET_DATA_PROVIDER=dev must not be honored."""
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    with pytest.raises(StrictRealDataUnavailableError, match="explicitly requests synthetic data"):
        await provider_factory.get_market_data_provider()


# --- test 9: real authenticated SAHMK data can pass under strict mode --


@pytest.mark.asyncio
async def test_strict_mode_real_authenticated_data_succeeds(monkeypatch):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)

    async def _ok():
        return True

    _FakeSahmkProvider.authenticate = lambda self: _ok()

    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, _FakeSahmkProvider)
    assert provider_factory.get_last_selected_provider_kind() == "sahmk"


# --- test 10: non-strict development mode is unaffected ----------------


@pytest.mark.asyncio
async def test_non_strict_mode_still_falls_back_to_dev_as_before(monkeypatch):
    """Explicit regression guard: strict mode is opt-in only -- every
    existing dev/CI flow (STRICT_REAL_DATA unset) keeps working exactly
    as before this change."""
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)


@pytest.mark.asyncio
async def test_non_strict_mode_explicit_dev_still_works(monkeypatch):
    monkeypatch.setenv("MARKET_DATA_PROVIDER", "dev")
    provider = await provider_factory.get_market_data_provider()
    assert isinstance(provider, DevMarketDataProvider)


@pytest.mark.asyncio
async def test_non_strict_mode_fundamental_provider_falls_back_to_dev(monkeypatch):
    provider = await fundamental_provider_factory.get_fundamental_data_provider()
    assert isinstance(provider, DevFundamentalDataProvider)


# --- test 11: no secret value ever appears in the raised error ---------


async def _authenticate_raising_401(self):
    raise SahmkAuthenticationError("401 Unauthorized", status_code=401)


async def _authenticate_raising_rate_limit(self):
    raise SahmkRateLimitError("429 rate limited", status_code=429)


async def _authenticate_raising_network_error(self):
    raise SahmkRequestError("network error")


async def _authenticate_returning_false(self):
    return False


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "authenticate_impl",
    [
        _authenticate_raising_401,
        _authenticate_raising_rate_limit,
        _authenticate_raising_network_error,
        _authenticate_returning_false,
    ],
)
async def test_strict_mode_error_never_contains_the_api_key(monkeypatch, authenticate_impl):
    monkeypatch.setenv("STRICT_REAL_DATA", "true")
    monkeypatch.setenv("SAHMK_API_KEY", _SECRET_MARKER)
    _FakeSahmkProvider.authenticate = authenticate_impl

    with pytest.raises(StrictRealDataUnavailableError) as excinfo:
        await provider_factory.get_market_data_provider()
    assert _SECRET_MARKER not in str(excinfo.value)
    assert _SECRET_MARKER not in excinfo.value.reason
