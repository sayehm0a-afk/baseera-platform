# Module 3.5: Runtime Technical Design

## 1. المقدمة

تُقدم هذه الوثيقة التصميم الفني الشامل لمحرك التشغيل والتنسيق (Runtime & Orchestration) لمنصة "بصيرة". الهدف الأساسي من هذا التصميم هو القضاء على أي غموض معماري قبل البدء في تنفيذ الوحدة الرابعة، مما يضمن بناء نظام قوي، قابل للتوسع، وموثوق به. يغطي هذا التصميم الجوانب الرئيسية لمحرك التشغيل، بما في ذلك المخططات المعمارية، عقود الأحداث والرسائل، نماذج الجدولة والتنفيذ، استراتيجيات إعادة المحاولة، عقود الذاكرة، نموذج الصلاحيات، وعقود واجهة برمجة التطبيقات، بالإضافة إلى سجل قرارات التصميم المعمارية (ADRs).

تم تصميم هذا المحرك ليكون العمود الفقري الذي يربط بين الوكلاء الأذكياء والأدوات، ويدير سير العمل المعقدة، ويضمن التفاعل السلس والآمن بين جميع مكونات المنصة.

## 2. المخططات المعمارية الشاملة

### 2.1 مخطط الفئات عالي المستوى (High-Level Class Diagram)

يوضح هذا المخطط المكونات الرئيسية لمحرك التشغيل والتنسيق وعلاقاتها.

![Runtime & Orchestration High-Level Class Diagram](/home/ubuntu/بصيرة/docs/runtime_orchestration_uml.png)

### 2.2 مخطط تسلسل دورة حياة سير العمل (Workflow Lifecycle Sequence Diagram)

يوضح هذا المخطط تدفق التفاعل بين المكونات المختلفة أثناء تنفيذ سير عمل نموذجي.

![Workflow Lifecycle Sequence Diagram](/home/ubuntu/بصيرة/docs/workflow_lifecycle_sequence.png)

### 2.3 مخطط حالة تنفيذ سير العمل (Workflow Execution State Machine Diagram)

يوضح هذا المخطط الحالات المختلفة التي يمر بها سير العمل أثناء التنفيذ والانتقالات بين هذه الحالات.

![Workflow Execution State Machine Diagram](/home/ubuntu/بصيرة/docs/workflow_state_machine.png)

## 3. عقود الأحداث ومخططات الرسائل

### 3.1 عقود الأحداث (Event Contracts)

تُعد عقود الأحداث حجر الزاوية في نظام المراسلة الداخلي، حيث تحدد بنية وتوقعات الأحداث التي يتم نشرها واستهلاكها داخل المنصة. تضمن هذه العقود الاتساق، قابلية التوسع، وسهولة التكامل بين المكونات المختلفة.

#### 3.1.1 مبادئ تصميم عقود الأحداث

-   **محددة بوضوح (Well-defined):** يجب أن يكون لكل حدث غرض واضح وبنية محددة.
-   **غير قابلة للتغيير (Immutable):** بمجرد نشر الحدث، لا يمكن تعديله.
-   **قابلة للتوسع (Extensible):** يجب أن تسمح العقود بإضافة حقول جديدة دون كسر التوافق مع الإصدارات السابقة.
-   **موثقة (Documented):** توثيق شامل لكل حدث، بما في ذلك الغرض، الحقول، والقيم المحتملة.

#### 3.1.2 بنية الحدث الأساسية (Base Event Structure)

جميع الأحداث ستتبع بنية أساسية موحدة لضمان سهولة التتبع والمعالجة:

```json
{
  "event_id": "<UUID>",
  "event_type": "<string>",
  "timestamp": "<ISO 8601 datetime>",
  "source": "<string>",
  "correlation_id": "<UUID>",
  "task_id": "<UUID>",
  "agent_id": "<string>",
  "payload": {
    // Event-specific data
  }
}
```

| الحقل | النوع | الوصف |
|---|---|---|
| `event_id` | `UUID` | معرف فريد للحدث. |
| `event_type` | `string` | نوع الحدث (مثال: `TaskCreated`, `AgentActivated`, `ToolExecuted`). |
| `timestamp` | `ISO 8601 datetime` | وقت إنشاء الحدث بتنسيق UTC. |
| `source` | `string` | المكون الذي قام بنشر الحدث (مثال: `OrchestrationEngine`, `AgentRuntime`, `ToolRegistry`). |
| `correlation_id` | `UUID` | معرف يستخدم لتتبع سلسلة من الأحداث المتعلقة بعملية واحدة عبر مكونات متعددة. |
| `task_id` | `UUID` | معرف المهمة التي يرتبط بها الحدث. |
| `agent_id` | `string` | معرف الوكيل الذي يرتبط به الحدث (اختياري، حسب نوع الحدث). |
| `payload` | `object` | البيانات الخاصة بالحدث. |

#### 3.1.3 أمثلة على عقود الأحداث

**`TaskCreated` Event:** يتم نشره عندما يتم إنشاء مهمة جديدة في النظام.

```json
{
  "event_id": "a1b2c3d4-e5f6-7890-1234-567890abcdef",
  "event_type": "TaskCreated",
  "timestamp": "2026-07-14T10:30:00Z",
  "source": "SupervisorAgent",
  "correlation_id": "f0e9d8c7-b6a5-4321-fedc-ba9876543210",
  "task_id": "f0e9d8c7-b6a5-4321-fedc-ba9876543210",
  "agent_id": null,
  "payload": {
    "task_name": "Analyze Stock X",
    "description": "Perform a comprehensive analysis of stock X for investment recommendation.",
    "priority": "HIGH",
    "requester_id": "user-123"
  }
}
```

**`AgentActivated` Event:** يتم نشره عندما يتم تفعيل وكيل بنجاح.

```json
{
  "event_id": "1a2b3c4d-5e6f-7890-abcd-ef1234567890",
  "event_type": "AgentActivated",
  "timestamp": "2026-07-14T10:31:00Z",
  "source": "AgentRuntime",
  "correlation_id": "f0e9d8c7-b6a5-4321-fedc-ba9876543210",
  "task_id": "f0e9d8c7-b6a5-4321-fedc-ba9876543210",
  "agent_id": "financial-analyst-agent-1",
  "payload": {
    "agent_type": "FinancialAnalystAgent",
    "status": "ACTIVE"
  }
}
```

**`ToolExecuted` Event:** يتم نشره بعد تنفيذ أداة بنجاح أو فشل.

```json
{
  "event_id": "98765432-10ab-cdef-1234-567890abcdef",
  "event_type": "ToolExecuted",
  "timestamp": "2026-07-14T10:35:00Z",
  "source": "ToolCallingFramework",
  "correlation_id": "f0e9d8c7-b6a5-4321-fedc-ba9876543210",
  "task_id": "f0e9d8c7-b6a5-4321-fedc-ba9876543210",
  "agent_id": "financial-analyst-agent-1",
  "payload": {
    "tool_name": "GetStockData",
    "inputs": {"symbol": "TASI"},
    "output": {"price": 120.50, "volume": 1000000},
    "status": "SUCCESS",
    "duration_ms": 150
  }
}
```

#### 3.1.4 إدارة إصدارات العقود (Contract Versioning)

سيتم استخدام استراتيجية "التوافق مع الإصدارات السابقة" (Backward Compatibility) قدر الإمكان. في حالة التغييرات الجوهرية التي تكسر التوافق، سيتم تقديم إصدارات جديدة للحدث (`event_type_v2`)، وسيتم استخدام `event_type` في بنية الحدث الأساسية للإشارة إلى الإصدار. سيتم توثيق جميع التغييرات في سجل التغييرات (Changelog) الخاص بالعقود.

### 3.2 مخططات الرسائل (Message Schemas)

بالإضافة إلى الأحداث، يتواصل النظام أيضاً عبر الأوامر (Commands) والطلبات/الردود (Requests/Responses). تختلف هذه عن الأحداث في أنها موجهة لمكون معين وتتوقع استجابة أو إجراءً محدداً.

#### 3.2.1 بنية الأمر الأساسية (Base Command Structure)

```json
{
  "command_id": "<UUID>",
  "command_type": "<string>",
  "timestamp": "<ISO 8601 datetime>",
  "source": "<string>",
  "target": "<string>",
  "correlation_id": "<UUID>",
  "task_id": "<UUID>",
  "agent_id": "<string>",
  "payload": {
    // Command-specific data
  }
}
```

| الحقل | النوع | الوصف |
|---|---|---|
| `command_id` | `UUID` | معرف فريد للأمر. |
| `command_type` | `string` | نوع الأمر (مثال: `StartAgent`, `ExecuteTool`, `PauseWorkflow`). |
| `timestamp` | `ISO 8601 datetime` | وقت إنشاء الأمر بتنسيق UTC. |
| `source` | `string` | المكون الذي قام بإرسال الأمر. |
| `target` | `string` | المكون المستهدف للأمر. |
| `correlation_id` | `UUID` | معرف يستخدم لتتبع سلسلة من العمليات. |
| `task_id` | `UUID` | معرف المهمة التي يرتبط بها الأمر. |
| `agent_id` | `string` | معرف الوكيل الذي يرتبط به الأمر (اختياري). |
| `payload` | `object` | البيانات الخاصة بالأمر. |

#### 3.2.2 بنية الطلب/الرد الأساسية (Base Request/Response Structure)

تُستخدم للاتصالات المتزامنة أو التي تتطلب استجابة مباشرة.

**بنية الطلب (Request Structure):**

```json
{
  "request_id": "<UUID>",
  "request_type": "<string>",
  "timestamp": "<ISO 8601 datetime>",
  "source": "<string>",
  "target": "<string>",
  "correlation_id": "<UUID>",
  "task_id": "<UUID>",
  "agent_id": "<string>",
  "payload": {
    // Request-specific data
  }
}
```

**بنية الرد (Response Structure):**

```json
{
  "response_id": "<UUID>",
  "request_id": "<UUID>",
  "response_type": "<string>",
  "timestamp": "<ISO 8601 datetime>",
  "source": "<string>",
  "target": "<string>",
  "correlation_id": "<UUID>",
  "task_id": "<UUID>",
  "agent_id": "<string>",
  "status": "<string>", // SUCCESS, FAILED, PENDING
  "payload": {
    // Response-specific data
  },
  "error": {
    "code": "<string>",
    "message": "<string>"
  }
}
```

| الحقل | النوع | الوصف |
|---|---|---|
| `response_id` | `UUID` | معرف فريد للرد. |
| `request_id` | `UUID` | معرف الطلب الذي يرتبط به هذا الرد. |
| `response_type` | `string` | نوع الرد (مثال: `AgentStatusResponse`, `ToolExecutionResponse`). |
| `timestamp` | `ISO 8601 datetime` | وقت إنشاء الرد بتنسيق UTC. |
| `source` | `string` | المكون الذي قام بإرسال الرد. |
| `target` | `string` | المكون المستهدف للرد. |
| `correlation_id` | `UUID` | معرف يستخدم لتتبع سلسلة من العمليات. |
| `task_id` | `UUID` | معرف المهمة التي يرتبط بها الرد. |
| `agent_id` | `string` | معرف الوكيل الذي يرتبط به الرد (اختياري). |
| `status` | `string` | حالة الرد (`SUCCESS`, `FAILED`, `PENDING`). |
| `payload` | `object` | البيانات الخاصة بالرد. |
| `error` | `object` | تفاصيل الخطأ في حالة الفشل. |

## 4. نموذج الجدولة (Scheduling Model)

يعتمد نموذج الجدولة على `TaskQueueScheduler` لإدارة وتنفيذ المهام بكفاءة وموثوقية. يهدف إلى توفير تحكم دقيق في توقيت تنفيذ المهام، أولوياتها، وكيفية التعامل مع حالات الفشل.

### 4.1 مكونات نموذج الجدولة

-   **Task Definition:** يحدد كل مهمة بخصائصها (ID, Type, Payload, Priority, Timeout, Max Retries).
-   **Task Queue:** قائمة انتظار دائمة للمهام، تدعم الأولويات.
-   **Scheduler:** مسؤول عن سحب المهام من قائمة الانتظار وتوزيعها على `Worker Agents` أو `Orchestration Engine` بناءً على الجدولة، التزامن، وتوفر الموارد.
-   **Worker Pool:** مجموعة من `Worker Agents` أو خيوط التنفيذ المتاحة لتنفيذ المهام.

### 4.2 خصائص المهام (Task Properties)

| الخاصية | النوع | الوصف |
|---|---|---|
| `task_id` | `UUID` | معرف فريد للمهمة. |
| `task_type` | `string` | نوع المهمة (مثال: `ExecuteAgentStep`, `RunTool`). |
| `payload` | `object` | البيانات المدخلة للمهمة. |
| `priority` | `enum` | أولوية المهمة (`LOW`, `MEDIUM`, `HIGH`, `CRITICAL`). |
| `timeout` | `integer` | أقصى وقت مسموح به لتنفيذ المهمة بالثواني. |
| `max_retries` | `integer` | الحد الأقصى لعدد محاولات إعادة تنفيذ المهمة في حالة الفشل. |
| `current_retries` | `integer` | عدد المحاولات الحالية. |
| `status` | `enum` | حالة المهمة (`PENDING`, `RUNNING`, `COMPLETED`, `FAILED`, `CANCELLED`, `RETRYING`). |
| `scheduled_for` | `ISO 8601 datetime` | الوقت المجدول لتنفيذ المهمة (للمهام المؤجلة). |
| `created_at` | `ISO 8601 datetime` | وقت إنشاء المهمة. |
| `updated_at` | `ISO 8601 datetime` | آخر وقت تم فيه تحديث المهمة. |

### 4.3 آليات الجدولة

-   **الجدولة الفورية (Immediate Scheduling):** المهام ذات الأولوية العالية أو المهام التي لا تتطلب تأخيراً يتم إرسالها للتنفيذ فوراً.
-   **الجدولة المؤجلة (Delayed Scheduling):** المهام التي يجب تنفيذها في وقت محدد في المستقبل.
-   **الجدولة المتكررة (Recurring Scheduling):** المهام التي تتكرر على فترات منتظمة (مثال: كل ساعة، يومياً).

### 4.4 التعامل مع حالات الفشل (Failure Handling)

-   **Retry with Backoff:** في حالة فشل المهمة، يتم إعادة جدولتها مع استراتيجية تراجع أسية (Exponential Backoff) لتقليل الحمل على النظام المستهدف.
-   **Dead-Letter Queue (DLQ):** المهام التي تستنفد جميع محاولات إعادة التنفيذ أو تفشل بشكل متكرر يتم نقلها إلى `DLQ` لمراجعتها يدوياً أو معالجتها بشكل خاص.
-   **Cancellation:** دعم إلغاء المهام الجارية أو المجدولة.

## 5. نموذج التنفيذ (Execution Model)

يحدد نموذج التنفيذ كيفية معالجة المهام والعمليات داخل المنصة، مع التركيز على التزامن، الموثوقية، وكفاءة استخدام الموارد.

### 5.1 مبادئ التنفيذ

-   **التنفيذ غير المتزامن (Asynchronous Execution):** جميع العمليات الطويلة الأمد (مثل استدعاءات LLM، تنفيذ الأدوات) يجب أن تكون غير متزامنة لتجنب حظر خيوط التنفيذ.
-   **الفصل بين المهام (Task Isolation):** يجب أن يتم تنفيذ كل مهمة في بيئة معزولة قدر الإمكان لتقليل التأثير الجانبي للفشل.
-   **قابلية الاستئناف (Resumability):** يجب أن تكون سير العمل والمهام قابلة للاستئناف بعد الانقطاع أو إعادة التشغيل.

### 5.2 تدفق التنفيذ الأساسي

1.  **استلام المهمة:** يتلقى `OrchestrationEngine` أو `AgentRuntime` مهمة جديدة.
2.  **التحقق من الصلاحيات:** يتم التحقق من صلاحيات الوكيل أو المكون لتنفيذ المهمة المطلوبة.
3.  **الجدولة:** يتم إضافة المهمة إلى `TaskQueue` بواسطة `TaskQueueScheduler`.
4.  **التوزيع:** يقوم `Scheduler` بسحب المهام الجاهزة للتنفيذ وتوزيعها على `Worker Agents` أو مكونات التنفيذ المناسبة.
5.  **التنفيذ:** يقوم `Worker Agent` بتنفيذ المهمة، والتي قد تتضمن:
    -   استدعاء LLM عبر `LLM Abstraction Layer`.
    -   استدعاء أداة عبر `Tool Calling Framework`.
    -   التفاعل مع `Memory Engine`.
    -   نشر أحداث عبر `Internal Messaging`.
6.  **تتبع الحالة:** يتم تحديث حالة المهمة باستمرار في `WorkflowEngine` أو `AgentRuntime`.
7.  **التعامل مع الأخطاء:** في حالة الفشل، يتم تطبيق استراتيجية إعادة المحاولة أو نقل المهمة إلى `DLQ`.
8.  **الإبلاغ عن النتيجة:** يتم إبلاغ `SupervisorAgent` أو المكون الأصلي بنتيجة المهمة (نجاح/فشل).

## 6. استراتيجية إعادة المحاولة (Retry Strategy)

تُعد استراتيجية إعادة المحاولة جزءًا أساسيًا من نموذج الموثوقية، حيث تضمن قدرة النظام على التعافي من الأخطاء العابرة دون تدخل يدوي. سيتم تطبيق هذه الاستراتيجية على مستوى `TaskQueueScheduler` وعلى مستوى استدعاءات الخدمات الخارجية (مثل LLMs و APIs).

### 6.1 مبادئ استراتيجية إعادة المحاولة

-   **الأخطاء العابرة فقط:** يجب أن يتم إعادة المحاولة فقط للأخطاء التي يُحتمل أن تُحل بإعادة المحاولة (مثل أخطاء الشبكة، تجاوز حدود المعدل، أخطاء الخادم المؤقتة).
-   **الحد الأقصى للمحاولات:** يجب تحديد حد أقصى لعدد محاولات إعادة المحاولة لتجنب الحلقات اللانهائية.
-   **التراجع (Backoff):** استخدام استراتيجية تراجع لزيادة الفاصل الزمني بين المحاولات المتتالية.

### 6.2 أنواع استراتيجيات التراجع (Backoff Strategies)

-   **التراجع الأسي (Exponential Backoff):** زيادة الفاصل الزمني بشكل أسي بين المحاولات (مثال: 1s, 2s, 4s, 8s...). هذه هي الاستراتيجية الافتراضية والمفضلة.
-   **التراجع الخطي (Linear Backoff):** زيادة الفاصل الزمني بشكل خطي (مثال: 1s, 2s, 3s, 4s...). تُستخدم في حالات خاصة.
-   **التراجع الثابت (Fixed Backoff):** فاصل زمني ثابت بين المحاولات. تُستخدم لمهام معينة.

### 6.3 آلية إعادة المحاولة

1.  **اكتشاف الخطأ:** يتم اكتشاف خطأ عابر أثناء تنفيذ مهمة أو استدعاء خدمة.
2.  **التحقق من قابلية إعادة المحاولة:** يتم التحقق مما إذا كان الخطأ من النوع الذي يمكن إعادة محاولته.
3.  **زيادة عداد المحاولات:** يتم زيادة عداد `current_retries` للمهمة.
4.  **التحقق من الحد الأقصى:** إذا كان `current_retries` أقل من `max_retries`:
    -   يتم حساب الفاصل الزمني للتراجع بناءً على الاستراتيجية المختارة.
    -   يتم إعادة جدولة المهمة في `TaskQueueScheduler` لتُنفذ بعد الفاصل الزمني المحسوب.
5.  **فشل دائم:** إذا تم استنفاد `max_retries`، يتم وضع المهمة في `Dead-Letter Queue` أو يتم الإبلاغ عن فشل دائم.

## 7. عقود الذاكرة (Memory Contracts)

تحدد عقود الذاكرة الواجهات الموحدة للتفاعل مع أنظمة الذاكرة قصيرة وطويلة المدى، مما يضمن الاتساق ويمنع تسرب البيانات أو السياق بين المهام والوكلاء.

### 7.1 مبادئ عقود الذاكرة

-   **عزل السياق (Context Isolation):** يجب أن يكون لكل مهمة سياقها الخاص في الذاكرة قصيرة المدى.
-   **واجهات واضحة:** يجب أن تكون الواجهات بسيطة ومحددة بوضوح لعمليات القراءة والكتابة والتحديث.
-   **المرونة:** يجب أن تسمح العقود بتغيير التنفيذ الأساسي للذاكرة (مثل Redis, Pinecone) دون التأثير على منطق الوكيل.

### 7.2 الذاكرة قصيرة المدى (Short-term Memory Contracts)

تُستخدم لتخزين السياق الحالي للمحادثة أو المهمة (Context Window).

#### 7.2.1 واجهة `IShortTermMemory`

```python
class IShortTermMemory(ABC):
    @abstractmethod
    async def get_context(self, task_id: str) -> Dict[str, Any]:
        """يسترجع السياق الحالي لمهمة معينة."""
        pass

    @abstractmethod
    async def set_context(self, task_id: str, context: Dict[str, Any]):
        """يحدد أو يحدّث السياق لمهمة معينة."""
        pass

    @abstractmethod
    async def append_to_context(self, task_id: str, key: str, value: Any):
        """يضيف بيانات إلى حقل معين في سياق المهمة."""
        pass

    @abstractmethod
    async def clear_context(self, task_id: str):
        """يمسح السياق لمهمة معينة."""
        pass

    @abstractmethod
    async def get_token_count(self, task_id: str) -> int:
        """يسترجع عدد الرموز في السياق الحالي للمهمة."""
        pass
```

### 7.3 الذاكرة طويلة المدى (Long-term Memory Contracts)

تُستخدم لتخزين المعرفة الدائمة، الخبرات السابقة، والبيانات التاريخية.

#### 7.3.1 واجهة `ILongTermMemory`

```python
class ILongTermMemory(ABC):
    @abstractmethod
    async def store_knowledge(self, agent_id: str, knowledge: Dict[str, Any], metadata: Optional[Dict[str, Any]] = None):
        """يخزن قطعة من المعرفة لوكيل معين."""
        pass

    @abstractmethod
    async def retrieve_knowledge(self, agent_id: str, query: str, top_k: int = 5) -> List[Dict[str, Any]]:
        """يسترجع المعرفة ذات الصلة لوكيل معين بناءً على استعلام."""
        pass

    @abstractmethod
    async def update_knowledge(self, knowledge_id: str, updates: Dict[str, Any]):
        """يحدّث قطعة معرفة موجودة."""
        pass

    @abstractmethod
    async def delete_knowledge(self, knowledge_id: str):
        """يحذف قطعة معرفة."""
        pass
```

## 8. نموذج الصلاحيات (Permission Model)

يحدد نموذج الصلاحيات كيفية التحكم في وصول الوكلاء إلى الأدوات والموارد، مما يضمن الأمان ويمنع التنفيذ غير المصرح به.

### 8.1 مبادئ نموذج الصلاحيات

-   **الحد الأدنى من الامتيازات (Principle of Least Privilege):** يجب أن يمتلك كل وكيل الحد الأدنى من الصلاحيات اللازمة لأداء وظيفته.
-   **التحكم القائم على الدور (Role-Based Access Control - RBAC):** يمكن تجميع الصلاحيات في أدوار، وتعيين الأدوار للوكلاء.
-   **التحقق الصريح:** يجب أن يتم التحقق من الصلاحيات بشكل صريح قبل كل عملية حساسة (مثل استدعاء أداة).

### 8.2 مكونات نموذج الصلاحيات

-   **Agent Roles:** أدوار محددة مسبقاً للوكلاء (مثال: `FinancialAnalyst`, `DataFetcher`, `ReportGenerator`).
-   **Tool Permissions:** قائمة بالأدوات المسموح بها لكل دور.
-   **Resource Permissions:** صلاحيات الوصول إلى الموارد (مثل قواعد البيانات، أنظمة الملفات).
-   **Permission Checker:** مكون مسؤول عن التحقق من الصلاحيات.

### 8.3 آلية التحقق من الصلاحيات

1.  **طلب عملية:** يقوم وكيل بطلب تنفيذ عملية تتطلب صلاحيات (مثال: `_call_tool`).
2.  **تحديد الصلاحية المطلوبة:** يتم تحديد الصلاحية المطلوبة للعملية (مثال: `can_execute_tool:GetStockData`).
3.  **استدعاء Permission Checker:** يتم استدعاء `PermissionChecker` مع `agent_id` والصلاحية المطلوبة.
4.  **التحقق من الدور/الصلاحية:** يقوم `PermissionChecker` بالتحقق مما إذا كان الوكيل يمتلك الدور الذي يمنح الصلاحية المطلوبة.
5.  **الاستجابة:** إذا كانت الصلاحية موجودة، يتم السماح بالعملية؛ وإلا، يتم رفضها ورفع استثناء `PermissionDeniedError`.

## 9. عقود واجهة برمجة التطبيقات (API Contracts)

تحدد عقود واجهة برمجة التطبيقات (API Contracts) الواجهات الموحدة للتفاعل مع الخدمات الخارجية والداخلية عبر HTTP أو بروتوكولات أخرى، مما يضمن الاتساق، قابلية الاكتشاف، وسهولة الاستخدام.

### 9.1 مبادئ عقود API

-   **محددة بوضوح (Well-defined):** يجب أن يكون لكل نقطة نهاية (endpoint) غرض واضح، مدخلات، ومخرجات محددة.
-   **مستقرة (Stable):** يجب أن تكون العقود مستقرة قدر الإمكان لتجنب كسر توافق العملاء.
-   **موثقة (Documented):** توثيق شامل لكل API، بما في ذلك نقاط النهاية، طرق HTTP، المدخلات، المخرجات، رموز الحالة، والأخطاء.
-   **التحقق من الصحة (Validation):** يجب أن يتم التحقق من صحة المدخلات والمخرجات لضمان سلامة البيانات.

### 9.2 بنية API الأساسية

سيتم استخدام OpenAPI Specification (Swagger) لتوثيق جميع واجهات برمجة التطبيقات، مما يوفر وصفاً قابلاً للقراءة آلياً وبشرياً.

### 9.3 أمثلة على عقود API

**`POST /api/v1/tasks` - إنشاء مهمة جديدة:**

-   **الوصف:** إنشاء مهمة جديدة ليتم معالجتها بواسطة `SupervisorAgent`.
-   **المدخلات (Request Body):**

    ```json
    {
      "task_name": "<string>",
      "description": "<string>",
      "priority": "<enum>", // HIGH, MEDIUM, LOW
      "requester_id": "<string>"
    }
    ```

-   **المخرجات (Response Body - 201 Created):**

    ```json
    {
      "task_id": "<UUID>",
      "status": "PENDING",
      "message": "Task created successfully."
    }
    ```

-   **الأخطاء (Error Responses):**
    -   `400 Bad Request`: إذا كانت المدخلات غير صالحة.
    -   `500 Internal Server Error`: لأي خطأ غير متوقع.

**`GET /api/v1/tasks/{task_id}` - استرجاع حالة مهمة:**

-   **الوصف:** استرجاع الحالة الحالية لمهمة معينة.
-   **المدخلات (Path Parameters):**
    -   `task_id`: `UUID` - معرف المهمة.
-   **المخرجات (Response Body - 200 OK):**

    ```json
    {
      "task_id": "<UUID>",
      "task_name": "<string>",
      "status": "<enum>", // PENDING, RUNNING, COMPLETED, FAILED, CANCELLED
      "progress": "<integer>", // 0-100
      "result": "<object>", // نتيجة المهمة النهائية (إذا اكتملت)
      "error": "<object>" // تفاصيل الخطأ (إذا فشلت)
    }
    ```

-   **الأخطاء (Error Responses):**
    -   `404 Not Found`: إذا لم يتم العثور على المهمة.
    -   `500 Internal Server Error`: لأي خطأ غير متوقع.

## 10. سجل القرارات المعمارية (ADRs)

تُسجل القرارات المعمارية التالية لتبرير الخيارات التصميمية الرئيسية لمحرك التشغيل والتنسيق:

-   [ADR 0003: Runtime & Orchestration Internal Messaging Strategy](/home/ubuntu/بصيرة/الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0003-runtime-orchestration-messaging.md)
-   [ADR 0004: Runtime & Orchestration Task Queue and Scheduler Design](/home/ubuntu/بصيرة/الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0004-runtime-orchestration-task-scheduling.md)
-   [ADR 0005: Runtime & Orchestration Workflow Engine Design](/home/ubuntu/بصيرة/الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0005-runtime-orchestration-workflow-engine.md)
-   [ADR 0006: Runtime & Orchestration Memory Contracts Design](/home/ubuntu/بصيرة/الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0006-runtime-orchestration-memory-contracts.md)
-   [ADR 0007: Runtime & Orchestration Permission Model Design](/home/ubuntu/بصيرة/الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0007-runtime-orchestration-permission-model.md)
-   [ADR 0008: Runtime & Orchestration API Contracts Design](/home/ubuntu/بصيرة/الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0008-runtime-orchestration-api-contracts.md)

## 11. الخلاصة

يمثل هذا التصميم الفني خريطة طريق مفصلة لتنفيذ محرك التشغيل والتنسيق في منصة "بصيرة". من خلال تحديد واضح للمكونات، التفاعلات، العقود، والقرارات المعمارية، نهدف إلى بناء نظام قوي، مرن، وآمن يدعم التطور المستقبلي للمنصة ويضمن تحقيق أهدافها الطموحة في تحليل السوق المالي السعودي. هذا التصميم يزيل الغموض المعماري ويضع الأساس المتين للبدء في التنفيذ البرمجي للوحدة الرابعة بثقة وكفاءة.
