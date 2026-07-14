#!/bin/bash
# ===========================
# سكريبت النسخ الاحتياطي التلقائي - منصة بصيرة
# يُشغَّل يومياً عبر Cron Job
# ===========================

set -e

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/backups/baseera"
DB_NAME="${BASEERA_DB_NAME:-baseera_db}"
LOG_FILE="/home/ubuntu/بصيرة/السجلات/backup_${TIMESTAMP}.log"

echo "[$TIMESTAMP] بدء النسخ الاحتياطي..." | tee -a "$LOG_FILE"

# إنشاء مجلد النسخ الاحتياطي إذا لم يكن موجوداً
mkdir -p "$BACKUP_DIR/database"
mkdir -p "$BACKUP_DIR/config"

# نسخ احتياطي لقاعدة البيانات
echo "[$TIMESTAMP] نسخ قاعدة البيانات..." | tee -a "$LOG_FILE"
pg_dump "$DB_NAME" | gzip > "$BACKUP_DIR/database/db_${TIMESTAMP}.sql.gz"

# نسخ احتياطي للإعدادات
echo "[$TIMESTAMP] نسخ ملفات الإعدادات..." | tee -a "$LOG_FILE"
cp -r /home/ubuntu/بصيرة/الإعدادات/ "$BACKUP_DIR/config/config_${TIMESTAMP}/"

echo "[$TIMESTAMP] ✅ اكتمل النسخ الاحتياطي بنجاح." | tee -a "$LOG_FILE"
