"""
وحدة BaseTool لمنصة basirah.
تحدد الواجهة الأساسية لجميع الأدوات التي يمكن للعملاء الذكيين استخدامها.
"""

import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)


class BaseTool(ABC):
    """
    BaseTool هو الصنف الأساسي المجرد لجميع الأدوات في منصة basirah.
    يجب على جميع الأدوات أن ترث من هذا الصنف وتطبق التوابع المجردة.
    """

    def __init__(
        self, name: str, description: str, parameters: Optional[Dict[str, Any]] = None
    ):
        self.name = name
        self.description = description
        self.parameters = parameters if parameters is not None else {}
        logger.info("BaseTool %s initialized.", self.name)

    @abstractmethod
    async def execute(self, **kwargs) -> Any:
        """
        ينفذ وظيفة الأداة.
        يجب أن يتم تجاوز هذا التابع بواسطة الأدوات المتخصصة.
        """
        raise NotImplementedError(
            "execute method must be implemented by subclasses"
        )  # pragma: no cover

    def get_info(self) -> Dict[str, Any]:
        """
        يعيد معلومات حول الأداة.
        """
        return {
            "name": self.name,
            "description": self.description,
            "parameters": self.parameters,
        }  # pylint: disable=C0301
