# توثيق وحدة BaseAgent Core

**النسخة:** 1.0
**التاريخ:** 14 يوليو 2026
**المؤلف:** Manus AI

## 1. مقدمة

توضح هذه الوثيقة تفاصيل تصميم وتنفيذ وحدة `BaseAgent Core`، وهي اللبنة الأساسية لجميع العملاء الذكيين في منصة "بصيرة". توفر هذه الوحدة الهيكل المشترك والوظائف الأساسية التي تمكن العملاء الذكيين من إدارة دورة حياتهم، التفاعل مع الذاكرة، استخدام الأدوات، والتواصل مع نماذج اللغة الكبيرة (LLMs).

## 2. الغرض

الغرض الرئيسي من `BaseAgent Core` هو:
*   توفير أساس موحد وقابل للتوسع لجميع العملاء الذكيين.
*   ضمان الاتساق في سلوك العملاء الذكيين وإدارتهم.
*   تجريد التعقيدات المشتركة مثل إدارة الحالة، الذاكرة، وتفاعل LLM.
*   تسهيل عملية تطوير عملاء ذكيين متخصصين من خلال توفير وظائف أساسية جاهزة للاستخدام.

## 3. المسؤوليات الرئيسية لـ BaseAgent

`BaseAgent` مسؤول عن إدارة الجوانب التالية:

*   **إدارة دورة حياة العميل:** التهيئة، التفعيل، الإيقاف المؤقت، والإنهاء.
*   **إدارة الحالة:** تتبع الحالة التشغيلية الحالية للعميل (initialized, active, paused, terminated).
*   **إدارة الذاكرة:** توفير آليات لتخزين واسترجاع المعلومات (ذاكرة قصيرة وطويلة المدى).
*   **إدارة الأدوات:** تسجيل واستدعاء الأدوات الخارجية التي يمكن للعميل استخدامها.
*   **طبقة تجريد LLM:** توفير واجهة موحدة للتفاعل مع نماذج اللغة الكبيرة المختلفة.
*   **التسجيل (Logging):** تسجيل الأحداث الهامة والعمليات لتسهيل المراقبة وتتبع الأخطاء.
*   **معالجة الأخطاء:** توفير آليات أساسية للتعامل مع الأخطاء.

## 4. هيكل الوحدة

تتكون وحدة `BaseAgent Core` من الملف الرئيسي `base_agent.py`.

### 4.1 `base_agent.py`

يحتوي هذا الملف على الصنف `BaseAgent`، والذي يتضمن الخصائص والوظائف التالية:

#### 4.1.1 الخصائص (Attributes)

| الخاصية | النوع | الوصف |
|---|---|---|
| `agent_id` | `str` | معرف فريد للعميل (UUID). |
| `name` | `str` | اسم العميل. |
| `description` | `str` | وصف موجز لوظيفة العميل. |
| `created_at` | `datetime` | تاريخ ووقت إنشاء العميل. |
| `status` | `str` | الحالة التشغيلية الحالية للعميل (initialized, active, paused, terminated). |
| `memory` | `Dict[str, Any]` | قاموس لتخزين بيانات الذاكرة (قصيرة وطويلة المدى). |
| `tools` | `Dict[str, Any]` | قاموس لتخزين الأدوات المتاحة للعميل. |
| `llm_client` | `Any` | كائن عميل طبقة تجريد LLM للتفاعل مع نماذج اللغة. |

#### 4.1.2 الوظائف (Methods)

| الوظيفة | الوصف |
|---|---|
| `__init__` | مهيئ الصنف، يقوم بتهيئة الخصائص الأساسية للعميل. |
| `_load_config` | (Placeholder) لتحميل التكوينات الخاصة بالعميل. |
| `_initialize_memory` | (Placeholder) لتهيئة نظام الذاكرة. |
| `_initialize_tools` | (Placeholder) لتهيئة الأدوات المتاحة للعميل. |
| `_initialize_llm_client` | (Placeholder) لتهيئة عميل طبقة تجريد LLM. |
| `activate` | يقوم بتفعيل العميل، ويجعله جاهزاً لمعالجة المهام. |
| `pause` | يقوم بإيقاف العميل مؤقتاً. |
| `terminate` | يقوم بإنهاء العميل وتحرير الموارد. |
| `process_task` | (Abstract) يجب أن يتم تنفيذها بواسطة العملاء المتخصصين لمعالجة المهام. |
| `_reason` | (Placeholder) يمثل خط أنابيب التفكير والاستدلال للعميل. |
| `_call_tool` | (Placeholder) لاستدعاء أداة خارجية متاحة للعميل. |
| `_interact_with_llm` | (Placeholder) للتفاعل مع طبقة تجريد LLM. |
| `get_status` | يعيد الحالة التشغيلية الحالية للعميل. |
| `get_info` | يعيد معلومات أساسية عن العميل. |

## 5. اختبارات الوحدات (Unit Tests)

تم توفير تغطية شاملة لاختبارات الوحدات لوحدة `BaseAgent Core` في الملف `tests/unit/core/base_agent/test_base_agent.py`. تغطي هذه الاختبارات:

*   التهيئة الصحيحة للعميل.
*   سلوك وظائف `activate`, `pause`, `terminate`.
*   التعامل مع الأخطاء المتوقعة (مثل استدعاء `process_task` قبل التفعيل).
*   التحقق من وظائف `get_status` و `get_info`.
*   التحقق من سلوك الـ placeholders للوظائف الداخلية مثل `_reason`, `_call_tool`, `_interact_with_llm`.

## 6. الاعتماديات (Dependencies)

تعتمد وحدة `BaseAgent Core` على مكتبات Python القياسية التالية:

*   `uuid` (لتوليد معرفات فريدة)
*   `logging` (للتسجيل)
*   `datetime` (لإدارة التواريخ والأوقات)
*   `typing` (لدعم Type Hinting)

## 7. الاستخدام

يجب على أي عميل ذكي متخصص يرغب في الاستفادة من الوظائف الأساسية لـ `BaseAgent` أن يرث من الصنف `BaseAgent` ويقوم بتنفيذ وظيفة `process_task` الخاصة به.

```python
from src.core.base_agent.base_agent import BaseAgent

class SpecializedAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(name="SpecializedAgent", description="وكيل متخصص", **kwargs)

    def process_task(self, task_data: dict) -> Any:
        # منطق معالجة المهام الخاص بالوكيل المتخصص
        self.memory["short_term"].append(f"Processed task: {task_data['task_id']}")
        response = self._interact_with_llm([{"role": "user", "content": task_data["query"]}])
        tool_result = self._call_tool("some_tool", input=response)
        return f"Specialized agent processed task {task_data['task_id']} with result: {tool_result}"

# مثال على الاستخدام
if __name__ == "__main__":
    agent = SpecializedAgent()
    agent.activate()
    result = agent.process_task({"task_id": "SA-001", "query": "ما هو سعر سهم أرامكو؟"})
    print(result)
```

## 8. التطور المستقبلي

سيتم توسيع `BaseAgent Core` في المستقبل ليشمل:

*   تكامل فعلي مع طبقة تجريد LLM.
*   تكامل مع نظام إدارة الذاكرة المتقدم (Knowledge Graph, Vector DB).
*   تكامل مع نظام استدعاء الأدوات الفعلي.
*   دعم آليات التفكير والاستدلال الأكثر تعقيداً.
*   تكامل مع نظام المراقبة والتسجيل المركزي للمنصة.
