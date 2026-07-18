import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Callable, Awaitable, Optional

from core.runtime.execution_engine.executor import IExecutor, Executor
from core.runtime.execution_engine.dependency_resolver import IDependencyResolver, DependencyResolver
from core.runtime.execution_engine.execution_graph import IExecutionGraph, ExecutionGraph

logger = logging.getLogger(__name__)

class IExecutionEngine(ABC):
    """واجهة مجردة لمحرك التنفيذ (Execution Engine).

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لمحرك التنفيذ.
    """

    @abstractmethod
    async def execute_workflow(self, workflow_definition: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """ينفذ سير عمل (workflow) معقدًا يتكون من مهام مترابطة.

        Args:
            workflow_definition (Dict[str, Dict[str, Any]]): تعريف سير العمل.
                                                            المفتاح هو معرف المهمة، والقيمة هي قاموس يحتوي على:
                                                            - "function": الدالة غير المتزامنة للمهمة.
                                                            - "dependencies": قائمة بمعرفات المهام التي تعتمد عليها.
                                                            - "kwargs": وسائط إضافية لدالة المهمة.

        Returns:
            Dict[str, Any]: قاموس يحتوي على نتائج كل مهمة تم تنفيذها في سير العمل.

        Raises:
            ValueError: إذا تم اكتشاف تبعية دائرية أو كانت هناك مهمة غير معرفة.
            Exception: إذا فشلت أي مهمة أثناء التنفيذ.
        """
        raise NotImplementedError


class ExecutionEngine(IExecutionEngine):
    """تنفيذ محرك التنفيذ (Execution Engine).

    مسؤول عن تنسيق تنفيذ سير العمل المعقد، باستخدام Executor و DependencyResolver و ExecutionGraph.
    """

    def __init__(self,
                 executor: Optional[IExecutor] = None,
                 dependency_resolver: Optional[IDependencyResolver] = None,
                 execution_graph: Optional[IExecutionGraph] = None) -> None:
        self._executor = executor or Executor()
        self._dependency_resolver = dependency_resolver or DependencyResolver()
        self._execution_graph = execution_graph or ExecutionGraph(self._executor, self._dependency_resolver)
        logger.info("ExecutionEngine instance created.")

    async def execute_workflow(self, workflow_definition: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        logger.info("Executing workflow with definition: %s", workflow_definition)
        try:
            results = await self._execution_graph.execute_graph(workflow_definition)
            logger.info("Workflow executed successfully. Results: %s", results)
            return results
        except Exception as e:
            logger.error("Workflow execution failed: %s", e, exc_info=True)
            raise
