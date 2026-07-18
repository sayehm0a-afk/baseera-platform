import pytest
import logging
from unittest.mock import AsyncMock
from typing import Any, Dict, Optional
from core.runtime.runtime_kernel import RuntimeKernel, IRuntimeKernel

logger = logging.getLogger(__name__)

@pytest.fixture
def runtime_kernel() -> RuntimeKernel:
    """Fixture لتوفير مثيل RuntimeKernel."""
    return RuntimeKernel()

@pytest.mark.asyncio
async def test_runtime_kernel_initial_state(runtime_kernel: RuntimeKernel):
    """اختبار الحالة الأولية لـ RuntimeKernel."""
    status = await runtime_kernel.get_status()
    assert status["initialized"] is False
    assert status["running"] is False
    assert status["config"] == {}

@pytest.mark.asyncio
async def test_runtime_kernel_initialize(runtime_kernel: RuntimeKernel):
    """اختبار تهيئة RuntimeKernel."""
    config = {"log_level": "DEBUG"}
    await runtime_kernel.initialize(config=config)
    status = await runtime_kernel.get_status()
    assert status["initialized"] is True
    assert status["running"] is False
    assert status["config"] == config

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
async def test_runtime_kernel_start(runtime_kernel: RuntimeKernel):
    """اختبار بدء RuntimeKernel بعد التهيئة."""
    await runtime_kernel.initialize()
    await runtime_kernel.start()
    status = await runtime_kernel.get_status()
    assert status["initialized"] is True
    assert status["running"] is True

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
async def test_runtime_kernel_stop(runtime_kernel: RuntimeKernel):
    """اختبار إيقاف RuntimeKernel."""
    await runtime_kernel.initialize()
    await runtime_kernel.start()
    await runtime_kernel.stop()
    status = await runtime_kernel.get_status()
    assert status["initialized"] is True
    assert status["running"] is False

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
        async def initialize(self, config: Optional[Dict[str, Any]] = None) -> None: pass
        async def start(self) -> None: pass
        async def stop(self) -> None: pass
        async def get_status(self) -> Dict[str, Any]: return {}

    kernel = ConcreteKernel()
    assert isinstance(kernel, IRuntimeKernel)

    with pytest.raises(TypeError):
        # لا يمكن إنشاء مثيل من فئة مجردة مباشرة
        IRuntimeKernel()
