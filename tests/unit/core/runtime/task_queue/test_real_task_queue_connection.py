"""Same fix and reasoning as
tests/unit/core/messaging/test_redis_message_bus_connection.py:
RealTaskQueue must build its connection from settings.redis_dsn by
default, not independently read REDIS_HOST/REDIS_PORT and default to
localhost.
"""

from unittest.mock import MagicMock, patch

from src.core.config.settings import Settings
from src.core.runtime.task_queue import real_task_queue as queue_module
from src.core.runtime.task_queue.real_task_queue import RealTaskQueue


def _fake_redis_client():
    client = MagicMock()
    client.ping.return_value = True
    return client


def test_no_explicit_args_uses_settings_redis_dsn(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://:secretpass@redis.railway.internal:6380/0")
    monkeypatch.setattr(queue_module, "settings", Settings(_env_file=None))

    with patch.object(queue_module.redis.Redis, "from_url", return_value=_fake_redis_client()) as mock_from_url:
        RealTaskQueue()

    mock_from_url.assert_called_once()
    dsn = mock_from_url.call_args[0][0]
    assert dsn == "redis://:secretpass@redis.railway.internal:6380/0"


def test_no_explicit_args_and_no_redis_url_falls_back_to_localhost(monkeypatch):
    monkeypatch.delenv("REDIS_URL", raising=False)
    monkeypatch.delenv("REDIS_HOST", raising=False)
    monkeypatch.delenv("REDIS_PORT", raising=False)
    monkeypatch.delenv("REDIS_PASSWORD", raising=False)
    monkeypatch.setattr(queue_module, "settings", Settings(_env_file=None))

    with patch.object(queue_module.redis.Redis, "from_url", return_value=_fake_redis_client()) as mock_from_url:
        RealTaskQueue()

    dsn = mock_from_url.call_args[0][0]
    assert dsn == "redis://localhost:6379/0"


def test_explicit_host_port_still_overrides_settings(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://redis.railway.internal:6380/0")
    monkeypatch.setattr(queue_module, "settings", Settings(_env_file=None))

    with patch.object(queue_module.redis.Redis, "from_url", return_value=_fake_redis_client()) as mock_from_url:
        RealTaskQueue(host="localhost", port=6379)

    dsn = mock_from_url.call_args[0][0]
    assert dsn == "redis://localhost:6379/0"
