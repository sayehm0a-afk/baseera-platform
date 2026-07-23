import pytest
import logging
from unittest.mock import AsyncMock
from typing import Any, Dict, Optional
from src.core.runtime.supervisor_runtime import SupervisorRuntime, ISupervisorRuntime

logger = logging.getLogger(__name__)


@pytest.fixture
def supervisor_runtime() -> SupervisorRuntime:
    """Fixture لتوفير مثيل SupervisorRuntime."""
    return SupervisorRuntime()


@pytest.mark.asyncio
async def test_supervisor_runtime_initial_state(supervisor_runtime: SupervisorRuntime):
    """اختبار الحالة الأولية لـ SupervisorRuntime."""
    status = await supervisor_runtime.get_supervised_status()
    assert status["supervising"] is False
    assert status["config"] == {}
    assert status["active_agents"] == 0
    assert status["pending_tasks"] == 0


@pytest.mark.asyncio
async def test_supervisor_runtime_start_supervision(supervisor_runtime: SupervisorRuntime):
    """اختبار بدء الإشراف في SupervisorRuntime."""
    config = {"agent_config": "default"}
    await supervisor_runtime.start_supervision(config=config)
    status = await supervisor_runtime.get_supervised_status()
    assert status["supervising"] is True
    assert status["config"] == config


@pytest.mark.asyncio
async def test_supervisor_runtime_start_supervision_already_supervising(supervisor_runtime: SupervisorRuntime, caplog):
    """اختبار بدء الإشراف عندما يكون SupervisorRuntime قيد الإشراف بالفعل."""
    await supervisor_runtime.start_supervision()
    with caplog.at_level(logging.WARNING):
        await supervisor_runtime.start_supervision()
        assert "SupervisorRuntime already supervising." in caplog.text
    status = await supervisor_runtime.get_supervised_status()
    assert status["supervising"] is True


@pytest.mark.asyncio
async def test_supervisor_runtime_stop_supervision(supervisor_runtime: SupervisorRuntime):
    """اختبار إيقاف الإشراف في SupervisorRuntime."""
    await supervisor_runtime.start_supervision()
    await supervisor_runtime.stop_supervision()
    status = await supervisor_runtime.get_supervised_status()
    assert status["supervising"] is False


@pytest.mark.asyncio
async def test_supervisor_runtime_stop_supervision_not_supervising(supervisor_runtime: SupervisorRuntime, caplog):
    """اختبار إيقاف الإشراف عندما لا يكون SupervisorRuntime قيد الإشراف."""
    with caplog.at_level(logging.WARNING):
        await supervisor_runtime.stop_supervision()
        assert "SupervisorRuntime is not supervising. Nothing to stop." in caplog.text
    status = await supervisor_runtime.get_supervised_status()
    assert status["supervising"] is False


@pytest.mark.asyncio
async def test_supervisor_runtime_get_supervised_status(supervisor_runtime: SupervisorRuntime):
    """اختبار الحصول على حالة الإشراف في SupervisorRuntime."""
    status = await supervisor_runtime.get_supervised_status()
    assert isinstance(status, dict)
    assert "supervising" in status
    assert "config" in status
    assert "active_agents" in status
    assert "pending_tasks" in status


@pytest.mark.asyncio
async def test_isupervisor_runtime_abstract_methods():
    """اختبار أن ISupervisorRuntime يفرض تنفيذ التوابع المجردة."""
    class ConcreteSupervisor(ISupervisorRuntime):
        async def start_supervision(self, config: Optional[Dict[str, Any]] = None) -> None:
            pass

        async def stop_supervision(self) -> None:
            pass

        async def get_supervised_status(self) -> Dict[str, Any]:
            return {}

    supervisor = ConcreteSupervisor()
    assert isinstance(supervisor, ISupervisorRuntime)

    with pytest.raises(TypeError):
        # لا يمكن إنشاء مثيل من فئة مجردة مباشرة
        ISupervisorRuntime()
