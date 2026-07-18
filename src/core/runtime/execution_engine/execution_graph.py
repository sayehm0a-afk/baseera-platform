import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Callable, Awaitable

from core.runtime.execution_engine.executor import IExecutor, Executor
from core.runtime.execution_engine.dependency_resolver import IDependencyResolver, DependencyResolver

logger = logging.getLogger(__name__)

class IExecutionGraph(ABC):
    """واجهة مجردة لـ Execution Graph.

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لـ Execution Graph.
    """

    @abstractmethod
    async def execute_graph(self, graph_definition: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        """ينفذ الرسم البياني للمهام بناءً على التبعيات.

        Args:
            graph_definition (Dict[str, Dict[str, Any]]): تعريف الرسم البياني للمهام.
                                                        المفتاح هو معرف المهمة، والقيمة هي قاموس يحتوي على:
                                                        - "function": الدالة غير المتزامنة للمهمة.
                                                        - "dependencies": قائمة بمعرفات المهام التي تعتمد عليها.
                                                        - "kwargs": وسائط إضافية لدالة المهمة.

        Returns:
            Dict[str, Any]: قاموس يحتوي على نتائج كل مهمة تم تنفيذها.

        Raises:
            ValueError: إذا تم اكتشاف تبعية دائرية أو كانت هناك مهمة غير معرفة.
            Exception: إذا فشلت أي مهمة أثناء التنفيذ.
        """
        raise NotImplementedError


class ExecutionGraph(IExecutionGraph):
    """تنفيذ Execution Graph.

    مسؤول عن تنفيذ مجموعة من المهام مع مراعاة تبعياتها.
    """

    def __init__(self, executor: IExecutor = None, dependency_resolver: IDependencyResolver = None) -> None:
        self._executor = executor or Executor()
        self._dependency_resolver = dependency_resolver or DependencyResolver()
        logger.info("ExecutionGraph instance created.")

    async def execute_graph(self, graph_definition: Dict[str, Dict[str, Any]]) -> Dict[str, Any]:
        tasks_for_resolver = {task_id: task_data.get("dependencies", []) for task_id, task_data in graph_definition.items()}

        try:
            execution_order = self._dependency_resolver.resolve(tasks_for_resolver)
        except ValueError as e:
            logger.error("Failed to resolve dependencies: %s", e)
            raise

        results: Dict[str, Any] = {}
        for task_id in execution_order:
            if task_id not in graph_definition:
                # This can happen if a dependency is not defined as a task itself
                # and was added by the dependency resolver. We should skip it.
                logger.warning("Skipping task %s as it is a dependency but not a defined task in the graph.", task_id)
                continue

            task_data = graph_definition[task_id]
            task_function = task_data["function"]
            task_kwargs = task_data.get("kwargs", {})

            # Inject results of dependencies into kwargs if needed
            for dep_id in task_data.get("dependencies", []):
                if dep_id in results:
                    # Assuming dependency results are passed as kwargs with dep_id as key
                    task_kwargs[f"dep_{dep_id}_result"] = results[dep_id] # Keep this for now, as the tests expect this format

            try:
                result = await self._executor.execute_task(task_id, task_function, **task_kwargs)
                results[task_id] = result
            except Exception as e:
                logger.error("Task %s failed during execution: %s", task_id, e)
                raise

        logger.info("Execution graph completed successfully.")
        return results
