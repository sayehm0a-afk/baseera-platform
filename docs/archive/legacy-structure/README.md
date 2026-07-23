# Legacy Directory Structure — Archived Empty Skeletons

The directories here were moved from the repository root during the M1
restructuring. Each one was verified, file by file, to contain nothing
but `__init__.py` and/or `.gitkeep` placeholders — a folder name implying
a subsystem (e.g. "Intelligent Agents", "Prompts", "Infrastructure",
"Tests", "Settings") with zero actual implementation behind it.

They are preserved here, unmodified, as deletion candidates for a future,
explicitly-approved cleanup PR — not deleted now, per the restructuring
rules for this milestone. A folder name was never evidence of an
implemented feature; see `docs/architecture/current-status.md` for what
is actually implemented.

Moved in this step: `العملاء_الذكيين/`, `الملقنات/`, `البنية_التحتية/`,
`الاختبارات/`, `الإعدادات/`, `الوثائق_الرئيسية/` (the latter only after
its real governance/vision content was relocated to `docs/governance/` —
see `docs/architecture/m1-move-map.md` section 3).

Two directories that were expected to be empty turned out to contain real
(if currently unreferenced) content and were **not** moved here — see
`docs/architecture/m1-move-map.md` section 7 for details:
`الأدوات_والنصوص/النسخ_الاحتياطي/backup.sh` and
`السجلات/config/logging_config.yml`.
