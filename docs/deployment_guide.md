# دليل نشر منصة بصيرة

## 1. المقدمة

يوفر هذا الدليل إرشادات مفصلة لنشر منصة بصيرة على مجموعة Kubernetes باستخدام Helm. يغطي الدليل المتطلبات الأساسية، خطوات النشر، والتحقق من صحة النشر.

## 2. المتطلبات الأساسية

قبل البدء في النشر، تأكد من توفر المتطلبات التالية:

*   **مجموعة Kubernetes عاملة**: يجب أن تكون لديك مجموعة Kubernetes عاملة (مثل GKE, EKS, AKS, أو Minikube).
*   **kubectl**: أداة سطر الأوامر للتفاعل مع مجموعة Kubernetes.
*   **Helm 3**: مدير حزم Kubernetes.
*   **Docker**: لتعبئة صور التطبيق (إذا كنت تقوم ببناء الصور محليًا).
*   **ملفات التكوين**: يجب أن تكون ملفات Helm Chart و `values.yaml` و `secrets.yaml` متوفرة.

## 3. إعداد البيئة

### 3.1. تثبيت الأدوات

تأكد من تثبيت `kubectl` و `helm` على جهازك المحلي أو خادم النشر.

```bash
# تثبيت kubectl (مثال لنظام Ubuntu)
sudo apt-get update && sudo apt-get install -y apt-transport-https gnupg2 curl
curl -s https://packages.cloud.google.com/apt/doc/apt-key.gpg | sudo apt-key add -
echo "deb https://apt.kubernetes.io/ kubernetes-xenial main" | sudo tee /etc/apt/sources.list.d/kubernetes.list
sudo apt-get update
sudo apt-get install -y kubectl

# تثبيت Helm (مثال لنظام Ubuntu)
curl https://raw.githubusercontent.com/helm/helm/master/scripts/get-helm-3 | bash
```

### 3.2. تكوين الوصول إلى Kubernetes

تأكد من أن `kubectl` مكون للوصول إلى مجموعة Kubernetes المستهدفة. يمكنك التحقق من ذلك باستخدام الأمر:

```bash
kubectl cluster-info
```

يجب أن يعرض هذا الأمر معلومات حول مجموعتك.

## 4. تكوين النشر

يتم تكوين منصة بصيرة باستخدام ملف `helm/values.yaml` وملفات الأسرار (Secrets) في `helm/templates/secrets.yaml`.

### 4.1. ملف `values.yaml`

يحتوي هذا الملف على التكوينات الافتراضية للنشر. يمكنك تعديل القيم لتناسب بيئتك. تتضمن بعض التكوينات الهامة:

*   `image.tag`: إصدار صورة Docker التي سيتم نشرها.
*   `replicaCount`: عدد النسخ (Replicas) لتطبيق بصيرة.
*   `database.host`, `database.name`, `database.user`: تفاصيل اتصال قاعدة بيانات PostgreSQL.
*   `redis.host`, `redis.port`: تفاصيل اتصال Redis.
*   `marketData.provider`: مزود بيانات السوق المستخدم.
*   `logging.level`, `logging.format`: مستوى وتنسيق التسجيل.
*   `monitoring.enabled`: تمكين/تعطيل مراقبة Prometheus و Grafana.

### 4.2. إدارة الأسرار (Secrets Management)

يجب توفير المعلومات الحساسة مثل كلمات المرور ومفاتيح API عبر Kubernetes Secrets. يتم تعريف هذه الأسرار في `helm/templates/secrets.yaml`.

**مثال على `secrets.yaml`:**

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: {{ include "basirah.fullname" . }}-secrets
  labels:
    {{- include "basirah.labels" . | nindent 4 }}
type: Opaque
data:
  database-url: {{ .Values.database.url | b64enc | quote }}
  redis-password: {{ .Values.redis.password | b64enc | quote }}
  market-data-api-endpoint: {{ .Values.marketData.apiEndpoint | b64enc | quote }}
  market-data-api-key: {{ .Values.marketData.apiKey | b64enc | quote }}
  openai-api-key: {{ .Values.openai.apiKey | b64enc | quote }}
```

**ملاحظات هامة:**

*   يجب أن يتم تمرير القيم الحساسة (مثل `database.url`, `redis.password`, `marketData.apiEndpoint`, `marketData.apiKey`, `openai.apiKey`) إلى Helm Chart إما عبر ملف `values.yaml` مخصص أو باستخدام الخيار `--set` أثناء النشر. **لا تقم بتضمين هذه القيم مباشرة في `values.yaml` إذا كان سيتم تخزينها في نظام التحكم بالإصدار (Git).**
*   يتم ترميز القيم في `secrets.yaml` باستخدام Base64 (`b64enc`).

## 5. عملية النشر

يمكنك استخدام النص البرمجي `deploy.sh` لتبسيط عملية النشر.

### 5.1. استخدام `deploy.sh`

```bash
./scripts/deploy.sh [OPTIONS]
```

**الخيارات:**

*   `-n, --namespace NAMESPACE`: مساحة اسم Kubernetes (افتراضي: `basirah`).
*   `-r, --release NAME`: اسم إصدار Helm (افتراضي: `basirah`).
*   `-v, --values FILE`: ملف قيم مخصص لتجاوز القيم الافتراضية في `values.yaml`.
*   `-t, --tag TAG`: علامة صورة Docker (افتراضي: `1.0.0`).
*   `-h, --help`: عرض رسالة المساعدة.

**مثال على النشر:**

```bash
# نشر باستخدام القيم الافتراضية
./scripts/deploy.sh

# نشر إلى مساحة اسم مخصصة مع علامة صورة محددة وملف قيم مخصص
./scripts/deploy.sh -n production -r basirah-prod -t 1.1.0 -v my-production-values.yaml
```

### 5.2. خطوات النشر اليدوي (اختياري)

إذا كنت تفضل النشر يدويًا بدون النص البرمجي `deploy.sh`، اتبع الخطوات التالية:

1.  **إنشاء مساحة الاسم (Namespace)**:
    ```bash
    kubectl create namespace basirah
    ```

2.  **نشر Helm Chart**:
    ```bash
    helm upgrade --install basirah ./helm \
      --namespace basirah \
      --set image.tag=1.0.0 \
      --set database.url=$(echo -n "postgresql://basirah_user:your_db_password@basirah-db:5432/basirah_db" | base64) \
      --set redis.password=$(echo -n "your_redis_password" | base64) \
      --set marketData.apiEndpoint=$(echo -n "https://api.saudimarketdata.com" | base64) \
      --set marketData.apiKey=$(echo -n "your_market_data_api_key" | base64) \
      --set openai.apiKey=$(echo -n "your_openai_api_key" | base64)
    ```
    **ملاحظة**: استبدل `your_db_password`, `your_redis_password`, `https://api.saudimarketdata.com`, `your_market_data_api_key`, و `your_openai_api_key` بالقيم الفعلية.

## 6. التحقق من صحة النشر

بعد النشر، استخدم النص البرمجي `validate-deployment.sh` للتحقق من صحة وسلامة النشر.

```bash
./scripts/validate-deployment.sh [OPTIONS]
```

**الخيارات:**

*   `-n, --namespace NAMESPACE`: مساحة اسم Kubernetes (افتراضي: `basirah`).
*   `-r, --release NAME`: اسم إصدار Helm (افتراضي: `basirah`).
*   `-t, --timeout SECONDS`: مهلة لفحوصات الصحة (افتراضي: `300` ثانية).
*   `-h, --help`: عرض رسالة المساعدة.

سيقوم النص البرمجي بإجراء فحوصات مختلفة، بما في ذلك التحقق من وجود مساحة الاسم، حالة النشر، حالة Pods، وجود الخدمة، حالة طرح النشر، ونقاط نهاية الصحة وقاعدة البيانات.

## 7. التراجع عن النشر (Rollback)

في حالة وجود مشكلات بعد النشر، يمكنك استخدام النص البرمجي `rollback.sh` للعودة إلى إصدار سابق.

```bash
./scripts/rollback.sh [OPTIONS]
```

**الخيارات:**

*   `-n, --namespace NAMESPACE`: مساحة اسم Kubernetes (افتراضي: `basirah`).
*   `-r, --release NAME`: اسم إصدار Helm (افتراضي: `basirah`).
*   `-v, --revision REVISION`: الإصدار الذي سيتم التراجع إليه (افتراضي: `0` للإصدار السابق مباشرة).
*   `-h, --help`: عرض رسالة المساعدة.

**مثال على التراجع:**

```bash
# التراجع إلى الإصدار السابق
./scripts/rollback.sh

# التراجع إلى إصدار محدد (على سبيل المثال، الإصدار 2)
./scripts/rollback.sh -v 2
```

**ملاحظة**: يمكنك عرض سجل الإصدارات باستخدام `helm history <release-name> -n <namespace>`.
