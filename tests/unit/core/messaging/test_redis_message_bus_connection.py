"""RedisMessageBus must build its connection from settings.redis_dsn
(prefers REDIS_URL, the variable a managed Redis provider like Railway
actually injects) by default, not independently read REDIS_HOST/
REDIS_PORT and default to localhost -- the bug that made this bus fail
to connect in production. Explicit host/port/password still take
priority when given (existing test/caller convention).
"""

from unittest.mock import MagicMock, patch

from src.core.config.settings import Settings
from src.core.messaging import redis_message_bus as bus_module
from src.core.messaging.redis_message_bus import RedisMessageBus


def _fake_redis_client():
    client = MagicMock()
    client.ping.return_value = True
    client.connection_pool = MagicMock()
    return client


def test_no_explicit_args_uses_settings_redis_dsn(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://:secretpass@redis.railway.internal:6380/0")
    monkeypatch.setattr(bus_module, "settings", Settings(_env_file=None))

    with patch.object(bus_module.Redis, "from_url", return_value=_fake_redis_client()) as mock_from_url:
        RedisMessageBus()

    mock_from_url.assert_called_once()
    dsn = mock_from_url.call_args[0][0]
    assert dsn == "redis://:secretpass@redis.railway.internal:6380/0"


def test_no_explicit_args_and_no_redis_url_falls_back_to_localhost(monkeypatch):
    """Regression guard: when nothing at all is configured, the
    documented default (Settings.redis_dsn with no REDIS_URL) is still
    localhost:6379 -- the fix must not change that fallback, only stop
    bypassing REDIS_URL when it IS set."""
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("REDIS_PORT", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setattr(bus_module, "settings", Settings(_env_file=None))

    with patch.object(bus_module.Redis, "from_url", return_value=_fake_redis_client()) as mock_from_url:
        RedisMessageBus()

    dsn = mock_from_url.call_args[0][0]
    assert dsn == "redis://localhost:6379/0"


def test_explicit_host_port_still_overrides_settings(monkeypatch):
    """A caller (e.g. a test) that explicitly passes host/port must
    still be honored, even when settings.redis_dsn would resolve to
    something else."""
    monkeypatch.setenv("REDIS_URL", "redis://redis.railway.internal:6380/0")
    monkeypatch.setattr(bus_module, "settings", Settings(_env_file=None))

    with patch.object(bus_module.Redis, "from_url", return_value=_fake_redis_client()) as mock_from_url:
        RedisMessageBus(host="localhost", port=6379)

    dsn = mock_from_url.call_args[0][0]
    assert dsn == "redis://localhost:6379/0"
