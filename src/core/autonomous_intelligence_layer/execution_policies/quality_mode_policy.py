from typing import Any, Dict
from .policy import Policy


class QualityModePolicy(Policy):
    """
    سياسة وضع الجودة: تركز على تحقيق أعلى دقة وجودة ممكنة، حتى لو كان ذلك على حساب السرعة أو التكلفة.
    """

    @property
    def name(self) -> str:
        return "QualityMode"

    def apply(self, task_context: Dict[str, Any]) -> Dict[str, Any]:
        """
        تطبق سياسة وضع الجودة على سياق المهمة.

        Args:
            task_context (Dict[str, Any]): سياق المهمة الذي سيتم تطبيق السياسة عليه.

        Returns:
            Dict[str, Any]: سياق المهمة المعدل.
        """
        modified_context = task_context.copy()
        modified_context["execution_mode"] = self.name
        modified_context["priority"] = "low"
        modified_context["resource_allocation"] = "high"
        modified_context["accuracy_tolerance"] = "high"
        return modified_context
