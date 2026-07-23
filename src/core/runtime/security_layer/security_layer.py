import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

from src.core.runtime.security_layer.permission_validation import (
    IPermissionValidation,
    PermissionValidation,
)
from src.core.runtime.security_layer.agent_isolation import IAgentIsolation, AgentIsolation
from src.core.runtime.security_layer.sandbox import ISandbox, Sandbox

logger = logging.getLogger(__name__)


class ISecurityLayer(ABC):
    """واجهة مجردة لطبقة الأمان.

    تحدد هذه الواجهة الحد الأدنى من الوظائف المطلوبة لأي تنفيذ لطبقة الأمان.
    """

    @abstractmethod
    async def validate_and_execute(
        self,
        agent_id: str,
        capability: str,
        func: callable,
        *func_args,
        context: Optional[Dict[str, Any]] = None,
        use_sandbox: bool = False,
        sandbox_config: Optional[Dict[str, Any]] = None,
        **func_kwargs,
    ) -> Any:
        """يقوم بالتحقق من الأذونات وتنفيذ الإجراء المطلوب.

        Args:
            agent_id (str): معرف الوكيل الذي يطلب التنفيذ.
            capability (str): القدرة المطلوبة (مثل "access_database",
                "send_email").
            func (callable): الدالة المراد تنفيذها.
            func_args (tuple): الوسائط الموضعية للدالة.
            func_kwargs (dict): الوسائط الكلمة للدالة.
            context (Optional[Dict[str, Any]]): سياق التنفيذ (مثل معرف المهمة،
                معرف المستخدم).
            use_sandbox (bool): ما إذا كان يجب تنفيذ الدالة في بيئة صندوق رمل
                معزولة.
            sandbox_config (Optional[Dict[str, Any]]): إعدادات تهيئة صندوق
                الرمل.

        Returns:
            Any: نتيجة تنفيذ الدالة.

        Raises:
            PermissionError: إذا لم يكن الوكيل مصرحًا له بالقدرة المطلوبة.
            SandboxError: إذا فشل تنفيذ صندوق الرمل.
        """
        raise NotImplementedError


class SecurityLayer(ISecurityLayer):
    """تنفيذ طبقة الأمان.

    تتولى هذه الطبقة مسؤولية فرض سياسات الأمان، إدارة الأذونات، وتوفير
    بيئات تنفيذ معزولة (صناديق الرمل) للوكلاء.
    """

    def __init__(
        self,
        permission_validation: Optional[IPermissionValidation] = None,
        agent_isolation: Optional[IAgentIsolation] = None,
        sandbox: Optional[ISandbox] = None,
    ):
        self._permission_validation = permission_validation or PermissionValidation()
        self._agent_isolation = agent_isolation or AgentIsolation()
        self._sandbox = sandbox or Sandbox()

    async def validate_and_execute(
        self,
        agent_id: str,
        capability: str,
        func: callable,
        *func_args,
        context: Optional[Dict[str, Any]] = None,
        use_sandbox: bool = False,
        sandbox_config: Optional[Dict[str, Any]] = None,
        **func_kwargs,
    ) -> Any:
        if context is None:
            context = {}
        if sandbox_config is None:
            sandbox_config = {}

        # 1. التحقق من الأذونات
        is_allowed = await self._permission_validation.validate_permission(
            agent_id, capability, context
        )
        if not is_allowed:
            raise PermissionError(
                f"Agent '{agent_id}' is not authorized to "
                f"perform capability '{capability}'"
            )

        # 2. التنفيذ (اختياريًا في صندوق رمل)
        if use_sandbox:
            sandbox_id = await self._sandbox.create_sandbox(agent_id, sandbox_config)
            try:
                # تحويل الدالة إلى كود يمكن تنفيذه في الصندوق الرمل
                # هذا تبسيط، في الواقع قد تحتاج إلى تسلسل الدالة ووسائطها
                # أو استخدام آلية RPC بين المحرك والصندوق الرمل
                code_to_execute = (
                    "_result = local_vars['func'](*local_vars['args'], "
                    "**local_vars['kwargs'])"
                )
                # يجب أن تكون الدالة func متاحة في سياق الصندوق الرمل
                # هنا، نفترض أن func هي دالة بسيطة يمكن استدعاؤها مباشرة
                # أو أننا نمررها كجزء من السياق إذا كانت معقدة
                # للتبسيط، سنقوم بتمريرها كمتغير محلي في exec
                local_vars_for_sandbox = {
                    "func": func,
                    "args": func_args,
                    "kwargs": func_kwargs,
                }
                result = await self._sandbox.execute_in_sandbox(
                    sandbox_id, code_to_execute, local_vars=local_vars_for_sandbox
                )
                return result
            finally:
                await self._sandbox.destroy_sandbox(sandbox_id)
        else:
            return await func(*func_args, **func_kwargs)
