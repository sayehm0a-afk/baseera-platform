import pytest
import logging
from unittest.mock import AsyncMock
from typing import Any, Callable, Dict, Optional
from src.core.runtime.runtime_kernel import RuntimeKernel, IRuntimeKernel
from src.core.runtime.message_bus.message_bus import IMessageBus
from src.core.runtime.task_queue.task_queue import ITaskQueue
from src.core.runtime.worker.worker import IWorker
from src.core.autonomous_intelligence_layer.agent_runtime.agent_runtime import IAgentRuntime
from src.core.service_layer.service_layer import IServiceLayer

logger = logging.getLogger(__name__)


@pytest.fixture
def mock_dependencies(mocker):
    mock_init_db = mocker.patch("src.core.db.database.init_db", new_callable=AsyncMock)
    mocker.patch("src.core.db.database.engine")
    mocker.patch("src.core.db.database.Base")
    mock_message_bus_instance = AsyncMock(spec=IMessageBus)
    mocker.patch("src.core.runtime.message_bus.message_bus.InMemoryMessageBus", return_value=mock_message_bus_instance)

    mock_task_queue_instance = AsyncMock(spec=ITaskQueue)
    mocker.patch("src.core.runtime.task_queue.task_queue.TaskQueue", return_value=mock_task_queue_instance)

    mock_agent_runtime_instance = AsyncMock(spec=IAgentRuntime)
    mocker.patch("src.core.autonomous_intelligence_layer.agent_runtime.agent_runtime.AgentRuntime", return_value=mock_agent_runtime_instance)

    mock_service_layer_instance = AsyncMock(spec=IServiceLayer)
    mocker.patch("src.core.service_layer.service_layer.ServiceLayer", return_value=mock_service_layer_instance)

    mock_worker_instance = AsyncMock(spec=IWorker)
    mocker.patch("src.core.runtime.worker.worker.Worker", return_value=mock_worker_instance)

    return mock_init_db, mock_message_bus_instance, mock_task_queue_instance, mock_agent_runtime_instance, mock_service_layer_instance, mock_worker_instance


@pytest.fixture
def runtime_kernel(mock_dependencies) -> RuntimeKernel:
    """Fixture لتوفير مثيل RuntimeKernel."""
    mock_init_db, mock_message_bus_instance, mock_task_queue_instance, mock_agent_runtime_instance, mock_service_layer_instance, mock_worker_instance = mock_dependencies
    return RuntimeKernel(
        message_bus=mock_message_bus_instance,
        task_queue=mock_task_queue_instance,
        worker=mock_worker_instance,
        agent_runtime=mock_agent_runtime_instance,
        service_layer=mock_service_layer_instance,
    )


@pytest.mark.asyncio
async def test_runtime_kernel_initial_state(runtime_kernel: RuntimeKernel):
    """اختبار الحالة الأولية لـ RuntimeKernel."""
    status = await runtime_kernel.get_status()
    assert status["initialized"] is False
    assert status["running"] is False
    assert status["config"] == {}


@pytest.mark.asyncio
async def test_runtime_kernel_initialize(runtime_kernel: RuntimeKernel, mock_dependencies):
    """اختبار تهيئة RuntimeKernel."""
    config = {"log_level": "DEBUG"}
    await runtime_kernel.initialize(config=config)
    status = await runtime_kernel.get_status()
    assert status["initialized"] is True
    assert status["running"] is False
    assert status["config"] == config
    mock_init_db, mock_message_bus_instance, mock_task_queue_instance, mock_agent_runtime_instance, mock_service_layer_instance, mock_worker_instance = mock_dependencies

    # لم تعد هذه التبعيات تُنشأ داخل initialize، بل تُمرر إلى المُنشئ
    mock_message_bus_instance.assert_not_called()
    mock_agent_runtime_instance.assert_not_called()


@pytest.mark.asyncio
async def test_runtime_kernel_initialize_already_initialized(runtime_kernel: RuntimeKernel, caplog):
    """اختبار تهيئة RuntimeKernel عندما يكون مهيأ بالفعل."""
    await runtime_kernel.initialize()
    with caplog.at_level(logging.WARNING):
        await runtime_kernel.initialize()
        assert "RuntimeKernel already initialized." in caplog.text
    status = await runtime_kernel.get_status()
    assert status["initialized"] is True


@pytest.mark.asyncio
async def test_runtime_kernel_start_without_initialize(runtime_kernel: RuntimeKernel, caplog):
    """اختبار بدء RuntimeKernel بدون تهيئة."""
    with pytest.raises(RuntimeError, match="RuntimeKernel must be initialized before starting."):
        with caplog.at_level(logging.ERROR):
            await runtime_kernel.start()
            assert "RuntimeKernel not initialized. Cannot start." in caplog.text


@pytest.mark.asyncio
async def test_runtime_kernel_start(runtime_kernel: RuntimeKernel, mock_dependencies):
    """اختبار بدء RuntimeKernel بعد التهيئة."""
    await runtime_kernel.initialize()
    await runtime_kernel.start()
    status = await runtime_kernel.get_status()
    assert status["initialized"] is True
    assert status["running"] is True
    mock_init_db, mock_message_bus_instance, mock_task_queue_instance, mock_agent_runtime_instance, mock_service_layer_instance, mock_worker_instance = mock_dependencies
    mock_task_queue_instance.start.assert_called_once()
    # العامل يتم تهيئته وبدء تشغيله داخل start() الآن
    mock_worker_instance.start.assert_called_once()


@pytest.mark.asyncio
async def test_runtime_kernel_start_already_running(runtime_kernel: RuntimeKernel, caplog):
    """اختبار بدء RuntimeKernel عندما يكون قيد التشغيل بالفعل."""
    await runtime_kernel.initialize()
    await runtime_kernel.start()
    with caplog.at_level(logging.WARNING):
        await runtime_kernel.start()
        assert "RuntimeKernel already running." in caplog.text
    status = await runtime_kernel.get_status()
    assert status["running"] is True


@pytest.mark.asyncio
async def test_runtime_kernel_stop(runtime_kernel: RuntimeKernel, mock_dependencies):
    """اختبار إيقاف RuntimeKernel."""
    await runtime_kernel.initialize()
    await runtime_kernel.start()
    await runtime_kernel.stop()
    status = await runtime_kernel.get_status()
    assert status["initialized"] is True
    assert status["running"] is False
    mock_init_db, mock_message_bus_instance, mock_task_queue_instance, mock_agent_runtime_instance, mock_service_layer_instance, mock_worker_instance = mock_dependencies
    mock_task_queue_instance.stop.assert_called_once()
    mock_worker_instance.stop.assert_called_once()


@pytest.mark.asyncio
async def test_runtime_kernel_stop_not_running(runtime_kernel: RuntimeKernel, caplog):
    """اختبار إيقاف RuntimeKernel عندما لا يكون قيد التشغيل."""
    await runtime_kernel.initialize()
    with caplog.at_level(logging.WARNING):
        await runtime_kernel.stop()
        assert "RuntimeKernel is not running. Nothing to stop." in caplog.text
    status = await runtime_kernel.get_status()
    assert status["running"] is False


@pytest.mark.asyncio
async def test_runtime_kernel_get_status(runtime_kernel: RuntimeKernel):
    """اختبار الحصول على حالة RuntimeKernel."""
    status = await runtime_kernel.get_status()
    assert isinstance(status, dict)
    assert "initialized" in status
    assert "running" in status
    assert "config" in status


@pytest.mark.asyncio
async def test_iruntime_kernel_abstract_methods():
    """اختبار أن IRuntimeKernel يفرض تنفيذ التوابع المجردة."""
    class ConcreteKernel(IRuntimeKernel):
        async def initialize(self, config: Optional[Dict[str, Any]] = None) -> None:
            pass

        async def start(self) -> None:
            pass

        async def stop(self) -> None:
            pass

        async def get_status(self) -> Dict[str, Any]:
            return {}

        async def enqueue_task(
            self,
            task_id: str,
            task_payload: Dict[str, Any],
            handler: Callable,
            delay_seconds: int = 0,
            priority: int = 0,
        ) -> None:
            pass

    kernel = ConcreteKernel()
    assert isinstance(kernel, IRuntimeKernel)

    with pytest.raises(TypeError):
        # لا يمكن إنشاء مثيل من فئة مجردة مباشرة
        IRuntimeKernel()
