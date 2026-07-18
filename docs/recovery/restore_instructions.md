## تعليمات استعادة النسخ الاحتياطي لـ Module 5 (قبل الانتهاء)

هذه التعليمات توضح كيفية استعادة مشروع بصيرة من النسخة الاحتياطية المضغوطة التي تم إنشاؤها قبل البدء في تنفيذ Module 5.

### 1. المتطلبات الأساسية

*   وصول إلى بيئة Linux (مثل Ubuntu).
*   أدوات `unzip` و `git` و `sha256sum` مثبتة.

### 2. خطوات الاستعادة

1.  **نقل ملف النسخ الاحتياطي:**
    انقل ملف `basirah_module5_pre_completion_backup.zip` إلى الدليل الذي ترغب في استعادة المشروع إليه.

2.  **فك ضغط النسخة الاحتياطية:**
    افتح الطرفية وانتقل إلى الدليل الذي يحتوي على ملف `.zip`. ثم قم بفك ضغط الملف:
    ```bash
    unzip basirah_module5_pre_completion_backup.zip -d /home/ubuntu/restore_test_basirah
    ```
    (استبدل `/home/ubuntu/restore_test_basirah` بالمسار الذي تريد الاستعادة إليه).

3.  **التحقق من SHA-256 Checksum:**
    للتأكد من سلامة ملف النسخ الاحتياطي، قم بإنشاء checksum للملف الذي تم فك ضغطه ومقارنته بالملف الأصلي `backup_checksum.txt`.
    ```bash
    cd /home/ubuntu/restore_test_basirah/home/ubuntu/بصيرة/
    sha256sum ../../../basirah_module5_pre_completion_backup.zip
    ```
    قارن الناتج بالـ checksum الموجود في `docs/recovery/backup_checksum.txt`.

4.  **التحقق من حالة Git:**
    انتقل إلى دليل المشروع الذي تم استعادته وتحقق من حالة Git:
    ```bash
    cd /home/ubuntu/restore_test_basirah/home/ubuntu/بصيرة/
    git status
    git log --oneline -1
    git tag
    ```
    يجب أن تكون على الفرع `backup/pre-module-5-completion` ويجب أن يكون الوسم `v0.5.0-module5-pre-completion` موجودًا.

5.  **تثبيت التبعيات (إذا لزم الأمر):**
    إذا كان المشروع يحتوي على تبعيات Python، فقد تحتاج إلى تثبيتها:
    ```bash
    pip install -r requirements.txt
    ```

6.  **تشغيل الاختبارات (اختياري):**
    لتأكيد أن المشروع يعمل بشكل صحيح بعد الاستعادة:
    ```bash
    pytest
    ```

### 3. ملاحظات

*   تأكد من أن لديك مساحة كافية على القرص قبل فك ضغط النسخة الاحتياطية.
*   قد تحتاج إلى تعديل المسارات في الخطوات أعلاه لتتناسب مع بيئة الاستعادة الخاصة بك.
