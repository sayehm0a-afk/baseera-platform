# تصميم معمارية BaseAgent - منصة بصيرة

**النسخة:** Architecture v1.0 Final
**التاريخ:** 14 يوليو 2026
**المؤلف:** Manus AI (بصفتي كبير مهندسي البرمجيات)

## 1. مقدمة (Introduction)

### 1.1 الغرض (Purpose)
تحدد هذه الوثيقة التصميم المعماري التفصيلي لـ `BaseAgent`، وهو المكون الأساسي الذي ستُبنى عليه جميع العملاء الذكيين المتخصصين في منصة "بصيرة". تهدف هذه الوثيقة إلى توفير فهم شامل لهيكل `BaseAgent` الداخلي، مسؤولياته، آليات عمله، وكيفية تفاعله مع بقية مكونات المنصة، لضمان التناسق، قابلية التوسع، وسهولة الصيانة عبر جميع العملاء الذكيين.

### 1.2 نطاق الوثيقة (Document Scope)
تغطي هذه الوثيقة الجوانب المعمارية لـ `BaseAgent`، بما في ذلك مسؤولياته، دورة حياته، إدارة الحالة والذاكرة، نظام التفكير، استدعاء الأدوات، طبقة الاتصال بنماذج الذكاء الاصطناعي (LLM)، إدارة الأخطاء، التسجيل والمراقبة، الأمان، واجهات الاتصال، معايير الكود، واستراتيجية الاختبارات. لا تتناول هذه الوثيقة تفاصيل تنفيذ العملاء الذكيين المتخصصين، بل تركز على الأساس المشترك الذي يجمعهم.

### 1.3 الجمهور المستهدف (Target Audience)
- **مهندسو البرمجيات والمطورون:** لتوجيه عملية تنفيذ `BaseAgent` والعملاء الذكيين المشتقين منه.
- **مهندسو المعمارية:** لضمان التوافق مع المعمارية الكلية للمنصة.
- **مديرو المشروع:** لفهم التعقيدات التقنية وتقدير الجهود.
- **المختبرون:** لتصميم خطط الاختبار بناءً على التصميم المعماري.

### 1.4 التعريفات والمختصرات (Definitions and Acronyms)
| المصطلح | التعريف |
|---|---|
| **BaseAgent** | الصنف الأساسي (Base Class) الذي يرث منه جميع العملاء الذكيين المتخصصين في منصة "بصيرة". |
| **عميل ذكي (AI Agent)** | مكون برمجي مستقل متخصص في مهمة محددة. |
| **المشرف العام (Supervisor Agent)** | العميل الذكي المركزي الذي يدير التفاعل بين العملاء الآخرين (Hub). |
| **SRS** | Software Requirements Specification (مواصفات متطلبات البرمجيات). |
| **ADR** | Architectural Decision Record (سجل قرار معماري). |
| **LLM** | Large Language Model (نموذج لغوي كبير). |
| **Tool** | وظيفة أو خدمة خارجية يمكن للعميل الذكي استدعاؤها لأداء مهام محددة. |
| **Prompt** | التعليمات أو المدخلات التي تُقدم لنموذج الذكاء الاصطناعي لتوجيه سلوكه. |
| **Memory** | آلية لتخزين واسترجاع المعلومات التي يحتاجها العميل الذكي. |
| **State** | الحالة الحالية للعميل الذكي أو المهمة التي يعمل عليها. |

## 2. نظرة عامة على BaseAgent (BaseAgent Overview)

`BaseAgent` هو حجر الزاوية في معمارية العملاء الذكيين لمنصة "بصيرة". إنه يوفر الهيكل الأساسي والوظائف المشتركة التي يحتاجها أي عميل ذكي، مما يضمن الاتساق، قابلية التوسع، وسهولة التطوير. جميع العملاء الذكيين المتخصصين (مثل وكيل التحليل الفني، وكيل أخبار السوق) سيرثون من `BaseAgent` ويوسعون وظائفه لتلبية متطلباتهم الخاصة.

### 2.1 المسؤوليات الكاملة لـ BaseAgent (Full Responsibilities)
يتحمل `BaseAgent` المسؤوليات الأساسية التالية:
- **إدارة دورة حياة العميل:** التهيئة، التشغيل، والإنهاء.
- **إدارة الحالة:** تتبع الحالة الداخلية للعميل الذكي.
- **إدارة الذاكرة:** توفير آليات للذاكرة قصيرة وطويلة المدى.
- **توفير إطار عمل للتفكير:** هيكل موحد لعمليات الاستدلال واتخاذ القرار.
- **توفير إطار عمل لاستدعاء الأدوات:** آلية آمنة وموثوقة لاستدعاء الأدوات الخارجية.
- **التفاعل مع طبقة LLM Abstraction:** الاتصال بنماذج الذكاء الاصطناعي الكبيرة (LLMs).
- **إدارة الأخطاء وإعادة المحاولة:** التعامل مع الاستثناءات واستراتيجيات التعافي.
- **التسجيل والمراقبة:** توفير وظائف التسجيل الأساسية وإمكانية المراقبة.
- **التعامل مع الصلاحيات والأمان:** تطبيق مبادئ الأمان الأساسية.
- **توفير واجهات اتصال موحدة:** لتمكين التواصل مع `Supervisor Agent` والمكونات الأخرى.
- **إدارة السياق:** الحفاظ على السياق ذي الصلة بالمهمة.
- **إدارة Prompts:** توفير آليات لتوليد وإدارة الـ Prompts.

### 2.2 الرؤية والأهداف (Vision and Goals)
- **الرؤية:** أن يكون `BaseAgent` أساساً متيناً ومرناً لبناء منظومة من العملاء الذكيين المتخصصين، قادرين على تقديم تحليلات مالية دقيقة وموثوقة في السوق السعودي.
- **الأهداف:**
    - توفير بنية موحدة وقابلة لإعادة الاستخدام لجميع العملاء الذكيين.
    - تسهيل عملية تطوير واختبار العملاء الذكيين الجدد.
    - ضمان الاتساق في السلوكيات الأساسية للعملاء الذكيين.
    - دعم قابلية التوسع والأداء العالي للمنصة ككل.

## 3. الهيكل المعماري لـ BaseAgent (BaseAgent Architectural Structure)

يتكون `BaseAgent` من عدة وحدات (Modules) وطبقات (Layers) تعمل معاً لتحقيق وظائفه. يعتمد التصميم على مبادئ الفصل بين الاهتمامات (Separation of Concerns) والاقتران المنخفض (Loose Coupling) لضمان المرونة وقابلية الصيانة.

### 3.1 الهيكل الداخلي (Internal Structure)

```d2
direction: right

BaseAgent: {
  shape: class
  label: "BaseAgent (الصنف الأساسي للوكيل)"
  
  Core: {
    shape: rectangle
    label: "Core Logic (المنطق الأساسي)"
    MemoryManager: { shape: cylinder; label: "Memory Manager (إدارة الذاكرة)" }
    ReasoningEngine: { shape: rectangle; label: "Reasoning Engine (محرك الاستدلال)" }
    ToolExecutor: { shape: rectangle; label: "Tool Executor (منفذ الأدوات)" }
    LLMInterface: { shape: rectangle; label: "LLM Interface (واجهة LLM)" }
    ErrorHandler: { shape: rectangle; label: "Error Handler (معالج الأخطاء)" }
    Logger: { shape: rectangle; label: "Logger (المسجل)" }
    SecurityManager: { shape: rectangle; label: "Security Manager (إدارة الأمان)" }
  }
  
  Interfaces: {
    shape: rectangle
    label: "Interfaces (واجهات الاتصال)"
    SupervisorAPI: { shape: rectangle; label: "Supervisor API (واجهة المشرف العام)" }
    ExternalAPI: { shape: rectangle; label: "External APIs (واجهات خارجية)" }
  }
  
  Plugins: {
    shape: rectangle
    label: "Plugins (الإضافات)"
    PluginManager: { shape: rectangle; label: "Plugin Manager (إدارة الإضافات)" }
  }
}

SupervisorAgent: { shape: class; label: "Supervisor Agent (وكيل المشرف العام)" }
ExternalTools: { shape: cloud; label: "External Tools (أدوات خارجية)" }
LLMProviders: { shape: cloud; label: "LLM Providers (مزودو LLM)" }
DataStores: { shape: cylinder; label: "Data Stores (مخازن البيانات)" }

SupervisorAgent -> BaseAgent.Interfaces.SupervisorAPI: "يتصل بـ"
BaseAgent.Core.ToolExecutor -> ExternalTools: "يستدعي"
BaseAgent.Core.LLMInterface -> LLMProviders: "يتصل بـ"
BaseAgent.Core.MemoryManager -> DataStores: "يخزن/يسترجع"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.MemoryManager: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.ToolExecutor: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.LLMInterface: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.ErrorHandler: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.Logger: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.SecurityManager: "يستخدم"
BaseAgent.Plugins.PluginManager -> BaseAgent.Core: "يوسع وظائف"
```

### 3.2 الوحدات (Modules)

| الوحدة | الوصف | المسؤوليات الرئيسية |
|---|---|---|
| **Core Logic** | يحتوي على المنطق الأساسي للعميل الذكي. | إدارة الذاكرة، التفكير، تنفيذ الأدوات، الاتصال بـ LLM، معالجة الأخطاء، التسجيل، الأمان. |
| **Interfaces** | يوفر نقاط اتصال موحدة للعميل الذكي. | واجهة برمجة تطبيقات للتواصل مع `Supervisor Agent`، واجهات للأنظمة الخارجية. |
| **Plugins** | يدير تحميل وتفريغ وتفاعل الإضافات. | تمكين التوسعة الديناميكية لوظائف العميل الذكي. |

### 3.3 الطبقات (Layers)

1.  **طبقة الواجهة (Interface Layer):** مسؤولة عن استقبال الطلبات من `Supervisor Agent` وإرسال الاستجابات إليه، بالإضافة إلى التفاعل مع الأنظمة الخارجية. (مثال: `SupervisorAPI`, `ExternalAPI`).
2.  **طبقة المنطق الأساسي (Core Logic Layer):** تحتوي على الوحدات الأساسية التي تدير سلوك العميل الذكي، مثل التفكير، الذاكرة، والأدوات. (مثال: `ReasoningEngine`, `MemoryManager`, `ToolExecutor`).
3.  **طبقة البنية التحتية (Infrastructure Layer):** تتعامل مع الخدمات الأساسية مثل الاتصال بـ LLMs، تخزين البيانات، التسجيل، والأمان. (مثال: `LLMInterface`, `DataStores`, `Logger`, `SecurityManager`).

### 3.4 المخططات المعمارية الأساسية (Core Architecture Diagrams)

**مخطط هيكل BaseAgent الداخلي:**

```d2
direction: right

BaseAgent: {
  shape: class
  label: "BaseAgent (الصنف الأساسي للوكيل)"
  
  Core: {
    shape: rectangle
    label: "Core Logic (المنطق الأساسي)"
    MemoryManager: { shape: cylinder; label: "Memory Manager (إدارة الذاكرة)" }
    ReasoningEngine: { shape: rectangle; label: "Reasoning Engine (محرك الاستدلال)" }
    ToolExecutor: { shape: rectangle; label: "Tool Executor (منفذ الأدوات)" }
    LLMInterface: { shape: rectangle; label: "LLM Interface (واجهة LLM)" }
    ErrorHandler: { shape: rectangle; label: "Error Handler (معالج الأخطاء)" }
    Logger: { shape: rectangle; label: "Logger (المسجل)" }
    SecurityManager: { shape: rectangle; label: "Security Manager (إدارة الأمان)" }
  }
  
  Interfaces: {
    shape: rectangle
    label: "Interfaces (واجهات الاتصال)"
    SupervisorAPI: { shape: rectangle; label: "Supervisor API (واجهة المشرف العام)" }
    ExternalAPI: { shape: rectangle; label: "External APIs (واجهات خارجية)" }
  }
  
  Plugins: {
    shape: rectangle
    label: "Plugins (الإضافات)"
    PluginManager: { shape: rectangle; label: "Plugin Manager (إدارة الإضافات)" }
  }
}

SupervisorAgent: { shape: class; label: "Supervisor Agent (وكيل المشرف العام)" }
ExternalTools: { shape: cloud; label: "External Tools (أدوات خارجية)" }
LLMProviders: { shape: cloud; label: "LLM Providers (مزودو LLM)" }
DataStores: { shape: cylinder; label: "Data Stores (مخازن البيانات)" }

SupervisorAgent -> BaseAgent.Interfaces.SupervisorAPI: "يتصل بـ"
BaseAgent.Core.ToolExecutor -> ExternalTools: "يستدعي"
BaseAgent.Core.LLMInterface -> LLMProviders: "يتصل بـ"
BaseAgent.Core.MemoryManager -> DataStores: "يخزن/يسترجع"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.MemoryManager: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.ToolExecutor: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.LLMInterface: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.ErrorHandler: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.Logger: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.SecurityManager: "يستخدم"
BaseAgent.Plugins.PluginManager -> BaseAgent.Core: "يوسع وظائف"
```

### 3.5 مخطط المكونات (Component Diagram)

```d2
direction: right

BaseAgentComponent: { shape: component; label: "BaseAgent Component" }
MemoryManagerComponent: { shape: component; label: "Memory Manager" }
ReasoningEngineComponent: { shape: component; label: "Reasoning Engine" }
ToolExecutorComponent: { shape: component; label: "Tool Executor" }
LLMInterfaceComponent: { shape: component; label: "LLM Interface" }
ErrorHandlerComponent: { shape: component; label: "Error Handler" }
LoggerComponent: { shape: component; label: "Logger" }
SecurityManagerComponent: { shape: component; label: "Security Manager" }
PluginManagerComponent: { shape: component; label: "Plugin Manager" }

BaseAgentComponent -> MemoryManagerComponent: "يحتوي على"
BaseAgentComponent -> ReasoningEngineComponent: "يحتوي على"
BaseAgentComponent -> ToolExecutorComponent: "يحتوي على"
BaseAgentComponent -> LLMInterfaceComponent: "يحتوي على"
BaseAgentComponent -> ErrorHandlerComponent: "يحتوي على"
BaseAgentComponent -> LoggerComponent: "يحتوي على"
BaseAgentComponent -> SecurityManagerComponent: "يحتوي على"
BaseAgentComponent -> PluginManagerComponent: "يحتوي على"

ReasoningEngineComponent -> MemoryManagerComponent: "يستخدم"
ReasoningEngineComponent -> ToolExecutorComponent: "يستخدم"
ReasoningEngineComponent -> LLMInterfaceComponent: "يستخدم"
ReasoningEngineComponent -> ErrorHandlerComponent: "يستخدم"
ReasoningEngineComponent -> LoggerComponent: "يستخدم"
ReasoningEngineComponent -> SecurityManagerComponent: "يستخدم"
PluginManagerComponent -> BaseAgentComponent: "يوسع"
```

### 3.6 مخطط الفئات (Class Diagram)

```d2
direction: right

class BaseAgent {
  + id: str
  + name: str
  + memory_manager: MemoryManager
  + reasoning_engine: ReasoningEngine
  + tool_executor: ToolExecutor
  + llm_interface: LLMInterface
  + error_handler: ErrorHandler
  + logger: Logger
  + security_manager: SecurityManager
  + plugin_manager: PluginManager
  + __init__(...)
  + handle_request(request: AgentRequest) -> AgentResponse
  + _initialize_agent()
  + _terminate_agent()
}

class MemoryManager {
  + short_term_memory: ShortTermMemory
  + long_term_memory: LongTermMemory
  + retrieve_context(task_id: str) -> Context
  + update_memory(task_id: str, data: Any)
}

class ReasoningEngine {
  + reason(task: Task, context: Context, tools: List[Tool]) -> Action
  + _plan_task(task: Task, context: Context) -> Plan
  + _select_tool(plan: Plan, available_tools: List[Tool]) -> Tool
  + _generate_tool_input(tool: Tool, context: Context) -> Dict
}

class ToolExecutor {
  + execute_tool(tool: Tool, input: Dict) -> ToolOutput
}

class LLMInterface {
  + generate_response(prompt: Prompt, model_config: Dict) -> LLMResponse
  + embed_text(text: str) -> Embedding
}

class ErrorHandler {
  + handle_error(error: Exception, context: Dict) -> ErrorRecoveryStrategy
  + _retry_operation(operation: Callable, retries: int) -> Any
}

class Logger {
  + log(level: LogLevel, message: str, context: Dict)
}

class SecurityManager {
  + authorize_tool_access(agent_id: str, tool_name: str) -> bool
  + encrypt_data(data: str) -> str
}

class PluginManager {
  + load_plugin(plugin_name: str)
  + unload_plugin(plugin_name: str)
  + get_available_plugins() -> List[Plugin]
}

BaseAgent *-- MemoryManager
BaseAgent *-- ReasoningEngine
BaseAgent *-- ToolExecutor
BaseAgent *-- LLMInterface
BaseAgent *-- ErrorHandler
BaseAgent *-- Logger
BaseAgent *-- SecurityManager
BaseAgent *-- PluginManager

ReasoningEngine --> MemoryManager: "يستخدم"
ReasoningEngine --> ToolExecutor: "يستخدم"
ReasoningEngine --> LLMInterface: "يستخدم"
ReasoningEngine --> ErrorHandler: "يستخدم"
ReasoningEngine --> Logger: "يستخدم"
ReasoningEngine --> SecurityManager: "يستخدم"

MemoryManager --> ShortTermMemory
MemoryManager --> LongTermMemory

LLMInterface --> PromptManager
```

### 3.7 مخطط التسلسل (Sequence Diagram) - مثال: معالجة طلب بسيط

```d2
direction: right

SupervisorAgent -> BaseAgent: request(task_id, query)
BaseAgent -> ReasoningEngine: analyze_request(query)
ReasoningEngine -> MemoryManager: retrieve_context(task_id)
MemoryManager --> ReasoningEngine: context
ReasoningEngine -> LLMInterface: generate_plan(query, context)
LLMInterface --> ReasoningEngine: plan
ReasoningEngine -> ToolExecutor: select_tool(plan)
ToolExecutor --> ReasoningEngine: tool_info
ReasoningEngine -> ToolExecutor: execute_tool(tool_info, input)
ToolExecutor --> ReasoningEngine: tool_output
ReasoningEngine -> MemoryManager: update_memory(task_id, tool_output)
MemoryManager --> ReasoningEngine: memory_updated
ReasoningEngine -> LLMInterface: generate_response(plan, tool_output, context)
LLMInterface --> ReasoningEngine: final_response
ReasoningEngine --> BaseAgent: agent_response
BaseAgent --> SupervisorAgent: response(task_id, agent_response)
```

### 3.8 مخطط النشر (Deployment Diagram)

```d2
direction: right

cloud "منصة بصيرة السحابية" {
  cluster "Kubernetes Cluster" {
    node "Worker Node 1" {
      container "Supervisor Agent Pod" {
        process "Supervisor Agent"
      }
      container "BaseAgent Instance 1 (وكيل التحليل الفني)" {
        process "BaseAgent"
      }
      container "BaseAgent Instance 2 (وكيل أخبار السوق)" {
        process "BaseAgent"
      }
    }
    node "Worker Node N" {
      container "BaseAgent Instance N" {
        process "BaseAgent"
      }
    }
  }
  database "Vector DB (ذاكرة طويلة المدى)"
  database "Relational DB (حالة، تكوينات)"
  queue "Message Queue (Kafka/RabbitMQ)"
  storage "Object Storage (S3)"
}

external_system "مزودو LLM (OpenAI, Gemini)"
external_system "مزودو بيانات السوق (Tadawul API)"

"Supervisor Agent" <-> "BaseAgent Instance 1 (وكيل التحليل الفني)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance 2 (وكيل أخبار السوق)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance N": "يتواصل عبر"

"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو LLM (OpenAI, Gemini)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو بيانات السوق (Tadawul API)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Vector DB (ذاكرة طويلة المدى)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Relational DB (حالة، تكوينات)": "يستخدم"

"Message Queue (Kafka/RabbitMQ)" <-> "Supervisor Agent": "للتواصل غير المتزامن"
"Object Storage (S3)" <-> "BaseAgent Instance N": "لتخزين البيانات الكبيرة"
```

### 3.9 مخطط تدفق البيانات (Data Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
LLMProviders: { shape: cloud; label: "مزودو LLM" }
ExternalTools: { shape: cloud; label: "أدوات خارجية" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى" }

User -> SupervisorAgent: "طلب تحليلي"
SupervisorAgent -> BaseAgent: "توجيه المهمة"

BaseAgent -> ShortTermMemory: "قراءة/كتابة السياق"
BaseAgent -> LongTermMemory: "قراءة/كتابة المعرفة"
BaseAgent -> LLMProviders: "استدعاء LLM (Prompt)"
LLMProviders -> BaseAgent: "استجابة LLM"
BaseAgent -> ExternalTools: "استدعاء أداة"
ExternalTools -> BaseAgent: "مخرجات الأداة"

BaseAgent -> SupervisorAgent: "نتائج المهمة"
SupervisorAgent -> User: "التحليل النهائي"
```

### 3.10 مخطط تدفق الأحداث (Event Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
MessageQueue: { shape: queue; label: "Message Queue" }

User -> SupervisorAgent: "يرسل طلب"
SupervisorAgent -> MessageQueue: "ينشر حدث: TaskAssigned"
MessageQueue -> BaseAgent: "يستقبل حدث: TaskAssigned"
BaseAgent -> BaseAgent: "يعالج المهمة"
BaseAgent -> MessageQueue: "ينشر حدث: TaskCompleted/TaskFailed"
MessageQueue -> SupervisorAgent: "يستقبل حدث: TaskCompleted/TaskFailed"
SupervisorAgent -> User: "يرسل إشعار/نتيجة"
```

### 3.11 مخطط تدفق الذاكرة (Memory Flow Diagram)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى (Redis/In-memory)" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى (Vector DB/Relational DB)" }

BaseAgent -> ShortTermMemory: "يخزن/يسترجع سياق الجلسة"
BaseAgent -> LongTermMemory: "يخزن/يسترجع المعرفة الدائمة"

ShortTermMemory -> LongTermMemory: "ترحيل السياق الهام (عند الحاجة)"
LongTermMemory -> ShortTermMemory: "استرجاع المعرفة ذات الصلة"
```

### 3.12 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 3.13 تدفق معالجة الـ Prompt (Prompt Processing Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
PromptManager: { shape: rectangle; label: "Prompt Manager" }
MemoryManager: { shape: rectangle; label: "Memory Manager" }
LLMInterface: { shape: rectangle; label: "LLM Interface" }
LLMProvider: { shape: cloud; label: "مزود LLM" }

BaseAgent -> PromptManager: "طلب توليد Prompt"
PromptManager -> MemoryManager: "يسترجع السياق ذي الصلة"
MemoryManager --> PromptManager: "السياق والذاكرة"
PromptManager -> PromptManager: "يطبق القوالب ويضغط السياق"
PromptManager --> BaseAgent: "Prompt النهائي"
BaseAgent -> LLMInterface: "يرسل Prompt لـ LLM"
LLMInterface -> LLMProvider: "يرسل Prompt"
LLMProvider --> LLMInterface: "استجابة LLM"
LLMInterface --> BaseAgent: "استجابة LLM"
```

### 3.14 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine -> BaseAgent: "يستأنف/يفشل المهمة"
```

### 3.15 مخطط انتقال الحالة (State Transition Diagram)

```d2
direction: right

stateDiagram-v2
    [*] --> Idle
    Idle --> Initializing: "استلام طلب"
    Initializing --> Ready: "تم التهيئة بنجاح"
    Ready --> Processing: "بدء معالجة المهمة"
    Processing --> Processing: "خطوة مهمة (تفكير/أداة)"
    Processing --> Ready: "المهمة مكتملة"
    Processing --> Failed: "فشل المهمة"
    Failed --> Ready: "إعادة تعيين/محاولة جديدة"
    Ready --> Terminating: "طلب إنهاء"
    Initializing --> Failed: "فشل التهيئة"
    Terminating --> [*]: "تم الإنهاء"
```

## 4. دورة حياة الوكيل (Agent Lifecycle)

تتبع دورة حياة `BaseAgent` المراحل التالية:

1.  **التهيئة (Initialization):**
    *   يتم إنشاء مثيل (instance) لـ `BaseAgent` أو العميل الذكي المشتق منه.
    *   يتم تحميل التكوينات الخاصة بالعميل (مثل الأدوات المتاحة، إعدادات الذاكرة، إعدادات LLM).
    *   يتم تهيئة وحدات الذاكرة، ومحرك التفكير، ومنفذ الأدوات.
    *   يتم تسجيل العميل الذكي لدى `Supervisor Agent` (إذا لزم الأمر).

2.  **التنفيذ (Execution):**
    *   يستقبل العميل الذكي طلباً أو مهمة من `Supervisor Agent` عبر واجهة `SupervisorAPI`.
    *   يقوم `ReasoningEngine` بتحليل الطلب، واستخدام الذاكرة، واستدعاء الأدوات، والتفاعل مع LLM لتوليد استجابة أو اتخاذ إجراء.
    *   تتكرر هذه العملية حتى تكتمل المهمة أو يتم الوصول إلى حالة نهائية.

3.  **الإنهاء (Termination):**
    *   يتم تحرير الموارد التي يستخدمها العميل الذكي (مثل اتصالات قاعدة البيانات، جلسات LLM).
    *   يتم حفظ أي حالة ضرورية للذاكرة طويلة المدى.
    *   يتم إلغاء تسجيل العميل الذكي من `Supervisor Agent`.

## 5. تدفق البيانات وتنفيذ المهام (Data Flow and Task Execution)

### 5.1 آلية التواصل مع Supervisor Agent (Communication with Supervisor Agent)

يعتمد التواصل بين العملاء الذكيين و`Supervisor Agent` على معمارية Hub-and-Spoke. `BaseAgent` يتصل بـ `Supervisor Agent` عبر واجهة `SupervisorAPI` الموحدة. لا يوجد اتصال مباشر بين العملاء الذكيين المتخصصين.

**تدفق الاتصال:**
1.  **الطلب:** يرسل `Supervisor Agent` طلباً (مهمة) إلى عميل ذكي محدد (أو مجموعة عملاء) عبر واجهة `SupervisorAPI` الخاصة به.
2.  **المعالجة:** يستقبل العميل الذكي الطلب، يقوم بمعالجته باستخدام `ReasoningEngine`، الذاكرة، والأدوات.
3.  **الاستجابة:** يرسل العميل الذكي النتائج أو التقدم المحرز إلى `Supervisor Agent` عبر نفس الواجهة.
4.  **التجميع:** يقوم `Supervisor Agent` بتجميع الاستجابات من العملاء المختلفين وتنسيقها.

### 5.2 بروتوكول الاتصال متعدد العملاء (Multi-Agent Communication Protocol)

لضمان التواصل الفعال والآمن بين `Supervisor Agent` والعملاء الذكيين، سيتم استخدام بروتوكول اتصال موحد يعتمد على الرسائل غير المتزامنة (Asynchronous Messaging) عبر قائمة انتظار رسائل (Message Queue) مثل Kafka أو RabbitMQ. هذا يضمن:
-   **المرونة:** فصل المرسل عن المستقبل.
-   **قابلية التوسع:** سهولة إضافة المزيد من العملاء أو `Supervisor Agents`.
-   **الموثوقية:** ضمان تسليم الرسائل حتى في حالة تعطل أحد المكونات.

**هيكل الرسالة (Message Structure):**
ستتبع الرسائل تنسيق JSON موحد يتضمن:
-   `message_id`: معرف فريد للرسالة.
-   `sender_id`: معرف العميل المرسل.
-   `receiver_id`: معرف العميل المستهدف (أو `broadcast`).
-   `message_type`: نوع الرسالة (مثال: `TaskRequest`, `TaskResponse`, `StatusUpdate`).
-   `payload`: الحمولة الفعلية للرسالة (بيانات المهمة، النتائج، الأخطاء).
-   `timestamp`: وقت إرسال الرسالة.
-   `signature`: توقيع رقمي لضمان سلامة الرسالة ومصدرها.

### 5.3 دورة تنفيذ المهام (Task Execution Flow)

1.  **استلام المهمة:** `BaseAgent` يستقبل مهمة من `Supervisor Agent`.
2.  **تحليل المهمة:** `ReasoningEngine` يحلل المهمة، ويحدد الأهداف الفرعية والإجراءات المطلوبة.
3.  **استرجاع السياق:** `MemoryManager` يسترجع المعلومات ذات الصلة من الذاكرة قصيرة وطويلة المدى.
4.  **التفكير (Reasoning):** `ReasoningEngine` يستخدم LLM (عبر `LLMInterface`) لتوليد خطة عمل، أو تحديد الأداة المناسبة للاستدعاء، أو صياغة استجابة.
5.  **تنفيذ الأداة (Tool Execution):** إذا تطلب الأمر، يقوم `ToolExecutor` باستدعاء الأداة المحددة، ويتم تمرير المدخلات واستقبال المخرجات.
6.  **تحديث الذاكرة:** يتم تحديث الذاكرة بالنتائج الجديدة أو التغييرات في الحالة.
7.  **تكرار أو إنهاء:** تتكرر الخطوات 2-6 حتى تكتمل المهمة أو يتم الوصول إلى استجابة نهائية.
8.  **إرسال الاستجابة:** يرسل `BaseAgent` الاستجابة النهائية إلى `Supervisor Agent`.

## 6. إدارة الحالة والذاكرة (State and Memory Management)

### 6.1 إدارة الحالة (State Management)
يحتفظ `BaseAgent` بحالة داخلية لكل مهمة قيد التنفيذ. تتضمن هذه الحالة:
-   **معرف المهمة (Task ID):** لتتبع المهام المتعددة.
-   **حالة المهمة (Task Status):** (قيد التنفيذ، مكتملة، فاشلة، معلقة).
-   **الخطوات المنفذة (Executed Steps):** سجل بالخطوات التي تم اتخاذها.
-   **المدخلات والمخرجات الحالية (Current Inputs/Outputs):** البيانات التي يتم معالجتها.
-   **الموارد المستخدمة (Used Resources):** الأدوات أو نماذج LLM المستدعاة.

يتم تحديث الحالة بشكل مستمر بواسطة `ReasoningEngine` ويتم حفظها في الذاكرة قصيرة المدى.

### 6.2 نظام الذاكرة قصيرة المدى (Short-Term Memory)
-   **الغرض:** تخزين السياق الحالي للمهمة، المحادثات الجارية، والنتائج الوسيطة.
-   **الآلية:** يتم استخدام هياكل بيانات داخلية (مثل القواميس أو الكائنات) لتخزين المعلومات في الذاكرة العاملة للعميل الذكي. يمكن أن تكون هذه الذاكرة عابرة (in-memory) أو مخزنة مؤقتاً في قاعدة بيانات سريعة (مثل Redis) للمهام الأطول.
-   **إدارة السياق (Context Management):** يتم تجميع السياق ذي الصلة من الذاكرة قصيرة المدى وتقديمه إلى LLM كجزء من الـ Prompt. يتم تطبيق تقنيات ضغط السياق (Context Compression) عند الضرورة للحفاظ على حجم الـ Prompt ضمن حدود LLM.

### 6.3 نظام الذاكرة طويلة المدى (Long-Term Memory)
-   **الغرض:** تخزين المعرفة الدائمة، الدروس المستفادة، التفضيلات، والبيانات التاريخية التي يحتاجها العميل الذكي عبر جلسات متعددة أو مهام مختلفة.
-   **الآلية:** يتم استخدام قواعد بيانات متخصصة (مثل Vector Databases لتخزين التضمينات الدلالية، أو قواعد بيانات علائقية/NoSQL لتخزين البيانات المنظمة) لتخزين الذاكرة طويلة المدى. يتم استرجاع المعلومات باستخدام تقنيات البحث الدلالي (Semantic Search) أو الاستعلامات التقليدية.

### 6.4 إدارة نافذة السياق (Context Window Management)

لتحسين كفاءة استخدام نماذج LLM والتحكم في التكلفة، سيتم تطبيق استراتيجيات لإدارة نافذة السياق:
-   **التقطيع (Chunking):** تقسيم النصوص الطويلة إلى أجزاء أصغر.
-   **التلخيص (Summarization):** تلخيص الأجزاء الأقل أهمية من السياق.
-   **الاسترجاع الانتقائي (Selective Retrieval):** استرجاع الأجزاء الأكثر صلة فقط من الذاكرة طويلة المدى.
-   **الضغط (Compression):** استخدام تقنيات ضغط السياق لتقليل عدد الرموز (tokens) المرسلة إلى LLM.

### 6.5 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 6.6 استراتيجية ضغط الذاكرة (Memory Compression Strategy)

لتحسين كفاءة الذاكرة طويلة المدى وتقليل تكاليف التخزين والاسترجاع، سيتم تطبيق استراتيجيات ضغط الذاكرة:
-   **التضمين الدلالي (Semantic Embedding):** تحويل النصوص إلى متجهات (vectors) لتقليل حجم التخزين وتمكين البحث الدلالي.
-   **التلخيص الدوري (Periodic Summarization):** تلخيص المحادثات أو الأحداث التاريخية بشكل دوري وتخزين الملخصات بدلاً من النصوص الكاملة.
-   **إزالة البيانات القديمة/غير ذات الصلة (Pruning):** حذف البيانات التي تجاوزت فترة صلاحيتها أو التي لم تعد ذات صلة.

## 7. نظام التفكير والاستدلال (Reasoning Pipeline)

`ReasoningEngine` هو قلب `BaseAgent`، وهو المسؤول عن توجيه سلوك العميل الذكي. يتبع هذا النظام عادةً نمط "التفكير/العمل" (Think/Act) أو "التخطيط/التنفيذ" (Plan/Execute).

### 7.1 مراحل التفكير (Reasoning Stages)
1.  **فهم المهمة (Task Understanding):** تحليل الطلب الوارد وتحديد النية والأهداف الرئيسية.
2.  **توليد الخطة (Plan Generation):** استخدام LLM لتوليد خطة عمل خطوة بخطوة لتحقيق الأهداف، مع الأخذ في الاعتبار السياق والذاكرة والأدوات المتاحة.
3.  **اختيار الأداة (Tool Selection):** تحديد الأداة الأنسب لتنفيذ الخطوة الحالية من الخطة.
4.  **توليد المدخلات للأداة (Tool Input Generation):** صياغة المدخلات اللازمة للأداة المختارة بناءً على السياق.
5.  **تحليل المخرجات (Output Analysis):** تقييم مخرجات الأداة أو استجابة LLM وتحديد الخطوة التالية.
6.  **تحديث الحالة والذاكرة (State & Memory Update):** تسجيل التقدم المحرز وتحديث الذاكرة.

### 7.2 آلية اتخاذ القرار (Decision-Making Mechanism)
تعتمد آلية اتخاذ القرار على مزيج من:
-   **نماذج LLM:** لتوليد الأفكار، الخطط، واختيار الأدوات بناءً على الـ Prompts المصممة بعناية.
-   **المنطق البرمجي (Programmatic Logic):** قواعد محددة مسبقاً للتعامل مع السيناريوهات الشائعة أو الحالات الحرجة.
-   **الذاكرة:** استخدام المعلومات المخزنة لتوجيه القرارات.

## 8. نظام استدعاء الأدوات (Tool Calling Framework)

`ToolExecutor` هو الوحدة المسؤولة عن إدارة واستدعاء الأدوات الخارجية التي يمكن للعميل الذكي استخدامها.

### 8.1 كيفية استخدام الأدوات (How Tools are Used)
1.  **تعريف الأداة:** يتم تعريف الأدوات بوضوح (اسم، وصف، معلمات المدخلات، نوع المخرجات) ليتمكن LLM من فهمها واستدعائها بشكل صحيح.
2.  **اختيار الأداة:** يقوم `ReasoningEngine` (بمساعدة LLM) باختيار الأداة المناسبة بناءً على المهمة الحالية.
3.  **تنفيذ الأداة:** يقوم `ToolExecutor` باستدعاء الأداة الفعلية، مع تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
4.  **معالجة المخرجات:** يتم استقبال مخرجات الأداة وتحليلها بواسطة `ReasoningEngine` لمواصلة دورة التفكير.

### 8.2 إدارة الأدوات (Tool Management)
-   **اكتشاف الأدوات (Tool Discovery):** آلية لتسجيل واكتشاف الأدوات المتاحة للعميل الذكي.
-   **التحقق من صحة الأدوات (Tool Validation):** التأكد من أن الأدوات تعمل بشكل صحيح وأن معلمات المدخلات والمخرجات متوافقة.
-   **عزل الأدوات (Tool Isolation):** تشغيل الأدوات في بيئات معزولة لتقليل المخاطر الأمنية وتأثير الأخطاء.

### 8.3 نظام Plugins والتوسعة المستقبلية (Plugins and Future Extensibility)
يدعم `BaseAgent` نظام إضافات (Plugins) يسمح بتوسيع وظائفه ديناميكياً دون الحاجة لتعديل الكود الأساسي. يمكن للإضافات توفير أدوات جديدة، تعديل سلوك التفكير، أو إضافة قدرات ذاكرة جديدة.

### 8.4 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 8.5 معمارية الإضافات (Plugin Architecture)

تعتمد معمارية الإضافات على مبدأ التحميل الديناميكي (Dynamic Loading) والفصل بين الإضافات والمنطق الأساسي. كل إضافة ستكون عبارة عن وحدة برمجية مستقلة (مثل حزمة Python) تلتزم بواجهة محددة (Plugin Interface). هذا يسمح بـ:
-   **التوسعة السهلة:** إضافة وظائف جديدة دون تعديل `BaseAgent`.
-   **العزل:** فشل إضافة لا يؤثر على عمل `BaseAgent` الأساسي.
-   **إدارة الإصدارات:** يمكن تحديث الإضافات بشكل مستقل.

## 9. طبقة الاتصال بنماذج الذكاء الاصطناعي (LLM Abstraction Layer)

### 9.1 الغرض (Purpose)
توفر هذه الطبقة واجهة موحدة للعملاء الذكيين للتفاعل مع نماذج الذكاء الاصطناعي الكبيرة (LLMs) المختلفة، بغض النظر عن المزود (مثل OpenAI, Gemini) أو النموذج المحدد. هذا يضمن المرونة، سهولة التبديل بين النماذج، وعزل منطق العميل الذكي عن تفاصيل API الخاصة بكل LLM.

### 9.2 المكونات (Components)
-   **LLM Provider Interface:** واجهة عامة تحدد طرق الاتصال الأساسية (مثل `generate_response`, `embed_text`).
-   **Concrete LLM Adapters:** تطبيقات محددة لـ `LLM Provider Interface` لكل مزود LLM (مثال: `OpenAIAdapter`, `GeminiAdapter`).
-   **Prompt Manager:** وحدة مسؤولة عن صياغة الـ Prompts، إدارة القوالب، وضغط السياق قبل إرسالها إلى LLM.

### 9.3 استراتيجية توجيه النماذج (Model Routing Strategy)

لتحسين الأداء والتكلفة، سيتم تطبيق استراتيجية توجيه ذكية للنماذج:
-   **التوجيه بناءً على المهمة:** توجيه المهام المختلفة إلى نماذج LLM الأنسب (مثال: نموذج سريع ورخيص للمهام البسيطة، نموذج قوي ومكلف للمهام المعقدة).
-   **التوجيه بناءً على التكلفة/الأداء:** اختيار النموذج بناءً على التوازن بين التكلفة والأداء المطلوب.
-   **التوجيه بناءً على التوفر:** التبديل التلقائي بين المزودين في حالة عدم توفر نموذج معين.

### 9.4 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 9.5 استراتيجية إصدار الـ Prompt (Prompt Versioning Strategy)

لإدارة تطور الـ Prompts وضمان إمكانية التتبع والتحكم، سيتم تطبيق استراتيجية لإصدار الـ Prompts:
-   **التخزين المركزي:** تخزين جميع الـ Prompts في مستودع مركزي (مثل نظام التحكم في الإصدارات Git أو قاعدة بيانات).
-   **الإصدارات (Versioning):** تعيين رقم إصدار لكل Prompt، مما يسمح بالعودة إلى إصدارات سابقة وتتبع التغييرات.
-   **الاختبار A/B:** إمكانية اختبار إصدارات مختلفة من الـ Prompts لتقييم فعاليتها.

## 10. إدارة الأخطاء وإعادة المحاولة (Error Handling and Retry)

### 10.1 آليات اكتشاف الأخطاء (Error Detection Mechanisms)
-   **التحقق من صحة المدخلات (Input Validation):** التحقق من صحة المدخلات قبل معالجتها.
-   **مراقبة استجابات الأدوات و LLM:** تحليل استجابات الأدوات ونماذج LLM لاكتشاف الأخطاء أو الاستجابات غير المتوقعة.
-   **الاستثناءات (Exceptions):** استخدام آليات الاستثناءات القياسية في البرمجة.

### 10.2 استراتيجيات إعادة المحاولة (Retry Strategies)
-   **إعادة المحاولة الأسية (Exponential Backoff):** إعادة محاولة العمليات الفاشلة مع زيادة زمن الانتظار بين المحاولات.
-   **الحد الأقصى للمحاولات (Max Retries):** تحديد عدد أقصى للمحاولات قبل الإبلاغ عن فشل دائم.

### 10.3 التعافي من الأخطاء (Error Recovery)
-   **العودة إلى حالة سابقة (Rollback):** التراجع عن التغييرات التي تمت قبل حدوث الخطأ.
-   **الإبلاغ عن الخطأ (Error Reporting):** إرسال تفاصيل الخطأ إلى `Supervisor Agent` أو نظام المراقبة.
-   **التعامل مع الأخطاء المعروفة (Known Error Handling):** وجود منطق محدد للتعامل مع أنواع معينة من الأخطاء.

### 10.4 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine -> BaseAgent: "يستأنف/يفشل المهمة"
```

## 11. نظام التسجيل والمراقبة (Logging and Monitoring)

### 11.1 التسجيل (Logging)
-   **مستويات التسجيل:** دعم مستويات تسجيل مختلفة (DEBUG, INFO, WARNING, ERROR, CRITICAL).
-   **تنسيق السجلات:** تنسيق موحد للسجلات يسهل التحليل (JSON).
-   **محتوى السجلات:** تسجيل تفاصيل المهمة، خطوات التفكير، استدعاءات الأدوات، استجابات LLM، والأخطاء.
-   **تخزين السجلات:** تخزين السجلات في نظام مركزي (مثل ELK Stack) للتحليل والمراجعة.

### 11.2 المراقبة (Monitoring)
-   **المقاييس (Metrics):** جمع مقاييس الأداء (مثل زمن الاستجابة، معدل النجاح/الفشل، استخدام الموارد).
-   **لوحات المعلومات (Dashboards):** توفير لوحات معلومات لمراقبة صحة وأداء العملاء الذكيين في الوقت الفعلي.
-   **التنبيهات (Alerts):** إعداد تنبيهات عند تجاوز المقاييس لحدود معينة أو عند حدوث أخطاء حرجة.

### 11.3 معمارية الملاحظة (Observability Architecture)

لضمان رؤية عميقة لأداء وسلوك العملاء الذكيين، سيتم تطبيق معمارية ملاحظة شاملة تتضمن:
-   **التسجيل المنظم (Structured Logging):** استخدام تنسيق JSON للسجلات لسهولة التحليل الآلي.
-   **المقاييس (Metrics):** جمع مقاييس الأداء والتشغيل (CPU, Memory, Latency, Error Rates) باستخدام أدوات مثل Prometheus.
-   **التتبع الموزع (Distributed Tracing):** تتبع مسار الطلب عبر العملاء الذكيين والخدمات المختلفة باستخدام أدوات مثل Jaeger أو OpenTelemetry.

### 11.4 تصميم القياس عن بعد (Telemetry Design)

سيتم تصميم نظام القياس عن بعد لجمع البيانات التشغيلية الهامة من `BaseAgent` والعملاء الذكيين المشتقين منه. يتضمن ذلك:
-   **بيانات الأداء:** زمن تنفيذ المهام، زمن استجابة LLM، زمن استدعاء الأدوات.
-   **بيانات الاستخدام:** عدد استدعاءات LLM، عدد استدعاءات الأدوات، عدد الرموز المستخدمة.
-   **بيانات الأخطاء:** أنواع الأخطاء، تكرارها، وسياق حدوثها.
-   **بيانات الموارد:** استخدام CPU، الذاكرة، والشبكة.

## 12. نظام الصلاحيات والأمان (Authorization and Security System)

### 12.1 مبادئ الأمان (Security Principles)
-   **الامتياز الأقل (Least Privilege):** يجب أن يمتلك كل عميل ذكي الحد الأدنى من الصلاحيات اللازمة لأداء وظيفته.
-   **عزل الموارد (Resource Isolation):** عزل موارد العملاء الذكيين عن بعضها البعض.
-   **التشفير (Encryption):** تشفير البيانات الحساسة أثناء النقل وفي وضع السكون.
-   **التحقق من صحة المدخلات (Input Validation):** حماية ضد حقن الـ Prompts (Prompt Injection) وغيرها من الهجمات.

### 12.2 آليات الصلاحيات (Authorization Mechanisms)
-   **رموز الوصول (Access Tokens):** استخدام رموز وصول مؤقتة ومحدودة الصلاحية للوصول إلى الأدوات الخارجية أو الخدمات.
-   **التحكم في الوصول المستند إلى الدور (Role-Based Access Control - RBAC):** تحديد الصلاحيات بناءً على دور العميل الذكي.

### 12.3 نموذج التهديد الأمني (Security Threat Model)

سيتم تطوير نموذج تهديد أمني شامل لتحديد وتحليل وتخفيف المخاطر الأمنية المحتملة لـ `BaseAgent` والمنصة ككل. سيتضمن ذلك:
-   **تحديد الأصول:** البيانات الحساسة، الوظائف الحيوية، واجهات برمجة التطبيقات.
-   **تحديد التهديدات:** هجمات حقن الـ Prompt، الوصول غير المصرح به، تسرب البيانات، هجمات حجب الخدمة (DoS).
-   **تحديد نقاط الضعف:** أخطاء في الكود، تكوينات خاطئة، نقاط ضعف في المكتبات الخارجية.
-   **تحديد الضوابط:** آليات المصادقة، التشفير، التحقق من صحة المدخلات، المراقبة الأمنية.

## 13. معايير كتابة الكود الخاصة بـ BaseAgent (BaseAgent Coding Standards)

بالإضافة إلى معايير كتابة الكود العامة للمشروع، يجب أن يلتزم كود `BaseAgent` بالمبادئ التالية:
-   **قابلية التوسع (Extensibility):** تصميم الوحدات بطريقة تسمح بإضافة وظائف جديدة بسهولة دون تعديل الكود الحالي (مبدأ Open/Closed).
-   **قابلية الاختبار (Testability):** تصميم الوحدات لتكون سهلة الاختبار بشكل منفصل.
-   **النمطية (Modularity):** تقسيم الكود إلى وحدات صغيرة ومستقلة ذات مسؤوليات واضحة.
-   **الوثوقية (Reliability):** التعامل مع الحالات الاستثنائية والأخطاء بشكل رشيد.
-   **الوضوح (Clarity):** كود نظيف، مقروء، وموثق جيداً.

## 14. استراتيجية الاختبارات (Testing Strategy)

تتبع استراتيجية الاختبارات لـ `BaseAgent` نهجاً شاملاً لضمان الجودة والموثوقية:

-   **اختبارات الوحدات (Unit Tests):** اختبار كل وحدة (Module) أو وظيفة بشكل منفصل لضمان عملها الصحيح.
-   **اختبارات التكامل (Integration Tests):** اختبار تفاعل الوحدات المختلفة مع بعضها البعض ومع الخدمات الخارجية (مثل LLMs، قواعد البيانات).
-   **اختبارات الأداء (Performance Tests):** تقييم أداء `BaseAgent` تحت أحمال مختلفة.
-   **اختبارات الأمان (Security Tests):** التحقق من مقاومة `BaseAgent` للهجمات الأمنية.
-   **اختبارات السلوك (Behavioral Tests):** التأكد من أن `BaseAgent` يتصرف كما هو متوقع في سيناريوهات مختلفة، خاصة فيما يتعلق بالتفكير واستدعاء الأدوات.

## 15. استراتيجيات التشغيل والأداء (Operational and Performance Strategies)

### 15.1 قابلية التوسع (Scalability Strategy)

لضمان قدرة المنصة على التعامل مع زيادة الحمل وعدد العملاء الذكيين، سيتم تطبيق استراتيجيات قابلية التوسع التالية:
-   **التوسع الأفقي (Horizontal Scaling):** القدرة على إضافة المزيد من مثيلات `BaseAgent` و `Supervisor Agent` بشكل ديناميكي.
-   **الخدمات المصغرة (Microservices):** تقسيم المنصة إلى خدمات صغيرة مستقلة يمكن توسيعها بشكل فردي.
-   **الحوسبة بدون خادم (Serverless Computing):** استخدام وظائف بدون خادم (مثل AWS Lambda, Azure Functions) للمهام التي تتطلب توسعاً مرناً.
-   **قوائم انتظار الرسائل (Message Queues):** استخدام قوائم انتظار الرسائل لفصل المكونات وتمكين المعالجة غير المتزامنة.

### 15.2 التوافرية العالية (High Availability Strategy)

لضمان استمرارية الخدمة وتقليل وقت التوقف، سيتم تطبيق استراتيجيات التوافرية العالية:
-   **التكرار (Redundancy):** تشغيل مثيلات متعددة من المكونات الحيوية في مناطق توفر مختلفة.
-   **موازنة التحميل (Load Balancing):** توزيع حركة المرور بين المثيلات المتعددة.
-   **الكشف التلقائي عن الفشل والتعافي (Automated Failure Detection and Recovery):** استخدام أدوات الأوركسترا (مثل Kubernetes) للكشف عن المكونات الفاشلة واستبدالها تلقائياً.
-   **النسخ الاحتياطي والاستعادة (Backup and Restore):** سياسات نسخ احتياطي منتظمة للبيانات والتكوينات مع خطط استعادة مجربة.

### 15.3 استراتيجية التعافي من الكوارث (Disaster Recovery Strategy)

لضمان استمرارية العمل في حالة وقوع كارثة كبرى، سيتم وضع خطة للتعافي من الكوارث تتضمن:
-   **النسخ المتماثل عبر المناطق (Cross-Region Replication):** نسخ البيانات والتطبيقات إلى مناطق جغرافية مختلفة.
-   **أهداف وقت الاسترداد (RTO) وأهداف نقطة الاسترداد (RPO):** تحديد الأهداف الزمنية والمقدار المسموح به لفقدان البيانات.
-   **اختبار التعافي من الكوارث (DR Drills):** إجراء اختبارات دورية لخطة التعافي من الكوارث لضمان فعاليتها.

### 15.4 معايير الأداء (Performance Benchmarks)

سيتم تحديد معايير أداء واضحة لكل مكون من مكونات `BaseAgent` والمنصة ككل، وسيتم قياسها بانتظام. تتضمن هذه المعايير:
-   **زمن الاستجابة (Latency):** زمن معالجة الطلب من البداية إلى النهاية.
-   **الإنتاجية (Throughput):** عدد الطلبات التي يمكن معالجتها في وحدة زمنية.
-   **استخدام الموارد (Resource Utilization):** استخدام CPU، الذاكرة، والشبكة.

### 15.5 تخطيط القدرة (Capacity Planning)

سيتم إجراء تخطيط دوري للقدرة لضمان توفر الموارد الكافية لدعم النمو المتوقع للمنصة. يتضمن ذلك:
-   **تحليل الاتجاهات:** تحليل بيانات الاستخدام والأداء التاريخية للتنبؤ بالاحتياجات المستقبلية.
-   **نمذجة الحمل (Load Modeling):** محاكاة أحمال العمل المستقبلية لتقييم متطلبات الموارد.
-   **توفير الموارد (Resource Provisioning):** تخصيص الموارد بشكل استباقي لتلبية الطلبات المتزايدة.

### 15.6 استراتيجية التخزين المؤقت (Caching Strategy)

لتحسين الأداء وتقليل الحمل على قواعد البيانات والخدمات الخارجية، سيتم تطبيق استراتيجيات التخزين المؤقت:
-   **التخزين المؤقت للبيانات (Data Caching):** تخزين البيانات المستخدمة بشكل متكرر في ذاكرة التخزين المؤقت (مثل Redis, Memcached).
-   **التخزين المؤقت للنتائج (Result Caching):** تخزين نتائج العمليات المعقدة أو المكلفة.
-   **إدارة انتهاء صلاحية ذاكرة التخزين المؤقت (Cache Invalidation):** آليات لضمان تحديث البيانات المخزنة مؤقتاً.

### 15.7 معمارية قوائم الانتظار (Queue Architecture)

ستستخدم المنصة قوائم انتظار الرسائل (Message Queues) بشكل مكثف لفصل المكونات، تمكين المعالجة غير المتزامنة، وتحسين قابلية التوسع والموثوقية. تتضمن المعمارية:
-   **قوائم انتظار المهام (Task Queues):** لتوجيه المهام إلى العملاء الذكيين.
-   **قوائم انتظار الأحداث (Event Queues):** لنشر الأحداث بين المكونات.
-   **قوائم انتظار الرسائل الميتة (Dead-Letter Queues - DLQ):** للتعامل مع الرسائل التي فشلت معالجتها.

### 15.8 سياسة إصدار واجهة برمجة التطبيقات (API Versioning Policy)

لإدارة تطور واجهات برمجة التطبيقات (APIs) وضمان التوافق مع الإصدارات السابقة، سيتم تطبيق سياسة إصدار واجهة برمجة التطبيقات:
-   **الإصدار في المسار (Path Versioning):** تضمين رقم الإصدار في مسار URL (مثال: `/api/v1/agent`).
-   **الإصدار في الرأس (Header Versioning):** تضمين رقم الإصدار في رأس HTTP (مثال: `X-API-Version: 1`).
-   **التوثيق الواضح:** توثيق جميع التغييرات في واجهات برمجة التطبيقات في سجل التغييرات (CHANGELOG) الخاص بالمشروع.

## 16. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 17. التطور المستقبلي (Future Evolution)

تم تصميم معمارية `BaseAgent` ومنصة "بصيرة" مع الأخذ في الاعتبار التطور المستقبلي وقابلية التوسع لدعم المتطلبات المتزايدة. فيما يلي بعض جوانب التطور المستقبلي:

### 17.1 التوسع إلى أكثر من 100 وكيل ذكي (Scaling to 100+ AI Agents)
-   **معمارية Hub-and-Spoke:** تسمح بإضافة عدد غير محدود من العملاء الذكيين المتخصصين دون التأثير على العملاء الحاليين.
-   **قوائم انتظار الرسائل:** توفر آلية قوية للتواصل غير المتزامن بين العملاء، مما يمنع الاختناقات.
-   **التوسع الأفقي:** يمكن نشر مثيلات متعددة من `Supervisor Agent` والعملاء الذكيين في مجموعات (Clusters) موزعة.

### 17.2 تشغيل عدة نماذج LLM في نفس الوقت (Running Multiple LLMs Concurrently)
-   **طبقة LLM Abstraction:** تسمح بالتبديل السلس بين نماذج LLM المختلفة من مزودين متعددين.
-   **استراتيجية توجيه النماذج:** تمكن من توجيه المهام إلى النموذج الأنسب بناءً على التكلفة، الأداء، أو نوع المهمة.
-   **الحوسبة الموزعة:** يمكن توزيع استدعاءات LLM عبر موارد حوسبة مختلفة لتحقيق التوازي.

### 17.3 دعم MCP Servers و A2A Protocol (Supporting MCP Servers and A2A Protocol)
-   **واجهات API مرنة:** تصميم واجهات `SupervisorAPI` و `ExternalAPI` لتكون قابلة للتكيف مع بروتوكولات الاتصال المستقبلية مثل MCP (Model Context Protocol) و A2A (Agent-to-Agent Protocol).
-   **طبقة بروتوكول قابلة للتوسعة:** إمكانية إضافة محولات (Adapters) جديدة لدعم بروتوكولات الاتصال المختلفة.

### 17.4 دعم الحوسبة الموزعة والخدمات المصغرة (Distributed Computing and Microservices)
-   **تصميم معياري:** `BaseAgent` مصمم كوحدة مستقلة يمكن نشرها كخدمة مصغرة.
-   **Kubernetes:** استخدام Kubernetes لإدارة ونشر الخدمات المصغرة، مما يوفر قابلية التوسع، التوافرية العالية، وإدارة الموارد.
-   **قوائم انتظار الرسائل:** أساس للتواصل بين الخدمات المصغرة في بيئة موزعة.

### 17.5 دعم العمل السحابي والمحلي Hybrid Deployment (Hybrid Cloud/On-Premise Deployment)
-   **البنية التحتية المحايدة للسحابة (Cloud-Agnostic Infrastructure):** تصميم المنصة لتكون مستقلة عن مزود سحابي معين، مما يسهل النشر في بيئات سحابية مختلفة أو في بيئات محلية.
-   **Docker و Kubernetes:** توفير حاويات (Containers) لـ `BaseAgent` والخدمات الأخرى، مما يضمن قابلية النقل عبر البيئات.

### 17.6 دعم التعلم المستمر للوكلاء (Continuous Learning for Agents)
-   **وكيل التعلم (Learning Agent):** يمكن لوكيل متخصص مراقبة أداء العملاء الآخرين، جمع البيانات، وتدريب نماذج جديدة أو تحسين الـ Prompts بشكل مستمر.
-   **حلقات التغذية الراجعة (Feedback Loops):** دمج آليات لجمع التغذية الراجعة من المستخدمين أو من أداء العملاء الذكيين لتحسين سلوكهم.

### 17.7 دعم إضافة وكلاء جدد دون تعديل BaseAgent (Adding New Agents Without Modifying BaseAgent)
-   **الوراثة من BaseAgent:** العملاء الذكيون الجدد يرثون جميع الوظائف الأساسية من `BaseAgent`.
-   **معمارية الإضافات (Plugin Architecture):** تسمح بتخصيص سلوك العميل الذكي الجديد عن طريق إضافة إضافات (Plugins) بدلاً من تعديل الكود الأساسي لـ `BaseAgent`.
-   **التكوين (Configuration-driven):** يمكن تكوين العملاء الذكيين الجدد بشكل كبير عبر ملفات التكوين بدلاً من الكود.

## 18. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 19. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)



### 3.5 مخطط المكونات (Component Diagram)

```d2
direction: right

BaseAgentComponent: { shape: component; label: "BaseAgent Component" }
MemoryManagerComponent: { shape: component; label: "Memory Manager" }
ReasoningEngineComponent: { shape: component; label: "Reasoning Engine" }
ToolExecutorComponent: { shape: component; label: "Tool Executor" }
LLMInterfaceComponent: { shape: component; label: "LLM Interface" }
ErrorHandlerComponent: { shape: component; label: "Error Handler" }
LoggerComponent: { shape: component; label: "Logger" }
SecurityManagerComponent: { shape: component; label: "Security Manager" }
PluginManagerComponent: { shape: component; label: "Plugin Manager" }

BaseAgentComponent -> MemoryManagerComponent: "يحتوي على"
BaseAgentComponent -> ReasoningEngineComponent: "يحتوي على"
BaseAgentComponent -> ToolExecutorComponent: "يحتوي على"
BaseAgentComponent -> LLMInterfaceComponent: "يحتوي على"
BaseAgentComponent -> ErrorHandlerComponent: "يحتوي على"
BaseAgentComponent -> LoggerComponent: "يحتوي على"
BaseAgentComponent -> SecurityManagerComponent: "يحتوي على"
BaseAgentComponent -> PluginManagerComponent: "يحتوي على"

ReasoningEngineComponent -> MemoryManagerComponent: "يستخدم"
ReasoningEngineComponent -> ToolExecutorComponent: "يستخدم"
ReasoningEngineComponent -> LLMInterfaceComponent: "يستخدم"
ReasoningEngineComponent -> ErrorHandlerComponent: "يستخدم"
ReasoningEngineComponent -> LoggerComponent: "يستخدم"
ReasoningEngineComponent -> SecurityManagerComponent: "يستخدم"
PluginManagerComponent -> BaseAgentComponent: "يوسع"
```

### 3.6 مخطط الفئات (Class Diagram)

```d2
direction: right

class BaseAgent {
  + id: str
  + name: str
  + memory_manager: MemoryManager
  + reasoning_engine: ReasoningEngine
  + tool_executor: ToolExecutor
  + llm_interface: LLMInterface
  + error_handler: ErrorHandler
  + logger: Logger
  + security_manager: SecurityManager
  + plugin_manager: PluginManager
  + __init__(...)
  + handle_request(request: AgentRequest) -> AgentResponse
  + _initialize_agent()
  + _terminate_agent()
}

class MemoryManager {
  + short_term_memory: ShortTermMemory
  + long_term_memory: LongTermMemory
  + retrieve_context(task_id: str) -> Context
  + update_memory(task_id: str, data: Any)
}

class ReasoningEngine {
  + reason(task: Task, context: Context, tools: List[Tool]) -> Action
  + _plan_task(task: Task, context: Context) -> Plan
  + _select_tool(plan: Plan, available_tools: List[Tool]) -> Tool
  + _generate_tool_input(tool: Tool, context: Context) -> Dict
}

class ToolExecutor {
  + execute_tool(tool: Tool, input: Dict) -> ToolOutput
}

class LLMInterface {
  + generate_response(prompt: Prompt, model_config: Dict) -> LLMResponse
  + embed_text(text: str) -> Embedding
}

class ErrorHandler {
  + handle_error(error: Exception, context: Dict) -> ErrorRecoveryStrategy
  + _retry_operation(operation: Callable, retries: int) -> Any
}

class Logger {
  + log(level: LogLevel, message: str, context: Dict)
}

class SecurityManager {
  + authorize_tool_access(agent_id: str, tool_name: str) -> bool
  + encrypt_data(data: str) -> str
}

class PluginManager {
  + load_plugin(plugin_name: str)
  + unload_plugin(plugin_name: str)
  + get_available_plugins() -> List[Plugin]
}

BaseAgent *-- MemoryManager
BaseAgent *-- ReasoningEngine
BaseAgent *-- ToolExecutor
BaseAgent *-- LLMInterface
BaseAgent *-- ErrorHandler
BaseAgent *-- Logger
BaseAgent *-- SecurityManager
BaseAgent *-- PluginManager

ReasoningEngine --> MemoryManager: "يستخدم"
ReasoningEngine --> ToolExecutor: "يستخدم"
ReasoningEngine --> LLMInterface: "يستخدم"
ReasoningEngine --> ErrorHandler: "يستخدم"
ReasoningEngine --> Logger: "يستخدم"
ReasoningEngine --> SecurityManager: "يستخدم"

MemoryManager --> ShortTermMemory
MemoryManager --> LongTermMemory

LLMInterface --> PromptManager
```

### 3.7 مخطط التسلسل (Sequence Diagram) - مثال: معالجة طلب بسيط

```d2
direction: right

SupervisorAgent -> BaseAgent: request(task_id, query)
BaseAgent -> ReasoningEngine: analyze_request(query)
ReasoningEngine -> MemoryManager: retrieve_context(task_id)
MemoryManager --> ReasoningEngine: context
ReasoningEngine -> LLMInterface: generate_plan(query, context)
LLMInterface --> ReasoningEngine: plan
ReasoningEngine -> ToolExecutor: select_tool(plan)
ToolExecutor --> ReasoningEngine: tool_info
ReasoningEngine -> ToolExecutor: execute_tool(tool_info, input)
ToolExecutor --> ReasoningEngine: tool_output
ReasoningEngine -> MemoryManager: update_memory(task_id, tool_output)
MemoryManager --> ReasoningEngine: memory_updated
ReasoningEngine -> LLMInterface: generate_response(plan, tool_output, context)
LLMInterface --> ReasoningEngine: final_response
ReasoningEngine --> BaseAgent: agent_response
BaseAgent --> SupervisorAgent: response(task_id, agent_response)
```

### 3.8 مخطط النشر (Deployment Diagram)

```d2
direction: right

cloud "منصة بصيرة السحابية" {
  cluster "Kubernetes Cluster" {
    node "Worker Node 1" {
      container "Supervisor Agent Pod" {
        process "Supervisor Agent"
      }
      container "BaseAgent Instance 1 (وكيل التحليل الفني)" {
        process "BaseAgent"
      }
      container "BaseAgent Instance 2 (وكيل أخبار السوق)" {
        process "BaseAgent"
      }
    }
    node "Worker Node N" {
      container "BaseAgent Instance N" {
        process "BaseAgent"
      }
    }
  }
  database "Vector DB (ذاكرة طويلة المدى)"
  database "Relational DB (حالة، تكوينات)"
  queue "Message Queue (Kafka/RabbitMQ)"
  storage "Object Storage (S3)"
}

external_system "مزودو LLM (OpenAI, Gemini)"
external_system "مزودو بيانات السوق (Tadawul API)"

"Supervisor Agent" <-> "BaseAgent Instance 1 (وكيل التحليل الفني)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance 2 (وكيل أخبار السوق)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance N": "يتواصل عبر"

"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو LLM (OpenAI, Gemini)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو بيانات السوق (Tadawul API)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Vector DB (ذاكرة طويلة المدى)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Relational DB (حالة، تكوينات)": "يستخدم"

"Message Queue (Kafka/RabbitMQ)" <-> "Supervisor Agent": "للتواصل غير المتزامن"
"Object Storage (S3)" <-> "BaseAgent Instance N": "لتخزين البيانات الكبيرة"
```

### 3.9 مخطط تدفق البيانات (Data Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
LLMProviders: { shape: cloud; label: "مزودو LLM" }
ExternalTools: { shape: cloud; label: "أدوات خارجية" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى" }

User -> SupervisorAgent: "طلب تحليلي"
SupervisorAgent -> BaseAgent: "توجيه المهمة"

BaseAgent -> ShortTermMemory: "قراءة/كتابة السياق"
BaseAgent -> LongTermMemory: "قراءة/كتابة المعرفة"
BaseAgent -> LLMProviders: "استدعاء LLM (Prompt)"
LLMProviders -> BaseAgent: "استجابة LLM"
BaseAgent -> ExternalTools: "استدعاء أداة"
ExternalTools -> BaseAgent: "مخرجات الأداة"

BaseAgent -> SupervisorAgent: "نتائج المهمة"
SupervisorAgent -> User: "التحليل النهائي"
```

### 3.10 مخطط تدفق الأحداث (Event Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
MessageQueue: { shape: queue; label: "Message Queue" }

User -> SupervisorAgent: "يرسل طلب"
SupervisorAgent -> MessageQueue: "ينشر حدث: TaskAssigned"
MessageQueue -> BaseAgent: "يستقبل حدث: TaskAssigned"
BaseAgent -> BaseAgent: "يعالج المهمة"
BaseAgent -> MessageQueue: "ينشر حدث: TaskCompleted/TaskFailed"
MessageQueue -> SupervisorAgent: "يستقبل حدث: TaskCompleted/TaskFailed"
SupervisorAgent -> User: "يرسل إشعار/نتيجة"
```

### 3.11 مخطط تدفق الذاكرة (Memory Flow Diagram)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى (Redis/In-memory)" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى (Vector DB/Relational DB)" }

BaseAgent -> ShortTermMemory: "يخزن/يسترجع سياق الجلسة"
BaseAgent -> LongTermMemory: "يخزن/يسترجع المعرفة الدائمة"

ShortTermMemory -> LongTermMemory: "ترحيل السياق الهام (عند الحاجة)"
LongTermMemory -> ShortTermMemory: "استرجاع المعرفة ذات الصلة"
```

### 3.12 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 3.13 تدفق معالجة الـ Prompt (Prompt Processing Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
PromptManager: { shape: rectangle; label: "Prompt Manager" }
MemoryManager: { shape: rectangle; label: "Memory Manager" }
LLMInterface: { shape: rectangle; label: "LLM Interface" }
LLMProvider: { shape: cloud; label: "مزود LLM" }

BaseAgent -> PromptManager: "طلب توليد Prompt"
PromptManager -> MemoryManager: "يسترجع السياق ذي الصلة"
MemoryManager --> PromptManager: "السياق والذاكرة"
PromptManager -> PromptManager: "يطبق القوالب ويضغط السياق"
PromptManager --> BaseAgent: "Prompt النهائي"
BaseAgent -> LLMInterface: "يرسل Prompt لـ LLM"
LLMInterface -> LLMProvider: "يرسل Prompt"
LLMProvider --> LLMInterface: "استجابة LLM"
LLMInterface --> BaseAgent: "استجابة LLM"
```

### 3.14 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine -> BaseAgent: "يستأنف/يفشل المهمة"
```

### 3.15 مخطط انتقال الحالة (State Transition Diagram)

```d2
direction: right

stateDiagram-v2
    [*] --> Idle
    Idle --> Initializing: "استلام طلب"
    Initializing --> Ready: "تم التهيئة بنجاح"
    Ready --> Processing: "بدء معالجة المهمة"
    Processing --> Processing: "خطوة مهمة (تفكير/أداة)"
    Processing --> Ready: "المهمة مكتملة"
    Processing --> Failed: "فشل المهمة"
    Failed --> Ready: "إعادة تعيين/محاولة جديدة"
    Ready --> Terminating: "طلب إنهاء"
    Initializing --> Failed: "فشل التهيئة"
    Terminating --> [*]: "تم الإنهاء"
```

## 4. دورة حياة الوكيل (Agent Lifecycle)

تتبع دورة حياة `BaseAgent` المراحل التالية:

1.  **التهيئة (Initialization):**
    *   يتم إنشاء مثيل (instance) لـ `BaseAgent` أو العميل الذكي المشتق منه.
    *   يتم تحميل التكوينات الخاصة بالعميل (مثل الأدوات المتاحة، إعدادات الذاكرة، إعدادات LLM).
    *   يتم تهيئة وحدات الذاكرة، ومحرك التفكير، ومنفذ الأدوات.
    *   يتم تسجيل العميل الذكي لدى `Supervisor Agent` (إذا لزم الأمر).

2.  **التنفيذ (Execution):**
    *   يستقبل العميل الذكي طلباً أو مهمة من `Supervisor Agent` عبر واجهة `SupervisorAPI`.
    *   يقوم `ReasoningEngine` بتحليل الطلب، واستخدام الذاكرة، واستدعاء الأدوات، والتفاعل مع LLM لتوليد استجابة أو اتخاذ إجراء.
    *   تتكرر هذه العملية حتى تكتمل المهمة أو يتم الوصول إلى حالة نهائية.

3.  **الإنهاء (Termination):**
    *   يتم تحرير الموارد التي يستخدمها العميل الذكي (مثل اتصالات قاعدة البيانات، جلسات LLM).
    *   يتم حفظ أي حالة ضرورية للذاكرة طويلة المدى.
    *   يتم إلغاء تسجيل العميل الذكي من `Supervisor Agent`.

## 5. تدفق البيانات وتنفيذ المهام (Data Flow and Task Execution)

### 5.1 آلية التواصل مع Supervisor Agent (Communication with Supervisor Agent)

يعتمد التواصل بين العملاء الذكيين و`Supervisor Agent` على معمارية Hub-and-Spoke. `BaseAgent` يتصل بـ `Supervisor Agent` عبر واجهة `SupervisorAPI` الموحدة. لا يوجد اتصال مباشر بين العملاء الذكيين المتخصصين.

**تدفق الاتصال:**
1.  **الطلب:** يرسل `Supervisor Agent` طلباً (مهمة) إلى عميل ذكي محدد (أو مجموعة عملاء) عبر واجهة `SupervisorAPI` الخاصة به.
2.  **المعالجة:** يستقبل العميل الذكي الطلب، يقوم بمعالجته باستخدام `ReasoningEngine`، الذاكرة، والأدوات.
3.  **الاستجابة:** يرسل العميل الذكي النتائج أو التقدم المحرز إلى `Supervisor Agent` عبر نفس الواجهة.
4.  **التجميع:** يقوم `Supervisor Agent` بتجميع الاستجابات من العملاء المختلفين وتنسيقها.

### 5.2 بروتوكول الاتصال متعدد العملاء (Multi-Agent Communication Protocol)

لضمان التواصل الفعال والآمن بين `Supervisor Agent` والعملاء الذكيين، سيتم استخدام بروتوكول اتصال موحد يعتمد على الرسائل غير المتزامنة (Asynchronous Messaging) عبر قائمة انتظار رسائل (Message Queue) مثل Kafka أو RabbitMQ. هذا يضمن:
-   **المرونة:** فصل المرسل عن المستقبل.
-   **قابلية التوسع:** سهولة إضافة المزيد من العملاء أو `Supervisor Agents`.
-   **الموثوقية:** ضمان تسليم الرسائل حتى في حالة تعطل أحد المكونات.

**هيكل الرسالة (Message Structure):**
ستتبع الرسائل تنسيق JSON موحد يتضمن:
-   `message_id`: معرف فريد للرسالة.
-   `sender_id`: معرف العميل المرسل.
-   `receiver_id`: معرف العميل المستهدف (أو `broadcast`).
-   `message_type`: نوع الرسالة (مثال: `TaskRequest`, `TaskResponse`, `StatusUpdate`).
-   `payload`: الحمولة الفعلية للرسالة (بيانات المهمة، النتائج، الأخطاء).
-   `timestamp`: وقت إرسال الرسالة.
-   `signature`: توقيع رقمي لضمان سلامة الرسالة ومصدرها.

### 5.3 دورة تنفيذ المهام (Task Execution Flow)

1.  **استلام المهمة:** `BaseAgent` يستقبل مهمة من `Supervisor Agent`.
2.  **تحليل المهمة:** `ReasoningEngine` يحلل المهمة، ويحدد الأهداف الفرعية والإجراءات المطلوبة.
3.  **استرجاع السياق:** `MemoryManager` يسترجع المعلومات ذات الصلة من الذاكرة قصيرة وطويلة المدى.
4.  **التفكير (Reasoning):** `ReasoningEngine` يستخدم LLM (عبر `LLMInterface`) لتوليد خطة عمل، أو تحديد الأداة المناسبة للاستدعاء، أو صياغة استجابة.
5.  **تنفيذ الأداة (Tool Execution):** إذا تطلب الأمر، يقوم `ToolExecutor` باستدعاء الأداة المحددة، ويتم تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
6.  **تحديث الذاكرة:** يتم تحديث الذاكرة بالنتائج الجديدة أو التغييرات في الحالة.
7.  **تكرار أو إنهاء:** تتكرر الخطوات 2-6 حتى تكتمل المهمة أو يتم الوصول إلى استجابة نهائية.
8.  **إرسال الاستجابة:** يرسل `BaseAgent` الاستجابة النهائية إلى `Supervisor Agent`.

## 6. إدارة الحالة والذاكرة (State and Memory Management)

### 6.1 إدارة الحالة (State Management)
يحتفظ `BaseAgent` بحالة داخلية لكل مهمة قيد التنفيذ. تتضمن هذه الحالة:
-   **معرف المهمة (Task ID):** لتتبع المهام المتعددة.
-   **حالة المهمة (Task Status):** (قيد التنفيذ، مكتملة، فاشلة، معلقة).
-   **الخطوات المنفذة (Executed Steps):** سجل بالخطوات التي تم اتخاذها.
-   **المدخلات والمخرجات الحالية (Current Inputs/Outputs):** البيانات التي يتم معالجتها.
-   **الموارد المستخدمة (Used Resources):** الأدوات أو نماذج LLM المستدعاة.

يتم تحديث الحالة بشكل مستمر بواسطة `ReasoningEngine` ويتم حفظها في الذاكرة قصيرة المدى.

### 6.2 نظام الذاكرة قصيرة المدى (Short-Term Memory)
-   **الغرض:** تخزين السياق الحالي للمهمة، المحادثات الجارية، والنتائج الوسيطة.
-   **الآلية:** يتم استخدام هياكل بيانات داخلية (مثل القواميس أو الكائنات) لتخزين المعلومات في الذاكرة العاملة للعميل الذكي. يمكن أن تكون هذه الذاكرة عابرة (in-memory) أو مخزنة مؤقتاً في قاعدة بيانات سريعة (مثل Redis) للمهام الأطول.
-   **إدارة السياق (Context Management):** يتم تجميع السياق ذي الصلة من الذاكرة قصيرة المدى وتقديمه إلى LLM كجزء من الـ Prompt. يتم تطبيق تقنيات ضغط السياق (Context Compression) عند الضرورة للحفاظ على حجم الـ Prompt ضمن حدود LLM.

### 6.3 نظام الذاكرة طويلة المدى (Long-Term Memory)
-   **الغرض:** تخزين المعرفة الدائمة، الدروس المستفادة، التفضيلات، والبيانات التاريخية التي يحتاجها العميل الذكي عبر جلسات متعددة أو مهام مختلفة.
-   **الآلية:** يتم استخدام قواعد بيانات متخصصة (مثل Vector Databases لتخزين التضمينات الدلالية، أو قواعد بيانات علائقية/NoSQL لتخزين البيانات المنظمة) لتخزين الذاكرة طويلة المدى. يتم استرجاع المعلومات باستخدام تقنيات البحث الدلالي (Semantic Search) أو الاستعلامات التقليدية.

### 6.4 إدارة نافذة السياق (Context Window Management)

لتحسين كفاءة استخدام نماذج LLM والتحكم في التكلفة، سيتم تطبيق استراتيجيات لإدارة نافذة السياق:
-   **التقطيع (Chunking):** تقسيم النصوص الطويلة إلى أجزاء أصغر.
-   **التلخيص (Summarization):** تلخيص الأجزاء الأقل أهمية من السياق.
-   **الاسترجاع الانتقائي (Selective Retrieval):** استرجاع الأجزاء الأكثر صلة فقط من الذاكرة طويلة المدى.
-   **الضغط (Compression):** استخدام تقنيات ضغط السياق لتقليل عدد الرموز (tokens) المرسلة إلى LLM.

### 6.5 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 6.6 استراتيجية ضغط الذاكرة (Memory Compression Strategy)

لتحسين كفاءة الذاكرة طويلة المدى وتقليل تكاليف التخزين والاسترجاع، سيتم تطبيق استراتيجيات ضغط الذاكرة:
-   **التضمين الدلالي (Semantic Embedding):** تحويل النصوص إلى متجهات (vectors) لتقليل حجم التخزين وتمكين البحث الدلالي.
-   **التلخيص الدوري (Periodic Summarization):** تلخيص المحادثات أو الأحداث التاريخية بشكل دوري وتخزين الملخصات بدلاً من النصوص الكاملة.
-   **إزالة البيانات القديمة/غير ذات الصلة (Pruning):** حذف البيانات التي تجاوزت فترة صلاحيتها أو التي لم تعد ذات صلة.

## 7. نظام التفكير والاستدلال (Reasoning Pipeline)

`ReasoningEngine` هو قلب `BaseAgent`، وهو المسؤول عن توجيه سلوك العميل الذكي. يتبع هذا النظام عادةً نمط "التفكير/العمل" (Think/Act) أو "التخطيط/التنفيذ" (Plan/Execute).

### 7.1 مراحل التفكير (Reasoning Stages)
1.  **فهم المهمة (Task Understanding):** تحليل الطلب الوارد وتحديد النية والأهداف الرئيسية.
2.  **توليد الخطة (Plan Generation):** استخدام LLM لتوليد خطة عمل خطوة بخطوة لتحقيق الأهداف، مع الأخذ في الاعتبار السياق والذاكرة والأدوات المتاحة.
3.  **اختيار الأداة (Tool Selection):** تحديد الأداة الأنسب لتنفيذ الخطوة الحالية من الخطة.
4.  **توليد المدخلات للأداة (Tool Input Generation):** صياغة المدخلات اللازمة للأداة المختارة بناءً على السياق.
5.  **تحليل المخرجات (Output Analysis):** تقييم مخرجات الأداة أو استجابة LLM وتحديد الخطوة التالية.
6.  **تحديث الحالة والذاكرة (State & Memory Update):** تسجيل التقدم المحرز وتحديث الذاكرة.

### 7.2 آلية اتخاذ القرار (Decision-Making Mechanism)
تعتمد آلية اتخاذ القرار على مزيج من:
-   **نماذج LLM:** لتوليد الأفكار، الخطط، واختيار الأدوات بناءً على الـ Prompts المصممة بعناية.
-   **المنطق البرمجي (Programmatic Logic):** قواعد محددة مسبقاً للتعامل مع السيناريوهات الشائعة أو الحالات الحرجة.
-   **الذاكرة:** استخدام المعلومات المخزنة لتوجيه القرارات.

## 8. نظام استدعاء الأدوات (Tool Calling Framework)

`ToolExecutor` هو الوحدة المسؤولة عن إدارة واستدعاء الأدوات الخارجية التي يمكن للعميل الذكي استخدامها.

### 8.1 كيفية استخدام الأدوات (How Tools are Used)
1.  **تعريف الأداة:** يتم تعريف الأدوات بوضوح (اسم، وصف، معلمات المدخلات، نوع المخرجات) ليتمكن LLM من فهمها واستدعائها بشكل صحيح.
2.  **اختيار الأداة:** يقوم `ReasoningEngine` (بمساعدة LLM) باختيار الأداة المناسبة بناءً على المهمة الحالية.
3.  **تنفيذ الأداة:** يقوم `ToolExecutor` باستدعاء الأداة الفعلية، مع تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
4.  **معالجة المخرجات:** يتم استقبال مخرجات الأداة وتحليلها بواسطة `ReasoningEngine` لمواصلة دورة التفكير.

### 8.2 إدارة الأدوات (Tool Management)
-   **اكتشاف الأدوات (Tool Discovery):** آلية لتسجيل واكتشاف الأدوات المتاحة للعميل الذكي.
-   **التحقق من صحة الأدوات (Tool Validation):** التأكد من أن الأدوات تعمل بشكل صحيح وأن معلمات المدخلات والمخرجات متوافقة.
-   **عزل الأدوات (Tool Isolation):** تشغيل الأدوات في بيئات معزولة لتقليل المخاطر الأمنية وتأثير الأخطاء.

### 8.3 نظام Plugins والتوسعة المستقبلية (Plugins and Future Extensibility)
يدعم `BaseAgent` نظام إضافات (Plugins) يسمح بتوسيع وظائفه ديناميكياً دون الحاجة لتعديل الكود الأساسي. يمكن للإضافات توفير أدوات جديدة، تعديل سلوك التفكير، أو إضافة قدرات ذاكرة جديدة.

### 8.4 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 8.5 معمارية الإضافات (Plugin Architecture)

تعتمد معمارية الإضافات على مبدأ التحميل الديناميكي (Dynamic Loading) والفصل بين الإضافات والمنطق الأساسي. كل إضافة ستكون عبارة عن وحدة برمجية مستقلة (مثل حزمة Python) تلتزم بواجهة محددة (Plugin Interface). هذا يسمح بـ:
-   **التوسعة السهلة:** إضافة وظائف جديدة دون تعديل `BaseAgent`.
-   **العزل:** فشل إضافة لا يؤثر على عمل `BaseAgent` الأساسي.
-   **إدارة الإصدارات:** يمكن تحديث الإضافات بشكل مستقل.

## 9. طبقة الاتصال بنماذج الذكاء الاصطناعي (LLM Abstraction Layer)

### 9.1 الغرض (Purpose)
توفر هذه الطبقة واجهة موحدة للعملاء الذكيين للتفاعل مع نماذج الذكاء الاصطناعي الكبيرة (LLMs) المختلفة، بغض النظر عن المزود (مثل OpenAI, Gemini) أو النموذج المحدد. هذا يضمن المرونة، سهولة التبديل بين النماذج، وعزل منطق العميل الذكي عن تفاصيل API الخاصة بكل LLM.

### 9.2 المكونات (Components)
-   **LLM Provider Interface:** واجهة عامة تحدد طرق الاتصال الأساسية (مثل `generate_response`, `embed_text`).
-   **Concrete LLM Adapters:** تطبيقات محددة لـ `LLM Provider Interface` لكل مزود LLM (مثال: `OpenAIAdapter`, `GeminiAdapter`).
-   **Prompt Manager:** وحدة مسؤولة عن صياغة الـ Prompts، إدارة القوالب، وضغط السياق قبل إرسالها إلى LLM.

### 9.3 استراتيجية توجيه النماذج (Model Routing Strategy)

لتحسين الأداء والتكلفة، سيتم تطبيق استراتيجية توجيه ذكية للنماذج:
-   **التوجيه بناءً على المهمة:** توجيه المهام المختلفة إلى نماذج LLM الأنسب (مثال: نموذج سريع ورخيص للمهام البسيطة، نموذج قوي ومكلف للمهام المعقدة).
-   **التوجيه بناءً على التكلفة/الأداء:** اختيار النموذج بناءً على التوازن بين التكلفة والأداء المطلوب.
-   **التوجيه بناءً على التوفر:** التبديل التلقائي بين المزودين في حالة عدم توفر نموذج معين.

### 9.4 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 9.5 استراتيجية إصدار الـ Prompt (Prompt Versioning Strategy)

لإدارة تطور الـ Prompts وضمان إمكانية التتبع والتحكم، سيتم تطبيق استراتيجية لإصدار الـ Prompts:
-   **التخزين المركزي:** تخزين جميع الـ Prompts في مستودع مركزي (مثل نظام التحكم في الإصدارات Git أو قاعدة بيانات).
-   **الإصدارات (Versioning):** تعيين رقم إصدار لكل Prompt، مما يسمح بالعودة إلى إصدارات سابقة وتتبع التغييرات.
-   **الاختبار A/B:** إمكانية اختبار إصدارات مختلفة من الـ Prompts لتقييم فعاليتها.

## 10. إدارة الأخطاء وإعادة المحاولة (Error Handling and Retry)

### 10.1 آليات اكتشاف الأخطاء (Error Detection Mechanisms)
-   **التحقق من صحة المدخلات (Input Validation):** التحقق من صحة المدخلات قبل معالجتها.
-   **مراقبة استجابات الأدوات و LLM:** تحليل استجابات الأدوات ونماذج LLM لاكتشاف الأخطاء أو الاستجابات غير المتوقعة.
-   **الاستثناءات (Exceptions):** استخدام آليات الاستثناءات القياسية في البرمجة.

### 10.2 استراتيجيات إعادة المحاولة (Retry Strategies)
-   **إعادة المحاولة الأسية (Exponential Backoff):** إعادة محاولة العمليات الفاشلة مع زيادة زمن الانتظار بين المحاولات.
-   **الحد الأقصى للمحاولات (Max Retries):** تحديد عدد أقصى للمحاولات قبل الإبلاغ عن فشل دائم.

### 10.3 التعافي من الأخطاء (Error Recovery)
-   **العودة إلى حالة سابقة (Rollback):** التراجع عن التغييرات التي تمت قبل حدوث الخطأ.
-   **الإبلاغ عن الخطأ (Error Reporting):** إرسال تفاصيل الخطأ إلى `Supervisor Agent` أو نظام المراقبة.
-   **التعامل مع الأخطاء المعروفة (Known Error Handling):** وجود منطق محدد للتعامل مع أنواع معينة من الأخطاء.

### 10.4 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine -> BaseAgent: "يستأنف/يفشل المهمة"
```

## 11. نظام التسجيل والمراقبة (Logging and Monitoring)

### 11.1 التسجيل (Logging)
-   **مستويات التسجيل:** دعم مستويات تسجيل مختلفة (DEBUG, INFO, WARNING, ERROR, CRITICAL).
-   **تنسيق السجلات:** تنسيق موحد للسجلات يسهل التحليل (JSON).
-   **محتوى السجلات:** تسجيل تفاصيل المهمة، خطوات التفكير، استدعاءات الأدوات، استجابات LLM، والأخطاء.
-   **تخزين السجلات:** تخزين السجلات في نظام مركزي (مثل ELK Stack) للتحليل والمراجعة.

### 11.2 المراقبة (Monitoring)
-   **المقاييس (Metrics):** جمع مقاييس الأداء (مثل زمن الاستجابة، معدل النجاح/الفشل، استخدام الموارد).
-   **لوحات المعلومات (Dashboards):** توفير لوحات معلومات لمراقبة صحة وأداء العملاء الذكيين في الوقت الفعلي.
-   **التنبيهات (Alerts):** إعداد تنبيهات عند تجاوز المقاييس لحدود معينة أو عند حدوث أخطاء حرجة.

### 11.3 معمارية الملاحظة (Observability Architecture)

لضمان رؤية عميقة لأداء وسلوك العملاء الذكيين، سيتم تطبيق معمارية ملاحظة شاملة تتضمن:
-   **التسجيل المنظم (Structured Logging):** استخدام تنسيق JSON للسجلات لسهولة التحليل الآلي.
-   **المقاييس (Metrics):** جمع مقاييس الأداء والتشغيل (CPU, Memory, Latency, Error Rates) باستخدام أدوات مثل Prometheus.
-   **التتبع الموزع (Distributed Tracing):** تتبع مسار الطلب عبر العملاء الذكيين والخدمات المختلفة باستخدام أدوات مثل Jaeger أو OpenTelemetry.

### 11.4 تصميم القياس عن بعد (Telemetry Design)

سيتم تصميم نظام القياس عن بعد لجمع البيانات التشغيلية الهامة من `BaseAgent` والعملاء الذكيين المشتقين منه. يتضمن ذلك:
-   **بيانات الأداء:** زمن تنفيذ المهام، زمن استجابة LLM، زمن استدعاء الأدوات.
-   **بيانات الاستخدام:** عدد استدعاءات LLM، عدد استدعاءات الأدوات، عدد الرموز المستخدمة.
-   **بيانات الأخطاء:** أنواع الأخطاء، تكرارها، وسياق حدوثها.
-   **بيانات الموارد:** استخدام CPU، الذاكرة، والشبكة.

## 12. نظام الصلاحيات والأمان (Authorization and Security System)

### 12.1 مبادئ الأمان (Security Principles)
-   **الامتياز الأقل (Least Privilege):** يجب أن يمتلك كل عميل ذكي الحد الأدنى من الصلاحيات اللازمة لأداء وظيفته.
-   **عزل الموارد (Resource Isolation):** عزل موارد العملاء الذكيين عن بعضها البعض.
-   **التشفير (Encryption):** تشفير البيانات الحساسة أثناء النقل وفي وضع السكون.
-   **التحقق من صحة المدخلات (Input Validation):** حماية ضد حقن الـ Prompts (Prompt Injection) وغيرها من الهجمات.

### 12.2 آليات الصلاحيات (Authorization Mechanisms)
-   **رموز الوصول (Access Tokens):** استخدام رموز وصول مؤقتة ومحدودة الصلاحية للوصول إلى الأدوات الخارجية أو الخدمات.
-   **التحكم في الوصول المستند إلى الدور (Role-Based Access Control - RBAC):** تحديد الصلاحيات بناءً على دور العميل الذكي.

### 12.3 نموذج التهديد الأمني (Security Threat Model)

سيتم تطوير نموذج تهديد أمني شامل لتحديد وتحليل وتخفيف المخاطر الأمنية المحتملة لـ `BaseAgent` والمنصة ككل. سيتضمن ذلك:
-   **تحديد الأصول:** البيانات الحساسة، الوظائف الحيوية، واجهات برمجة التطبيقات.
-   **تحديد التهديدات:** هجمات حقن الـ Prompt، الوصول غير المصرح به، تسرب البيانات، هجمات حجب الخدمة (DoS).
-   **تحديد نقاط الضعف:** أخطاء في الكود، تكوينات خاطئة، نقاط ضعف في المكتبات الخارجية.
-   **تحديد الضوابط:** آليات المصادقة، التشفير، التحقق من صحة المدخلات، المراقبة الأمنية.

## 13. معايير كتابة الكود الخاصة بـ BaseAgent (BaseAgent Coding Standards)

بالإضافة إلى معايير كتابة الكود العامة للمشروع، يجب أن يلتزم كود `BaseAgent` بالمبادئ التالية:
-   **قابلية التوسع (Extensibility):** تصميم الوحدات بطريقة تسمح بإضافة وظائف جديدة بسهولة دون تعديل الكود الحالي (مبدأ Open/Closed).
-   **قابلية الاختبار (Testability):** تصميم الوحدات لتكون سهلة الاختبار بشكل منفصل.
-   **النمطية (Modularity):** تقسيم الكود إلى وحدات صغيرة ومستقلة ذات مسؤوليات واضحة.
-   **الوثوقية (Reliability):** التعامل مع الحالات الاستثنائية والأخطاء بشكل رشيد.
-   **الوضوح (Clarity):** كود نظيف، مقروء، وموثق جيداً.

## 14. استراتيجية الاختبارات (Testing Strategy)

تتبع استراتيجية الاختبارات لـ `BaseAgent` نهجاً شاملاً لضمان الجودة والموثوقية:

-   **اختبارات الوحدات (Unit Tests):** اختبار كل وحدة (Module) أو وظيفة بشكل منفصل لضمان عملها الصحيح.
-   **اختبارات التكامل (Integration Tests):** اختبار تفاعل الوحدات المختلفة مع بعضها البعض ومع الخدمات الخارجية (مثل LLMs، قواعد البيانات).
-   **اختبارات الأداء (Performance Tests):** تقييم أداء `BaseAgent` تحت أحمال مختلفة.
-   **اختبارات الأمان (Security Tests):** التحقق من مقاومة `BaseAgent` للهجمات الأمنية.
-   **اختبارات السلوك (Behavioral Tests):** التأكد من أن `BaseAgent` يتصرف كما هو متوقع في سيناريوهات مختلفة، خاصة فيما يتعلق بالتفكير واستدعاء الأدوات.

## 15. استراتيجيات التشغيل والأداء (Operational and Performance Strategies)

### 15.1 قابلية التوسع (Scalability Strategy)

لضمان قدرة المنصة على التعامل مع زيادة الحمل وعدد العملاء الذكيين، سيتم تطبيق استراتيجيات قابلية التوسع التالية:
-   **التوسع الأفقي (Horizontal Scaling):** القدرة على إضافة المزيد من مثيلات `BaseAgent` و `Supervisor Agent` بشكل ديناميكي.
-   **الخدمات المصغرة (Microservices):** تقسيم المنصة إلى خدمات صغيرة مستقلة يمكن توسيعها بشكل فردي.
-   **الحوسبة بدون خادم (Serverless Computing):** استخدام وظائف بدون خادم (مثل AWS Lambda, Azure Functions) للمهام التي تتطلب توسعاً مرناً.
-   **قوائم انتظار الرسائل (Message Queues):** استخدام قوائم انتظار الرسائل لفصل المكونات وتمكين المعالجة غير المتزامنة.

### 15.2 التوافرية العالية (High Availability Strategy)

لضمان استمرارية الخدمة وتقليل وقت التوقف، سيتم تطبيق استراتيجيات التوافرية العالية:
-   **التكرار (Redundancy):** تشغيل مثيلات متعددة من المكونات الحيوية في مناطق توفر مختلفة.
-   **موازنة التحميل (Load Balancing):** توزيع حركة المرور بين المثيلات المتعددة.
-   **الكشف التلقائي عن الفشل والتعافي (Automated Failure Detection and Recovery):** استخدام أدوات الأوركسترا (مثل Kubernetes) للكشف عن المكونات الفاشلة واستبدالها تلقائياً.
-   **النسخ الاحتياطي والاستعادة (Backup and Restore):** سياسات نسخ احتياطي منتظمة للبيانات والتكوينات مع خطط استعادة مجربة.

### 15.3 استراتيجية التعافي من الكوارث (Disaster Recovery Strategy)

لضمان استمرارية العمل في حالة وقوع كارثة كبرى، سيتم وضع خطة للتعافي من الكوارث تتضمن:
-   **النسخ المتماثل عبر المناطق (Cross-Region Replication):** نسخ البيانات والتطبيقات إلى مناطق جغرافية مختلفة.
-   **أهداف وقت الاسترداد (RTO) وأهداف نقطة الاسترداد (RPO):** تحديد الأهداف الزمنية والمقدار المسموح به لفقدان البيانات.
-   **اختبار التعافي من الكوارث (DR Drills):** إجراء اختبارات دورية لخطة التعافي من الكوارث لضمان فعاليتها.

### 15.4 معايير الأداء (Performance Benchmarks)

سيتم تحديد معايير أداء واضحة لكل مكون من مكونات `BaseAgent` والمنصة ككل، وسيتم قياسها بانتظام. تتضمن هذه المعايير:
-   **زمن الاستجابة (Latency):** زمن معالجة الطلب من البداية إلى النهاية.
-   **الإنتاجية (Throughput):** عدد الطلبات التي يمكن معالجتها في وحدة زمنية.
-   **استخدام الموارد (Resource Utilization):** استخدام CPU، الذاكرة، والشبكة.

### 15.5 تخطيط القدرة (Capacity Planning)

سيتم إجراء تخطيط دوري للقدرة لضمان توفر الموارد الكافية لدعم النمو المتوقع للمنصة. يتضمن ذلك:
-   **تحليل الاتجاهات:** تحليل بيانات الاستخدام والأداء التاريخية للتنبؤ بالاحتياجات المستقبلية.
-   **نمذجة الحمل (Load Modeling):** محاكاة أحمال العمل المستقبلية لتقييم متطلبات الموارد.
-   **توفير الموارد (Resource Provisioning):** تخصيص الموارد بشكل استباقي لتلبية الطلبات المتزايدة.

### 15.6 استراتيجية التخزين المؤقت (Caching Strategy)

لتحسين الأداء وتقليل الحمل على قواعد البيانات والخدمات الخارجية، سيتم تطبيق استراتيجيات التخزين المؤقت:
-   **التخزين المؤقت للبيانات (Data Caching):** تخزين البيانات المستخدمة بشكل متكرر في ذاكرة التخزين المؤقت (مثل Redis, Memcached).
-   **التخزين المؤقت للنتائج (Result Caching):** تخزين نتائج العمليات المعقدة أو المكلفة.
-   **إدارة انتهاء صلاحية ذاكرة التخزين المؤقت (Cache Invalidation):** آليات لضمان تحديث البيانات المخزنة مؤقتاً.

### 15.7 معمارية قوائم الانتظار (Queue Architecture)

ستستخدم المنصة قوائم انتظار الرسائل (Message Queues) بشكل مكثف لفصل المكونات، تمكين المعالجة غير المتزامنة، وتحسين قابلية التوسع والموثوقية. تتضمن المعمارية:
-   **قوائم انتظار المهام (Task Queues):** لتوجيه المهام إلى العملاء الذكيين.
-   **قوائم انتظار الأحداث (Event Queues):** لنشر الأحداث بين المكونات.
-   **قوائم انتظار الرسائل الميتة (Dead-Letter Queues - DLQ):** للتعامل مع الرسائل التي فشلت معالجتها.

### 15.8 سياسة إصدار واجهة برمجة التطبيقات (API Versioning Policy)

لإدارة تطور واجهات برمجة التطبيقات (APIs) وضمان التوافق مع الإصدارات السابقة، سيتم تطبيق سياسة إصدار واجهة برمجة التطبيقات:
-   **الإصدار في المسار (Path Versioning):** تضمين رقم الإصدار في مسار URL (مثال: `/api/v1/agent`).
-   **الإصدار في الرأس (Header Versioning):** تضمين رقم الإصدار في رأس HTTP (مثال: `X-API-Version: 1`).
-   **التوثيق الواضح:** توثيق جميع التغييرات في واجهات برمجة التطبيقات في سجل التغييرات (CHANGELOG) الخاص بالمشروع.

## 16. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 17. التطور المستقبلي (Future Evolution)

تم تصميم معمارية `BaseAgent` ومنصة "بصيرة" مع الأخذ في الاعتبار التطور المستقبلي وقابلية التوسع لدعم المتطلبات المتزايدة. فيما يلي بعض جوانب التطور المستقبلي:

### 17.1 التوسع إلى أكثر من 100 وكيل ذكي (Scaling to 100+ AI Agents)
-   **معمارية Hub-and-Spoke:** تسمح بإضافة عدد غير محدود من العملاء الذكيين المتخصصين دون التأثير على العملاء الحاليين.
-   **قوائم انتظار الرسائل:** توفر آلية قوية للتواصل غير المتزامن بين العملاء، مما يمنع الاختناقات.
-   **التوسع الأفقي:** يمكن نشر مثيلات متعددة من `Supervisor Agent` والعملاء الذكيين في مجموعات (Clusters) موزعة.

### 17.2 تشغيل عدة نماذج LLM في نفس الوقت (Running Multiple LLMs Concurrently)
-   **طبقة LLM Abstraction:** تسمح بالتبديل السلس بين نماذج LLM المختلفة من مزودين متعددين.
-   **استراتيجية توجيه النماذج:** تمكن من توجيه المهام إلى النموذج الأنسب بناءً على التكلفة، الأداء، أو نوع المهمة.
-   **الحوسبة الموزعة:** يمكن توزيع استدعاءات LLM عبر موارد حوسبة مختلفة لتحقيق التوازي.

### 17.3 دعم MCP Servers و A2A Protocol (Supporting MCP Servers and A2A Protocol)
-   **واجهات API مرنة:** تصميم واجهات `SupervisorAPI` و `ExternalAPI` لتكون قابلة للتكيف مع بروتوكولات الاتصال المستقبلية مثل MCP (Model Context Protocol) و A2A (Agent-to-Agent Protocol).
-   **طبقة بروتوكول قابلة للتوسعة:** إمكانية إضافة محولات (Adapters) جديدة لدعم بروتوكولات الاتصال المختلفة.

### 17.4 دعم الحوسبة الموزعة والخدمات المصغرة (Distributed Computing and Microservices)
-   **تصميم معياري:** `BaseAgent` مصمم كوحدة مستقلة يمكن نشرها كخدمة مصغرة.
-   **Kubernetes:** استخدام Kubernetes لإدارة ونشر الخدمات المصغرة، مما يوفر قابلية التوسع، التوافرية العالية، وإدارة الموارد.
-   **قوائم انتظار الرسائل:** أساس للتواصل بين الخدمات المصغرة في بيئة موزعة.

### 17.5 دعم العمل السحابي والمحلي Hybrid Deployment (Hybrid Cloud/On-Premise Deployment)
-   **البنية التحتية المحايدة للسحابة (Cloud-Agnostic Infrastructure):** تصميم المنصة لتكون مستقلة عن مزود سحابي معين، مما يسهل النشر في بيئات سحابية مختلفة أو في بيئات محلية.
-   **Docker و Kubernetes:** توفير حاويات (Containers) لـ `BaseAgent` والخدمات الأخرى، مما يضمن قابلية النقل عبر البيئات.

### 17.6 دعم التعلم المستمر للوكلاء (Continuous Learning for Agents)
-   **وكيل التعلم (Learning Agent):** يمكن لوكيل متخصص مراقبة أداء العملاء الآخرين، جمع البيانات، وتدريب نماذج جديدة أو تحسين الـ Prompts بشكل مستمر.
-   **حلقات التغذية الراجعة (Feedback Loops):** دمج آليات لجمع التغذية الراجعة من المستخدمين أو من أداء العملاء الذكيين لتحسين سلوكهم.

### 17.7 دعم إضافة وكلاء جدد دون تعديل BaseAgent (Adding New Agents Without Modifying BaseAgent)
-   **الوراثة من BaseAgent:** العملاء الذكيون الجدد يرثون جميع الوظائف الأساسية من `BaseAgent`.
-   **معمارية الإضافات (Plugin Architecture):** تسمح بتخصيص سلوك العميل الذكي الجديد عن طريق إضافة إضافات (Plugins) بدلاً من تعديل الكود الأساسي لـ `BaseAgent`.
-   **التكوين (Configuration-driven):** يمكن تكوين العملاء الذكيين الجدد بشكل كبير عبر ملفات التكوين بدلاً من الكود.

## 18. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 19. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)


سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 19. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)


**مخطط هيكل BaseAgent الداخلي:**

```d2
direction: right

BaseAgent: {
  shape: class
  label: "BaseAgent (الصنف الأساسي للوكيل)"
  
  Core: {
    shape: rectangle
    label: "Core Logic (المنطق الأساسي)"
    MemoryManager: { shape: cylinder; label: "Memory Manager (إدارة الذاكرة)" }
    ReasoningEngine: { shape: rectangle; label: "Reasoning Engine (محرك الاستدلال)" }
    ToolExecutor: { shape: rectangle; label: "Tool Executor (منفذ الأدوات)" }
    LLMInterface: { shape: rectangle; label: "LLM Interface (واجهة LLM)" }
    ErrorHandler: { shape: rectangle; label: "Error Handler (معالج الأخطاء)" }
    Logger: { shape: rectangle; label: "Logger (المسجل)" }
    SecurityManager: { shape: rectangle; label: "Security Manager (إدارة الأمان)" }
  }
  
  Interfaces: {
    shape: rectangle
    label: "Interfaces (واجهات الاتصال)"
    SupervisorAPI: { shape: rectangle; label: "Supervisor API (واجهة المشرف العام)" }
    ExternalAPI: { shape: rectangle; label: "External APIs (واجهات خارجية)" }
  }
  
  Plugins: {
    shape: rectangle
    label: "Plugins (الإضافات)"
    PluginManager: { shape: rectangle; label: "Plugin Manager (إدارة الإضافات)" }
  }
}

SupervisorAgent: { shape: class; label: "Supervisor Agent (وكيل المشرف العام)" }
ExternalTools: { shape: cloud; label: "External Tools (أدوات خارجية)" }
LLMProviders: { shape: cloud; label: "LLM Providers (مزودو LLM)" }
DataStores: { shape: cylinder; label: "Data Stores (مخازن البيانات)" }

SupervisorAgent -> BaseAgent.Interfaces.SupervisorAPI: "يتصل بـ"
BaseAgent.Core.ToolExecutor -> ExternalTools: "يستدعي"
BaseAgent.Core.LLMInterface -> LLMProviders: "يتصل بـ"
BaseAgent.Core.MemoryManager -> DataStores: "يخزن/يسترجع"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.MemoryManager: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.ToolExecutor: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.LLMInterface: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.ErrorHandler: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.Logger: "يستخدم"
BaseAgent.Core.ReasoningEngine -> BaseAgent.Core.SecurityManager: "يستخدم"
BaseAgent.Plugins.PluginManager -> BaseAgent.Core: "يوسع وظائف"
```

## 4. دورة حياة الوكيل (Agent Lifecycle)

تتبع دورة حياة `BaseAgent` المراحل التالية:

1.  **التهيئة (Initialization):**
    *   يتم إنشاء مثيل (instance) لـ `BaseAgent` أو العميل الذكي المشتق منه.
    *   يتم تحميل التكوينات الخاصة بالعميل (مثل الأدوات المتاحة، إعدادات الذاكرة، إعدادات LLM).
    *   يتم تهيئة وحدات الذاكرة، ومحرك التفكير، ومنفذ الأدوات.
    *   يتم تسجيل العميل الذكي لدى `Supervisor Agent` (إذا لزم الأمر).

2.  **التنفيذ (Execution):**
    *   يستقبل العميل الذكي طلباً أو مهمة من `Supervisor Agent` عبر واجهة `SupervisorAPI`.
    *   يقوم `ReasoningEngine` بتحليل الطلب، واستخدام الذاكرة، واستدعاء الأدوات، والتفاعل مع LLM لتوليد استجابة أو اتخاذ إجراء.
    *   تتكرر هذه العملية حتى تكتمل المهمة أو يتم الوصول إلى حالة نهائية.

3.  **الإنهاء (Termination):**
    *   يتم تحرير الموارد التي يستخدمها العميل الذكي (مثل اتصالات قاعدة البيانات، جلسات LLM).
    *   يتم حفظ أي حالة ضرورية للذاكرة طويلة المدى.
    *   يتم إلغاء تسجيل العميل الذكي من `Supervisor Agent`.

## 5. تدفق البيانات وتنفيذ المهام (Data Flow and Task Execution)

### 5.1 آلية التواصل مع Supervisor Agent (Communication with Supervisor Agent)

يعتمد التواصل بين العملاء الذكيين و`Supervisor Agent` على معمارية Hub-and-Spoke. `BaseAgent` يتصل بـ `Supervisor Agent` عبر واجهة `SupervisorAPI` الموحدة. لا يوجد اتصال مباشر بين العملاء الذكيين المتخصصين.

**تدفق الاتصال:**
1.  **الطلب:** يرسل `Supervisor Agent` طلباً (مهمة) إلى عميل ذكي محدد (أو مجموعة عملاء) عبر واجهة `SupervisorAPI` الخاصة به.
2.  **المعالجة:** يستقبل العميل الذكي الطلب، يقوم بمعالجته باستخدام `ReasoningEngine`، الذاكرة، والأدوات.
3.  **الاستجابة:** يرسل العميل الذكي النتائج أو التقدم المحرز إلى `Supervisor Agent` عبر نفس الواجهة.
4.  **التجميع:** يقوم `Supervisor Agent` بتجميع الاستجابات من العملاء المختلفين وتنسيقها.

### 5.2 دورة تنفيذ المهام (Task Execution Flow)

1.  **استلام المهمة:** `BaseAgent` يستقبل مهمة من `Supervisor Agent`.
2.  **تحليل المهمة:** `ReasoningEngine` يحلل المهمة، ويحدد الأهداف الفرعية والإجراءات المطلوبة.
3.  **استرجاع السياق:** `MemoryManager` يسترجع المعلومات ذات الصلة من الذاكرة قصيرة وطويلة المدى.
4.  **التفكير (Reasoning):** `ReasoningEngine` يستخدم LLM (عبر `LLMInterface`) لتوليد خطة عمل، أو تحديد الأداة المناسبة للاستدعاء، أو صياغة استجابة.
5.  **تنفيذ الأداة (Tool Execution):** إذا تطلب الأمر، يقوم `ToolExecutor` باستدعاء الأداة المحددة، ويتم تمرير المدخلات واستقبال المخرجات.
6.  **تحديث الذاكرة:** يتم تحديث الذاكرة بالنتائج الجديدة أو التغييرات في الحالة.
7.  **تكرار أو إنهاء:** تتكرر الخطوات 2-6 حتى تكتمل المهمة أو يتم الوصول إلى استجابة نهائية.
8.  **إرسال الاستجابة:** يرسل `BaseAgent` الاستجابة النهائية إلى `Supervisor Agent`.

## 6. إدارة الحالة والذاكرة (State and Memory Management)

### 6.1 إدارة الحالة (State Management)
يحتفظ `BaseAgent` بحالة داخلية لكل مهمة قيد التنفيذ. تتضمن هذه الحالة:
-   **معرف المهمة (Task ID):** لتتبع المهام المتعددة.
-   **حالة المهمة (Task Status):** (قيد التنفيذ، مكتملة، فاشلة، معلقة).
-   **الخطوات المنفذة (Executed Steps):** سجل بالخطوات التي تم اتخاذها.
-   **المدخلات والمخرجات الحالية (Current Inputs/Outputs):** البيانات التي يتم معالجتها.
-   **الموارد المستخدمة (Used Resources):** الأدوات أو نماذج LLM المستدعاة.

يتم تحديث الحالة بشكل مستمر بواسطة `ReasoningEngine` ويتم حفظها في الذاكرة قصيرة المدى.

### 6.2 نظام الذاكرة قصيرة المدى (Short-Term Memory)
-   **الغرض:** تخزين السياق الحالي للمهمة، المحادثات الجارية، والنتائج الوسيطة.
-   **الآلية:** يتم استخدام هياكل بيانات داخلية (مثل القواميس أو الكائنات) لتخزين المعلومات في الذاكرة العاملة للعميل الذكي. يمكن أن تكون هذه الذاكرة عابرة (in-memory) أو مخزنة مؤقتاً في قاعدة بيانات سريعة (مثل Redis) للمهام الأطول.
-   **إدارة السياق (Context Management):** يتم تجميع السياق ذي الصلة من الذاكرة قصيرة المدى وتقديمه إلى LLM كجزء من الـ Prompt. يتم تطبيق تقنيات ضغط السياق (Context Compression) عند الضرورة للحفاظ على حجم الـ Prompt ضمن حدود LLM.

### 6.3 نظام الذاكرة طويلة المدى (Long-Term Memory)
-   **الغرض:** تخزين المعرفة الدائمة، الدروس المستفادة، التفضيلات، والبيانات التاريخية التي يحتاجها العميل الذكي عبر جلسات متعددة أو مهام مختلفة.
-   **الآلية:** يتم استخدام قواعد بيانات متخصصة (مثل Vector Databases لتخزين التضمينات الدلالية، أو قواعد بيانات علائقية/NoSQL لتخزين البيانات المنظمة) لتخزين الذاكرة طويلة المدى. يتم استرجاع المعلومات باستخدام تقنيات البحث الدلالي (Semantic Search) أو الاستعلامات التقليدية.

## 7. نظام التفكير والاستدلال (Reasoning Pipeline)

`ReasoningEngine` هو قلب `BaseAgent`، وهو المسؤول عن توجيه سلوك العميل الذكي. يتبع هذا النظام عادةً نمط "التفكير/العمل" (Think/Act) أو "التخطيط/التنفيذ" (Plan/Execute).

### 7.1 مراحل التفكير (Reasoning Stages)
1.  **فهم المهمة (Task Understanding):** تحليل الطلب الوارد وتحديد النية والأهداف الرئيسية.
2.  **توليد الخطة (Plan Generation):** استخدام LLM لتوليد خطة عمل خطوة بخطوة لتحقيق الأهداف، مع الأخذ في الاعتبار السياق والذاكرة والأدوات المتاحة.
3.  **اختيار الأداة (Tool Selection):** تحديد الأداة الأنسب لتنفيذ الخطوة الحالية من الخطة.
4.  **توليد المدخلات للأداة (Tool Input Generation):** صياغة المدخلات اللازمة للأداة المختارة بناءً على السياق.
5.  **تحليل المخرجات (Output Analysis):** تقييم مخرجات الأداة أو استجابة LLM وتحديد الخطوة التالية.
6.  **تحديث الحالة والذاكرة (State & Memory Update):** تسجيل التقدم المحرز وتحديث الذاكرة.

### 7.2 آلية اتخاذ القرار (Decision-Making Mechanism)
تعتمد آلية اتخاذ القرار على مزيج من:
-   **نماذج LLM:** لتوليد الأفكار، الخطط، واختيار الأدوات بناءً على الـ Prompts المصممة بعناية.
-   **المنطق البرمجي (Programmatic Logic):** قواعد محددة مسبقاً للتعامل مع السيناريوهات الشائعة أو الحالات الحرجة.
-   **الذاكرة:** استخدام المعلومات المخزنة لتوجيه القرارات.

## 8. نظام استدعاء الأدوات (Tool Calling Framework)

`ToolExecutor` هو الوحدة المسؤولة عن إدارة واستدعاء الأدوات الخارجية التي يمكن للعميل الذكي استخدامها.

### 8.1 كيفية استخدام الأدوات (How Tools are Used)
1.  **تعريف الأداة:** يتم تعريف الأدوات بوضوح (اسم، وصف، معلمات المدخلات، نوع المخرجات) ليتمكن LLM من فهمها واستدعائها بشكل صحيح.
2.  **اختيار الأداة:** يقوم `ReasoningEngine` (بمساعدة LLM) باختيار الأداة المناسبة بناءً على المهمة الحالية.
3.  **تنفيذ الأداة:** يقوم `ToolExecutor` باستدعاء الأداة الفعلية، مع تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
4.  **معالجة المخرجات:** يتم استقبال مخرجات الأداة وتحليلها بواسطة `ReasoningEngine` لمواصلة دورة التفكير.

### 8.2 إدارة الأدوات (Tool Management)
-   **اكتشاف الأدوات (Tool Discovery):** آلية لتسجيل واكتشاف الأدوات المتاحة للعميل الذكي.
-   **التحقق من صحة الأدوات (Tool Validation):** التأكد من أن الأدوات تعمل بشكل صحيح وأن معلمات المدخلات والمخرجات متوافقة.
-   **عزل الأدوات (Tool Isolation):** تشغيل الأدوات في بيئات معزولة لتقليل المخاطر الأمنية وتأثير الأخطاء.

### 8.3 نظام Plugins والتوسعة المستقبلية (Plugins and Future Extensibility)
يدعم `BaseAgent` نظام إضافات (Plugins) يسمح بتوسيع وظائفه ديناميكياً دون الحاجة لتعديل الكود الأساسي. يمكن للإضافات توفير أدوات جديدة، تعديل سلوك التفكير، أو إضافة قدرات ذاكرة جديدة.

## 9. طبقة الاتصال بنماذج الذكاء الاصطناعي (LLM Abstraction Layer)

### 9.1 الغرض (Purpose)
توفر هذه الطبقة واجهة موحدة للعملاء الذكيين للتفاعل مع نماذج الذكاء الاصطناعي الكبيرة (LLMs) المختلفة، بغض النظر عن المزود (مثل OpenAI, Gemini) أو النموذج المحدد. هذا يضمن المرونة، سهولة التبديل بين النماذج، وعزل منطق العميل الذكي عن تفاصيل API الخاصة بكل LLM.

### 9.2 المكونات (Components)
-   **LLM Provider Interface:** واجهة عامة تحدد طرق الاتصال الأساسية (مثل `generate_response`, `embed_text`).
-   **Concrete LLM Adapters:** تطبيقات محددة لـ `LLM Provider Interface` لكل مزود LLM (مثال: `OpenAIAdapter`, `GeminiAdapter`).
-   **Prompt Manager:** وحدة مسؤولة عن صياغة الـ Prompts، إدارة القوالب، وضغط السياق قبل إرسالها إلى LLM.

## 10. إدارة الأخطاء وإعادة المحاولة (Error Handling and Retry)

### 10.1 آليات اكتشاف الأخطاء (Error Detection Mechanisms)
-   **التحقق من صحة المدخلات (Input Validation):** التحقق من صحة المدخلات قبل معالجتها.
-   **مراقبة استجابات الأدوات و LLM:** تحليل استجابات الأدوات ونماذج LLM لاكتشاف الأخطاء أو الاستجابات غير المتوقعة.
-   **الاستثناءات (Exceptions):** استخدام آليات الاستثناءات القياسية في البرمجة.

### 10.2 استراتيجيات إعادة المحاولة (Retry Strategies)
-   **إعادة المحاولة الأسية (Exponential Backoff):** إعادة محاولة العمليات الفاشلة مع زيادة زمن الانتظار بين المحاولات.
-   **الحد الأقصى للمحاولات (Max Retries):** تحديد عدد أقصى للمحاولات قبل الإبلاغ عن فشل دائم.

### 10.3 التعافي من الأخطاء (Error Recovery)
-   **العودة إلى حالة سابقة (Rollback):** التراجع عن التغييرات التي تمت قبل حدوث الخطأ.
-   **الإبلاغ عن الخطأ (Error Reporting):** إرسال تفاصيل الخطأ إلى `Supervisor Agent` أو نظام المراقبة.
-   **التعامل مع الأخطاء المعروفة (Known Error Handling):** وجود منطق محدد للتعامل مع أنواع معينة من الأخطاء.

## 11. نظام التسجيل والمراقبة (Logging and Monitoring)

### 11.1 التسجيل (Logging)
-   **مستويات التسجيل:** دعم مستويات تسجيل مختلفة (DEBUG, INFO, WARNING, ERROR, CRITICAL).
-   **تنسيق السجلات:** تنسيق موحد للسجلات يسهل التحليل (JSON).
-   **محتوى السجلات:** تسجيل تفاصيل المهمة، خطوات التفكير، استدعاءات الأدوات، استجابات LLM، والأخطاء.
-   **تخزين السجلات:** تخزين السجلات في نظام مركزي (مثل ELK Stack) للتحليل والمراجعة.

### 11.2 المراقبة (Monitoring)
-   **المقاييس (Metrics):** جمع مقاييس الأداء (مثل زمن الاستجابة، معدل النجاح/الفشل، استخدام الموارد).
-   **لوحات المعلومات (Dashboards):** توفير لوحات معلومات لمراقبة صحة وأداء العملاء الذكيين في الوقت الفعلي.
-   **التنبيهات (Alerts):** إعداد تنبيهات عند تجاوز المقاييس لحدود معينة أو عند حدوث أخطاء حرجة.

## 12. نظام الصلاحيات والأمان (Authorization and Security System)

### 12.1 مبادئ الأمان (Security Principles)
-   **الامتياز الأقل (Least Privilege):** يجب أن يمتلك كل عميل ذكي الحد الأدنى من الصلاحيات اللازمة لأداء وظيفته.
-   **عزل الموارد (Resource Isolation):** عزل موارد العملاء الذكيين عن بعضها البعض.
-   **التشفير (Encryption):** تشفير البيانات الحساسة أثناء النقل وفي وضع السكون.
-   **التحقق من صحة المدخلات (Input Validation):** حماية ضد حقن الـ Prompts (Prompt Injection) وغيرها من الهجمات.

### 12.2 آليات الصلاحيات (Authorization Mechanisms)
-   **رموز الوصول (Access Tokens):** استخدام رموز وصول مؤقتة ومحدودة الصلاحية للوصول إلى الأدوات الخارجية أو الخدمات.
-   **التحكم في الوصول المستند إلى الدور (Role-Based Access Control - RBAC):** تحديد الصلاحيات بناءً على دور العميل الذكي.

## 13. معايير كتابة الكود الخاصة بـ BaseAgent (BaseAgent Coding Standards)

بالإضافة إلى معايير كتابة الكود العامة للمشروع، يجب أن يلتزم كود `BaseAgent` بالمبادئ التالية:
-   **قابلية التوسع (Extensibility):** تصميم الوحدات بطريقة تسمح بإضافة وظائف جديدة بسهولة دون تعديل الكود الحالي (مبدأ Open/Closed).
-   **قابلية الاختبار (Testability):** تصميم الوحدات لتكون سهلة الاختبار بشكل منفصل.
-   **النمطية (Modularity):** تقسيم الكود إلى وحدات صغيرة ومستقلة ذات مسؤوليات واضحة.
-   **الوثوقية (Reliability):** التعامل مع الحالات الاستثنائية والأخطاء بشكل رشيد.
-   **الوضوح (Clarity):** كود نظيف، مقروء، وموثق جيداً.

## 14. استراتيجية الاختبارات (Testing Strategy)

تتبع استراتيجية الاختبارات لـ `BaseAgent` نهجاً شاملاً لضمان الجودة والموثوقية:

-   **اختبارات الوحدات (Unit Tests):** اختبار كل وحدة (Module) أو وظيفة بشكل منفصل لضمان عملها الصحيح.
-   **اختبارات التكامل (Integration Tests):** اختبار تفاعل الوحدات المختلفة مع بعضها البعض ومع الخدمات الخارجية (مثل LLMs، قواعد البيانات).
-   **اختبارات الأداء (Performance Tests):** تقييم أداء `BaseAgent` تحت أحمال مختلفة.
-   **اختبارات الأمان (Security Tests):** التحقق من مقاومة `BaseAgent` للهجمات الأمنية.
-   **اختبارات السلوك (Behavioral Tests):** التأكد من أن `BaseAgent` يتصرف كما هو متوقع في سيناريوهات مختلفة، خاصة فيما يتعلق بالتفكير واستدعاء الأدوات.

## 15. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 16. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)


### 3.5 مخطط المكونات (Component Diagram)

```d2
direction: right

BaseAgentComponent: { shape: component; label: "BaseAgent Component" }
MemoryManagerComponent: { shape: component; label: "Memory Manager" }
ReasoningEngineComponent: { shape: component; label: "Reasoning Engine" }
ToolExecutorComponent: { shape: component; label: "Tool Executor" }
LLMInterfaceComponent: { shape: component; label: "LLM Interface" }
ErrorHandlerComponent: { shape: component; label: "Error Handler" }
LoggerComponent: { shape: component; label: "Logger" }
SecurityManagerComponent: { shape: component; label: "Security Manager" }
PluginManagerComponent: { shape: component; label: "Plugin Manager" }

BaseAgentComponent -> MemoryManagerComponent: "يحتوي على"
BaseAgentComponent -> ReasoningEngineComponent: "يحتوي على"
BaseAgentComponent -> ToolExecutorComponent: "يحتوي على"
BaseAgentComponent -> LLMInterfaceComponent: "يحتوي على"
BaseAgentComponent -> ErrorHandlerComponent: "يحتوي على"
BaseAgentComponent -> LoggerComponent: "يحتوي على"
BaseAgentComponent -> SecurityManagerComponent: "يحتوي على"
BaseAgentComponent -> PluginManagerComponent: "يحتوي على"

ReasoningEngineComponent -> MemoryManagerComponent: "يستخدم"
ReasoningEngineComponent -> ToolExecutorComponent: "يستخدم"
ReasoningEngineComponent -> LLMInterfaceComponent: "يستخدم"
ReasoningEngineComponent -> ErrorHandlerComponent: "يستخدم"
ReasoningEngineComponent -> LoggerComponent: "يستخدم"
ReasoningEngineComponent -> SecurityManagerComponent: "يستخدم"
PluginManagerComponent -> BaseAgentComponent: "يوسع"
```

### 3.6 مخطط الفئات (Class Diagram)

```d2
direction: right

class BaseAgent {
  + id: str
  + name: str
  + memory_manager: MemoryManager
  + reasoning_engine: ReasoningEngine
  + tool_executor: ToolExecutor
  + llm_interface: LLMInterface
  + error_handler: ErrorHandler
  + logger: Logger
  + security_manager: SecurityManager
  + plugin_manager: PluginManager
  + __init__(...)
  + handle_request(request: AgentRequest) -> AgentResponse
  + _initialize_agent()
  + _terminate_agent()
}

class MemoryManager {
  + short_term_memory: ShortTermMemory
  + long_term_memory: LongTermMemory
  + retrieve_context(task_id: str) -> Context
  + update_memory(task_id: str, data: Any)
}

class ReasoningEngine {
  + reason(task: Task, context: Context, tools: List[Tool]) -> Action
  + _plan_task(task: Task, context: Context) -> Plan
  + _select_tool(plan: Plan, available_tools: List[Tool]) -> Tool
  + _generate_tool_input(tool: Tool, context: Context) -> Dict
}

class ToolExecutor {
  + execute_tool(tool: Tool, input: Dict) -> ToolOutput
}

class LLMInterface {
  + generate_response(prompt: Prompt, model_config: Dict) -> LLMResponse
  + embed_text(text: str) -> Embedding
}

class ErrorHandler {
  + handle_error(error: Exception, context: Dict) -> ErrorRecoveryStrategy
  + _retry_operation(operation: Callable, retries: int) -> Any
}

class Logger {
  + log(level: LogLevel, message: str, context: Dict)
}

class SecurityManager {
  + authorize_tool_access(agent_id: str, tool_name: str) -> bool
  + encrypt_data(data: str) -> str
}

class PluginManager {
  + load_plugin(plugin_name: str)
  + unload_plugin(plugin_name: str)
  + get_available_plugins() -> List[Plugin]
}

BaseAgent *-- MemoryManager
BaseAgent *-- ReasoningEngine
BaseAgent *-- ToolExecutor
BaseAgent *-- LLMInterface
BaseAgent *-- ErrorHandler
BaseAgent *-- Logger
BaseAgent *-- SecurityManager
BaseAgent *-- PluginManager

ReasoningEngine --> MemoryManager: "يستخدم"
ReasoningEngine --> ToolExecutor: "يستخدم"
ReasoningEngine --> LLMInterface: "يستخدم"
ReasoningEngine --> ErrorHandler: "يستخدم"
ReasoningEngine --> Logger: "يستخدم"
ReasoningEngine --> SecurityManager: "يستخدم"

MemoryManager --> ShortTermMemory
MemoryManager --> LongTermMemory

LLMInterface --> PromptManager
```

### 3.7 مخطط التسلسل (Sequence Diagram) - مثال: معالجة طلب بسيط

```d2
direction: right

SupervisorAgent -> BaseAgent: request(task_id, query)
BaseAgent -> ReasoningEngine: analyze_request(query)
ReasoningEngine -> MemoryManager: retrieve_context(task_id)
MemoryManager --> ReasoningEngine: context
ReasoningEngine -> LLMInterface: generate_plan(query, context)
LLMInterface --> ReasoningEngine: plan
ReasoningEngine -> ToolExecutor: select_tool(plan)
ToolExecutor --> ReasoningEngine: tool_info
ReasoningEngine -> ToolExecutor: execute_tool(tool_info, input)
ToolExecutor --> ReasoningEngine: tool_output
ReasoningEngine -> MemoryManager: update_memory(task_id, tool_output)
MemoryManager --> ReasoningEngine: memory_updated
ReasoningEngine -> LLMInterface: generate_response(plan, tool_output, context)
LLMInterface --> ReasoningEngine: final_response
ReasoningEngine --> BaseAgent: agent_response
BaseAgent --> SupervisorAgent: response(task_id, agent_response)
```

### 3.8 مخطط النشر (Deployment Diagram)

```d2
direction: right

cloud "منصة بصيرة السحابية" {
  cluster "Kubernetes Cluster" {
    node "Worker Node 1" {
      container "Supervisor Agent Pod" {
        process "Supervisor Agent"
      }
      container "BaseAgent Instance 1 (وكيل التحليل الفني)" {
        process "BaseAgent"
      }
      container "BaseAgent Instance 2 (وكيل أخبار السوق)" {
        process "BaseAgent"
      }
    }
    node "Worker Node N" {
      container "BaseAgent Instance N" {
        process "BaseAgent"
      }
    }
  }
  database "Vector DB (ذاكرة طويلة المدى)"
  database "Relational DB (حالة، تكوينات)"
  queue "Message Queue (Kafka/RabbitMQ)"
  storage "Object Storage (S3)"
}

external_system "مزودو LLM (OpenAI, Gemini)"
external_system "مزودو بيانات السوق (Tadawul API)"

"Supervisor Agent" <-> "BaseAgent Instance 1 (وكيل التحليل الفني)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance 2 (وكيل أخبار السوق)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance N": "يتواصل عبر"

"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو LLM (OpenAI, Gemini)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو بيانات السوق (Tadawul API)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Vector DB (ذاكرة طويلة المدى)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Relational DB (حالة، تكوينات)": "يستخدم"

"Message Queue (Kafka/RabbitMQ)" <-> "Supervisor Agent": "للتواصل غير المتزامن"
"Object Storage (S3)" <-> "BaseAgent Instance N": "لتخزين البيانات الكبيرة"
```

### 3.9 مخطط تدفق البيانات (Data Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
LLMProviders: { shape: cloud; label: "مزودو LLM" }
ExternalTools: { shape: cloud; label: "أدوات خارجية" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى" }

User -> SupervisorAgent: "طلب تحليلي"
SupervisorAgent -> BaseAgent: "توجيه المهمة"

BaseAgent -> ShortTermMemory: "قراءة/كتابة السياق"
BaseAgent -> LongTermMemory: "قراءة/كتابة المعرفة"
BaseAgent -> LLMProviders: "استدعاء LLM (Prompt)"
LLMProviders -> BaseAgent: "استجابة LLM"
BaseAgent -> ExternalTools: "استدعاء أداة"
ExternalTools -> BaseAgent: "مخرجات الأداة"

BaseAgent -> SupervisorAgent: "نتائج المهمة"
SupervisorAgent -> User: "التحليل النهائي"
```

### 3.10 مخطط تدفق الأحداث (Event Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
MessageQueue: { shape: queue; label: "Message Queue" }

User -> SupervisorAgent: "يرسل طلب"
SupervisorAgent -> MessageQueue: "ينشر حدث: TaskAssigned"
MessageQueue -> BaseAgent: "يستقبل حدث: TaskAssigned"
BaseAgent -> BaseAgent: "يعالج المهمة"
BaseAgent -> MessageQueue: "ينشر حدث: TaskCompleted/TaskFailed"
MessageQueue -> SupervisorAgent: "يستقبل حدث: TaskCompleted/TaskFailed"
SupervisorAgent -> User: "يرسل إشعار/نتيجة"
```

### 3.11 مخطط تدفق الذاكرة (Memory Flow Diagram)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى (Redis/In-memory)" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى (Vector DB/Relational DB)" }

BaseAgent -> ShortTermMemory: "يخزن/يسترجع سياق الجلسة"
BaseAgent -> LongTermMemory: "يخزن/يسترجع المعرفة الدائمة"

ShortTermMemory -> LongTermMemory: "ترحيل السياق الهام (عند الحاجة)"
LongTermMemory -> ShortTermMemory: "استرجاع المعرفة ذات الصلة"
```

### 3.12 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 3.13 تدفق معالجة الـ Prompt (Prompt Processing Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
PromptManager: { shape: rectangle; label: "Prompt Manager" }
MemoryManager: { shape: rectangle; label: "Memory Manager" }
LLMInterface: { shape: rectangle; label: "LLM Interface" }
LLMProvider: { shape: cloud; label: "مزود LLM" }

BaseAgent -> PromptManager: "طلب توليد Prompt"
PromptManager -> MemoryManager: "يسترجع السياق ذي الصلة"
MemoryManager --> PromptManager: "السياق والذاكرة"
PromptManager -> PromptManager: "يطبق القوالب ويضغط السياق"
PromptManager --> BaseAgent: "Prompt النهائي"
BaseAgent -> LLMInterface: "يرسل Prompt لـ LLM"
LLMInterface -> LLMProvider: "يرسل Prompt"
LLMProvider --> LLMInterface: "استجابة LLM"
LLMInterface --> BaseAgent: "استجابة LLM"
```

### 3.14 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine -> BaseAgent: "يستأنف/يفشل المهمة"
```

### 3.15 مخطط انتقال الحالة (State Transition Diagram)

```d2
direction: right

stateDiagram-v2
    [*] --> Idle
    Idle --> Initializing: "استلام طلب"
    Initializing --> Ready: "تم التهيئة بنجاح"
    Ready --> Processing: "بدء معالجة المهمة"
    Processing --> Processing: "خطوة مهمة (تفكير/أداة)"
    Processing --> Ready: "المهمة مكتملة"
    Processing --> Failed: "فشل المهمة"
    Failed --> Ready: "إعادة تعيين/محاولة جديدة"
    Ready --> Terminating: "طلب إنهاء"
    Initializing --> Failed: "فشل التهيئة"
    Terminating --> [*]: "تم الإنهاء"
```

## 4. دورة حياة الوكيل (Agent Lifecycle)

تتبع دورة حياة `BaseAgent` المراحل التالية:

1.  **التهيئة (Initialization):**
    *   يتم إنشاء مثيل (instance) لـ `BaseAgent` أو العميل الذكي المشتق منه.
    *   يتم تحميل التكوينات الخاصة بالعميل (مثل الأدوات المتاحة، إعدادات الذاكرة، إعدادات LLM).
    *   يتم تهيئة وحدات الذاكرة، ومحرك التفكير، ومنفذ الأدوات.
    *   يتم تسجيل العميل الذكي لدى `Supervisor Agent` (إذا لزم الأمر).

2.  **التنفيذ (Execution):**
    *   يستقبل العميل الذكي طلباً أو مهمة من `Supervisor Agent` عبر واجهة `SupervisorAPI`.
    *   يقوم `ReasoningEngine` بتحليل الطلب، واستخدام الذاكرة، واستدعاء الأدوات، والتفاعل مع LLM لتوليد استجابة أو اتخاذ إجراء.
    *   تتكرر هذه العملية حتى تكتمل المهمة أو يتم الوصول إلى حالة نهائية.

3.  **الإنهاء (Termination):**
    *   يتم تحرير الموارد التي يستخدمها العميل الذكي (مثل اتصالات قاعدة البيانات، جلسات LLM).
    *   يتم حفظ أي حالة ضرورية للذاكرة طويلة المدى.
    *   يتم إلغاء تسجيل العميل الذكي من `Supervisor Agent`.

## 5. تدفق البيانات وتنفيذ المهام (Data Flow and Task Execution)

### 5.1 آلية التواصل مع Supervisor Agent (Communication with Supervisor Agent)

يعتمد التواصل بين العملاء الذكيين و`Supervisor Agent` على معمارية Hub-and-Spoke. `BaseAgent` يتصل بـ `Supervisor Agent` عبر واجهة `SupervisorAPI` الموحدة. لا يوجد اتصال مباشر بين العملاء الذكيين المتخصصين.

**تدفق الاتصال:**
1.  **الطلب:** يرسل `Supervisor Agent` طلباً (مهمة) إلى عميل ذكي محدد (أو مجموعة عملاء) عبر واجهة `SupervisorAPI` الخاصة به.
2.  **المعالجة:** يستقبل العميل الذكي الطلب، يقوم بمعالجته باستخدام `ReasoningEngine`، الذاكرة، والأدوات.
3.  **الاستجابة:** يرسل العميل الذكي النتائج أو التقدم المحرز إلى `Supervisor Agent` عبر نفس الواجهة.
4.  **التجميع:** يقوم `Supervisor Agent` بتجميع الاستجابات من العملاء المختلفين وتنسيقها.

### 5.2 بروتوكول الاتصال متعدد العملاء (Multi-Agent Communication Protocol)

لضمان التواصل الفعال والآمن بين `Supervisor Agent` والعملاء الذكيين، سيتم استخدام بروتوكول اتصال موحد يعتمد على الرسائل غير المتزامنة (Asynchronous Messaging) عبر قائمة انتظار رسائل (Message Queue) مثل Kafka أو RabbitMQ. هذا يضمن:
-   **المرونة:** فصل المرسل عن المستقبل.
-   **قابلية التوسع:** سهولة إضافة المزيد من العملاء أو `Supervisor Agents`.
-   **الموثوقية:** ضمان تسليم الرسائل حتى في حالة تعطل أحد المكونات.

**هيكل الرسالة (Message Structure):**
ستتبع الرسائل تنسيق JSON موحد يتضمن:
-   `message_id`: معرف فريد للرسالة.
-   `sender_id`: معرف العميل المرسل.
-   `receiver_id`: معرف العميل المستهدف (أو `broadcast`).
-   `message_type`: نوع الرسالة (مثال: `TaskRequest`, `TaskResponse`, `StatusUpdate`).
-   `payload`: الحمولة الفعلية للرسالة (بيانات المهمة، النتائج، الأخطاء).
-   `timestamp`: وقت إرسال الرسالة.
-   `signature`: توقيع رقمي لضمان سلامة الرسالة ومصدرها.

### 5.3 دورة تنفيذ المهام (Task Execution Flow)

1.  **استلام المهمة:** `BaseAgent` يستقبل مهمة من `Supervisor Agent`.
2.  **تحليل المهمة:** `ReasoningEngine` يحلل المهمة، ويحدد الأهداف الفرعية والإجراءات المطلوبة.
3.  **استرجاع السياق:** `MemoryManager` يسترجع المعلومات ذات الصلة من الذاكرة قصيرة وطويلة المدى.
4.  **التفكير (Reasoning):** `ReasoningEngine` يستخدم LLM (عبر `LLMInterface`) لتوليد خطة عمل، أو تحديد الأداة المناسبة للاستدعاء، أو صياغة استجابة.
5.  **تنفيذ الأداة (Tool Execution):** إذا تطلب الأمر، يقوم `ToolExecutor` باستدعاء الأداة المحددة، ويتم تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
6.  **تحديث الذاكرة:** يتم تحديث الذاكرة بالنتائج الجديدة أو التغييرات في الحالة.
7.  **تكرار أو إنهاء:** تتكرر الخطوات 2-6 حتى تكتمل المهمة أو يتم الوصول إلى استجابة نهائية.
8.  **إرسال الاستجابة:** يرسل `BaseAgent` الاستجابة النهائية إلى `Supervisor Agent`.

## 6. إدارة الحالة والذاكرة (State and Memory Management)

### 6.1 إدارة الحالة (State Management)
يحتفظ `BaseAgent` بحالة داخلية لكل مهمة قيد التنفيذ. تتضمن هذه الحالة:
-   **معرف المهمة (Task ID):** لتتبع المهام المتعددة.
-   **حالة المهمة (Task Status):** (قيد التنفيذ، مكتملة، فاشلة، معلقة).
-   **الخطوات المنفذة (Executed Steps):** سجل بالخطوات التي تم اتخاذها.
-   **المدخلات والمخرجات الحالية (Current Inputs/Outputs):** البيانات التي يتم معالجتها.
-   **الموارد المستخدمة (Used Resources):** الأدوات أو نماذج LLM المستدعاة.

يتم تحديث الحالة بشكل مستمر بواسطة `ReasoningEngine` ويتم حفظها في الذاكرة قصيرة المدى.

### 6.2 نظام الذاكرة قصيرة المدى (Short-Term Memory)
-   **الغرض:** تخزين السياق الحالي للمهمة، المحادثات الجارية، والنتائج الوسيطة.
-   **الآلية:** يتم استخدام هياكل بيانات داخلية (مثل القواميس أو الكائنات) لتخزين المعلومات في الذاكرة العاملة للعميل الذكي. يمكن أن تكون هذه الذاكرة عابرة (in-memory) أو مخزنة مؤقتاً في قاعدة بيانات سريعة (مثل Redis) للمهام الأطول.
-   **إدارة السياق (Context Management):** يتم تجميع السياق ذي الصلة من الذاكرة قصيرة المدى وتقديمه إلى LLM كجزء من الـ Prompt. يتم تطبيق تقنيات ضغط السياق (Context Compression) عند الضرورة للحفاظ على حجم الـ Prompt ضمن حدود LLM.

### 6.3 نظام الذاكرة طويلة المدى (Long-Term Memory)
-   **الغرض:** تخزين المعرفة الدائمة، الدروس المستفادة، التفضيلات، والبيانات التاريخية التي يحتاجها العميل الذكي عبر جلسات متعددة أو مهام مختلفة.
-   **الآلية:** يتم استخدام قواعد بيانات متخصصة (مثل Vector Databases لتخزين التضمينات الدلالية، أو قواعد بيانات علائقية/NoSQL لتخزين البيانات المنظمة) لتخزين الذاكرة طويلة المدى. يتم استرجاع المعلومات باستخدام تقنيات البحث الدلالي (Semantic Search) أو الاستعلامات التقليدية.

### 6.4 إدارة نافذة السياق (Context Window Management)

لتحسين كفاءة استخدام نماذج LLM والتحكم في التكلفة، سيتم تطبيق استراتيجيات لإدارة نافذة السياق:
-   **التقطيع (Chunking):** تقسيم النصوص الطويلة إلى أجزاء أصغر.
-   **التلخيص (Summarization):** تلخيص الأجزاء الأقل أهمية من السياق.
-   **الاسترجاع الانتقائي (Selective Retrieval):** استرجاع الأجزاء الأكثر صلة فقط من الذاكرة طويلة المدى.
-   **الضغط (Compression):** استخدام تقنيات ضغط السياق لتقليل عدد الرموز (tokens) المرسلة إلى LLM.

### 6.5 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 6.6 استراتيجية ضغط الذاكرة (Memory Compression Strategy)

لتحسين كفاءة الذاكرة طويلة المدى وتقليل تكاليف التخزين والاسترجاع، سيتم تطبيق استراتيجيات ضغط الذاكرة:
-   **التضمين الدلالي (Semantic Embedding):** تحويل النصوص إلى متجهات (vectors) لتقليل حجم التخزين وتمكين البحث الدلالي.
-   **التلخيص الدوري (Periodic Summarization):** تلخيص المحادثات أو الأحداث التاريخية بشكل دوري وتخزين الملخصات بدلاً من النصوص الكاملة.
-   **إزالة البيانات القديمة/غير ذات الصلة (Pruning):** حذف البيانات التي تجاوزت فترة صلاحيتها أو التي لم تعد ذات صلة.

## 7. نظام التفكير والاستدلال (Reasoning Pipeline)

`ReasoningEngine` هو قلب `BaseAgent`، وهو المسؤول عن توجيه سلوك العميل الذكي. يتبع هذا النظام عادةً نمط "التفكير/العمل" (Think/Act) أو "التخطيط/التنفيذ" (Plan/Execute).

### 7.1 مراحل التفكير (Reasoning Stages)
1.  **فهم المهمة (Task Understanding):** تحليل الطلب الوارد وتحديد النية والأهداف الرئيسية.
2.  **توليد الخطة (Plan Generation):** استخدام LLM لتوليد خطة عمل خطوة بخطوة لتحقيق الأهداف، مع الأخذ في الاعتبار السياق والذاكرة والأدوات المتاحة.
3.  **اختيار الأداة (Tool Selection): و**تحديد الأداة الأنسب لتنفيذ الخطوة الحالية من الخطة.
4.  **توليد المدخلات للأداة (Tool Input Generation):** صياغة المدخلات اللازمة للأداة المختارة بناءً على السياق.
5.  **تحليل المخرجات (Output Analysis):** تقييم مخرجات الأداة أو استجابة LLM وتحديد الخطوة التالية.
6.  **تحديث الحالة والذاكرة (State & Memory Update):** تسجيل التقدم المحرز وتحديث الذاكرة.

### 7.2 آلية اتخاذ القرار (Decision-Making Mechanism)
تعتمد آلية اتخاذ القرار على مزيج من:
-   **نماذج LLM:** لتوليد الأفكار، الخطط، واختيار الأدوات بناءً على الـ Prompts المصممة بعناية.
-   **المنطق البرمجي (Programmatic Logic):** قواعد محددة مسبقاً للتعامل مع السيناريوهات الشائعة أو الحالات الحرجة.
-   **الذاكرة:** استخدام المعلومات المخزنة لتوجيه القرارات.

## 8. نظام استدعاء الأدوات (Tool Calling Framework)

`ToolExecutor` هو الوحدة المسؤولة عن إدارة واستدعاء الأدوات الخارجية التي يمكن للعميل الذكي استخدامها.

### 8.1 كيفية استخدام الأدوات (How Tools are Used)
1.  **تعريف الأداة:** يتم تعريف الأدوات بوضوح (اسم، وصف، معلمات المدخلات، نوع المخرجات) ليتمكن LLM من فهمها واستدعائها بشكل صحيح.
2.  **اختيار الأداة:** يقوم `ReasoningEngine` (بمساعدة LLM) باختيار الأداة المناسبة بناءً على المهمة الحالية.
3.  **تنفيذ الأداة:** يقوم `ToolExecutor` باستدعاء الأداة الفعلية، مع تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
4.  **معالجة المخرجات:** يتم استقبال مخرجات الأداة وتحليلها بواسطة `ReasoningEngine` لمواصلة دورة التفكير.

### 8.2 إدارة الأدوات (Tool Management)
-   **اكتشاف الأدوات (Tool Discovery):** آلية لتسجيل واكتشاف الأدوات المتاحة للعميل الذكي.
-   **التحقق من صحة الأدوات (Tool Validation):** التأكد من أن الأدوات تعمل بشكل صحيح وأن معلمات المدخلات والمخرجات متوافقة.
-   **عزل الأدوات (Tool Isolation):** تشغيل الأدوات في بيئات معزولة لتقليل المخاطر الأمنية وتأثير الأخطاء.

### 8.3 نظام Plugins والتوسعة المستقبلية (Plugins and Future Extensibility)
يدعم `BaseAgent` نظام إضافات (Plugins) يسمح بتوسيع وظائفه ديناميكياً دون الحاجة لتعديل الكود الأساسي. يمكن للإضافات توفير أدوات جديدة، تعديل سلوك التفكير، أو إضافة قدرات ذاكرة جديدة.

### 8.4 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 8.5 معمارية الإضافات (Plugin Architecture)

تعتمد معمارية الإضافات على مبدأ التحميل الديناميكي (Dynamic Loading) والفصل بين الإضافات والمنطق الأساسي. كل إضافة ستكون عبارة عن وحدة برمجية مستقلة (مثل حزمة Python) تلتزم بواجهة محددة (Plugin Interface). هذا يسمح بـ:
-   **التوسعة السهلة:** إضافة وظائف جديدة دون تعديل `BaseAgent`.
-   **العزل:** فشل إضافة لا يؤثر على عمل `BaseAgent` الأساسي.
-   **إدارة الإصدارات:** يمكن تحديث الإضافات بشكل مستقل.

## 9. طبقة الاتصال بنماذج الذكاء الاصطناعي (LLM Abstraction Layer)

### 9.1 الغرض (Purpose)
توفر هذه الطبقة واجهة موحدة للعملاء الذكيين للتفاعل مع نماذج الذكاء الاصطناعي الكبيرة (LLMs) المختلفة، بغض النظر عن المزود (مثل OpenAI, Gemini) أو النموذج المحدد. هذا يضمن المرونة، سهولة التبديل بين النماذج، وعزل منطق العميل الذكي عن تفاصيل API الخاصة بكل LLM.

### 9.2 المكونات (Components)
-   **LLM Provider Interface:** واجهة عامة تحدد طرق الاتصال الأساسية (مثل `generate_response`, `embed_text`).
-   **Concrete LLM Adapters:** تطبيقات محددة لـ `LLM Provider Interface` لكل مزود LLM (مثال: `OpenAIAdapter`, `GeminiAdapter`).
-   **Prompt Manager:** وحدة مسؤولة عن صياغة الـ Prompts، إدارة القوالب، وضغط السياق قبل إرسالها إلى LLM.

### 9.3 استراتيجية توجيه النماذج (Model Routing Strategy)

لتحسين الأداء والتكلفة، سيتم تطبيق استراتيجية توجيه ذكية للنماذج:
-   **التوجيه بناءً على المهمة:** توجيه المهام المختلفة إلى نماذج LLM الأنسب (مثال: نموذج سريع ورخيص للمهام البسيطة، نموذج قوي ومكلف للمهام المعقدة).
-   **التوجيه بناءً على التكلفة/الأداء:** اختيار النموذج بناءً على التوازن بين التكلفة والأداء المطلوب.
-   **التوجيه بناءً على التوفر:** التبديل التلقائي بين المزودين في حالة عدم توفر نموذج معين.

### 9.4 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 9.5 استراتيجية إصدار الـ Prompt (Prompt Versioning Strategy)

لإدارة تطور الـ Prompts وضمان إمكانية التتبع والتحكم، سيتم تطبيق استراتيجية لإصدار الـ Prompts:
-   **التخزين المركزي:** تخزين جميع الـ Prompts في مستودع مركزي (مثل نظام التحكم في الإصدارات Git أو قاعدة بيانات).
-   **الإصدارات (Versioning):** تعيين رقم إصدار لكل Prompt، مما يسمح بالعودة إلى إصدارات سابقة وتتبع التغييرات.
-   **الاختبار A/B:** إمكانية اختبار إصدارات مختلفة من الـ Prompts لتقييم فعاليتها.

## 10. إدارة الأخطاء وإعادة المحاولة (Error Handling and Retry)

### 10.1 آليات اكتشاف الأخطاء (Error Detection Mechanisms)
-   **التحقق من صحة المدخلات (Input Validation):** التحقق من صحة المدخلات قبل معالجتها.
-   **مراقبة استجابات الأدوات و LLM:** تحليل استجابات الأدوات ونماذج LLM لاكتشاف الأخطاء أو الاستجابات غير المتوقعة.
-   **الاستثناءات (Exceptions):** استخدام آليات الاستثناءات القياسية في البرمجة.

### 10.2 استراتيجيات إعادة المحاولة (Retry Strategies)
-   **إعادة المحاولة الأسية (Exponential Backoff):** إعادة محاولة العمليات الفاشلة مع زيادة زمن الانتظار بين المحاولات.
-   **الحد الأقصى للمحاولات (Max Retries):** تحديد عدد أقصى للمحاولات قبل الإبلاغ عن فشل دائم.

### 10.3 التعافي من الأخطاء (Error Recovery)
-   **العودة إلى حالة سابقة (Rollback):** التراجع عن التغييرات التي تمت قبل حدوث الخطأ.
-   **الإبلاغ عن الخطأ (Error Reporting):** إرسال تفاصيل الخطأ إلى `Supervisor Agent` أو نظام المراقبة.
-   **التعامل مع الأخطاء المعروفة (Known Error Handling):** وجود منطق محدد للتعامل مع أنواع معينة من الأخطاء.

### 10.4 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine -> BaseAgent: "يستأنف/يفشل المهمة"
```

## 11. نظام التسجيل والمراقبة (Logging and Monitoring)

### 11.1 التسجيل (Logging)
-   **مستويات التسجيل:** دعم مستويات تسجيل مختلفة (DEBUG, INFO, WARNING, ERROR, CRITICAL).
-   **تنسيق السجلات:** تنسيق موحد للسجلات يسهل التحليل (JSON).
-   **محتوى السجلات:** تسجيل تفاصيل المهمة، خطوات التفكير، استدعاءات الأدوات، استجابات LLM، والأخطاء.
-   **تخزين السجلات:** تخزين السجلات في نظام مركزي (مثل ELK Stack) للتحليل والمراجعة.

### 11.2 المراقبة (Monitoring)
-   **المقاييس (Metrics):** جمع مقاييس الأداء (مثل زمن الاستجابة، معدل النجاح/الفشل، استخدام الموارد).
-   **لوحات المعلومات (Dashboards):** توفير لوحات معلومات لمراقبة صحة وأداء العملاء الذكيين في الوقت الفعلي.
-   **التنبيهات (Alerts):** إعداد تنبيهات عند تجاوز المقاييس لحدود معينة أو عند حدوث أخطاء حرجة.

### 11.3 معمارية الملاحظة (Observability Architecture)

لضمان رؤية عميقة لأداء وسلوك العملاء الذكيين، سيتم تطبيق معمارية ملاحظة شاملة تتضمن:
-   **التسجيل المنظم (Structured Logging):** استخدام تنسيق JSON للسجلات لسهولة التحليل الآلي.
-   **المقاييس (Metrics):** جمع مقاييس الأداء والتشغيل (CPU, Memory, Latency, Error Rates) باستخدام أدوات مثل Prometheus.
-   **التتبع الموزع (Distributed Tracing):** تتبع مسار الطلب عبر العملاء الذكيين والخدمات المختلفة باستخدام أدوات مثل Jaeger أو OpenTelemetry.

### 11.4 تصميم القياس عن بعد (Telemetry Design)

سيتم تصميم نظام القياس عن بعد لجمع البيانات التشغيلية الهامة من `BaseAgent` والعملاء الذكيين المشتقين منه. يتضمن ذلك:
-   **بيانات الأداء:** زمن تنفيذ المهام، زمن استجابة LLM، زمن استدعاء الأدوات.
-   **بيانات الاستخدام:** عدد استدعاءات LLM، عدد استدعاءات الأدوات، عدد الرموز المستخدمة.
-   **بيانات الأخطاء:** أنواع الأخطاء، تكرارها، وسياق حدوثها.
-   **بيانات الموارد:** استخدام CPU، الذاكرة، والشبكة.

## 12. نظام الصلاحيات والأمان (Authorization and Security System)

### 12.1 مبادئ الأمان (Security Principles)
-   **الامتياز الأقل (Least Privilege):** يجب أن يمتلك كل عميل ذكي الحد الأدنى من الصلاحيات اللازمة لأداء وظيفته.
-   **عزل الموارد (Resource Isolation):** عزل موارد العملاء الذكيين عن بعضها البعض.
-   **التشفير (Encryption):** تشفير البيانات الحساسة أثناء النقل وفي وضع السكون.
-   **التحقق من صحة المدخلات (Input Validation):** حماية ضد حقن الـ Prompts (Prompt Injection) وغيرها من الهجمات.

### 12.2 آليات الصلاحيات (Authorization Mechanisms)
-   **رموز الوصول (Access Tokens):** استخدام رموز وصول مؤقتة ومحدودة الصلاحية للوصول إلى الأدوات الخارجية أو الخدمات.
-   **التحكم في الوصول المستند إلى الدور (Role-Based Access Control - RBAC):** تحديد الصلاحيات بناءً على دور العميل الذكي.

### 12.3 نموذج التهديد الأمني (Security Threat Model)

سيتم تطوير نموذج تهديد أمني شامل لتحديد وتحليل وتخفيف المخاطر الأمنية المحتملة لـ `BaseAgent` والمنصة ككل. سيتضمن ذلك:
-   **تحديد الأصول:** البيانات الحساسة، الوظائف الحيوية، واجهات برمجة التطبيقات.
-   **تحديد التهديدات:** هجمات حقن الـ Prompt، الوصول غير المصرح به، تسرب البيانات، هجمات حجب الخدمة (DoS).
-   **تحديد نقاط الضعف:** أخطاء في الكود، تكوينات خاطئة، نقاط ضعف في المكتبات الخارجية.
-   **تحديد الضوابط:** آليات المصادقة، التشفير، التحقق من صحة المدخلات، المراقبة الأمنية.

## 13. معايير كتابة الكود الخاصة بـ BaseAgent (BaseAgent Coding Standards)

بالإضافة إلى معايير كتابة الكود العامة للمشروع، يجب أن يلتزم كود `BaseAgent` بالمبادئ التالية:
-   **قابلية التوسع (Extensibility):** تصميم الوحدات بطريقة تسمح بإضافة وظائف جديدة بسهولة دون تعديل الكود الحالي (مبدأ Open/Closed).
-   **قابلية الاختبار (Testability):** تصميم الوحدات لتكون سهلة الاختبار بشكل منفصل.
-   **النمطية (Modularity):** تقسيم الكود إلى وحدات صغيرة ومستقلة ذات مسؤوليات واضحة.
-   **الوثوقية (Reliability):** التعامل مع الحالات الاستثنائية والأخطاء بشكل رشيد.
-   **الوضوح (Clarity):** كود نظيف، مقروء، وموثق جيداً.

## 14. استراتيجية الاختبارات (Testing Strategy)

تتبع استراتيجية الاختبارات لـ `BaseAgent` نهجاً شاملاً لضمان الجودة والموثوقية:

-   **اختبارات الوحدات (Unit Tests):** اختبار كل وحدة (Module) أو وظيفة بشكل منفصل لضمان عملها الصحيح.
-   **اختبارات التكامل (Integration Tests):** اختبار تفاعل الوحدات المختلفة مع بعضها البعض ومع الخدمات الخارجية (مثل LLMs، قواعد البيانات).
-   **اختبارات الأداء (Performance Tests):** تقييم أداء `BaseAgent` تحت أحمال مختلفة.
-   **اختبارات الأمان (Security Tests):** التحقق من مقاومة `BaseAgent` للهجمات الأمنية.
-   **اختبارات السلوك (Behavioral Tests):** التأكد من أن `BaseAgent` يتصرف كما هو متوقع في سيناريوهات مختلفة، خاصة فيما يتعلق بالتفكير واستدعاء الأدوات.

## 15. استراتيجيات التشغيل والأداء (Operational and Performance Strategies)

### 15.1 قابلية التوسع (Scalability Strategy)

لضمان قدرة المنصة على التعامل مع زيادة الحمل وعدد العملاء الذكيين، سيتم تطبيق استراتيجيات قابلية التوسع التالية:
-   **التوسع الأفقي (Horizontal Scaling):** القدرة على إضافة المزيد من مثيلات `BaseAgent` و `Supervisor Agent` بشكل ديناميكي.
-   **الخدمات المصغرة (Microservices):** تقسيم المنصة إلى خدمات صغيرة مستقلة يمكن توسيعها بشكل فردي.
-   **الحوسبة بدون خادم (Serverless Computing):** استخدام وظائف بدون خادم (مثل AWS Lambda, Azure Functions) للمهام التي تتطلب توسعاً مرناً.
-   **قوائم انتظار الرسائل (Message Queues):** استخدام قوائم انتظار الرسائل لفصل المكونات وتمكين المعالجة غير المتزامنة.

### 15.2 التوافرية العالية (High Availability Strategy)

لضمان استمرارية الخدمة وتقليل وقت التوقف، سيتم تطبيق استراتيجيات التوافرية العالية:
-   **التكرار (Redundancy):** تشغيل مثيلات متعددة من المكونات الحيوية في مناطق توفر مختلفة.
-   **موازنة التحميل (Load Balancing):** توزيع حركة المرور بين المثيلات المتعددة.
-   **الكشف التلقائي عن الفشل والتعافي (Automated Failure Detection and Recovery):** استخدام أدوات الأوركسترا (مثل Kubernetes) للكشف عن المكونات الفاشلة واستبدالها تلقائياً.
-   **النسخ الاحتياطي والاستعادة (Backup and Restore):** سياسات نسخ احتياطي منتظمة للبيانات والتكوينات مع خطط استعادة مجربة.

### 15.3 استراتيجية التعافي من الكوارث (Disaster Recovery Strategy)

لضمان استمرارية العمل في حالة وقوع كارثة كبرى، سيتم وضع خطة للتعافي من الكوارث تتضمن:
-   **النسخ المتماثل عبر المناطق (Cross-Region Replication):** نسخ البيانات والتطبيقات إلى مناطق جغرافية مختلفة.
-   **أهداف وقت الاسترداد (RTO) وأهداف نقطة الاسترداد (RPO):** تحديد الأهداف الزمنية والمقدار المسموح به لفقدان البيانات.
-   **اختبار التعافي من الكوارث (DR Drills):** إجراء اختبارات دورية لخطة التعافي من الكوارث لضمان فعاليتها.

### 15.4 معايير الأداء (Performance Benchmarks)

سيتم تحديد معايير أداء واضحة لكل مكون من مكونات `BaseAgent` والمنصة ككل، وسيتم قياسها بانتظام. تتضمن هذه المعايير:
-   **زمن الاستجابة (Latency):** زمن معالجة الطلب من البداية إلى النهاية.
-   **الإنتاجية (Throughput):** عدد الطلبات التي يمكن معالجتها في وحدة زمنية.
-   **استخدام الموارد (Resource Utilization):** استخدام CPU، الذاكرة، والشبكة.

### 15.5 تخطيط القدرة (Capacity Planning)

سيتم إجراء تخطيط دوري للقدرة لضمان توفر الموارد الكافية لدعم النمو المتوقع للمنصة. يتضمن ذلك:
-   **تحليل الاتجاهات:** تحليل بيانات الاستخدام والأداء التاريخية للتنبؤ بالاحتياجات المستقبلية.
-   **نمذجة الحمل (Load Modeling):** محاكاة أحمال العمل المستقبلية لتقييم متطلبات الموارد.
-   **توفير الموارد (Resource Provisioning):** تخصيص الموارد بشكل استباقي لتلبية الطلبات المتزايدة.

### 15.6 استراتيجية التخزين المؤقت (Caching Strategy)

لتحسين الأداء وتقليل الحمل على قواعد البيانات والخدمات الخارجية، سيتم تطبيق استراتيجيات التخزين المؤقت:
-   **التخزين المؤقت للبيانات (Data Caching):** تخزين البيانات المستخدمة بشكل متكرر في ذاكرة التخزين المؤقت (مثل Redis, Memcached).
-   **التخزين المؤقت للنتائج (Result Caching):** تخزين نتائج العمليات المعقدة أو المكلفة.
-   **إدارة انتهاء صلاحية ذاكرة التخزين المؤقت (Cache Invalidation):** آليات لضمان تحديث البيانات المخزنة مؤقتاً.

### 15.7 معمارية قوائم الانتظار (Queue Architecture)

ستستخدم المنصة قوائم انتظار الرسائل (Message Queues) بشكل مكثف لفصل المكونات، تمكين المعالجة غير المتزامنة، وتحسين قابلية التوسع والموثوقية. تتضمن المعمارية:
-   **قوائم انتظار المهام (Task Queues):** لتوجيه المهام إلى العملاء الذكيين.
-   **قوائم انتظار الأحداث (Event Queues):** لنشر الأحداث بين المكونات.
-   **قوائم انتظار الرسائل الميتة (Dead-Letter Queues - DLQ):** للتعامل مع الرسائل التي فشلت معالجتها.

### 15.8 سياسة إصدار واجهة برمجة التطبيقات (API Versioning Policy)

لإدارة تطور واجهات برمجة التطبيقات (APIs) وضمان التوافق مع الإصدارات السابقة، سيتم تطبيق سياسة إصدار واجهة برمجة التطبيقات:
-   **الإصدار في المسار (Path Versioning):** تضمين رقم الإصدار في مسار URL (مثال: `/api/v1/agent`).
-   **الإصدار في الرأس (Header Versioning):** تضمين رقم الإصدار في رأس HTTP (مثال: `X-API-Version: 1`).
-   **التوثيق الواضح:** توثيق جميع التغييرات في واجهات برمجة التطبيقات في سجل التغييرات (CHANGELOG) الخاص بالمشروع.

## 16. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 17. التطور المستقبلي (Future Evolution)

تم تصميم معمارية `BaseAgent` ومنصة "بصيرة" مع الأخذ في الاعتبار التطور المستقبلي وقابلية التوسع لدعم المتطلبات المتزايدة. فيما يلي بعض جوانب التطور المستقبلي:

### 17.1 التوسع إلى أكثر من 100 وكيل ذكي (Scaling to 100+ AI Agents)
-   **معمارية Hub-and-Spoke:** تسمح بإضافة عدد غير محدود من العملاء الذكيين المتخصصين دون التأثير على العملاء الحاليين.
-   **قوائم انتظار الرسائل:** توفر آلية قوية للتواصل غير المتزامن بين العملاء، مما يمنع الاختناقات.
-   **التوسع الأفقي:** يمكن نشر مثيلات متعددة من `Supervisor Agent` والعملاء الذكيين في مجموعات (Clusters) موزعة.

### 17.2 تشغيل عدة نماذج LLM في نفس الوقت (Running Multiple LLMs Concurrently)
-   **طبقة LLM Abstraction:** تسمح بالتبديل السلس بين نماذج LLM المختلفة من مزودين متعددين.
-   **استراتيجية توجيه النماذج:** تمكن من توجيه المهام إلى النموذج الأنسب بناءً على التكلفة، الأداء، أو نوع المهمة.
-   **الحوسبة الموزعة:** يمكن توزيع استدعاءات LLM عبر موارد حوسبة مختلفة لتحقيق التوازي.

### 17.3 دعم MCP Servers و A2A Protocol (Supporting MCP Servers and A2A Protocol)
-   **واجهات API مرنة:** تصميم واجهات `SupervisorAPI` و `ExternalAPI` لتكون قابلة للتكيف مع بروتوكولات الاتصال المستقبلية مثل MCP (Model Context Protocol) و A2A (Agent-to-Agent Protocol).
-   **طبقة بروتوكول قابلة للتوسعة:** إمكانية إضافة محولات (Adapters) جديدة لدعم بروتوكولات الاتصال المختلفة.

### 17.4 دعم الحوسبة الموزعة والخدمات المصغرة (Distributed Computing and Microservices)
-   **تصميم معياري:** `BaseAgent` مصمم كوحدة مستقلة يمكن نشرها كخدمة مصغرة.
-   **Kubernetes:** استخدام Kubernetes لإدارة ونشر الخدمات المصغرة، مما يوفر قابلية التوسع، التوافرية العالية، وإدارة الموارد.
-   **قوائم انتظار الرسائل:** أساس للتواصل بين الخدمات المصغرة في بيئة موزعة.

### 17.5 دعم العمل السحابي والمحلي Hybrid Deployment (Hybrid Cloud/On-Premise Deployment)
-   **البنية التحتية المحايدة للسحابة (Cloud-Agnostic Infrastructure):** تصميم المنصة لتكون مستقلة عن مزود سحابي معين، مما يسهل النشر في بيئات سحابية مختلفة أو في بيئات محلية.
-   **Docker و Kubernetes:** توفير حاويات (Containers) لـ `BaseAgent` والخدمات الأخرى، مما يضمن قابلية النقل عبر البيئات.

### 17.6 دعم التعلم المستمر للوكلاء (Continuous Learning for Agents)
-   **وكيل التعلم (Learning Agent):** يمكن لوكيل متخصص مراقبة أداء العملاء الآخرين، جمع البيانات، وتدريب نماذج جديدة أو تحسين الـ Prompts بشكل مستمر.
-   **حلقات التغذية الراجعة (Feedback Loops):** دمج آليات لجمع التغذية الراجعة من المستخدمين أو من أداء العملاء الذكيين لتحسين سلوكهم.

### 17.7 دعم إضافة وكلاء جدد دون تعديل BaseAgent (Adding New Agents Without Modifying BaseAgent)
-   **الوراثة من BaseAgent:** العملاء الذكيون الجدد يرثون جميع الوظائف الأساسية من `BaseAgent`.
-   **معمارية الإضافات (Plugin Architecture):** تسمح بتخصيص سلوك العميل الذكي الجديد عن طريق إضافة إضافات (Plugins) بدلاً من تعديل الكود الأساسي لـ `BaseAgent`.
-   **التكوين (Configuration-driven):** يمكن تكوين العملاء الذكيين الجدد بشكل كبير عبر ملفات التكوين بدلاً من الكود.

## 18. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 19. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)


## 20. استراتيجية تحسين التكلفة (Cost Optimization Strategy)

لضمان كفاءة التكلفة في تشغيل منصة "بصيرة"، سيتم تطبيق الاستراتيجيات التالية:
-   **توجيه النماذج الذكي (Intelligent Model Routing):** استخدام نماذج LLM الأقل تكلفة للمهام التي لا تتطلب قدرات عالية، والنماذج الأكثر تكلفة للمهام الحرجة فقط.
-   **ضغط الـ Prompts (Prompt Compression):** تقليل حجم الـ Prompts المرسلة إلى LLM لتقليل عدد الرموز (tokens) المستخدمة.
-   **التخزين المؤقت (Caching):** تخزين استجابات LLM الشائعة أو نتائج الأدوات لتجنب إعادة الحساب.
-   **إدارة الموارد (Resource Management):** تحسين استخدام موارد الحوسبة (CPU, GPU, Memory) لتجنب الهدر.
-   **الاستخدام الأمثل لواجهات برمجة التطبيقات (API Optimization):** تجميع الطلبات (Batching) وتقليل عدد استدعاءات API.

## 21. التطور المستقبلي (Future Evolution)

تم تصميم معمارية `BaseAgent` ومنصة "بصيرة" مع الأخذ في الاعتبار التطور المستقبلي وقابلية التوسع لدعم المتطلبات المتزايدة. فيما يلي بعض جوانب التطور المستقبلي:

### 21.1 التوسع إلى أكثر من 100 وكيل ذكي (Scaling to 100+ AI Agents)
-   **معمارية Hub-and-Spoke:** تسمح بإضافة عدد غير محدود من العملاء الذكيين المتخصصين دون التأثير على العملاء الحاليين.
-   **قوائم انتظار الرسائل:** توفر آلية قوية للتواصل غير المتزامن بين العملاء، مما يمنع الاختناقات.
-   **التوسع الأفقي:** يمكن نشر مثيلات متعددة من `Supervisor Agent` والعملاء الذكيين في مجموعات (Clusters) موزعة.

### 21.2 تشغيل عدة نماذج LLM في نفس الوقت (Running Multiple LLMs Concurrently)
-   **طبقة LLM Abstraction:** تسمح بالتبديل السلس بين نماذج LLM المختلفة من مزودين متعددين.
-   **استراتيجية توجيه النماذج:** تمكن من توجيه المهام إلى النموذج الأنسب بناءً على التكلفة، الأداء، أو نوع المهمة.
-   **الحوسبة الموزعة:** يمكن توزيع استدعاءات LLM عبر موارد حوسبة مختلفة لتحقيق التوازي.

### 21.3 دعم MCP Servers و A2A Protocol (Supporting MCP Servers and A2A Protocol)
-   **واجهات API مرنة:** تصميم واجهات `SupervisorAPI` و `ExternalAPI` لتكون قابلة للتكيف مع بروتوكولات الاتصال المستقبلية مثل MCP (Model Context Protocol) و A2A (Agent-to-Agent Protocol).
-   **طبقة بروتوكول قابلة للتوسعة:** إمكانية إضافة محولات (Adapters) جديدة لدعم بروتوكولات الاتصال المختلفة.

### 21.4 دعم الحوسبة الموزعة والخدمات المصغرة (Distributed Computing and Microservices)
-   **تصميم معياري:** `BaseAgent` مصمم كوحدة مستقلة يمكن نشرها كخدمة مصغرة.
-   **Kubernetes:** استخدام Kubernetes لإدارة ونشر الخدمات المصغرة، مما يوفر قابلية التوسع، التوافرية العالية، وإدارة الموارد.
-   **قوائم انتظار الرسائل:** أساس للتواصل بين الخدمات المصغرة في بيئة موزعة.

### 21.5 دعم العمل السحابي والمحلي Hybrid Deployment (Hybrid Cloud/On-Premise Deployment)
-   **البنية التحتية المحايدة للسحابة (Cloud-Agnostic Infrastructure):** تصميم المنصة لتكون مستقلة عن مزود سحابي معين، مما يسهل النشر في بيئات سحابية مختلفة أو في بيئات محلية.
-   **Docker و Kubernetes:** توفير حاويات (Containers) لـ `BaseAgent` والخدمات الأخرى، مما يضمن قابلية النقل عبر البيئات.

### 21.6 دعم التعلم المستمر للوكلاء (Continuous Learning for Agents)
-   **وكيل التعلم (Learning Agent):** يمكن لوكيل متخصص مراقبة أداء العملاء الآخرين، جمع البيانات، وتدريب نماذج جديدة أو تحسين الـ Prompts بشكل مستمر.
-   **حلقات التغذية الراجعة (Feedback Loops):** دمج آليات لجمع التغذية الراجعة من المستخدمين أو من أداء العملاء الذكيين لتحسين سلوكهم.

### 21.7 دعم إضافة وكلاء جدد دون تعديل BaseAgent (Adding New Agents Without Modifying BaseAgent)
-   **الوراثة من BaseAgent:** العملاء الذكيون الجدد يرثون جميع الوظائف الأساسية من `BaseAgent`.
-   **معمارية الإضافات (Plugin Architecture):** تسمح بتخصيص سلوك العميل الذكي الجديد عن طريق إضافة إضافات (Plugins) بدلاً من تعديل الكود الأساسي لـ `BaseAgent`.
-   **التكوين (Configuration-driven):** يمكن تكوين العملاء الذكيين الجدد بشكل كبير عبر ملفات التكوين بدلاً من الكود.

## 22. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)


## 22. التطور المستقبلي (Future Evolution)

تم تصميم معمارية `BaseAgent` ومنصة "بصيرة" مع الأخذ في الاعتبار التطور المستقبلي وقابلية التوسع لدعم المتطلبات المتزايدة. فيما يلي بعض جوانب التطور المستقبلي:

### 22.1 التوسع إلى أكثر من 100 وكيل ذكي (Scaling to 100+ AI Agents)
-   **معمارية Hub-and-Spoke:** تسمح بإضافة عدد غير محدود من العملاء الذكيين المتخصصين دون التأثير على العملاء الحاليين.
-   **قوائم انتظار الرسائل:** توفر آلية قوية للتواصل غير المتزامن بين العملاء، مما يمنع الاختناقات.
-   **التوسع الأفقي:** يمكن نشر مثيلات متعددة من `Supervisor Agent` والعملاء الذكيين في مجموعات (Clusters) موزعة.

### 22.2 تشغيل عدة نماذج LLM في نفس الوقت (Running Multiple LLMs Concurrently)
-   **طبقة LLM Abstraction:** تسمح بالتبديل السلس بين نماذج LLM المختلفة من مزودين متعددين.
-   **استراتيجية توجيه النماذج:** تمكن من توجيه المهام إلى النموذج الأنسب بناءً على التكلفة، الأداء، أو نوع المهمة.
-   **الحوسبة الموزعة:** يمكن توزيع استدعاءات LLM عبر موارد حوسبة مختلفة لتحقيق التوازي.

### 22.3 دعم MCP Servers و A2A Protocol (Supporting MCP Servers and A2A Protocol)
-   **واجهات API مرنة:** تصميم واجهات `SupervisorAPI` و `ExternalAPI` لتكون قابلة للتكيف مع بروتوكولات الاتصال المستقبلية مثل MCP (Model Context Protocol) و A2A (Agent-to-Agent Protocol).
-   **طبقة بروتوكول قابلة للتوسعة:** إمكانية إضافة محولات (Adapters) جديدة لدعم بروتوكولات الاتصال المختلفة.

### 22.4 دعم الحوسبة الموزعة والخدمات المصغرة (Distributed Computing and Microservices)
-   **تصميم معياري:** `BaseAgent` مصمم كوحدة مستقلة يمكن نشرها كخدمة مصغرة.
-   **Kubernetes:** استخدام Kubernetes لإدارة ونشر الخدمات المصغرة، مما يوفر قابلية التوسع، التوافرية العالية، وإدارة الموارد.
-   **قوائم انتظار الرسائل:** أساس للتواصل بين الخدمات المصغرة في بيئة موزعة.

### 22.5 دعم العمل السحابي والمحلي Hybrid Deployment (Hybrid Cloud/On-Premise Deployment)
-   **البنية التحتية المحايدة للسحابة (Cloud-Agnostic Infrastructure):** تصميم المنصة لتكون مستقلة عن مزود سحابي معين، مما يسهل النشر في بيئات سحابية مختلفة أو في بيئات محلية.
-   **Docker و Kubernetes:** توفير حاويات (Containers) لـ `BaseAgent` والخدمات الأخرى، مما يضمن قابلية النقل عبر البيئات.

### 22.6 دعم التعلم المستمر للوكلاء (Continuous Learning for Agents)
-   **وكيل التعلم (Learning Agent):** يمكن لوكيل متخصص مراقبة أداء العملاء الآخرين، جمع البيانات، وتدريب نماذج جديدة أو تحسين الـ Prompts بشكل مستمر.
-   **حلقات التغذية الراجعة (Feedback Loops):** دمج آليات لجمع التغذية الراجعة من المستخدمين أو من أداء العملاء الذكيين لتحسين سلوكهم.

### 22.7 دعم إضافة وكلاء جدد دون تعديل BaseAgent (Adding New Agents Without Modifying BaseAgent)
-   **الوراثة من BaseAgent:** العملاء الذكيون الجدد يرثون جميع الوظائف الأساسية من `BaseAgent`.
-   **معمارية الإضافات (Plugin Architecture):** تسمح بتخصيص سلوك العميل الذكي الجديد عن طريق إضافة إضافات (Plugins) بدلاً من تعديل الكود الأساسي لـ `BaseAgent`.
-   **التكوين (Configuration-driven):** يمكن تكوين العملاء الذكيين الجدد بشكل كبير عبر ملفات التكوين بدلاً من الكود.

## 23. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)


## 9.6 استراتيجية ضغط الذاكرة (Memory Compression Strategy)

لتحسين كفاءة الذاكرة طويلة المدى وتقليل تكاليف التخزين والاسترجاع، سيتم تطبيق استراتيجيات ضغط الذاكرة:
-   **التضمين الدلالي (Semantic Embedding):** تحويل النصوص إلى متجهات (vectors) لتقليل حجم التخزين وتمكين البحث الدلالي.
-   **التلخيص الدوري (Periodic Summarization):** تلخيص المحادثات أو الأحداث التاريخية بشكل دوري وتخزين الملخصات بدلاً من النصوص الكاملة.
-   **إزالة البيانات القديمة/غير ذات الصلة (Pruning):** حذف البيانات التي تجاوزت فترة صلاحيتها أو التي لم تعد ذات صلة.

## 9.7 استراتيجية إصدار الـ Prompt (Prompt Versioning Strategy)

لإدارة تطور الـ Prompts وضمان إمكانية التتبع والتحكم، سيتم تطبيق استراتيجية لإصدار الـ Prompts:
-   **التخزين المركزي:** تخزين جميع الـ Prompts في مستودع مركزي (مثل نظام التحكم في الإصدارات Git أو قاعدة بيانات).
-   **الإصدارات (Versioning):** تعيين رقم إصدار لكل Prompt، مما يسمح بالعودة إلى إصدارات سابقة وتتبع التغييرات.
-   **الاختبار A/B:** إمكانية اختبار إصدارات مختلفة من الـ Prompts لتقييم فعاليتها.

## 10. إدارة الأخطاء وإعادة المحاولة (Error Handling and Retry)

### 10.1 آليات اكتشاف الأخطاء (Error Detection Mechanisms)
-   **التحقق من صحة المدخلات (Input Validation):** التحقق من صحة المدخلات قبل معالجتها.
-   **مراقبة استجابات الأدوات و LLM:** تحليل استجابات الأدوات ونماذج LLM لاكتشاف الأخطاء أو الاستجابات غير المتوقعة.
-   **الاستثناءات (Exceptions):** استخدام آليات الاستثناءات القياسية في البرمجة.

### 10.2 استراتيجيات إعادة المحاولة (Retry Strategies)
-   **إعادة المحاولة الأسية (Exponential Backoff):** إعادة محاولة العمليات الفاشلة مع زيادة زمن الانتظار بين المحاولات.
-   **الحد الأقصى للمحاولات (Max Retries):** تحديد عدد أقصى للمحاولات قبل الإبلاغ عن فشل دائم.

### 10.3 التعافي من الأخطاء (Error Recovery)
-   **العودة إلى حالة سابقة (Rollback):** التراجع عن التغييرات التي تمت قبل حدوث الخطأ.
-   **الإبلاغ عن الخطأ (Error Reporting):** إرسال تفاصيل الخطأ إلى `Supervisor Agent` أو نظام المراقبة.
-   **التعامل مع الأخطاء المعروفة (Known Error Handling):** وجود منطق محدد للتعامل مع أنواع معينة من الأخطاء.

### 10.4 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine --> BaseAgent: "يستأنف/يفشل المهمة"
```

## 11. نظام التسجيل والمراقبة (Logging and Monitoring)

### 11.1 التسجيل (Logging)
-   **مستويات التسجيل:** دعم مستويات تسجيل مختلفة (DEBUG, INFO, WARNING, ERROR, CRITICAL).
-   **تنسيق السجلات:** تنسيق موحد للسجلات يسهل التحليل (JSON).
-   **محتوى السجلات:** تسجيل تفاصيل المهمة، خطوات التفكير، استدعاءات الأدوات، استجابات LLM، والأخطاء.
-   **تخزين السجلات:** تخزين السجلات في نظام مركزي (مثل ELK Stack) للتحليل والمراجعة.

### 11.2 المراقبة (Monitoring)
-   **المقاييس (Metrics):** جمع مقاييس الأداء (مثل زمن الاستجابة، معدل النجاح/الفشل، استخدام الموارد).
-   **لوحات المعلومات (Dashboards):** توفير لوحات معلومات لمراقبة صحة وأداء العملاء الذكيين في الوقت الفعلي.
-   **التنبيهات (Alerts):** إعداد تنبيهات عند تجاوز المقاييس لحدود معينة أو عند حدوث أخطاء حرجة.

### 11.3 معمارية الملاحظة (Observability Architecture)

لضمان رؤية عميقة لأداء وسلوك العملاء الذكيين، سيتم تطبيق معمارية ملاحظة شاملة تتضمن:
-   **التسجيل المنظم (Structured Logging):** استخدام تنسيق JSON للسجلات لسهولة التحليل الآلي.
-   **المقاييس (Metrics):** جمع مقاييس الأداء والتشغيل (CPU, Memory, Latency, Error Rates) باستخدام أدوات مثل Prometheus.
-   **التتبع الموزع (Distributed Tracing):** تتبع مسار الطلب عبر العملاء الذكيين والخدمات المختلفة باستخدام أدوات مثل Jaeger أو OpenTelemetry.

### 11.4 تصميم القياس عن بعد (Telemetry Design)

سيتم تصميم نظام القياس عن بعد لجمع البيانات التشغيلية الهامة من `BaseAgent` والعملاء الذكيين المشتقين منه. يتضمن ذلك:
-   **بيانات الأداء:** زمن تنفيذ المهام، زمن استجابة LLM، زمن استدعاء الأدوات.
-   **بيانات الاستخدام:** عدد استدعاءات LLM، عدد استدعاءات الأدوات، عدد الرموز المستخدمة.
-   **بيانات الأخطاء:** أنواع الأخطاء، تكرارها، وسياق حدوثها.
-   **بيانات الموارد:** استخدام CPU، الذاكرة، والشبكة.

## 12. نظام الصلاحيات والأمان (Authorization and Security System)

### 12.1 مبادئ الأمان (Security Principles)
-   **الامتياز الأقل (Least Privilege):** يجب أن يمتلك كل عميل ذكي الحد الأدنى من الصلاحيات اللازمة لأداء وظيفته.
-   **عزل الموارد (Resource Isolation):** عزل موارد العملاء الذكيين عن بعضها البعض.
-   **التشفير (Encryption):** تشفير البيانات الحساسة أثناء النقل وفي وضع السكون.
-   **التحقق من صحة المدخلات (Input Validation):** حماية ضد حقن الـ Prompts (Prompt Injection) وغيرها من الهجمات.

### 12.2 آليات الصلاحيات (Authorization Mechanisms)
-   **رموز الوصول (Access Tokens):** استخدام رموز وصول مؤقتة ومحدودة الصلاحية للوصول إلى الأدوات الخارجية أو الخدمات.
-   **التحكم في الوصول المستند إلى الدور (Role-Based Access Control - RBAC):** تحديد الصلاحيات بناءً على دور العميل الذكي.

### 12.3 نموذج التهديد الأمني (Security Threat Model)

سيتم تطوير نموذج تهديد أمني شامل لتحديد وتحليل وتخفيف المخاطر الأمنية المحتملة لـ `BaseAgent` والمنصة ككل. سيتضمن ذلك:
-   **تحديد الأصول:** البيانات الحساسة، الوظائف الحيوية، واجهات برمجة التطبيقات.
-   **تحديد التهديدات:** هجمات حقن الـ Prompt، الوصول غير المصرح به، تسرب البيانات، هجمات حجب الخدمة (DoS).
-   **تحديد نقاط الضعف:** أخطاء في الكود، تكوينات خاطئة، نقاط ضعف في المكتبات الخارجية.
-   **تحديد الضوابط:** آليات المصادقة، التشفير، التحقق من صحة المدخلات، المراقبة الأمنية.

## 13. معايير كتابة الكود الخاصة بـ BaseAgent (BaseAgent Coding Standards)

بالإضافة إلى معايير كتابة الكود العامة للمشروع، يجب أن يلتزم كود `BaseAgent` بالمبادئ التالية:
-   **قابلية التوسع (Extensibility):** تصميم الوحدات بطريقة تسمح بإضافة وظائف جديدة بسهولة دون تعديل الكود الحالي (مبدأ Open/Closed).
-   **قابلية الاختبار (Testability):** تصميم الوحدات لتكون سهلة الاختبار بشكل منفصل.
-   **النمطية (Modularity):** تقسيم الكود إلى وحدات صغيرة ومستقلة ذات مسؤوليات واضحة.
-   **الوثوقية (Reliability):** التعامل مع الحالات الاستثنائية والأخطاء بشكل رشيد.
-   **الوضوح (Clarity):** كود نظيف، مقروء، وموثق جيداً.

## 14. استراتيجية الاختبارات (Testing Strategy)

تتبع استراتيجية الاختبارات لـ `BaseAgent` نهجاً شاملاً لضمان الجودة والموثوقية:

-   **اختبارات الوحدات (Unit Tests):** اختبار كل وحدة (Module) أو وظيفة بشكل منفصل لضمان عملها الصحيح.
-   **اختبارات التكامل (Integration Tests):** اختبار تفاعل الوحدات المختلفة مع بعضها البعض ومع الخدمات الخارجية (مثل LLMs، قواعد البيانات).
-   **اختبارات الأداء (Performance Tests):** تقييم أداء `BaseAgent` تحت أحمال مختلفة.
-   **اختبارات الأمان (Security Tests):** التحقق من مقاومة `BaseAgent` للهجمات الأمنية.
-   **اختبارات السلوك (Behavioral Tests):** التأكد من أن `BaseAgent` يتصرف كما هو متوقع في سيناريوهات مختلفة، خاصة فيما يتعلق بالتفكير واستدعاء الأدوات.

## 15. استراتيجيات التشغيل والأداء (Operational and Performance Strategies)

### 15.1 قابلية التوسع (Scalability Strategy)

لضمان قدرة المنصة على التعامل مع زيادة الحمل وعدد العملاء الذكيين، سيتم تطبيق استراتيجيات قابلية التوسع التالية:
-   **التوسع الأفقي (Horizontal Scaling):** القدرة على إضافة المزيد من مثيلات `BaseAgent` و `Supervisor Agent` بشكل ديناميكي.
-   **الخدمات المصغرة (Microservices):** تقسيم المنصة إلى خدمات صغيرة مستقلة يمكن توسيعها بشكل فردي.
-   **الحوسبة بدون خادم (Serverless Computing):** استخدام وظائف بدون خادم (مثل AWS Lambda, Azure Functions) للمهام التي تتطلب توسعاً مرناً.
-   **قوائم انتظار الرسائل (Message Queues):** استخدام قوائم انتظار الرسائل لفصل المكونات وتمكين المعالجة غير المتزامنة.

### 15.2 التوافرية العالية (High Availability Strategy)

لضمان استمرارية الخدمة وتقليل وقت التوقف، سيتم تطبيق استراتيجيات التوافرية العالية:
-   **التكرار (Redundancy):** تشغيل مثيلات متعددة من المكونات الحيوية في مناطق توفر مختلفة.
-   **موازنة التحميل (Load Balancing):** توزيع حركة المرور بين المثيلات المتعددة.
-   **الكشف التلقائي عن الفشل والتعافي (Automated Failure Detection and Recovery):** استخدام أدوات الأوركسترا (مثل Kubernetes) للكشف عن المكونات الفاشلة واستبدالها تلقائياً.
-   **النسخ الاحتياطي والاستعادة (Backup and Restore):** سياسات نسخ احتياطي منتظمة للبيانات والتكوينات مع خطط استعادة مجربة.

### 15.3 استراتيجية التعافي من الكوارث (Disaster Recovery Strategy)

لضمان استمرارية العمل في حالة وقوع كارثة كبرى، سيتم وضع خطة للتعافي من الكوارث تتضمن:
-   **النسخ المتماثل عبر المناطق (Cross-Region Replication):** نسخ البيانات والتطبيقات إلى مناطق جغرافية مختلفة.
-   **أهداف وقت الاسترداد (RTO) وأهداف نقطة الاسترداد (RPO):** تحديد الأهداف الزمنية والمقدار المسموح به لفقدان البيانات.
-   **اختبار التعافي من الكوارث (DR Drills):** إجراء اختبارات دورية لخطة التعافي من الكوارث لضمان فعاليتها.

### 15.4 معايير الأداء (Performance Benchmarks)

سيتم تحديد معايير أداء واضحة لكل مكون من مكونات `BaseAgent` والمنصة ككل، وسيتم قياسها بانتظام. تتضمن هذه المعايير:
-   **زمن الاستجابة (Latency):** زمن معالجة الطلب من البداية إلى النهاية.
-   **الإنتاجية (Throughput):** عدد الطلبات التي يمكن معالجتها في وحدة زمنية.
-   **استخدام الموارد (Resource Utilization):** استخدام CPU، الذاكرة، والشبكة.

### 15.5 تخطيط القدرة (Capacity Planning)

سيتم إجراء تخطيط دوري للقدرة لضمان توفر الموارد الكافية لدعم النمو المتوقع للمنصة. يتضمن ذلك:
-   **تحليل الاتجاهات:** تحليل بيانات الاستخدام والأداء التاريخية للتنبؤ بالاحتياجات المستقبلية.
-   **نمذجة الحمل (Load Modeling):** محاكاة أحمال العمل المستقبلية لتقييم متطلبات الموارد.
-   **توفير الموارد (Resource Provisioning):** تخصيص الموارد بشكل استباقي لتلبية الطلبات المتزايدة.

### 15.6 استراتيجية التخزين المؤقت (Caching Strategy)

لتحسين الأداء وتقليل الحمل على قواعد البيانات والخدمات الخارجية، سيتم تطبيق استراتيجيات التخزين المؤقت:
-   **التخزين المؤقت للبيانات (Data Caching):** تخزين البيانات المستخدمة بشكل متكرر في ذاكرة التخزين المؤقت (مثل Redis, Memcached).
-   **التخزين المؤقت للنتائج (Result Caching):** تخزين نتائج العمليات المعقدة أو المكلفة.
-   **إدارة انتهاء صلاحية ذاكرة التخزين المؤقت (Cache Invalidation):** آليات لضمان تحديث البيانات المخزنة مؤقتاً.

### 15.7 معمارية قوائم الانتظار (Queue Architecture)

ستستخدم المنصة قوائم انتظار الرسائل (Message Queues) بشكل مكثف لفصل المكونات، تمكين المعالجة غير المتزامنة، وتحسين قابلية التوسع والموثوقية. تتضمن المعمارية:
-   **قوائم انتظار المهام (Task Queues):** لتوجيه المهام إلى العملاء الذكيين.
-   **قوائم انتظار الأحداث (Event Queues):** لنشر الأحداث بين المكونات.
-   **قوائم انتظار الرسائل الميتة (Dead-Letter Queues - DLQ):** للتعامل مع الرسائل التي فشلت معالجتها.

### 15.8 سياسة إصدار واجهة برمجة التطبيقات (API Versioning Policy)

لإدارة تطور واجهات برمجة التطبيقات (APIs) وضمان التوافق مع الإصدارات السابقة، سيتم تطبيق سياسة إصدار واجهة برمجة التطبيقات:
-   **الإصدار في المسار (Path Versioning):** تضمين رقم الإصدار في مسار URL (مثال: `/api/v1/agent`).
-   **الإصدار في الرأس (Header Versioning):** تضمين رقم الإصدار في رأس HTTP (مثال: `X-API-Version: 1`).
-   **التوثيق الواضح:** توثيق جميع التغييرات في واجهات برمجة التطبيقات في سجل التغييرات (CHANGELOG) الخاص بالمشروع).

## 16. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 17. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)


class BaseAgent {
  + id: str
  + name: str
  + memory_manager: MemoryManager
  + reasoning_engine: ReasoningEngine
  + tool_executor: ToolExecutor
  + llm_interface: LLMInterface
  + error_handler: ErrorHandler
  + logger: Logger
  + security_manager: SecurityManager
  + plugin_manager: PluginManager
  + __init__(...)
  + handle_request(request: AgentRequest) -> AgentResponse
  + _initialize_agent()
  + _terminate_agent()
}

class MemoryManager {
  + short_term_memory: ShortTermMemory
  + long_term_memory: LongTermMemory
  + retrieve_context(task_id: str) -> Context
  + update_memory(task_id: str, data: Any)
}

class ReasoningEngine {
  + reason(task: Task, context: Context, tools: List[Tool]) -> Action
  + _plan_task(task: Task, context: Context) -> Plan
  + _select_tool(plan: Plan, available_tools: List[Tool]) -> Tool
  + _generate_tool_input(tool: Tool, context: Context) -> Dict
}

class ToolExecutor {
  + execute_tool(tool: Tool, input: Dict) -> ToolOutput
}

class LLMInterface {
  + generate_response(prompt: Prompt, model_config: Dict) -> LLMResponse
  + embed_text(text: str) -> Embedding
}

class ErrorHandler {
  + handle_error(error: Exception, context: Dict) -> ErrorRecoveryStrategy
  + _retry_operation(operation: Callable, retries: int) -> Any
}

class Logger {
  + log(level: LogLevel, message: str, context: Dict)
}

class SecurityManager {
  + authorize_tool_access(agent_id: str, tool_name: str) -> bool
  + encrypt_data(data: str) -> str
}

class PluginManager {
  + load_plugin(plugin_name: str)
  + unload_plugin(plugin_name: str)
  + get_available_plugins() -> List[Plugin]
}

BaseAgent *-- MemoryManager
BaseAgent *-- ReasoningEngine
BaseAgent *-- ToolExecutor
BaseAgent *-- LLMInterface
BaseAgent *-- ErrorHandler
BaseAgent *-- Logger
BaseAgent *-- SecurityManager
BaseAgent *-- PluginManager

ReasoningEngine --> MemoryManager: "يستخدم"
ReasoningEngine --> ToolExecutor: "يستخدم"
ReasoningEngine --> LLMInterface: "يستخدم"
ReasoningEngine --> ErrorHandler: "يستخدم"
ReasoningEngine --> Logger: "يستخدم"
ReasoningEngine --> SecurityManager: "يستخدم"

MemoryManager --> ShortTermMemory
MemoryManager --> LongTermMemory

LLMInterface --> PromptManager
```

### 3.7 مخطط التسلسل (Sequence Diagram) - مثال: معالجة طلب بسيط

```d2
direction: right

SupervisorAgent -> BaseAgent: request(task_id, query)
BaseAgent -> ReasoningEngine: analyze_request(query)
ReasoningEngine -> MemoryManager: retrieve_context(task_id)
MemoryManager --> ReasoningEngine: context
ReasoningEngine -> LLMInterface: generate_plan(query, context)
LLMInterface --> ReasoningEngine: plan
ReasoningEngine -> ToolExecutor: select_tool(plan)
ToolExecutor --> ReasoningEngine: tool_info
ReasoningEngine -> ToolExecutor: execute_tool(tool_info, input)
ToolExecutor --> ReasoningEngine: tool_output
ReasoningEngine -> MemoryManager: update_memory(task_id, tool_output)
MemoryManager --> ReasoningEngine: memory_updated
ReasoningEngine -> LLMInterface: generate_response(plan, tool_output, context)
LLMInterface --> ReasoningEngine: final_response
ReasoningEngine --> BaseAgent: agent_response
BaseAgent --> SupervisorAgent: response(task_id, agent_response)
```

### 3.8 مخطط النشر (Deployment Diagram)

```d2
direction: right

cloud "منصة بصيرة السحابية" {
  cluster "Kubernetes Cluster" {
    node "Worker Node 1" {
      container "Supervisor Agent Pod" {
        process "Supervisor Agent"
      }
      container "BaseAgent Instance 1 (وكيل التحليل الفني)" {
        process "BaseAgent"
      }
      container "BaseAgent Instance 2 (وكيل أخبار السوق)" {
        process "BaseAgent"
      }
    }
    node "Worker Node N" {
      container "BaseAgent Instance N" {
        process "BaseAgent"
      }
    }
  }
  database "Vector DB (ذاكرة طويلة المدى)"
  database "Relational DB (حالة، تكوينات)"
  queue "Message Queue (Kafka/RabbitMQ)"
  storage "Object Storage (S3)"
}

external_system "مزودو LLM (OpenAI, Gemini)"
external_system "مزودو بيانات السوق (Tadawul API)"

"Supervisor Agent" <-> "BaseAgent Instance 1 (وكيل التحليل الفني)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance 2 (وكيل أخبار السوق)": "يتواصل عبر"
"Supervisor Agent" <-> "BaseAgent Instance N": "يتواصل عبر"

"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو LLM (OpenAI, Gemini)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "مزودو بيانات السوق (Tadawul API)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Vector DB (ذاكرة طويلة المدى)": "يستخدم"
"BaseAgent Instance 1 (وكيل التحليل الفني)" <-> "Relational DB (حالة، تكوينات)": "يستخدم"

"Message Queue (Kafka/RabbitMQ)" <-> "Supervisor Agent": "للتواصل غير المتزامن"
"Object Storage (S3)" <-> "BaseAgent Instance N": "لتخزين البيانات الكبيرة"
```

### 3.9 مخطط تدفق البيانات (Data Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
LLMProviders: { shape: cloud; label: "مزودو LLM" }
ExternalTools: { shape: cloud; label: "أدوات خارجية" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى" }

User -> SupervisorAgent: "طلب تحليلي"
SupervisorAgent -> BaseAgent: "توجيه المهمة"

BaseAgent -> ShortTermMemory: "قراءة/كتابة السياق"
BaseAgent -> LongTermMemory: "قراءة/كتابة المعرفة"
BaseAgent -> LLMProviders: "استدعاء LLM (Prompt)"
LLMProviders -> BaseAgent: "استجابة LLM"
BaseAgent -> ExternalTools: "استدعاء أداة"
ExternalTools -> BaseAgent: "مخرجات الأداة"

BaseAgent -> SupervisorAgent: "نتائج المهمة"
SupervisorAgent -> User: "التحليل النهائي"
```

### 3.10 مخطط تدفق الأحداث (Event Flow Diagram)

```d2
direction: right

User: { shape: person; label: "المستخدم" }
SupervisorAgent: { shape: rectangle; label: "Supervisor Agent" }
BaseAgent: { shape: rectangle; label: "BaseAgent (وكيل متخصص)" }
MessageQueue: { shape: queue; label: "Message Queue" }

User -> SupervisorAgent: "يرسل طلب"
SupervisorAgent -> MessageQueue: "ينشر حدث: TaskAssigned"
MessageQueue -> BaseAgent: "يستقبل حدث: TaskAssigned"
BaseAgent -> BaseAgent: "يعالج المهمة"
BaseAgent -> MessageQueue: "ينشر حدث: TaskCompleted/TaskFailed"
MessageQueue -> SupervisorAgent: "يستقبل حدث: TaskCompleted/TaskFailed"
SupervisorAgent -> User: "يرسل إشعار/نتيجة"
```

### 3.11 مخطط تدفق الذاكرة (Memory Flow Diagram)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ShortTermMemory: { shape: cylinder; label: "الذاكرة قصيرة المدى (Redis/In-memory)" }
LongTermMemory: { shape: cylinder; label: "الذاكرة طويلة المدى (Vector DB/Relational DB)" }

BaseAgent -> ShortTermMemory: "يخزن/يسترجع سياق الجلسة"
BaseAgent -> LongTermMemory: "يخزن/يسترجع المعرفة الدائمة"

ShortTermMemory -> LongTermMemory: "ترحيل السياق الهام (عند الحاجة)"
LongTermMemory -> ShortTermMemory: "استرجاع المعرفة ذات الصلة"
```

### 3.12 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 3.13 تدفق معالجة الـ Prompt (Prompt Processing Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
PromptManager: { shape: rectangle; label: "Prompt Manager" }
MemoryManager: { shape: rectangle; label: "Memory Manager" }
LLMInterface: { shape: rectangle; label: "LLM Interface" }
LLMProvider: { shape: cloud; label: "مزود LLM" }

BaseAgent -> PromptManager: "طلب توليد Prompt"
PromptManager -> MemoryManager: "يسترجع السياق ذي الصلة"
MemoryManager --> PromptManager: "السياق والذاكرة"
PromptManager -> PromptManager: "يطبق القوالب ويضغط السياق"
PromptManager --> BaseAgent: "Prompt النهائي"
BaseAgent -> LLMInterface: "يرسل Prompt لـ LLM"
LLMInterface -> LLMProvider: "يرسل Prompt"
LLMProvider --> LLMInterface: "استجابة LLM"
LLMInterface --> BaseAgent: "استجابة LLM"
```

### 3.14 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine --> BaseAgent: "يستأنف/يفشل المهمة"
```

### 3.15 مخطط انتقال الحالة (State Transition Diagram)

```d2
direction: right

stateDiagram-v2
    [*] --> Idle
    Idle --> Initializing: "استلام طلب"
    Initializing --> Ready: "تم التهيئة بنجاح"
    Ready --> Processing: "بدء معالجة المهمة"
    Processing --> Processing: "خطوة مهمة (تفكير/أداة)"
    Processing --> Ready: "المهمة مكتملة"
    Processing --> Failed: "فشل المهمة"
    Failed --> Ready: "إعادة تعيين/محاولة جديدة"
    Ready --> Terminating: "طلب إنهاء"
    Initializing --> Failed: "فشل التهيئة"
    Terminating --> [*]: "تم الإنهاء"
```

## 4. دورة حياة الوكيل (Agent Lifecycle)

تتبع دورة حياة `BaseAgent` المراحل التالية:

1.  **التهيئة (Initialization):**
    *   يتم إنشاء مثيل (instance) لـ `BaseAgent` أو العميل الذكي المشتق منه.
    *   يتم تحميل التكوينات الخاصة بالعميل (مثل الأدوات المتاحة، إعدادات الذاكرة، إعدادات LLM).
    *   يتم تهيئة وحدات الذاكرة، ومحرك التفكير، ومنفذ الأدوات.
    *   يتم تسجيل العميل الذكي لدى `Supervisor Agent` (إذا لزم الأمر).

2.  **التنفيذ (Execution):**
    *   يستقبل العميل الذكي طلباً أو مهمة من `Supervisor Agent` عبر واجهة `SupervisorAPI`.
    *   يقوم `ReasoningEngine` بتحليل الطلب، واستخدام الذاكرة، واستدعاء الأدوات، والتفاعل مع LLM لتوليد استجابة أو اتخاذ إجراء.
    *   تتكرر هذه العملية حتى تكتمل المهمة أو يتم الوصول إلى حالة نهائية.

3.  **الإنهاء (Termination):**
    *   يتم تحرير الموارد التي يستخدمها العميل الذكي (مثل اتصالات قاعدة البيانات، جلسات LLM).
    *   يتم حفظ أي حالة ضرورية للذاكرة طويلة المدى.
    *   يتم إلغاء تسجيل العميل الذكي من `Supervisor Agent`.

## 5. تدفق البيانات وتنفيذ المهام (Data Flow and Task Execution)

### 5.1 آلية التواصل مع Supervisor Agent (Communication with Supervisor Agent)

يعتمد التواصل بين العملاء الذكيين و`Supervisor Agent` على معمارية Hub-and-Spoke. `BaseAgent` يتصل بـ `Supervisor Agent` عبر واجهة `SupervisorAPI` الموحدة. لا يوجد اتصال مباشر بين العملاء الذكيين المتخصصين.

**تدفق الاتصال:**
1.  **الطلب:** يرسل `Supervisor Agent` طلباً (مهمة) إلى عميل ذكي محدد (أو مجموعة عملاء) عبر واجهة `SupervisorAPI` الخاصة به.
2.  **المعالجة:** يستقبل العميل الذكي الطلب، يقوم بمعالجته باستخدام `ReasoningEngine`، الذاكرة، والأدوات.
3.  **الاستجابة:** يرسل العميل الذكي النتائج أو التقدم المحرز إلى `Supervisor Agent` عبر نفس الواجهة.
4.  **التجميع:** يقوم `Supervisor Agent` بتجميع الاستجابات من العملاء المختلفين وتنسيقها.

### 5.2 بروتوكول الاتصال متعدد العملاء (Multi-Agent Communication Protocol)

لضمان التواصل الفعال والآمن بين `Supervisor Agent` والعملاء الذكيين، سيتم استخدام بروتوكول اتصال موحد يعتمد على الرسائل غير المتزامنة (Asynchronous Messaging) عبر قائمة انتظار رسائل (Message Queue) مثل Kafka أو RabbitMQ. هذا يضمن:
-   **المرونة:** فصل المرسل عن المستقبل.
-   **قابلية التوسع:** سهولة إضافة المزيد من العملاء أو `Supervisor Agents`.
-   **الموثوقية:** ضمان تسليم الرسائل حتى في حالة تعطل أحد المكونات.

**هيكل الرسالة (Message Structure):**
ستتبع الرسائل تنسيق JSON موحد يتضمن:
-   `message_id`: معرف فريد للرسالة.
-   `sender_id`: معرف العميل المرسل.
-   `receiver_id`: معرف العميل المستهدف (أو `broadcast`).
-   `message_type`: نوع الرسالة (مثال: `TaskRequest`, `TaskResponse`, `StatusUpdate`).
-   `payload`: الحمولة الفعلية للرسالة (بيانات المهمة، النتائج، الأخطاء).
-   `timestamp`: وقت إرسال الرسالة.
-   `signature`: توقيع رقمي لضمان سلامة الرسالة ومصدرها.

### 5.3 دورة تنفيذ المهام (Task Execution Flow)

1.  **استلام المهمة:** `BaseAgent` يستقبل مهمة من `Supervisor Agent`.
2.  **تحليل المهمة:** `ReasoningEngine` يحلل المهمة، ويحدد الأهداف الفرعية والإجراءات المطلوبة.
3.  **استرجاع السياق:** `MemoryManager` يسترجع المعلومات ذات الصلة من الذاكرة قصيرة وطويلة المدى.
4.  **التفكير (Reasoning):** `ReasoningEngine` يستخدم LLM (عبر `LLMInterface`) لتوليد خطة عمل، أو تحديد الأداة المناسبة للاستدعاء، أو صياغة استجابة.
5.  **تنفيذ الأداة (Tool Execution):** إذا تطلب الأمر، يقوم `ToolExecutor` باستدعاء الأداة المحددة، ويتم تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
6.  **تحديث الذاكرة:** يتم تحديث الذاكرة بالنتائج الجديدة أو التغييرات في الحالة.
7.  **تكرار أو إنهاء:** تتكرر الخطوات 2-6 حتى تكتمل المهمة أو يتم الوصول إلى استجابة نهائية.
8.  **إرسال الاستجابة:** يرسل `BaseAgent` الاستجابة النهائية إلى `Supervisor Agent`.

## 6. إدارة الحالة والذاكرة (State and Memory Management)

### 6.1 إدارة الحالة (State Management)
يحتفظ `BaseAgent` بحالة داخلية لكل مهمة قيد التنفيذ. تتضمن هذه الحالة:
-   **معرف المهمة (Task ID):** لتتبع المهام المتعددة.
-   **حالة المهمة (Task Status):** (قيد التنفيذ، مكتملة، فاشلة، معلقة).
-   **الخطوات المنفذة (Executed Steps):** سجل بالخطوات التي تم اتخاذها.
-   **المدخلات والمخرجات الحالية (Current Inputs/Outputs):** البيانات التي يتم معالجتها.
-   **الموارد المستخدمة (Used Resources):** الأدوات أو نماذج LLM المستدعاة.

يتم تحديث الحالة بشكل مستمر بواسطة `ReasoningEngine` ويتم حفظها في الذاكرة قصيرة المدى.

### 6.2 نظام الذاكرة قصيرة المدى (Short-Term Memory)
-   **الغرض:** تخزين السياق الحالي للمهمة، المحادثات الجارية، والنتائج الوسيطة.
-   **الآلية:** يتم استخدام هياكل بيانات داخلية (مثل القواميس أو الكائنات) لتخزين المعلومات في الذاكرة العاملة للعميل الذكي. يمكن أن تكون هذه الذاكرة عابرة (in-memory) أو مخزنة مؤقتاً في قاعدة بيانات سريعة (مثل Redis) للمهام الأطول.
-   **إدارة السياق (Context Management):** يتم تجميع السياق ذي الصلة من الذاكرة قصيرة المدى وتقديمه إلى LLM كجزء من الـ Prompt. يتم تطبيق تقنيات ضغط السياق (Context Compression) عند الضرورة للحفاظ على حجم الـ Prompt ضمن حدود LLM.

### 6.3 نظام الذاكرة طويلة المدى (Long-Term Memory)
-   **الغرض:** تخزين المعرفة الدائمة، الدروس المستفادة، التفضيلات، والبيانات التاريخية التي يحتاجها العميل الذكي عبر جلسات متعددة أو مهام مختلفة.
-   **الآلية:** يتم استخدام قواعد بيانات متخصصة (مثل Vector Databases لتخزين التضمينات الدلالية، أو قواعد بيانات علائقية/NoSQL لتخزين البيانات المنظمة) لتخزين الذاكرة طويلة المدى. يتم استرجاع المعلومات باستخدام تقنيات البحث الدلالي (Semantic Search) أو الاستعلامات التقليدية.

### 6.4 إدارة نافذة السياق (Context Window Management)

لتحسين كفاءة استخدام نماذج LLM والتحكم في التكلفة، سيتم تطبيق استراتيجيات لإدارة نافذة السياق:
-   **التقطيع (Chunking):** تقسيم النصوص الطويلة إلى أجزاء أصغر.
-   **التلخيص (Summarization):** تلخيص الأجزاء الأقل أهمية من السياق.
-   **الاسترجاع الانتقائي (Selective Retrieval):** استرجاع الأجزاء الأكثر صلة فقط من الذاكرة طويلة المدى.
-   **الضغط (Compression):** استخدام تقنيات ضغط السياق لتقليل عدد الرموز (tokens) المرسلة إلى LLM.

### 6.5 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 6.6 استراتيجية ضغط الذاكرة (Memory Compression Strategy)

لتحسين كفاءة الذاكرة طويلة المدى وتقليل تكاليف التخزين والاسترجاع، سيتم تطبيق استراتيجيات ضغط الذاكرة:
-   **التضمين الدلالي (Semantic Embedding):** تحويل النصوص إلى متجهات (vectors) لتقليل حجم التخزين وتمكين البحث الدلالي.
-   **التلخيص الدوري (Periodic Summarization):** تلخيص المحادثات أو الأحداث التاريخية بشكل دوري وتخزين الملخصات بدلاً من النصوص الكاملة.
-   **إزالة البيانات القديمة/غير ذات الصلة (Pruning):** حذف البيانات التي تجاوزت فترة صلاحيتها أو التي لم تعد ذات صلة.

## 7. نظام التفكير والاستدلال (Reasoning Pipeline)

`ReasoningEngine` هو قلب `BaseAgent`، وهو المسؤول عن توجيه سلوك العميل الذكي. يتبع هذا النظام عادةً نمط "التفكير/العمل" (Think/Act) أو "التخطيط/التنفيذ" (Plan/Execute).

### 7.1 مراحل التفكير (Reasoning Stages)
1.  **فهم المهمة (Task Understanding):** تحليل الطلب الوارد وتحديد النية والأهداف الرئيسية.
2.  **توليد الخطة (Plan Generation):** استخدام LLM لتوليد خطة عمل خطوة بخطوة لتحقيق الأهداف، مع الأخذ في الاعتبار السياق والذاكرة والأدوات المتاحة.
3.  **اختيار الأداة (Tool Selection): و**تحديد الأداة الأنسب لتنفيذ الخطوة الحالية من الخطة.
4.  **توليد المدخلات للأداة (Tool Input Generation):** صياغة المدخلات اللازمة للأداة المختارة بناءً على السياق.
5.  **تحليل المخرجات (Output Analysis):** تقييم مخرجات الأداة أو استجابة LLM وتحديد الخطوة التالية.
6.  **تحديث الحالة والذاكرة (State & Memory Update):** تسجيل التقدم المحرز وتحديث الذاكرة.

### 7.2 آلية اتخاذ القرار (Decision-Making Mechanism)
تعتمد آلية اتخاذ القرار على مزيج من:
-   **نماذج LLM:** لتوليد الأفكار، الخطط، واختيار الأدوات بناءً على الـ Prompts المصممة بعناية.
-   **المنطق البرمجي (Programmatic Logic):** قواعد محددة مسبقاً للتعامل مع السيناريوهات الشائعة أو الحالات الحرجة.
-   **الذاكرة:** استخدام المعلومات المخزنة لتوجيه القرارات.

## 8. نظام استدعاء الأدوات (Tool Calling Framework)

`ToolExecutor` هو الوحدة المسؤولة عن إدارة واستدعاء الأدوات الخارجية التي يمكن للعميل الذكي استخدامها.

### 8.1 كيفية استخدام الأدوات (How Tools are Used)
1.  **تعريف الأداة:** يتم تعريف الأدوات بوضوح (اسم، وصف، معلمات المدخلات، نوع المخرجات) ليتمكن LLM من فهمها واستدعائها بشكل صحيح.
2.  **اختيار الأداة:** يقوم `ReasoningEngine` (بمساعدة LLM) باختيار الأداة المناسبة بناءً على المهمة الحالية.
3.  **تنفيذ الأداة:** يقوم `ToolExecutor` باستدعاء الأداة الفعلية، مع تمرير المدخلات التي تم توليدها بواسطة `ReasoningEngine`.
4.  **معالجة المخرجات:** يتم استقبال مخرجات الأداة وتحليلها بواسطة `ReasoningEngine` لمواصلة دورة التفكير.

### 8.2 إدارة الأدوات (Tool Management)
-   **اكتشاف الأدوات (Tool Discovery):** آلية لتسجيل واكتشاف الأدوات المتاحة للعميل الذكي.
-   **التحقق من صحة الأدوات (Tool Validation):** التأكد من أن الأدوات تعمل بشكل صحيح وأن معلمات المدخلات والمخرجات متوافقة.
-   **عزل الأدوات (Tool Isolation):** تشغيل الأدوات في بيئات معزولة لتقليل المخاطر الأمنية وتأثير الأخطاء.

### 8.3 نظام Plugins والتوسعة المستقبلية (Plugins and Future Extensibility)
يدعم `BaseAgent` نظام إضافات (Plugins) يسمح بتوسيع وظائفه ديناميكياً دون الحاجة لتعديل الكود الأساسي. يمكن للإضافات توفير أدوات جديدة، تعديل سلوك التفكير، أو إضافة قدرات ذاكرة جديدة.

### 8.4 تدفق استدعاء الأدوات (Tool Invocation Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ToolExecutor: { shape: rectangle; label: "Tool Executor" }
ToolRegistry: { shape: rectangle; label: "Tool Registry" }
ExternalTool: { shape: cloud; label: "أداة خارجية (API/Service)" }

BaseAgent -> ReasoningEngine: "طلب تنفيذ مهمة"
ReasoningEngine -> ToolRegistry: "يستعلم عن الأدوات المتاحة"
ToolRegistry --> ReasoningEngine: "قائمة الأدوات"
ReasoningEngine -> ReasoningEngine: "يختار الأداة المناسبة"
ReasoningEngine -> ToolExecutor: "يطلب تنفيذ الأداة (Tool, Input)"
ToolExecutor -> ExternalTool: "يستدعي الأداة الفعلية"
ExternalTool --> ToolExecutor: "مخرجات الأداة"
ToolExecutor --> ReasoningEngine: "نتائج الأداة"
ReasoningEngine --> BaseAgent: "نتائج المعالجة"
```

### 8.5 معمارية الإضافات (Plugin Architecture)

تعتمد معمارية الإضافات على مبدأ التحميل الديناميكي (Dynamic Loading) والفصل بين الإضافات والمنطق الأساسي. كل إضافة ستكون عبارة عن وحدة برمجية مستقلة (مثل حزمة Python) تلتزم بواجهة محددة (Plugin Interface). هذا يسمح بـ:
-   **التوسعة السهلة:** إضافة وظائف جديدة دون تعديل `BaseAgent`.
-   **العزل:** فشل إضافة لا يؤثر على عمل `BaseAgent` الأساسي.
-   **إدارة الإصدارات:** يمكن تحديث الإضافات بشكل مستقل.

## 9. طبقة الاتصال بنماذج الذكاء الاصطناعي (LLM Abstraction Layer)

### 9.1 الغرض (Purpose)
توفر هذه الطبقة واجهة موحدة للعملاء الذكيين للتفاعل مع نماذج الذكاء الاصطناعي الكبيرة (LLMs) المختلفة، بغض النظر عن المزود (مثل OpenAI, Gemini) أو النموذج المحدد. هذا يضمن المرونة، سهولة التبديل بين النماذج، وعزل منطق العميل الذكي عن تفاصيل API الخاصة بكل LLM.

### 9.2 المكونات (Components)
-   **LLM Provider Interface:** واجهة عامة تحدد طرق الاتصال الأساسية (مثل `generate_response`, `embed_text`).
-   **Concrete LLM Adapters:** تطبيقات محددة لـ `LLM Provider Interface` لكل مزود LLM (مثال: `OpenAIAdapter`, `GeminiAdapter`).
-   **Prompt Manager:** وحدة مسؤولة عن صياغة الـ Prompts، إدارة القوالب، وضغط السياق قبل إرسالها إلى LLM.

### 9.3 استراتيجية توجيه النماذج (Model Routing Strategy)

لتحسين الأداء والتكلفة، سيتم تطبيق استراتيجية توجيه ذكية للنماذج:
-   **التوجيه بناءً على المهمة:** توجيه المهام المختلفة إلى نماذج LLM الأنسب (مثال: نموذج سريع ورخيص للمهام البسيطة، نموذج قوي ومكلف للمهام الحرجة فقط).
-   **التوجيه بناءً على التكلفة/الأداء:** اختيار النموذج بناءً على التوازن بين التكلفة والأداء المطلوب.
-   **التوجيه بناءً على التوفر:** التبديل التلقائي بين المزودين في حالة عدم توفر نموذج معين.

### 9.4 استراتيجية ميزانية الرموز (Token Budget Strategy)

سيتم تحديد ميزانية قصوى للرموز (tokens) لكل تفاعل مع LLM. عند تجاوز هذه الميزانية، سيتم تطبيق استراتيجيات لتقليل حجم الـ Prompt، مثل:
-   **إزالة المعلومات الأقل أهمية:** تحديد أولويات المعلومات بناءً على أهميتها للمهمة الحالية.
-   **الضغط التلخيصي:** تلخيص أجزاء كبيرة من المحادثة أو الوثائق.
-   **التقطيع الديناميكي:** تعديل حجم الأجزاء المرسلة إلى LLM.

### 9.5 استراتيجية إصدار الـ Prompt (Prompt Versioning Strategy)

لإدارة تطور الـ Prompts وضمان إمكانية التتبع والتحكم، سيتم تطبيق استراتيجية لإصدار الـ Prompts:
-   **التخزين المركزي:** تخزين جميع الـ Prompts في مستودع مركزي (مثل نظام التحكم في الإصدارات Git أو قاعدة بيانات).
-   **الإصدارات (Versioning):** تعيين رقم إصدار لكل Prompt، مما يسمح بالعودة إلى إصدارات سابقة وتتبع التغييرات.
-   **الاختبار A/B:** إمكانية اختبار إصدارات مختلفة من الـ Prompts لتقييم فعاليتها.

## 10. إدارة الأخطاء وإعادة المحاولة (Error Handling and Retry)

### 10.1 آليات اكتشاف الأخطاء (Error Detection Mechanisms)
-   **التحقق من صحة المدخلات (Input Validation):** التحقق من صحة المدخلات قبل معالجتها.
-   **مراقبة استجابات الأدوات و LLM:** تحليل استجابات الأدوات ونماذج LLM لاكتشاف الأخطاء أو الاستجابات غير المتوقعة.
-   **الاستثناءات (Exceptions):** استخدام آليات الاستثناءات القياسية في البرمجة.

### 10.2 استراتيجيات إعادة المحاولة (Retry Strategies)
-   **إعادة المحاولة الأسية (Exponential Backoff):** إعادة محاولة العمليات الفاشلة مع زيادة زمن الانتظار بين المحاولات.
-   **الحد الأقصى للمحاولات (Max Retries):** تحديد عدد أقصى للمحاولات قبل الإبلاغ عن فشل دائم.

### 10.3 التعافي من الأخطاء (Error Recovery)
-   **العودة إلى حالة سابقة (Rollback):** التراجع عن التغييرات التي تمت قبل حدوث الخطأ.
-   **الإبلاغ عن الخطأ (Error Reporting):** إرسال تفاصيل الخطأ إلى `Supervisor Agent` أو نظام المراقبة.
-   **التعامل مع الأخطاء المعروفة (Known Error Handling):** وجود منطق محدد للتعامل مع أنواع معينة من الأخطاء.

### 10.4 تدفق التعافي من الأخطاء (Error Recovery Flow)

```d2
direction: right

BaseAgent: { shape: rectangle; label: "BaseAgent" }
ReasoningEngine: { shape: rectangle; label: "Reasoning Engine" }
ErrorHandler: { shape: rectangle; label: "Error Handler" }
Logger: { shape: rectangle; label: "Logger" }

BaseAgent -> ReasoningEngine: "تنفيذ مهمة"
ReasoningEngine -> ErrorHandler: "يحدث خطأ"
ErrorHandler -> Logger: "يسجل الخطأ"
Logger --> ErrorHandler: "تم التسجيل"
ErrorHandler -> ErrorHandler: "يحدد استراتيجية التعافي (إعادة محاولة/تراجع)"
ErrorHandler --> ReasoningEngine: "إجراء التعافي"
ReasoningEngine --> BaseAgent: "يستأنف/يفشل المهمة"
```

## 11. نظام التسجيل والمراقبة (Logging and Monitoring)

### 11.1 التسجيل (Logging)
-   **مستويات التسجيل:** دعم مستويات تسجيل مختلفة (DEBUG, INFO, WARNING, ERROR, CRITICAL).
-   **تنسيق السجلات:** تنسيق موحد للسجلات يسهل التحليل (JSON).
-   **محتوى السجلات:** تسجيل تفاصيل المهمة، خطوات التفكير، استدعاءات الأدوات، استجابات LLM، والأخطاء.
-   **تخزين السجلات:** تخزين السجلات في نظام مركزي (مثل ELK Stack) للتحليل والمراجعة.

### 11.2 المراقبة (Monitoring)
-   **المقاييس (Metrics):** جمع مقاييس الأداء (مثل زمن الاستجابة، معدل النجاح/الفشل، استخدام الموارد).
-   **لوحات المعلومات (Dashboards):** توفير لوحات معلومات لمراقبة صحة وأداء العملاء الذكيين في الوقت الفعلي.
-   **التنبيهات (Alerts):** إعداد تنبيهات عند تجاوز المقاييس لحدود معينة أو عند حدوث أخطاء حرجة.

### 11.3 معمارية الملاحظة (Observability Architecture)

لضمان رؤية عميقة لأداء وسلوك العملاء الذكيين، سيتم تطبيق معمارية ملاحظة شاملة تتضمن:
-   **التسجيل المنظم (Structured Logging):** استخدام تنسيق JSON للسجلات لسهولة التحليل الآلي.
-   **المقاييس (Metrics):** جمع مقاييس الأداء والتشغيل (CPU, Memory, Latency, Error Rates) باستخدام أدوات مثل Prometheus.
-   **التتبع الموزع (Distributed Tracing):** تتبع مسار الطلب عبر العملاء الذكيين والخدمات المختلفة باستخدام أدوات مثل Jaeger أو OpenTelemetry.

### 11.4 تصميم القياس عن بعد (Telemetry Design)

سيتم تصميم نظام القياس عن بعد لجمع البيانات التشغيلية الهامة من `BaseAgent` والعملاء الذكيين المشتقين منه. يتضمن ذلك:
-   **بيانات الأداء:** زمن تنفيذ المهام، زمن استجابة LLM، زمن استدعاء الأدوات.
-   **بيانات الاستخدام:** عدد استدعاءات LLM، عدد استدعاءات الأدوات، عدد الرموز المستخدمة.
-   **بيانات الأخطاء:** أنواع الأخطاء، تكرارها، وسياق حدوثها.
-   **بيانات الموارد:** استخدام CPU، الذاكرة، والشبكة.

## 12. نظام الصلاحيات والأمان (Authorization and Security System)

### 12.1 مبادئ الأمان (Security Principles)
-   **الامتياز الأقل (Least Privilege):** يجب أن يمتلك كل عميل ذكي الحد الأدنى من الصلاحيات اللازمة لأداء وظيفته.
-   **عزل الموارد (Resource Isolation):** عزل موارد العملاء الذكيين عن بعضها البعض.
-   **التشفير (Encryption):** تشفير البيانات الحساسة أثناء النقل وفي وضع السكون.
-   **التحقق من صحة المدخلات (Input Validation):** حماية ضد حقن الـ Prompts (Prompt Injection) وغيرها من الهجمات.

### 12.2 آليات الصلاحيات (Authorization Mechanisms)
-   **رموز الوصول (Access Tokens):** استخدام رموز وصول مؤقتة ومحدودة الصلاحية للوصول إلى الأدوات الخارجية أو الخدمات.
-   **التحكم في الوصول المستند إلى الدور (Role-Based Access Control - RBAC):** تحديد الصلاحيات بناءً على دور العميل الذكي.

### 12.3 نموذج التهديد الأمني (Security Threat Model)

سيتم تطوير نموذج تهديد أمني شامل لتحديد وتحليل وتخفيف المخاطر الأمنية المحتملة لـ `BaseAgent` والمنصة ككل. سيتضمن ذلك:
-   **تحديد الأصول:** البيانات الحساسة، الوظائف الحيوية، واجهات برمجة التطبيقات.
-   **تحديد التهديدات:** هجمات حقن الـ Prompt، الوصول غير المصرح به، تسرب البيانات، هجمات حجب الخدمة (DoS).
-   **تحديد نقاط الضعف:** أخطاء في الكود، تكوينات خاطئة، نقاط ضعف في المكتبات الخارجية.
-   **تحديد الضوابط:** آليات المصادقة، التشفير، التحقق من صحة المدخلات، المراقبة الأمنية.

## 13. معايير كتابة الكود الخاصة بـ BaseAgent (BaseAgent Coding Standards)

بالإضافة إلى معايير كتابة الكود العامة للمشروع، يجب أن يلتزم كود `BaseAgent` بالمبادئ التالية:
-   **قابلية التوسع (Extensibility):** تصميم الوحدات بطريقة تسمح بإضافة وظائف جديدة بسهولة دون تعديل الكود الحالي (مبدأ Open/Closed).
-   **قابلية الاختبار (Testability):** تصميم الوحدات لتكون سهلة الاختبار بشكل منفصل.
-   **النمطية (Modularity):** تقسيم الكود إلى وحدات صغيرة ومستقلة ذات مسؤوليات واضحة.
-   **الوثوقية (Reliability):** التعامل مع الحالات الاستثنائية والأخطاء بشكل رشيد.
-   **الوضوح (Clarity):** كود نظيف، مقروء، وموثق جيداً.

## 14. استراتيجية الاختبارات (Testing Strategy)

تتبع استراتيجية الاختبارات لـ `BaseAgent` نهجاً شاملاً لضمان الجودة والموثوقية:

-   **اختبارات الوحدات (Unit Tests):** اختبار كل وحدة (Module) أو وظيفة بشكل منفصل لضمان عملها الصحيح.
-   **اختبارات التكامل (Integration Tests):** اختبار تفاعل الوحدات المختلفة مع بعضها البعض ومع الخدمات الخارجية (مثل LLMs، قواعد البيانات).
-   **اختبارات الأداء (Performance Tests):** تقييم أداء `BaseAgent` تحت أحمال مختلفة.
-   **اختبارات الأمان (Security Tests):** التحقق من مقاومة `BaseAgent` للهجمات الأمنية.
-   **اختبارات السلوك (Behavioral Tests):** التأكد من أن `BaseAgent` يتصرف كما هو متوقع في سيناريوهات مختلفة، خاصة فيما يتعلق بالتفكير واستدعاء الأدوات.

## 15. استراتيجيات التشغيل والأداء (Operational and Performance Strategies)

### 15.1 قابلية التوسع (Scalability Strategy)

لضمان قدرة المنصة على التعامل مع زيادة الحمل وعدد العملاء الذكيين، سيتم تطبيق استراتيجيات قابلية التوسع التالية:
-   **التوسع الأفقي (Horizontal Scaling):** القدرة على إضافة المزيد من مثيلات `BaseAgent` و `Supervisor Agent` بشكل ديناميكي.
-   **الخدمات المصغرة (Microservices):** تقسيم المنصة إلى خدمات صغيرة مستقلة يمكن توسيعها بشكل فردي.
-   **الحوسبة بدون خادم (Serverless Computing):** استخدام وظائف بدون خادم (مثل AWS Lambda, Azure Functions) للمهام التي تتطلب توسعاً مرناً.
-   **قوائم انتظار الرسائل (Message Queues):** استخدام قوائم انتظار الرسائل لفصل المكونات وتمكين المعالجة غير المتزامنة.

### 15.2 التوافرية العالية (High Availability Strategy)

لضمان استمرارية الخدمة وتقليل وقت التوقف، سيتم تطبيق استراتيجيات التوافرية العالية:
-   **التكرار (Redundancy):** تشغيل مثيلات متعددة من المكونات الحيوية في مناطق توفر مختلفة.
-   **موازنة التحميل (Load Balancing):** توزيع حركة المرور بين المثيلات المتعددة.
-   **الكشف التلقائي عن الفشل والتعافي (Automated Failure Detection and Recovery):** استخدام أدوات الأوركسترا (مثل Kubernetes) للكشف عن المكونات الفاشلة واستبدالها تلقائياً.
-   **النسخ الاحتياطي والاستعادة (Backup and Restore):** سياسات نسخ احتياطي منتظمة للبيانات والتكوينات مع خطط استعادة مجربة.

### 15.3 استراتيجية التعافي من الكوارث (Disaster Recovery Strategy)

لضمان استمرارية العمل في حالة وقوع كارثة كبرى، سيتم وضع خطة للتعافي من الكوارث تتضمن:
-   **النسخ المتماثل عبر المناطق (Cross-Region Replication):** نسخ البيانات والتطبيقات إلى مناطق جغرافية مختلفة.
-   **أهداف وقت الاسترداد (RTO) وأهداف نقطة الاسترداد (RPO):** تحديد الأهداف الزمنية والمقدار المسموح به لفقدان البيانات.
-   **اختبار التعافي من الكوارث (DR Drills):** إجراء اختبارات دورية لخطة التعافي من الكوارث لضمان فعاليتها.

### 15.4 معايير الأداء (Performance Benchmarks)

سيتم تحديد معايير أداء واضحة لكل مكون من مكونات `BaseAgent` والمنصة ككل، وسيتم قياسها بانتظام. تتضمن هذه المعايير:
-   **زمن الاستجابة (Latency):** زمن معالجة الطلب من البداية إلى النهاية.
-   **الإنتاجية (Throughput):** عدد الطلبات التي يمكن معالجتها في وحدة زمنية.
-   **استخدام الموارد (Resource Utilization):** استخدام CPU، الذاكرة، والشبكة.

### 15.5 تخطيط القدرة (Capacity Planning)

سيتم إجراء تخطيط دوري للقدرة لضمان توفر الموارد الكافية لدعم النمو المتوقع للمنصة. يتضمن ذلك:
-   **تحليل الاتجاهات:** تحليل بيانات الاستخدام والأداء التاريخية للتنبؤ بالاحتياجات المستقبلية.
-   **نمذجة الحمل (Load Modeling):** محاكاة أحمال العمل المستقبلية لتقييم متطلبات الموارد.
-   **توفير الموارد (Resource Provisioning):** تخصيص الموارد بشكل استباقي لتلبية الطلبات المتزايدة.

### 15.6 استراتيجية التخزين المؤقت (Caching Strategy)

لتحسين الأداء وتقليل الحمل على قواعد البيانات والخدمات الخارجية، سيتم تطبيق استراتيجيات التخزين المؤقت:
-   **التخزين المؤقت للبيانات (Data Caching):** تخزين البيانات المستخدمة بشكل متكرر في ذاكرة التخزين المؤقت (مثل Redis, Memcached).
-   **التخزين المؤقت للنتائج (Result Caching):** تخزين نتائج العمليات المعقدة أو المكلفة.
-   **إدارة انتهاء صلاحية ذاكرة التخزين المؤقت (Cache Invalidation):** آليات لضمان تحديث البيانات المخزنة مؤقتاً.

### 15.7 معمارية قوائم الانتظار (Queue Architecture)

ستستخدم المنصة قوائم انتظار الرسائل (Message Queues) بشكل مكثف لفصل المكونات، تمكين المعالجة غير المتزامنة، وتحسين قابلية التوسع والموثوقية. تتضمن المعمارية:
-   **قوائم انتظار المهام (Task Queues):** لتوجيه المهام إلى العملاء الذكيين.
-   **قوائم انتظار الأحداث (Event Queues):** لنشر الأحداث بين المكونات.
-   **قوائم انتظار الرسائل الميتة (Dead-Letter Queues - DLQ):** للتعامل مع الرسائل التي فشلت معالجتها.

### 15.8 سياسة إصدار واجهة برمجة التطبيقات (API Versioning Policy)

لإدارة تطور واجهات برمجة التطبيقات (APIs) وضمان التوافق مع الإصدارات السابقة، سيتم تطبيق سياسة إصدار واجهة برمجة التطبيقات:
-   **الإصدار في المسار (Path Versioning):** تضمين رقم الإصدار في مسار URL (مثال: `/api/v1/agent`).
-   **الإصدار في الرأس (Header Versioning):** تضمين رقم الإصدار في رأس HTTP (مثال: `X-API-Version: 1`).
-   **التوثيق الواضح:** توثيق جميع التغييرات في واجهات برمجة التطبيقات في سجل التغييرات (CHANGELOG) الخاص بالمشروع).

## 16. توثيق القرارات المعمارية (Architectural Decision Records - ADRs)

سيتم توثيق جميع القرارات المعمارية الهامة المتعلقة بـ `BaseAgent` في سجلات القرارات المعمارية (ADRs) لضمان الشفافية، المساءلة، وتوفير سياق تاريخي للقرارات. كل ADR سيحتوي على:
-   **العنوان:** وصف موجز للقرار.
-   **التاريخ:** تاريخ اتخاذ القرار.
-   **الحالة:** (مقترح، مقبول، مرفوض، منتهي).
-   **السياق:** المشكلة التي يحاول القرار حلها.
-   **القرار:** الحل المختار.
-   **الاعتبارات:** البدائل التي تم النظر فيها ومزايا وعيوب كل منها.
-   **الآثار:** تأثير القرار على النظام.

سيتم تخزين ADRs في المجلد `الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/`.

## 17. المراجع (References)
- ميثاق منصة بصيرة. (`ميثاق_منصة_بصيرة.md`)
- مواصفات متطلبات البرمجيات (SRS) - منصة بصيرة. (`الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md`)
- سجل قرار معماري 0001: اعتماد معمارية Hub-and-Spoke للعملاء الذكيين. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0001-hub-and-spoke-architecture.md`)
- سجل قرار معماري 0002: تصميم معمارية BaseAgent الأساسية لمنصة بصيرة. (`الوثائق_الرئيسية/الحوكمة_والقرارات/سجلات_القرارات_المعمارية/0002-baseagent-architectural-design.md`)
