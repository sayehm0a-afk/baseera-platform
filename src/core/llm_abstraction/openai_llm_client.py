"""
تطبيق عميل OpenAI LLM لمنصة بصيرة.
يوفر واجهة للتعامل مع نماذج OpenAI LLM.
"""
import logging
import os
import asyncio
from typing import Dict, Any, List, Optional
from openai import AsyncOpenAI
from src.core.llm_abstraction.base_llm_client import BaseLLMClient

logger = logging.getLogger(__name__)

class OpenAILLMClient(BaseLLMClient):
    """
    عميل OpenAI LLM الذي يطبق واجهة BaseLLMClient.
    يتعامل مع التفاعل مع واجهة برمجة تطبيقات OpenAI.
    """

    def __init__(self, model_name: str, config: Optional[Dict[str, Any]] = None):
        super().__init__(model_name, config)
        self.api_key = os.getenv("OPENAI_API_KEY")
        if not self.api_key:
            raise ValueError("OPENAI_API_KEY environment variable not set.")
        self.client = AsyncOpenAI(api_key=self.api_key)
        logger.info("OpenAILLMClient initialized for model: %s", self.model_name)

    async def generate_response(self, messages: List[Dict[str, str]], **kwargs) -> Dict[str, Any]:
        """
        ينشئ استجابة من نموذج OpenAI LLM.
        """
        try:
            response = await self._handle_retry(self.client.chat.completions.create,
                                                model=self.model_name,
                                                messages=messages,
                                                **kwargs)
            if response and response.choices:
                return {
                    "content": response.choices[0].message.content,
                    "role": response.choices[0].message.role,
                    "finish_reason": response.choices[0].finish_reason,
                    "usage": response.usage.model_dump() if response.usage else None,
                    "model": response.model
                }
            return {"content": "", "role": "assistant", "finish_reason": "no_response"}
        except Exception as e:
            logger.error("Error generating response from OpenAI: %s", e)
            raise

    async def count_tokens(self, text: str) -> int:
        """
        يحسب عدد التوكنات في نص معين باستخدام مكتبة tiktoken.
        ملاحظة: يتطلب تثبيت `tiktoken`.
        """
        try:
            import tiktoken
            encoding = tiktoken.encoding_for_model(self.model_name)
            return len(encoding.encode(text))
        except ImportError:
            logger.warning("tiktoken not installed. Cannot accurately count tokens.")
            # Fallback to a rough estimate if tiktoken is not available
            return len(text.split()) * 4 // 3 # Rough estimate
        except Exception as e:
            logger.error("Error counting tokens with tiktoken: %s", e)
            return len(text.split()) * 4 // 3 # Fallback

    async def get_model_info(self) -> Dict[str, Any]:
        """
        يحصل على معلومات حول نموذج OpenAI.
        (هذه معلومات تقريبية ويجب تحديثها من وثائق OpenAI الرسمية).
        """
        # Placeholder for actual model info retrieval. In a real scenario, this would query OpenAI API
        # or a local configuration for up-to-date pricing and limits.
        info = {
            "model_name": self.model_name,
            "provider": "OpenAI",
            "pricing_input_per_1k_tokens": 0.0015, # Example for gpt-3.5-turbo
            "pricing_output_per_1k_tokens": 0.002, # Example for gpt-3.5-turbo
            "max_tokens": 4096, # Example for gpt-3.5-turbo
            "description": "نموذج لغة كبير من OpenAI."
        }
        # Attempt to get more specific info if available (e.g., from a config file or API call)
        if self.model_name.startswith("gpt-4"):
            info["pricing_input_per_1k_tokens"] = 0.03
            info["pricing_output_per_1k_tokens"] = 0.06
            info["max_tokens"] = 8192
        elif self.model_name.startswith("gpt-3.5"):
            info["pricing_input_per_1k_tokens"] = 0.0005
            info["pricing_output_per_1k_tokens"] = 0.0015
            info["max_tokens"] = 16385 # For gpt-3.5-turbo-0125
        return info

# Example Usage (for testing purposes)
async def main():
    os.environ["OPENAI_API_KEY"] = "sk-YOUR_OPENAI_API_KEY" # Replace with actual key or set env var
    client = OpenAILLMClient(model_name="gpt-3.5-turbo")
    messages = [
        {"role": "system", "content": "أنت مساعد ذكاء اصطناعي مفيد."},
        {"role": "user", "content": "ما هي عاصمة المملكة العربية السعودية؟"}
    ]
    response = await client.generate_response(messages)
    print(f"Response: {response['content']}")

    tokens = await client.count_tokens("هذا نص تجريبي لحساب التوكنات.")
    print(f"Tokens: {tokens}")

    info = await client.get_model_info()
    print(f"Model Info: {info}")

if __name__ == "__main__":
    asyncio.run(main())
