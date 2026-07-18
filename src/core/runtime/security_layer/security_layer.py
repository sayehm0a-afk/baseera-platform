from abc import ABC, abstractmethod
from typing import Any, Dict

from core.runtime.security_layer.permission_validation import IPermissionValidation, PermissionValidation
from core.runtime.security_layer.agent_isolation import IAgentIsolation, AgentIsolation
from core.runtime.security_layer.sandbox import ISandbox, Sandbox

class ISecurityLayer(ABC):
    @abstractmethod
    async def validate_and_execute(
        self,
        agent_id: str,
        capability: str,
        func: Any,
        *func_args,
        context: Dict[str, Any] = None,
        use_sandbox: bool = False,
        sandbox_config: Dict[str, Any] = None,
        **func_kwargs
    ) -> Any:
        """
        يقوم بالتحقق من الأذونات وتنفيذ دالة بشكل آمن، اختياريًا داخل صندوق رمل.

        Args:
            agent_id (str): معرف الوكيل الذي يحاول تنفيذ القدرة.
            capability (str): القدرة التي يتم التحقق منها.
            func (Any): الدالة المراد تنفيذها.
            context (Dict[str, Any], optional): سياق إضافي للتحقق من الإذن. الافتراضي هو None.
            use_sandbox (bool, optional): ما إذا كان سيتم تنفيذ الدالة داخل صندوق رمل. الافتراضي هو False.
            sandbox_config (Dict[str, Any], optional): إعدادات صندوق الرمل إذا تم استخدامه. الافتراضي هو None.
            *args: وسائط موضعية لتمريرها إلى الدالة.
            **kwargs: وسائط كلمات رئيسية لتمريرها إلى الدالة.

        Returns:
            Any: نتيجة تنفيذ الدالة.

        Raises:
            PermissionError: إذا لم يكن الوكيل لديه الإذن اللازم.
        """
        raise NotImplementedError

class SecurityLayer(ISecurityLayer):
    def __init__(
        self,
        permission_validation: IPermissionValidation = None,
        agent_isolation: IAgentIsolation = None,
        sandbox: ISandbox = None
    ):
        self._permission_validation = permission_validation or PermissionValidation()
        self._agent_isolation = agent_isolation or AgentIsolation()
        self._sandbox = sandbox or Sandbox()

    async def validate_and_execute(
        self,
        agent_id: str,
        capability: str,
        func: Any,
        *func_args,
        context: Dict[str, Any] = None,
        use_sandbox: bool = False,
        sandbox_config: Dict[str, Any] = None,
        **func_kwargs
    ) -> Any:
        if context is None:
            context = {}
        if sandbox_config is None:
            sandbox_config = {}

        # 1. التحقق من الأذونات
        is_allowed = await self._permission_validation.validate_permission(agent_id, capability, context)
        if not is_allowed:
            raise PermissionError(f"Agent '{agent_id}' is not authorized to perform capability '{capability}'.")

        # 2. التنفيذ (اختياريًا في صندوق رمل)
        if use_sandbox:
            sandbox_id = await self._sandbox.create_sandbox(agent_id, sandbox_config)
            try:
                # تحويل الدالة إلى كود يمكن تنفيذه في الصندوق الرمل
                # هذا تبسيط، في الواقع قد تحتاج إلى تسلسل الدالة ووسائطها
                # أو استخدام آلية RPC بين المحرك والصندوق الرمل
                code_to_execute = "_result = local_vars['func'](*local_vars['args'], **local_vars['kwargs'])"
                # يجب أن تكون الدالة func متاحة في سياق الصندوق الرمل
                # هنا، نفترض أن func هي دالة بسيطة يمكن استدعاؤها مباشرة
                # أو أننا نمررها كجزء من السياق إذا كانت معقدة
                # للتبسيط، سنقوم بتمريرها كمتغير محلي في exec
                local_vars_for_sandbox = {"func": func, "args": func_args, "kwargs": func_kwargs}
                result = await self._sandbox.execute_in_sandbox(sandbox_id, code_to_execute, local_vars=local_vars_for_sandbox)
                return result
            finally:
                await self._sandbox.destroy_sandbox(sandbox_id)
        else:
            return await func(*func_args, **func_kwargs)
