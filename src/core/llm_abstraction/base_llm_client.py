"""
وحدة BaseLLMClient الأساسية لمنصة basirah.
توفر واجهة موحدة للتعامل مع نماذج اللغة الكبيرة (LLMs).
"""
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import asyncio

logger = logging.getLogger(__name__)

class BaseLLMClient(ABC):
    """
    واجهة مجردة لعملاء نماذج اللغة الكبيرة (LLMs).
    يجب على جميع تطبيقات عملاء LLM أن ترث من هذه الواجهة.
    """

    def __init__(self, model_name: str, config: Optional[Dict[str, Any]] = None):
        self.model_name = model_name
        self.config = config if config is not None else {}
        logger.info("BaseLLMClient initialized for model: %s", self.model_name)

    @abstractmethod
    async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        ينشئ استجابة من نموذج اللغة الكبيرة.

        Args:
            messages (List[Dict[str, str]]): قائمة بالرسائل التي تمثل المحادثة.
            **kwargs: أي وسائط إضافية خاصة بالنموذج.

        Returns:
            Dict[str, Any]: قاموس يحتوي على الاستجابة من النموذج.
        """
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    async def count_tokens(self, text: str) -> int:
        """
        يحسب عدد التوكنات في نص معين.

        Args:
            text (str): النص المراد حساب توكناته.

        Returns:
            int: عدد التوكنات.
        """
        raise NotImplementedError  # pragma: no cover

    @abstractmethod
    async def get_model_info(self) -> Dict[str, Any]:
        """
        يحصل على معلومات حول النموذج.

        Returns:
            Dict[str, Any]: قاموس يحتوي على معلومات النموذج (مثل التكاليف، حدود التوكنات).
        """
        raise NotImplementedError  # pragma: no cover

    async def _handle_retry(self, func, *args, **kwargs) -> Any:
        """
        منطق إعادة المحاولة الافتراضي لأي استدعاء لـ LLM.
        يمكن تجاوز هذه الوظيفة بواسطة العملاء المحددين.
        """
        max_retries = self.config.get("max_retries", 3)
        delay = self.config.get("retry_delay", 1)
        for i in range(max_retries):
            try:
                return await func(*args, **kwargs)
            except (asyncio.TimeoutError, ConnectionError, Exception) as e:  # pylint: disable=W0718,broad-exception-caught
            # Catching broad Exception here is intentional for retry mechanism robustness.
                logger.warning("Attempt %d failed: %s", i + 1, e)
                if i < max_retries - 1:
                    await asyncio.sleep(delay)
                else:
                    raise


# Example of how a concrete client would implement this interface
# class ConcreteLLMClient(BaseLLMClient):
#     async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
#         # Implementation specific to the concrete LLM provider
#         raise NotImplementedError  # pragma: no cover
#
#     async def count_tokens(self, text: str) -> int:
#         # Implementation specific to the concrete LLM provider
#         raise NotImplementedError  # pragma: no cover
#
#     async def get_model_info(self) -> Dict[str, Any]:
#         # Implementation specific to the concrete LLM provider
#         raise NotImplementedError  # pragma: no cover
