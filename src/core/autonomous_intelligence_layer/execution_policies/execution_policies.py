from typing import Dict, List
from .policy import Policy
from .fast_mode_policy import FastModePolicy
from .balanced_mode_policy import BalancedModePolicy
from .quality_mode_policy import QualityModePolicy
from .cost_optimized_mode_policy import CostOptimizedModePolicy
from .research_mode_policy import ResearchModePolicy
from .production_mode_policy import ProductionModePolicy


class ExecutionPolicies:
    """
    مدير لسياسات التنفيذ المختلفة.

    يوفر واجهة موحدة للوصول إلى السياسات وتطبيقها على سياقات المهام.
    """

    def __init__(self):
        """
        يهيئ مثيلًا جديدًا لـ ExecutionPolicies ويقوم بتسجيل السياسات المتاحة.
        """
        self._policies: Dict[str, Policy] = {
            policy.name: policy
            for policy in [
                FastModePolicy(),
                BalancedModePolicy(),
                QualityModePolicy(),
                CostOptimizedModePolicy(),
                ResearchModePolicy(),
                ProductionModePolicy(),
            ]
        }

    def get_policy(self, policy_name: str) -> Policy:
        """
        يسترد كائن سياسة بناءً على اسمها.

        Args:
            policy_name (str): اسم السياسة المطلوبة.

        Returns:
            Policy: كائن السياسة المطابق.

        Raises:
            ValueError: إذا لم يتم العثور على السياسة المطلوبة.
        """
        if policy_name not in self._policies:
            raise ValueError(
                f"السياسة ‏'{policy_name}'‏ غير موجودة. السياسات المتاحة: {list(self._policies.keys())}"
            )
        return self._policies[policy_name]

    def list_available_policies(self) -> List[str]:
        """
        يسرد أسماء جميع السياسات المتاحة.

        Returns:
            List[str]: قائمة بأسماء السياسات.
        """
        return list(self._policies.keys())

    def __repr__(self) -> str:
        return f"ExecutionPolicies(available_policies={self.list_available_policies()})"
