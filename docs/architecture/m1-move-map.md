# M1 Move Map

This is the plan executed by the M1 restructuring commits, recorded before the
moves so the actual `git mv` commits can be checked against it. Every entry
below was carried out with `git mv` (history-preserving) unless marked
otherwise. Nothing listed here was deleted.

## 1. Legacy completion/readiness/certification reports → `docs/archive/legacy-reports/`

Selection rule: a document is archived here if it claims or implies, about
the platform or a major subsystem, one of: 100% completion, production
readiness, final certification, successful production validation, a fully
completed AI agent layer, or a completed stock-analysis engine. Each file
below was read (title + opening content, and grepped for explicit
completion/certification phrases) before being classified — filename
pattern alone was not treated as sufficient evidence.

Root-level (12):
- `INDEPENDENT_AUDIT_REPORT.md`
- `PRODUCTION_VALIDATION_REPORT.md`
- `Production_Readiness_Report.md`
- `env_and_external_connections_report.md`
- `final_readiness_report.md`
- `production_deployment_checklist.md`
- `production_deployment_plan.md`
- `production_readiness_documentation.md`
- `production_readiness_report.md`
- `production_requirements_report.md`
- `production_runbook.md`
- `repository_audit_report.md`

`docs/` top-level (14):
- `docs/Architecture_Report.md` — asserts the system "is designed to be production-ready"
- `docs/Deployment_Readiness_Report.md` — "Deployment Readiness Report"
- `docs/Final_Completion_Report.md` — "completed successfully... production readiness percentage"
- `docs/Final_Technical_Report.md` — "ready for further development and deployment"
- `docs/Integration_Report.md` — "all integration tests passed successfully"
- `docs/Platform_Architecture_Review_v2.0.md` — "completed components" framing
- `docs/Production_Readiness_Report.md` — title is literally "Production Readiness Report"
- `docs/Project_Health_Report.md` — "Modules 1-5 considered complete and stable"
- `docs/Release_Candidate_Report.md` — release/production readiness claims
- `docs/Test_Summary.md` — "unit/integration tests ran successfully" framed as completion evidence
- `docs/Security_Report.md` — framed as post-"completion of modules 1-5"
- `docs/Security_Summary.md` — framed as post-"completion of modules 1-5"
- `docs/Technical_Debt_Report.md` — framed as post-"completion of modules 1-5"
- `docs/ownership_and_backup_audit_report.md` — self-certifying "comprehensive engineering review"

`docs/final_engineering_*` (6) — "final"/"certification"/"audit" naming and content, same cluster:
- `docs/final_engineering_audit_guide.md`
- `docs/final_engineering_audit_report.md`
- `docs/final_engineering_audit_report_after_fix.md`
- `docs/final_engineering_certification_report.md`
- `docs/final_engineering_certification_report_docker_evidence.md`
- `docs/final_independent_production_audit.md`

`docs/module5/PHASE_*` (5) — implementation-complete claims per phase:
- `docs/module5/PHASE_4_AUTONOMOUS_CORE_IMPLEMENTATION_REPORT.md`
- `docs/module5/PHASE_4_IMPLEMENTATION_SUMMARY.md`
- `docs/module5/PHASE_5_DECISION_INTELLIGENCE_IMPLEMENTATION_REPORT.md`
- `docs/module5/PHASE_6_RESOURCE_FINANCIAL_INTELLIGENCE_REPORT.md`
- `docs/module5/PHASE_7_SELF_HEALING_AUTONOMOUS_LEARNING_REPORT.md`

`docs/recovery/` (1):
- `docs/recovery/MODULE_5_PRE_COMPLETION_BACKUP_REPORT.md`

`الوثائق_الرئيسية/تقارير_المراجعة/` and `تقارير_التنفيذ/` (4) — "final production quality," "final architecture readiness," "production quality gate," "implementation report":
- `الوثائق_الرئيسية/تقارير_المراجعة/تقرير_جاهزية_المعمارية_النهائي.md`
- `الوثائق_الرئيسية/تقارير_المراجعة/تقرير_جودة_الإنتاج_النهائي_BaseAgent_Core.md`
- `الوثائق_الرئيسية/تقارير_المراجعة/تقرير_بوابة_جودة_الإنتاج_BaseAgent_Core.md`
- `الوثائق_الرئيسية/تقارير_التنفيذ/BaseAgent_Core_Implementation_Report.md`

**Total archived: 42 files.**

## 2. Explicitly NOT archived — kept as legitimate reference (evidence noted)

These were checked for the same signal phrases and did not qualify — they
are technical/design/operational content or, in one case, an honest gap
analysis that contradicts the misleading cluster above rather than joining it:

- `docs/Architecture_Summary.md`, `docs/Dependency_Report.md`, `docs/Performance_Report.md` — descriptive/neutral, no completion claim
- `docs/Runtime_Orchestration_Gap_Analysis_v1.0.md` — explicitly identifies missing components ("مفقود"); this is the opposite of a misleading completion claim
- `docs/module5/MODULE_5_CURRENT_STATE_AUDIT.md` — component-by-component, marks items "partially complete" with real gaps listed, not a blanket completion claim
- `docs/Module_3.5_Runtime_Technical_Design.md`, `docs/architecture_document.md`, `docs/autonomous_intelligence_layer/*` — forward design specs, not status claims
- `docs/deployment_guide.md`, `docs/operations_guide.md`, `docs/incident_recovery_guide.md`, `docs/runtime_event_contracts.md`, `docs/recovery/restore_instructions.md`, `docs/recovery/backup_manifest.txt`, `docs/recovery/backup_checksum.txt` — operational reference material
- All `.mmd`/`.png`/`.d2` diagrams under `docs/` and `docs/module5/diagrams/` — visual artifacts, not textual completion claims
- `docs/module5/__init__.py`, `docs/recovery/__init__.py`, `docs/autonomous_intelligence_layer/__init__.py` — leave as-is, harmless empty package markers

None of these were moved in M1; they remain at their current paths.

## 3. Arabic governance and vision documents → `docs/governance/`

Filenames and content preserved exactly; only location changes. Arabic
subfolder grouping preserved under the new parent for readability:

- `ميثاق_منصة_بصيرة.md` → `docs/governance/ميثاق_منصة_بصيرة.md`
- `الوثائق_الرئيسية/Implementation_Roadmap_v1.0.md` → `docs/governance/Implementation_Roadmap_v1.0.md`
- `الوثائق_الرئيسية/Platform_Engineering_Blueprint_v1.0.md` → `docs/governance/Platform_Engineering_Blueprint_v1.0.md`
- `الوثائق_الرئيسية/Technical_Design_Specification_v1.0.md` → `docs/governance/Technical_Design_Specification_v1.0.md`
- `الوثائق_الرئيسية/سياسة_حفظ_واسترجاع_بصيرة.md` → `docs/governance/سياسة_حفظ_واسترجاع_بصيرة.md`
- `الوثائق_الرئيسية/مواصفات_متطلبات_البرمجيات_SRS.md` → `docs/governance/مواصفات_متطلبات_البرمجيات_SRS.md`
- `الوثائق_الرئيسية/الحوكمة_والقرارات/*` (DECISIONS_LOG.md, LESSONS_LEARNED.md, 9 ADRs under `سجلات_القرارات_المعمارية/` — note: two of the nine are both numbered `0003` in the original source, `0003-runtime-orchestration-messaging.md` and `0003-technical-design-specification.md`; this numbering collision predates M1 and was not introduced or corrected by this move) → `docs/governance/الحوكمة_والقرارات/...` (same relative structure)
- `الوثائق_الرئيسية/المعمارية/تصميم_معمارية_BaseAgent.md` → `docs/governance/المعمارية/تصميم_معمارية_BaseAgent.md`
- `الوثائق_الرئيسية/توثيق_الوحدات/*` (2 files) → `docs/governance/توثيق_الوحدات/...`
- `الوثائق_الرئيسية/خارطة_الطريق/خارطة_بصيرة_2030.md` → `docs/governance/خارطة_الطريق/خارطة_بصيرة_2030.md`
- `الوثائق_الرئيسية/معايير_التطوير/*` (2 files) → `docs/governance/معايير_التطوير/...`

**Total moved to `docs/governance/`: 23 files** (6 single top-level
documents + 9 ADRs + `DECISIONS_LOG.md` + `LESSONS_LEARNED.md` + 1
architecture design doc + 2 module-documentation files + 1 roadmap + 2
standards documents = 23; verified by `find docs/governance -type f`).

After these moves, `الوثائق_الرئيسية/` contains only `__init__.py` /
`.gitkeep` placeholders and an empty `واجهات_برمجة_التطبيقات/` subfolder —
no real content remains. That emptied shell is handled in step 5 below,
the same way as the other empty Arabic skeleton directories, since it is
now in the identical state (name implying structure, zero implementation).

## 4. New canonical empty subsystem scaffolding (no code, `.gitkeep` only)

Per the instruction that empty future directories may contain only
`.gitkeep`/minimal `__init__.py`, and must not contain placeholder
implementations:

- `src/market_data/providers/`, `src/market_data/validators/`, `src/market_data/schemas/`
- `src/analysis/indicators/`, `src/analysis/price_action/`, `src/analysis/volume/`
- `src/agents/base/`
- `src/pipeline/`
- `src/domain/`
- `src/learning/`
- `prompts/`
- `frontend/`
- `tests/financial_validation/`
- `tests/operational/`
- `migrations/versions/`

Each gets a `.gitkeep` and, where it sits inside the `src/` Python package
tree, an empty `__init__.py` so `setup.py`'s `find_packages()` picks it up
consistently with the rest of `src/`. No class, function, or stub logic is
added anywhere in this list.

## 5. Existing source code relocated to match the canonical tree

Only one real code move, because it is the only existing module whose
current location and target location differ *and* has zero importers
(verified via repo-wide grep before moving — no import path updates
needed anywhere else):

- `src/core/market_data/market_data_provider.py` → `src/market_data/providers/market_data_provider.py`
- `src/core/market_data/__init__.py` → `src/market_data/__init__.py`

**Everything else already matches the canonical tree and is not moved:**
`src/api/{routes,schemas,middleware}`, `src/core/{runtime,llm_abstraction,messaging,db,monitoring}`.

### Explicitly deferred, not moved, with reasoning

`src/core/autonomous_intelligence_layer/`, `src/core/multi_agent_system/`,
`src/core/base_agent/`, `src/core/service_layer/`, `src/core/shared_models/`,
`src/core/exceptions/`, `src/core/utils/` do not have an unambiguous slot in
the canonical tree above (the tree does not enumerate them, and `src/agents/`
is reserved for the *future* clean agent interface, not a relocation target
for the current orphaned/legacy code documented in
`docs/architecture/runtime-ownership.md`). Relocating ~30 interconnected
files with cross-imports for no functional benefit, purely to fit a
diagram, would be exactly the kind of large, risky, unrelated-refactoring
move this milestone's rules prohibit ("update imports only when required
by a file move," "do not perform unrelated refactoring"). They remain at
their current, verified-working M0 paths. Their disposition (retire,
keep, or fold into the future `src/agents/` framework) is a decision for a
dedicated future milestone, informed by the ownership map in
`docs/architecture/runtime-ownership.md`, not a side effect of this one.

## 6. Tests

`tests/unit/` and `tests/integration/` already match the canonical tree
and are not moved. `tests/e2e/`, `tests/load/`, and `tests/security/` do
not map unambiguously onto the canonical `financial_validation` /
`operational` categories (none of those tests are financial-validation or
chaos/operational tests in the sense Phase 10 of the original plan
defines) — per "move tests only when their category is unambiguous," they
are left in place. The two new categories are scaffolded empty
(`tests/financial_validation/`, `tests/operational/`) for future use.

## 7. Empty Arabic engineering skeletons → `docs/archive/legacy-structure/`

Verified by inspecting every file in each of the 7 named directories
(not assumed from the earlier audit): 5 are confirmed entirely empty
(`__init__.py`/`.gitkeep` only) — `العملاء_الذكيين/`, `الملقنات/`,
`البنية_التحتية/`, `الاختبارات/`, `الإعدادات/` — and, together with the
now-emptied `الوثائق_الرئيسية/` shell (see §3), are moved as-is to
`docs/archive/legacy-structure/`, preserving their names. No Python code
is introduced into them. They are not deleted.

**2 of the 7 are not actually empty** and are therefore *not* moved in
this step, since the instruction is to relocate skeletons only "if they
are still entirely empty":
- `الأدوات_والنصوص/النسخ_الاحتياطي/backup.sh` — a real 28-line backup
  script, hardcoding a nonexistent path (`/home/ubuntu/بصيرة/...`, the
  same fictional-environment pattern found and fixed for test paths in
  M0). Not referenced by any script, CI workflow, or Docker/Compose/K8s
  config anywhere in the repo (verified by grep).
- `السجلات/config/logging_config.yml` — a real, plausible Python
  `logging.config.dictConfig`-style YAML config. Not referenced by
  `src/core/monitoring/structured_logging.py` or anywhere else (verified
  by grep) — the actual logging setup is done in code, not via this file.

Both are left exactly where they are, untouched, and flagged here as a
finding for a future decision (wire them in, or archive them) rather than
silently swept into the "empty skeleton" bucket they don't belong in.

## 8. Infrastructure and config path references

Checked, not changed unless a reference was found: `Dockerfile`,
`docker-compose.yml`, `kubernetes/*.yaml`, `helm/`, `alembic.ini`,
`migrations/env.py`, `.github/workflows/ci.yml`, `scripts/*.sh`. Findings
recorded in `docs/architecture/repository-structure.md` and the M1 PR
description.
