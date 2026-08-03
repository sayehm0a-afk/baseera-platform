"""setup_production_dependencies() used to construct RedisMessageBus/
RealTaskQueue with host/port/password explicitly derived from
REDIS_HOST/REDIS_PORT/REDIS_PASSWORD (defaulting to localhost), which
silently overrode those classes' own settings.redis_dsn-based default
and ignored REDIS_URL entirely. This regression-guards that the
registered factories no longer pass those explicit kwargs at all.
"""

from unittest.mock import MagicMock, patch

from src.core.runtime import dependency_injection


def test_message_bus_and_task_queue_factories_pass_no_explicit_redis_args(monkeypatch):
    monkeypatch.setenv("REDIS_HOST", "should-never-be-read-directly-here")
    monkeypatch.setenv("REDIS_PORT", "9999")

    dependency_injection._container = dependency_injection.DependencyContainer()  # fresh singleton for this test

    with patch("src.core.messaging.redis_message_bus.RedisMessageBus") as mock_bus_cls, \
            patch("src.core.runtime.task_queue.real_task_queue.RealTaskQueue") as mock_queue_cls, \
            patch("src.core.db.database.get_engine", return_value=MagicMock()), \
            patch("src.core.db.database.get_session_factory", return_value=MagicMock()), \
            patch("src.core.db.database.get_session", return_value=MagicMock()), \
            patch("src.core.runtime.real_agent_runtime.RealAgentRuntime", return_value=MagicMock()), \
            patch("src.core.runtime.real_service_layer.RealServiceLayer", return_value=MagicMock()):
        container = dependency_injection.setup_production_dependencies()
        container.get_service("message_bus")
        container.get_service("task_queue")

    mock_bus_cls.assert_called_once_with()
    mock_queue_cls.assert_called_once_with()
