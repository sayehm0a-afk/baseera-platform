# سجل التغييرات (Changelog)

جميع التغييرات الملحوظة في هذا المشروع سيتم توثيقها في هذا الملف.

يعتمد هذا السجل على معايير [Keep a Changelog](https://keepachangelog.com/en/1.0.0/)، ويلتزم المشروع بنظام [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]
### تمت الإضافة
- الهيكل الأساسي للمشروع وتأسيس المجلدات.
- ميثاق منصة بصيرة كمرجعية عليا.
- الوثائق الرئيسية للمشروع باللغة العربية.

## v0.2.1 - 2026-07-14

### Added
-   **BaseAgent Core:** تنفيذ الوحدة الأساسية `BaseAgent` في `src/core/base_agent/base_agent.py`.
-   **Unit Tests:** إضافة اختبارات الوحدات لـ `BaseAgent` في `tests/unit/core/base_agent/test_base_agent.py`.

### Fixed
-   تم إصلاح أخطاء بناء الجملة والمسافات البادئة في ملف اختبارات الوحدات.
-   تم إصلاح مشكلة استيراد الوحدة في ملف اختبارات الوحدات.
