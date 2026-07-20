from typing import Any, Dict, Optional
from enum import Enum


class TaskType(Enum):
    DATA_PROCESSING = "data_processing"
    ANOMALY_DETECTION = "anomaly_detection"
    COST_ANALYSIS = "cost_analysis"
    DEBATE = "debate"
    DECISION_FUSION = "decision_fusion"
    ERROR_RECOVERY = "error_recovery"
    FINANCIAL_INTELLIGENCE = "financial_intelligence"
    LEARNING = "learning"
    MEMORY_REASONING = "memory_reasoning"
    RANKING = "ranking"
    RESOURCE_OPTIMIZATION = "resource_optimization"
    ROI_CALCULATION = "roi_calculation"
    SELF_OPTIMIZATION = "self_optimization"
    VOTING = "voting"
    PLANNING = "planning"
    EXECUTION = "execution"
    OBSERVABILITY = "observability"
    SECURITY = "security"
    RELIABILITY = "reliability"
    CONTEXT_MANAGEMENT = "context_management"
    AGENT_REGISTRY = "agent_registry"
    UNKNOWN = "unknown"


class TaskStatus(Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    PAUSED = "paused"


class Task:
    """
    يمثل مهمة فردية داخل نظام basirah.

    تتضمن المهمة معرفًا فريدًا، وحالة، ومعرف وكيل مسؤول عن تنفيذها، وحمولة بيانات.
    """

    def __init__(
        self,
        task_id: str,
        payload: Dict[str, Any],
        agent_id: Optional[str] = None,
        status: TaskStatus = TaskStatus.PENDING,
    ):
        """
        يهيئ مثيلًا جديدًا للمهمة.

        Args:
            task_id (str): معرف فريد للمهمة.
            payload (Dict[str, Any]): حمولة بيانات المهمة التي تحتوي على المعلومات اللازمة للتنفيذ.
            agent_id (Optional[str]): معرف الوكيل المسؤول عن تنفيذ المهمة. اختياري.
            status (TaskStatus): الحالة الأولية للمهمة (افتراضي: PENDING).
        """
        if not isinstance(task_id, str) or not task_id:
            raise ValueError("معرف المهمة (task_id) يجب أن يكون سلسلة نصية غير فارغة.")
        if not isinstance(payload, dict):
            raise ValueError("حمولة المهمة (payload) يجب أن تكون قاموسًا.")
        if agent_id is not None and not isinstance(agent_id, str):
            raise ValueError("معرف الوكيل (agent_id) يجب أن يكون سلسلة نصية أو لا شيء.")
        if not isinstance(status, TaskStatus):
            raise ValueError("الحالة (status) يجب أن تكون من نوع TaskStatus.")

        self.id: str = task_id
        self.payload: Dict[str, Any] = payload
        self.agent_id: Optional[str] = agent_id
        self.status: TaskStatus = status

    def update_status(self, new_status: TaskStatus) -> None:
        """
        يحدث حالة المهمة.

        Args:
            new_status (str): الحالة الجديدة للمهمة.
        """
        if not isinstance(new_status, TaskStatus):
            raise ValueError(
                "الحالة الجديدة (new_status) يجب أن تكون من نوع TaskStatus."
            )
        self.status = new_status

    def assign_agent(self, agent_id: str) -> None:
        """
        يعين وكيلًا للمهمة.

        Args:
            agent_id (str): معرف الوكيل الذي سيتم تعيينه للمهمة.
        """
        if not isinstance(agent_id, str) or not agent_id:
            raise ValueError("معرف الوكيل (agent_id) يجب أن يكون سلسلة نصية غير فارغة.")
        self.agent_id = agent_id

    def to_dict(self) -> Dict[str, Any]:
        """
        يحول المهمة إلى قاموس.

        Returns:
            Dict[str, Any]: تمثيل قاموسي للمهمة.
        """
        return {
            "id": self.id,
            "payload": self.payload,
            "agent_id": self.agent_id,
            "status": self.status.value,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        ينشئ مثيل مهمة من قاموس.

        Args:
            data (Dict[str, Any]): قاموس يحتوي على بيانات المهمة.

        Returns:
            Task: مثيل المهمة.
        """
        return cls(
            task_id=data["id"],
            payload=data["payload"],
            agent_id=data.get("agent_id"),
            status=TaskStatus(data.get("status", TaskStatus.PENDING.value)),
        )

    def __repr__(self) -> str:
        return f"Task(id='{self.id}', status='{self.status.value}', agent_id='{self.agent_id}')"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Task):
            return NotImplemented
        return (
            self.id == other.id
            and self.payload == other.payload
            and self.agent_id == other.agent_id
            and self.status == other.status
        )

    def __hash__(self) -> int:
        def make_hashable(obj):
            if isinstance(obj, dict):
                return frozenset({k: make_hashable(v) for k, v in obj.items()}.items())
            elif isinstance(obj, list):
                return tuple(make_hashable(elem) for elem in obj)
            return obj

        return hash((self.id, make_hashable(self.payload), self.agent_id, self.status))
