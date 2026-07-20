from typing import Any, Dict
from src.core.autonomous_intelligence_layer.task_graph_engine.task import Task


class Node:
    """
    يمثل عقدة في الرسم البياني الموجه غير الدوري (DAG).

    تحتوي كل عقدة على مهمة (Task) فريدة ومعرف فريد.
    """

    def __init__(self, node_id: str, task: Task):
        """
        يهيئ مثيلًا جديدًا للعقدة.

        Args:
            node_id (str): معرف فريد للعقدة.
            task (Task): كائن المهمة المرتبط بهذه العقدة.
        """
        if not isinstance(node_id, str) or not node_id:
            raise ValueError("معرف العقدة (node_id) يجب أن يكون سلسلة نصية غير فارغة.")

        if not isinstance(task, Task):
            raise ValueError("المهمة (task) يجب أن تكون من نوع Task.")

        self.id: str = node_id
        self.task: Task = task

    def to_dict(self) -> Dict[str, Any]:
        """
        يحول العقدة إلى قاموس.

        Returns:
            Dict[str, Any]: تمثيل قاموسي للعقدة.
        """
        return {"id": self.id, "task": self.task.to_dict()}

    @classmethod
    def from_dict(cls, data: Dict[str, Any]):
        """
        ينشئ مثيل عقدة من قاموس.

        Args:
            data (Dict[str, Any]): قاموس يحتوي على بيانات العقدة.

        Returns:
            Node: مثيل العقدة.
        """
        return cls(node_id=data["id"], task=Task.from_dict(data["task"]))

    def __repr__(self) -> str:
        return f"Node(id='{self.id}', task={self.task})"

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, Node):
            return NotImplemented
        return self.id == other.id and self.task == other.task

    def __hash__(self) -> int:
        return hash((self.id, self.task))
