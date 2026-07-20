import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional
from src.core.llm_abstraction.base_llm_client import BaseLLMClient

# Configure logging for BaseAgent
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class BaseAgent:
    """
    BaseAgent هو الصنف الأساسي لجميع العملاء الذكيين في منصة basirah.
    يوفر هذا الصنف الهيكل الأساسي والوظائف المشتركة لإدارة دورة حياة العميل،
    الذاكرة، التفكير، استدعاء الأدوات، والتفاعل مع نماذج اللغة الكبيرة (LLMs).
    """

    def __init__(
        self,
        agent_id: Optional[str] = None,
        name: str = "BaseAgent",
        description: str = "وكيل ذكي أساسي لمنصة basirah",
    ):
        self.agent_id: str = agent_id if agent_id else str(uuid.uuid4())
        self.name: str = name
        self.description: str = description
        self.created_at: datetime = datetime.now()
        self.status: str = (
            "initialized"  # States: initialized, active, paused, terminated
        )
        self.memory: Dict[str, Any] = {}
        # This will be populated by ToolRegistry
        self.tools: Dict[str, Any] = {}
        self.tool_registry: Any = None  # سيتم تعيين ToolRegistry عند تنشيط العميل.
        self.llm_client: Optional[BaseLLMClient] = None  # سيتم تعيين عميل LLM عند تنشيط العميل.
        logger.info("BaseAgent '%s' (%s) initialized.", self.name, self.agent_id)

    def _load_config(self) -> None:
        """Loads agent-specific configuration."""
        logger.debug("Loading configuration for agent '%s'.", self.name)
        # في تطبيق حقيقي، سيتم تحميل التكوين من مصدر دائم (مثل ملف، قاعدة بيانات، أو خدمة تكوين).

    def _initialize_memory(self) -> None:
        """Initializes the agent's memory system."""
        logger.debug("Initializing memory for agent '%s'.", self.name)
        # في تطبيق حقيقي، سيتم تهيئة نظام الذاكرة الفعلي (مثل قاعدة بيانات، مخزن ذاكرة مؤقتة).
        self.memory["short_term"] = []
        self.memory["long_term"] = {}

    async def _initialize_tools(self, tool_registry: Any = None) -> None:
        """Initializes the tools available to the agent using a ToolRegistry."""
        logger.debug("Initializing tools for agent %s.", self.name)
        if tool_registry:
            self.tool_registry = tool_registry
            # Optionally, register agent-specific tools or fetch all available tools
            # Fetch all available tools from the registry and store them locally
            all_tools = await self.tool_registry.get_all_tools()
            self.tools = dict(all_tools.items())
        else:
            logger.warning(
                "No ToolRegistry provided for agent %s. Tools will be empty.", self.name
            )

    async def _initialize_llm_client(self, llm_client: Optional[BaseLLMClient] = None) -> None:
        """Initializes the LLM client abstraction layer."""
        logger.debug("Initializing LLM client for agent \'%s\'.", self.name)
        if llm_client:
            self.llm_client = llm_client
        # في تطبيق حقيقي، إذا لم يتم توفير llm_client، فسيتم تهيئة عميل LLM الافتراضي هنا.

    async def activate(self, tool_registry: Any = None) -> bool:
        """Activates the agent, making it ready to process tasks."""
        if self.status in ("initialized", "paused"):
            self._load_config()
            self._initialize_memory()
            await self._initialize_tools(tool_registry)
            # يجب أن يتم تمرير عميل LLM الحقيقي إلى activate أو تهيئته هنا
            # حاليًا، لا يتم تمرير عميل LLM، لذا سيبقى None ما لم يتم تهيئته في مكان آخر.
            # هذا يحتاج إلى معالجة لضمان أن الوكيل لديه عميل LLM يعمل.
            # سأفترض مؤقتًا أنه سيتم توفيره من خلال آلية حقن التبعية أو سيتم تهيئته بشكل افتراضي.
            # for now, we will assume it's passed or initialized elsewhere.
            await self._initialize_llm_client()
            self.status = "active"
            logger.info("BaseAgent '%s' (%s) activated.", self.name, self.agent_id)
            return True
        logger.warning(
            "Cannot activate agent '%s' in status '%s'.", self.name, self.status
        )
        return False

    def pause(self) -> bool:
        """Pauses the agent's operations."""
        if self.status == "active":
            self.status = "paused"
            logger.info("BaseAgent '%s' (%s) paused.", self.name, self.agent_id)
            return True
        logger.warning(
            "Cannot pause agent '%s' in status '%s'.", self.name, self.status
        )
        return False

    def terminate(self) -> bool:
        """Terminates the agent, releasing resources."""
        if self.status != "terminated":
            self.status = "terminated"
            logger.info("BaseAgent '%s' (%s) terminated.", self.name, self.agent_id)
            # في تطبيق حقيقي، سيتم تحرير الموارد هنا (مثل إغلاق الاتصالات، إيقاف العمليات).
            return True
        logger.warning("Agent '%s' is already terminated.", self.name)
        return False

    def process_task(self, task_data: Dict[str, Any]) -> Any:
        """Abstract method to be implemented by specialized agents for task processing."""
        if self.status != "active":
            logger.error("Agent '%s' is not active. Cannot process task.", self.name)
            raise RuntimeError("Agent not active")
        logger.info(
            "Agent '%s' processing task: %s", self.name, task_data.get("task_id", "N/A")
        )
        # This method will contain the core reasoning pipeline, tool calling, and LLM interaction
        # It should be overridden by specialized agents.
        raise NotImplementedError(
            "process_task method must be implemented by subclasses"
        )  # pragma: no cover

    def _reason(
        self, prompt: str, context: Dict[str, Any]
    ) -> str:  # pylint: disable=W0613
        """يمثل هذا توجيهًا لخط أنابيب التفكير للعميل. في تطبيق حقيقي، سيتضمن ذلك استدعاءات LLM، استرجاع الذاكرة، والمعالجة المنطقية."""
        logger.debug("Agent '%s' reasoning with prompt: %s...", self.name, prompt[:50])
        # This will involve LLM calls, memory retrieval, and logical processing
        return "Reasoning result"

    async def _call_tool(self, tool_name: str, **kwargs) -> Any:
        """يمثل هذا توجيهًا لاستدعاء أداة خارجية. في تطبيق حقيقي، سيتفاعل هذا مع ToolRegistry لتحديد الأداة وتنفيذها."""
        if tool_name is None:
            logger.error("Tool name cannot be None.")
            raise ValueError("Tool name cannot be None")
        if not self.tool_registry:
            logger.error("ToolRegistry not initialized for agent %s.", self.name)
            raise RuntimeError("ToolRegistry not initialized for this agent")

        tool = await self.tool_registry.get_tool(tool_name)
        if not tool:
            logger.error(
                "Tool %s not found in registry for agent %s.", tool_name, self.name
            )
            raise ValueError(f"Tool {tool_name} not found in registry")

        logger.info(
            "Agent %s calling tool: %s with args: %s", self.name, tool_name, kwargs
        )
        return await tool.execute(**kwargs)

    async def _interact_with_llm(
        self, messages: List[Dict[str, str]], model: str = "default"
    ) -> str:  # pylint: disable=W0613
        """يمثل هذا توجيهًا للتفاعل مع طبقة تجريد LLM. في تطبيق حقيقي، سيستخدم هذا عميل LLM لإرسال الرسائل إلى LLM وتلقي الاستجابات."""
        if not self.llm_client:
            logger.error("LLM client not initialized for agent '%s'.", self.name)
            raise RuntimeError("LLM client not available")
        logger.info(
            "Agent '%s' interacting with LLM with messages: %s", self.name, messages
        )
        # This will use self.llm_client to send messages to the LLM
        if self.llm_client:
            response = await self.llm_client.generate_text(messages, model)
            return response
        else:
            logger.warning("LLM client not available for agent \'%s\'. Returning placeholder response.", self.name)
            return "LLM response (placeholder)"

    def get_status(self) -> str:
        """Returns the current status of the agent."""
        return self.status

    def get_info(self) -> Dict[str, Any]:
        """Returns basic information about the agent."""
        return {
            "agent_id": self.agent_id,
            "name": self.name,
            "description": self.description,
            "status": self.status,
            "created_at": self.created_at.isoformat(),
            "memory_keys": list(self.memory.keys()),
            "available_tools": list(self.tools.keys()) if self.tools else [],
        }


if __name__ == "__main__":  # pragma: no cover
    # Example Usage
    logger.info("\n--- BaseAgent Example Usage ---")
    agent_example = BaseAgent(name="TestAgent", description="وكيل اختباري بسيط")
    logger.info(f"Initial Status: {agent_example.get_status()}")
    logger.info(f"Agent Info: {agent_example.get_info()}")

    # لتفعيل الوكيل، يجب توفير ToolRegistry و LLMClient حقيقيين.
    # هذا مثال توضيحي فقط، وفي بيئة الإنتاج، سيتم حقن هذه التبعيات.
    # agent_example.activate(tool_registry=real_tool_registry, llm_client=real_llm_client)
    logger.info(f"Status after activation: {agent_example.get_status()}")

    try:
        agent_example.process_task({"task_id": "123", "query": "حلل السوق"})
    except NotImplementedError as e:
        logger.error(f"Expected error: {e}")

    agent_example.pause()
    logger.info(f"Status after pausing: {agent_example.get_status()}")

    agent_example.terminate()
    logger.info(f"Status after termination: {agent_example.get_status()}")
    logger.info("--- End of Example ---")
