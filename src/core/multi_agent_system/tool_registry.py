"""
وحدة ToolRegistry لمنصة basirah.
تدير تسجيل الأدوات وإلغاء تسجيلها واسترجاعها.
"""

import logging
from typing import Dict, List, Optional

from core.multi_agent_system.base_tool import (
    BaseTool,
)  # pylint: disable=E0402 # type: ignore

logger = logging.getLogger(__name__)


class ToolRegistry:
    """
    ToolRegistry هو مخزن مركزي لتسجيل وإدارة الأدوات المتاحة للعملاء الذكيين.
    يسمح للعملاء باكتشاف الأدوات واستخدامها.
    """

    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
        logger.info("ToolRegistry initialized.")

    async def register_tool(self, tool: BaseTool) -> bool:
        """
        يسجل أداة جديدة.
        """
        if tool.name in self._tools:
            logger.warning("Tool with name %s already registered.", tool.name)
            return False
        self._tools[tool.name] = tool
        logger.info("Tool %s registered successfully.", tool.name)
        return True

    async def unregister_tool(self, tool_name: str) -> bool:
        """
        يزيل أداة من السجل.
        """
        if tool_name not in self._tools:
            logger.warning("Tool with name %s not found for unregistration.", tool_name)
            return False
        del self._tools[tool_name]
        logger.info("Tool %s unregistered successfully.", tool_name)
        return True

    async def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        يسترجع أداة بواسطة اسمها.
        """
        return self._tools.get(tool_name)

    async def get_all_tools(self) -> Dict[str, BaseTool]:
        """
        يسترجع قاموساً بجميع الأدوات المسجلة.
        """
        return self._tools

    async def get_tools_by_keyword(self, keyword: str) -> List[BaseTool]:
        """
        يسترجع قائمة بالأدوات التي تحتوي أوصافها على كلمة مفتاحية معينة.
        """
        return [
            tool
            for tool in self._tools.values()
            if keyword.lower() in tool.description.lower()
        ]
