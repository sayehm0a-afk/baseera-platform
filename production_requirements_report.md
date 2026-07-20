# تقرير متطلبات التشغيل الفعلية لمشروع Basirah

**التاريخ:** 18 يوليو 2026
**المؤلف:** Manus AI

---

## ملخص

يحدد هذا التقرير جميع المتطلبات التشغيلية الفعلية لمشروع Basirah، وهو منصة ذكاء اصطناعي لتحليل السوق المالي السعودي. الهدف هو توفير قائمة شاملة بالتبعيات والتكوينات اللازمة للنشر في بيئة إنتاج حقيقية.

---

## 1. متطلبات Python

- **إصدار Python:** `3.11` (محدد في `Dockerfile`)
- **الحزم (Packages):** مدرجة في `requirements.txt`
  - `python-dotenv>=1.0.0`
  - `pydantic>=2.0.0`
  - `pydantic-settings>=2.0.0`
  - `openai>=1.0.0`
  - `langchain>=0.2.0`
  - `langchain-openai>=0.1.0`
  - `pandas>=2.0.0`
  - `numpy>=1.26.0`
  - `fastapi>=0.110.0`
  - `uvicorn[standard]>=0.27.0`
  - `sqlalchemy>=2.0.0`
  - `asyncpg>=0.29.0`
  - `alembic>=1.13.0`
  - `pytest>=8.0.0` (للاختبارات)
  - `pytest-asyncio>=0.23.0` (للاختبارات)
  - `pytest-cov>=5.0.0` (للاختبارات)
  - `black>=24.0.0` (لجودة الكود)
  - `flake8>=7.0.0` (لجودة الكود)
  - `isort>=5.13.0` (لجودة الكود)
  - `mypy>=1.9.0` (لجودة الكود)

---

## 2. متغيرات البيئة (Environment Variables)

| المتغير | الوصف | الافتراضي (إذا وجد) | الاستخدام |
|---------|--------|---------------------|-----------|
| `DATABASE_URL` | عنوان URL لاتصال قاعدة بيانات PostgreSQL | `postgresql://postgres:postgres@localhost:5432/basirah` | `src/core/db/database.py` |
| `OPENAI_API_KEY` | مفتاح API لخدمة OpenAI | لا يوجد | `src/core/llm_abstraction/openai_llm_client.py` |
| `REDIS_HOST` | اسم مضيف خادم Redis | `localhost` | `src/core/runtime/task_queue/real_task_queue.py`, `src/core/messaging/redis_message_bus.py`, `src/core/runtime/dependency_injection.py` |
| `REDIS_PORT` | منفذ خادم Redis | `6379` | `src/core/runtime/task_queue/real_task_queue.py`, `src/core/messaging/redis_message_bus.py`, `src/core/runtime/dependency_injection.py` |
| `REDIS_PASSWORD` | كلمة مرور خادم Redis | لا يوجد | `src/core/messaging/redis_message_bus.py` |

---

## 3. متطلبات PostgreSQL

- **النوع:** قاعدة بيانات علائقية (Relational Database)
- **الإصدار الموصى به:** PostgreSQL 13 أو أحدث
- **المتطلبات:**
  - قاعدة بيانات باسم `basirah` (أو ما يحدده `DATABASE_URL`)
  - مستخدم `postgres` (أو ما يحدده `DATABASE_URL`)
  - كلمة مرور `postgres` (أو ما يحدده `DATABASE_URL`)
  - تجميع الاتصالات (Connection Pooling) مطلوب للأداء
  - دعم الترحيلات (Migrations) عبر Alembic
- **الوصول:** يجب أن يكون متاحًا من التطبيق عبر المنفذ الافتراضي `5432`

---

## 4. متطلبات Redis

- **النوع:** مخزن بيانات في الذاكرة (In-memory Data Store) ووسيط رسائل (Message Broker)
- **الإصدار الموصى به:** Redis 6 أو أحدث
- **المتطلبات:**
  - تشغيل خادم Redis
  - كلمة مرور (اختياري، ولكن موصى به للإنتاج)
  - تجميع الاتصالات (Connection Pooling) مطلوب للأداء
- **الوصول:** يجب أن يكون متاحًا من التطبيق عبر المنفذ الافتراضي `6379`

---

## 5. متطلبات Docker

- **الإصدار الموصى به:** Docker Engine 20.10 أو أحدث
- **المتطلبات:**
  - Docker Engine مثبت على الخادم
  - Docker Compose مثبت على الخادم (للبيئات غير Kubernetes)
  - بناء صور Docker بنجاح من `Dockerfile`
  - تشغيل الحاويات بنجاح من `docker-compose.yml`

---

## 6. متطلبات Kubernetes

- **الإصدار الموصى به:** Kubernetes 1.20 أو أحدث
- **المتطلبات:**
  - مجموعة Kubernetes عاملة (Working Kubernetes Cluster)
  - `kubectl` مثبت ومكون للوصول إلى المجموعة
  - القدرة على نشر `app-deployment.yaml` و `db-deployment.yaml`
  - القدرة على إنشاء `app-service.yaml` و `db-service.yaml`
  - القدرة على إنشاء `postgres-pv-claim.yaml` و `openai-secret.yaml` و `environment.yaml`
  - دعم Persistent Volumes (لـ PostgreSQL)
  - دعم Secrets (لـ OpenAI API Key)
  - دعم ConfigMaps (لمتغيرات البيئة العامة)

---

## 7. متطلبات OpenAI

- **الخدمة:** OpenAI API
- **المتطلبات:**
  - مفتاح API صالح (يتم توفيره عبر `OPENAI_API_KEY`)
  - الوصول إلى نماذج اللغة الكبيرة (LLMs) المدعومة من OpenAI
- **الوصول:** يتطلب اتصالاً بالإنترنت للوصول إلى نقاط نهاية OpenAI API

---

## 8. متطلبات بيانات السوق (Market Data Requirements)

- **الخدمة:** مزود بيانات السوق السعودي (غير محدد حاليًا في الكود)
- **المتطلبات:**
  - نقطة نهاية API لمزود بيانات السوق
  - مفتاح API أو بيانات اعتماد للمصادقة (إذا لزم الأمر)
  - القدرة على جلب بيانات الأسهم والمؤشرات المالية السعودية
- **الوصول:** يتطلب اتصالاً بالإنترنت للوصول إلى مزود بيانات السوق

---

## 9. واجهات برمجة التطبيقات الخارجية (External APIs)

- **OpenAI API:** (مذكور أعلاه)
- **مزود بيانات السوق:** (مذكور أعلاه)
- **أخرى:** لا توجد واجهات برمجة تطبيقات خارجية أخرى محددة حاليًا في الكود.

---

## 10. الأسرار المطلوبة (Required Secrets)

- `OPENAI_API_KEY`: مفتاح API لـ OpenAI (يجب تخزينه بشكل آمن، مثل Kubernetes Secret أو HashiCorp Vault)
- `DATABASE_URL`: قد يحتوي على بيانات اعتماد حساسة لقاعدة البيانات (يجب تخزينه بشكل آمن)
- `REDIS_PASSWORD`: كلمة مرور Redis (إذا تم تكوينها، يجب تخزينها بشكل آمن)

---

## 11. المنافذ (Ports)

- **8000:** منفذ التطبيق الرئيسي (FastAPI/Uvicorn) - مكشوف (Exposed)
- **5432:** منفذ PostgreSQL - داخلي (Internal) أو مكشوف حسب التكوين
- **6379:** منفذ Redis - داخلي (Internal) أو مكشوف حسب التكوين

---

## 12. الأحجام (Volumes)

- **PostgreSQL Data Volume:** مطلوب لتخزين بيانات PostgreSQL بشكل دائم (مثال: `postgres-pv-claim.yaml`)
- **Application Logs Volume:** موصى به لتخزين سجلات التطبيق بشكل دائم

---

## 13. متطلبات الشبكة (Network Requirements)

- **الاتصال الداخلي:**
  - يجب أن يكون التطبيق قادرًا على الاتصال بـ PostgreSQL على المنفذ `5432`
  - يجب أن يكون التطبيق قادرًا على الاتصال بـ Redis على المنفذ `6379`
- **الاتصال الخارجي:**
  - يجب أن يكون التطبيق قادرًا على الوصول إلى OpenAI API (HTTPS)
  - يجب أن يكون التطبيق قادرًا على الوصول إلى مزود بيانات السوق (HTTPS)
- **جدار الحماية (Firewall):** يجب تكوين جدار الحماية للسماح بالوصول إلى المنفذ `8000` للتطبيق، وتقييد الوصول إلى المنافذ الداخلية `5432` و `6379`.

---

## REQUIRED FROM PROJECT OWNER

1. **Market Data Provider API Key/Credentials:** بيانات اعتماد لمزود بيانات السوق السعودي الحقيقي.
2. **OpenAI API Key:** مفتاح API صالح لـ OpenAI (إذا لم يتم توفيره بالفعل عبر متغيرات البيئة).
3. **PostgreSQL Production Credentials:** بيانات اعتماد PostgreSQL للإنتاج (اسم المستخدم، كلمة المرور، اسم قاعدة البيانات) إذا كانت مختلفة عن الافتراضيات.
4. **Redis Production Credentials:** بيانات اعتماد Redis للإنتاج (كلمة المرور) إذا تم تكوينها.
5. **Kubernetes Cluster Access:** الوصول إلى مجموعة Kubernetes عاملة (إذا كان النشر سيتم على Kubernetes).
6. **Domain Name/SSL Certificate:** اسم النطاق وشهادة SSL (إذا كان التطبيق سيتم نشره على نطاق عام).
7. **Logging & Monitoring Solution:** تفاصيل حل التسجيل والمراقبة المفضل (مثل ELK Stack، Prometheus، Grafana) لتكامل السجلات والمقاييس.

---

**ملاحظة:** هذا التقرير يعتمد على تحليل الكود الحالي وملفات التكوين. قد تكون هناك متطلبات إضافية بناءً على بيئة النشر المحددة أو متطلبات العمل المستقبلية.
