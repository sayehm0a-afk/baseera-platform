# دليل عمليات منصة بصيرة

## 1. المقدمة

يوفر هذا الدليل معلومات أساسية للمشغلين الذين يديرون منصة بصيرة في بيئة الإنتاج. يغطي الدليل جوانب المراقبة، إدارة السجلات، النسخ الاحتياطي والاستعادة، وإدارة التكوين.

## 2. المراقبة (Monitoring)

تستخدم منصة بصيرة Prometheus لجمع المقاييس و Grafana لتصورها. يمكن الوصول إلى لوحات معلومات Grafana عبر عنوان URL الخاص بها.

### 2.1. لوحات معلومات Grafana

*   **لوحة معلومات صحة النظام (System Health Dashboard)**: توفر نظرة عامة على صحة المكونات الرئيسية مثل استخدام وحدة المعالجة المركزية (CPU)، الذاكرة، الشبكة، وحالة Pods في Kubernetes.
*   **لوحة معلومات أداء التطبيق (Application Performance Dashboard)**: تعرض مقاييس أداء FastAPI API، مثل زمن الاستجابة (latency)، معدل الطلبات (request rate)، ومعدلات الأخطاء (error rates).
*   **لوحة معلومات بيانات السوق (Market Data Dashboard)**: تراقب صحة مزودي بيانات السوق، ومعدلات الطلبات، وأوقات الاستجابة.
*   **لوحة معلومات قائمة المهام (Task Queue Dashboard)**: تعرض حجم قائمة المهام، ومعدلات معالجة المهام، وحالة العاملين (Workers).

### 2.2. التنبيهات (Alerting)

يتم تكوين Prometheus Alertmanager لإرسال التنبيهات بناءً على قواعد محددة. يجب على المشغلين التأكد من تكوين قنوات التنبيه (مثل البريد الإلكتروني، Slack، PagerDuty) بشكل صحيح.

**أمثلة على التنبيهات الهامة:**

*   ارتفاع معدل الأخطاء في API.
*   انخفاض صحة مزود بيانات السوق.
*   امتلاء قائمة المهام.
*   استخدام موارد النظام بشكل مفرط (CPU، الذاكرة).
*   فشل Pods أو Deployments في Kubernetes.

## 3. إدارة السجلات (Logging Management)

تستخدم منصة بصيرة تسجيل JSON منظم، مما يسهل تجميع السجلات وتحليلها.

### 3.1. الوصول إلى السجلات

يمكن الوصول إلى سجلات التطبيق من خلال أدوات تجميع السجلات المركزية (مثل ELK Stack أو Grafana Loki) التي يجب أن تكون مدمجة مع مجموعة Kubernetes.

**مثال على عرض السجلات باستخدام kubectl:**

```bash
kubectl logs -f <pod-name> -n basirah
```

### 3.2. مستويات التسجيل (Log Levels)

يمكن تكوين مستوى التسجيل (INFO, DEBUG, WARNING, ERROR, CRITICAL) عبر ملف `values.yaml` الخاص بـ Helm. يوصى باستخدام `INFO` في الإنتاج و `DEBUG` لاستكشاف الأخطاء وإصلاحها.

## 4. النسخ الاحتياطي والاستعادة (Backup and Restore)

### 4.1. قاعدة بيانات PostgreSQL

يجب تنفيذ استراتيجية نسخ احتياطي منتظمة لقاعدة بيانات PostgreSQL. يمكن استخدام أدوات مثل `pg_dump` أو حلول النسخ الاحتياطي الخاصة بـ Kubernetes (مثل Velero).

**مثال على النسخ الاحتياطي اليدوي:**

```bash
kubectl exec -it <postgresql-pod-name> -n basirah -- pg_dump -U basirah_user basirah_db > basirah_db_backup.sql
```

### 4.2. Redis

يمكن تكوين Redis للنسخ الاحتياطي المستمر (RDB persistence) أو إضافة (AOF persistence) لضمان استمرارية البيانات.

## 5. إدارة التكوين (Configuration Management)

يتم إدارة تكوين التطبيق بشكل أساسي عبر Helm Chart و `values.yaml` و Kubernetes Secrets.

### 5.1. تحديث التكوين

لتحديث التكوين، قم بتعديل ملف `values.yaml` أو ملف قيم مخصص، ثم قم بتطبيق التغييرات باستخدام `helm upgrade`:

```bash
./scripts/deploy.sh -v my-updated-values.yaml
```

### 5.2. إدارة الأسرار

يجب إدارة الأسرار الحساسة بعناية. تجنب تخزينها في نظام التحكم بالإصدار (Git) مباشرة. استخدم حلول إدارة الأسرار مثل HashiCorp Vault أو Kubernetes External Secrets.

## 6. الصيانة الدورية (Routine Maintenance)

*   **تحديثات النظام (System Updates)**: حافظ على تحديث صور Docker، إصدارات Kubernetes، و Helm باستمرار.
*   **تنظيف السجلات (Log Rotation)**: تأكد من تكوين تدوير السجلات لمنع استهلاك مساحة التخزين.
*   **مراجعة الأداء (Performance Review)**: راجع لوحات معلومات Grafana بانتظام لتحديد أي اختناقات في الأداء.

## 7. استكشاف الأخطاء وإصلاحها (Troubleshooting)

عند مواجهة مشكلات، اتبع الخطوات التالية:

1.  **التحقق من سجلات Pods**: استخدم `kubectl logs` لتحديد الأخطاء في سجلات التطبيق.
2.  **التحقق من حالة Pods**: استخدم `kubectl get pods` و `kubectl describe pod <pod-name>` للتحقق من حالة Pods وأحداثها.
3.  **التحقق من Deployments**: استخدم `kubectl get deployments` و `kubectl rollout status` للتحقق من حالة النشر.
4.  **التحقق من الخدمات (Services) و Ingress**: تأكد من أن الخدمات و Ingress تعمل بشكل صحيح وتوجه حركة المرور إلى Pods الصحيحة.
5.  **مراجعة لوحات معلومات Grafana**: ابحث عن أي انحرافات في المقاييس التي قد تشير إلى المشكلة.

## 8. إيقاف التشغيل (Shutdown)

لإيقاف تشغيل التطبيق، يمكنك حذف إصدار Helm:

```bash
helm uninstall <release-name> -n <namespace>
```

**مثال:**

```bash
helm uninstall basirah -n basirah
```
