from typing import Any, Dict
from .policy import Policy


class CostOptimizedModePolicy(Policy):
    """
    سياسة وضع التكلفة المحسّنة: تركز على تقليل التكلفة إلى أقصى حد ممكن، حتى لو كان ذلك على حساب السرعة أو الجودة.
    """

    @property
    def name(self) -> str:
        return "CostOptimizedMode"

    def apply(self, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        تطبق سياسة وضع التكلفة المحسّنة على سياق المهمة.

        Args:
            task_context (Dict[str, Any]): سياق المهمة الذي سيتم تطبيق السياسة عليه.

        Returns:
            Dict[str, Any]: سياق المهمة المعدل.
        """
        modified_context = task_context.copy()
        modified_context["execution_mode"] = self.name
        modified_context["priority"] = "low"
        modified_context["resource_allocation"] = "minimal_cost"
        modified_context["accuracy_tolerance"] = "flexible"
        modified_context["cost_limit"] = "strict"
        return modified_context
