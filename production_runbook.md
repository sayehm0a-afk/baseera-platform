# دليل تشغيل Basirah في الإنتاج

**التاريخ:** 18 يوليو 2026
**المؤلف:** Manus AI

---

## ملخص

يوفر هذا الدليل إرشادات خطوة بخطوة لتشغيل وصيانة واستكشاف أخطاء منصة Basirah في بيئة الإنتاج. يهدف إلى تمكين فرق العمليات من إدارة النظام بفعالية وضمان استمرارية الخدمة.

---

## 1. النشر الأولي (Initial Deployment)

### 1.1. المتطلبات المسبقة

-   بيئة Kubernetes عاملة (أو خادم Docker مع Docker Compose).
-   `kubectl` مثبت ومكون للوصول إلى مجموعة Kubernetes (إذا كان النشر على Kubernetes).
-   `docker` و `docker-compose` مثبتان (إذا كان النشر باستخدام Docker Compose).
-   بيانات اعتماد OpenAI API مشفرة بـ Base64.
-   بيانات اعتماد PostgreSQL و Redis للإنتاج.
-   نقطة نهاية API وبيانات اعتماد مزود بيانات السوق السعودي.

### 1.2. خطوات النشر (Kubernetes)

1.  **تكوين الأسرار (Secrets):**
    -   تعديل `kubernetes/openai-secret.yaml` بقيمة `OPENAI_API_KEY` المشفرة بـ Base64.
    -   تعديل `kubernetes/environment.yaml` بـ `REDIS_HOST` و `REDIS_PORT` و `DATABASE_URL` (إذا لم يتم تحديثها بالفعل).
    -   تطبيق الأسرار والتكوينات:
        ```bash
        kubectl apply -f kubernetes/openai-secret.yaml
        kubectl apply -f kubernetes/environment.yaml
        ```

2.  **نشر قاعدة البيانات (PostgreSQL):**
    -   تطبيق Persistent Volume Claim (مطالبة وحدة التخزين الدائمة):
        ```bash
        kubectl apply -f kubernetes/postgres-pv-claim.yaml
        ```
    -   نشر قاعدة البيانات:
        ```bash
        kubectl apply -f kubernetes/db-deployment.yaml
        kubectl apply -f kubernetes/db-service.yaml
        ```
    -   التحقق من حالة قاعدة البيانات:
        ```bash
        kubectl get pods -l app=basirah,component=db
        kubectl logs -f <basirah-db-pod-name>
        ```

3.  **نشر التطبيق (Basirah App):**
    -   تطبيق نشر التطبيق:
        ```bash
        kubectl apply -f kubernetes/app-deployment.yaml
        kubectl apply -f kubernetes/app-service.yaml
        ```
    -   التحقق من حالة التطبيق:
        ```bash
        kubectl get pods -l app=basirah,component=app
        kubectl logs -f <basirah-app-pod-name>
        ```

4.  **تطبيق الترحيلات (Migrations):**
    -   بمجرد تشغيل التطبيق وقاعدة البيانات، يجب تطبيق ترحيلات قاعدة البيانات. يمكن القيام بذلك عن طريق تشغيل أمر `alembic upgrade head` داخل حاوية التطبيق:
        ```bash
        kubectl exec -it <basirah-app-pod-name> -- alembic upgrade head
        ```

### 1.3. خطوات النشر (Docker Compose)

1.  **تكوين ملف `.env`:**
    -   إنشاء ملف `.env` في جذر المشروع يحتوي على:
        ```
        DATABASE_URL="postgresql+asyncpg://user:password@db:5432/basirah_db"
        OPENAI_API_KEY="your_openai_api_key"
        REDIS_HOST="redis"
        REDIS_PORT="6379"
        REDIS_PASSWORD="your_redis_password" # إذا كان Redis يتطلب كلمة مرور
        POSTGRES_USER="user"
        POSTGRES_PASSWORD="password"
        ```

2.  **بناء وتشغيل الخدمات:**
    ```bash
    docker-compose build
    docker-compose up -d
    ```

3.  **تطبيق الترحيلات (Migrations):**
    -   تشغيل أمر `alembic upgrade head` داخل حاوية التطبيق:
        ```bash
        docker-compose exec app alembic upgrade head
        ```

## 2. العمليات اليومية (Daily Operations)

### 2.1. مراقبة الصحة (Health Monitoring)

-   **نقطة نهاية فحص الصحة:** الوصول إلى نقطة نهاية `/health` للتطبيق للتحقق من حالته:
    ```bash
    curl http://<app-ip-or-hostname>/health
    ```
-   **سجلات التطبيق:** مراقبة سجلات التطبيق بحثًا عن الأخطاء أو التحذيرات:
    ```bash
    kubectl logs -f <basirah-app-pod-name>
    # أو لـ Docker Compose
    docker-compose logs -f app
    ```
-   **مقاييس البنية التحتية:** مراقبة استخدام CPU والذاكرة والشبكة للخوادم وقاعدة البيانات و Redis.

### 2.2. إدارة السجلات (Log Management)

-   يجب تجميع السجلات في نظام تسجيل مركزي (مثل ELK Stack أو Loki/Grafana) لتحليلها وتنبيهها.

### 2.3. النسخ الاحتياطي (Backup)

-   **PostgreSQL:** تنفيذ إجراءات النسخ الاحتياطي المحددة في خطة النشر.
-   **Redis:** التأكد من تكوين مثابرة Redis بشكل صحيح ومراقبة النسخ الاحتياطي.

## 3. استكشاف الأخطاء وإصلاحها (Troubleshooting)

### 3.1. التطبيق لا يستجيب

-   **التحقق من حالة Pod/Container:**
    ```bash
    kubectl get pods -l app=basirah,component=app
    docker-compose ps
    ```
-   **فحص السجلات:**
    ```bash
    kubectl logs -f <basirah-app-pod-name>
    docker-compose logs -f app
    ```
-   **التحقق من فحص الصحة:** الوصول إلى نقطة نهاية `/health`.

### 3.2. مشكلات قاعدة البيانات

-   **التحقق من حالة Pod/Container:**
    ```bash
    kubectl get pods -l app=basirah,component=db
    docker-compose ps
    ```
-   **فحص السجلات:**
    ```bash
    kubectl logs -f <basirah-db-pod-name>
    docker-compose logs -f db
    ```
-   **التحقق من الاتصال:** محاولة الاتصال بقاعدة البيانات من داخل حاوية التطبيق.

### 3.3. مشكلات Redis

-   **التحقق من حالة Pod/Container:**
    ```bash
    kubectl get pods -l app=basirah,component=redis # إذا كان Redis في Kubernetes
    docker-compose ps
    ```
-   **فحص السجلات:**
    ```bash
    kubectl logs -f <basirah-redis-pod-name>
    docker-compose logs -f redis
    ```
-   **التحقق من الاتصال:** محاولة الاتصال بـ Redis من داخل حاوية التطبيق.

## 4. التحديثات والترقيات (Updates and Upgrades)

-   **تحديث صور Docker:** بناء صور Docker جديدة مع أحدث الكود أو التبعيات.
-   **تطبيق التحديثات (Kubernetes):** استخدام `kubectl apply -f <manifest-file>` لتطبيق التغييرات. يوصى باستخدام استراتيجيات التحديث المتدحرج (Rolling Updates).
-   **تطبيق التحديثات (Docker Compose):** `docker-compose pull && docker-compose up -d`.
-   **ترحيلات قاعدة البيانات:** تشغيل `alembic upgrade head` بعد كل تحديث يتضمن تغييرات في مخطط قاعدة البيانات.

---

**ملاحظة:** هذا الدليل هو نقطة بداية ويجب تحديثه بانتظام ليعكس التغييرات في النظام وبيئة التشغيل.
