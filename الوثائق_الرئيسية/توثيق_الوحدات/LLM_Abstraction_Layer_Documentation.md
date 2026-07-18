# توثيق وحدة LLM Abstraction Layer

## 1. نظرة عامة
توفر وحدة `LLM Abstraction Layer` طبقة تجريد موحدة للتعامل مع نماذج اللغة الكبيرة (LLMs)، مما يتيح للمنصة التبديل بين المزودين المختلفين (مثل OpenAI، Anthropic، أو نماذج محلية) بسهولة ومرونة. تهدف هذه الطبقة إلى فصل منطق الأعمال عن تفاصيل تنفيذ نماذج LLM، مما يضمن قابلية التوسع والصيانة للمنصة.

## 2. المكونات الرئيسية

### 2.1. `BaseLLMClient` (src/core/llm_abstraction/base_llm_client.py)
*   **النوع:** واجهة برمجية مجردة (Abstract Base Class).
*   **الغرض:** تحدد الواجهة القياسية التي يجب أن تلتزم بها جميع تطبيقات عملاء LLM. تضمن وجود وظائف أساسية مثل `generate_response`, `count_tokens`, و `get_model_info`.
*   **الميزات:**
    *   **`generate_response(messages, **kwargs)`:** لإنشاء استجابة من نموذج LLM.
    *   **`count_tokens(text)`:** لحساب عدد التوكنات في نص معين.
    *   **`get_model_info()`:** للحصول على معلومات حول النموذج (مثل التكاليف وحدود التوكنات).
    *   **`_handle_retry()`:** آلية إعادة محاولة افتراضية قابلة للتخصيص لتعزيز المرونة ضد الأخطاء المؤقتة.

### 2.2. `OpenAILLMClient` (src/core/llm_abstraction/openai_llm_client.py)
*   **النوع:** تطبيق ملموس (Concrete Implementation).
*   **الغرض:** يوفر تطبيقاً لواجهة `BaseLLMClient` للتعامل مع نماذج OpenAI LLM.
*   **الميزات:**
    *   يتكامل مع مكتبة `openai` (AsyncOpenAI) للتفاعل غير المتزامن.
    *   يستخدم `tiktoken` لحساب التوكنات بدقة.
    *   يدعم متغير البيئة `OPENAI_API_KEY` لإدارة مفتاح API بشكل آمن.
    *   يتضمن منطقاً تقريبياً لاسترجاع معلومات النموذج والتكاليف (يمكن توسيعه لاحقاً لاستعلام API).

## 3. تدفق البيانات والتفاعل

1.  **العميل الذكي (Agent):** يستدعي وظائف `BaseLLMClient` (مثل `generate_response`).
2.  **طبقة التجريد:** تقوم بتوجيه الاستدعاء إلى التطبيق المحدد (مثلاً `OpenAILLMClient`).
3.  **تطبيق LLM:** يتفاعل مع واجهة برمجة تطبيقات المزود الخارجي (مثلاً OpenAI API).
4.  **الاستجابة:** يتم معالجة الاستجابة وإعادتها بتنسيق موحد إلى العميل الذكي.

## 4. الميزات الرئيسية
*   **المرونة:** سهولة إضافة أو تبديل مزودي LLM دون التأثير على العملاء الذكيين.
*   **إدارة التكاليف:** توفير وظائف لحساب التوكنات ومعلومات التسعير للمساعدة في مراقبة التكاليف.
*   **الموثوقية:** آلية إعادة المحاولة المدمجة تزيد من موثوقية التفاعلات مع LLMs.
*   **الأمان:** استخدام متغيرات البيئة لمفاتيح API يقلل من مخاطر تسريب البيانات الحساسة.

## 5. الاعتماديات
*   `openai` (لـ `OpenAILLMClient`)
*   `tiktoken` (لحساب التوكنات بدقة)

## 6. الاستخدام

```python
import asyncio
import os
from src.core.llm_abstraction.openai_llm_client import OpenAILLMClient

async def example_usage():
    # يجب تعيين مفتاح API كمتغير بيئة
    os.environ["OPENAI_API_KEY"] = "your_openai_api_key"

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
    asyncio.run(example_usage())
```

## 7. التطور المستقبلي
*   إضافة تطبيقات لعملاء LLM آخرين (مثل Anthropic, Google Gemini).
*   تطوير طبقة توجيه ديناميكية لاختيار أفضل نموذج LLM بناءً على المهمة والتكلفة والأداء.
*   دمج آليات التخزين المؤقت (Caching) لتحسين الأداء وتقليل التكاليف.
