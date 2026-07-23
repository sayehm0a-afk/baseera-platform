import pytest
import logging
from unittest.mock import AsyncMock
from typing import Any, Dict, Optional
from src.core.runtime.agent_runtime import AgentRuntime, IAgentRuntime

logger = logging.getLogger(__name__)


@pytest.fixture
def agent_runtime() -> AgentRuntime:
    """Fixture لتوفير مثيل AgentRuntime."""
    return AgentRuntime()


@pytest.mark.asyncio
async def test_agent_runtime_initial_state(agent_runtime: AgentRuntime):
    """اختبار الحالة الأولية لـ AgentRuntime."""
    assert await agent_runtime.get_agent_status("test_agent") == {"status": "INACTIVE", "agent_id": "test_agent"}


@pytest.mark.asyncio
async def test_agent_runtime_activate_agent(agent_runtime: AgentRuntime):
    """اختبار تفعيل وكيل في AgentRuntime."""
    agent_id = "test_agent_1"
    config = {"model": "gpt-4"}
    await agent_runtime.activate_agent(agent_id, config=config)
    status = await agent_runtime.get_agent_status(agent_id)
    assert status["status"] == "ACTIVE"
    assert status["config"] == config
    assert status["last_activity"] == "N/A"


@pytest.mark.asyncio
async def test_agent_runtime_activate_agent_already_active(agent_runtime: AgentRuntime, caplog):
    """اختبار تفعيل وكيل عندما يكون نشطًا بالفعل."""
    agent_id = "test_agent_2"
    await agent_runtime.activate_agent(agent_id)
    with caplog.at_level(logging.WARNING):
        await agent_runtime.activate_agent(agent_id)
        assert f"Agent '{agent_id}' is already active." in caplog.text
    status = await agent_runtime.get_agent_status(agent_id)
    assert status["status"] == "ACTIVE"


@pytest.mark.asyncio
async def test_agent_runtime_deactivate_agent(agent_runtime: AgentRuntime):
    """اختبار إلغاء تفعيل وكيل في AgentRuntime."""
    agent_id = "test_agent_3"
    await agent_runtime.activate_agent(agent_id)
    await agent_runtime.deactivate_agent(agent_id)
    status = await agent_runtime.get_agent_status(agent_id)
    assert status["status"] == "INACTIVE"


@pytest.mark.asyncio
async def test_agent_runtime_deactivate_agent_not_active(agent_runtime: AgentRuntime, caplog):
    """اختبار إلغاء تفعيل وكيل عندما لا يكون نشطًا."""
    agent_id = "non_existent_agent"
    with caplog.at_level(logging.WARNING):
        await agent_runtime.deactivate_agent(agent_id)
        assert f"Agent '{agent_id}' is not active. Cannot deactivate." in caplog.text
    status = await agent_runtime.get_agent_status(agent_id)
    assert status["status"] == "INACTIVE"


@pytest.mark.asyncio
async def test_agent_runtime_execute_agent_step(agent_runtime: AgentRuntime):
    """اختبار تنفيذ خطوة وكيل في AgentRuntime."""
    agent_id = "test_agent_4"
    await agent_runtime.activate_agent(agent_id)
    step_data = {"action": "analyze_data", "data": {"stock": "TASI"}}
    result = await agent_runtime.execute_agent_step(agent_id, step_data)
    assert result == {"result": f"Step \'analyze_data\' completed for agent \'{agent_id}\'"}
    status = await agent_runtime.get_agent_status(agent_id)
    assert status["last_activity"] == f"Executed step: {step_data.get('action')}"


@pytest.mark.asyncio
async def test_agent_runtime_execute_agent_step_not_active(agent_runtime: AgentRuntime, caplog):
    """اختبار تنفيذ خطوة وكيل عندما لا يكون نشطًا."""
    agent_id = "non_active_agent"
    step_data = {"action": "fetch_data"}
    with pytest.raises(RuntimeError, match=r"Agent \'%s\' is not active." % agent_id):
        with caplog.at_level(logging.ERROR):
            await agent_runtime.execute_agent_step(agent_id, step_data)
            assert f"Agent '{agent_id}' is not active. Cannot execute step." in caplog.text


@pytest.mark.asyncio
async def test_iagent_runtime_abstract_methods():
    """اختبار أن IAgentRuntime يفرض تنفيذ التوابع المجردة."""
    class ConcreteAgentRuntime(IAgentRuntime):
        async def activate_agent(self, agent_id: str, config: Optional[Dict[str, Any]] = None) -> None:
            pass

        async def deactivate_agent(self, agent_id: str) -> None:
            pass

        async def get_agent_status(self, agent_id: str) -> Dict[str, Any]:
            return {}

        async def execute_agent_step(self, agent_id: str, step_data: Dict[str, Any]) -> Any:
            return None

    agent_rt = ConcreteAgentRuntime()
    assert isinstance(agent_rt, IAgentRuntime)

    with pytest.raises(TypeError):
        # لا يمكن إنشاء مثيل من فئة مجردة مباشرة
        IAgentRuntime()
