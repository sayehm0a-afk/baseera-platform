# Database Table Classification & Migration Roadmap

**Produced by:** Phase 2 Foundation Cleanup (production hardening, no
new AI features), goal 3 -- "remove dead architecture."

**Scope:** every one of the 49 tables defined under
`src/domain/models/` as of migration head `be797f1fc67b`. Per the
cleanup mandate, **no schema was changed and no data was deleted or
touched** to produce this document -- it is a classification and a
roadmap, not a migration.

## How each table was classified

- **ACTIVE** -- read and/or written by a real, reachable API route or
  a running background job, as part of the product today.
- **RESERVED** -- the model and migration exist, and the table maps
  cleanly onto a specific, plausible near-term feature (several are
  explicit audit findings from the Technical Baseline Report's
  "missing production features" section, §22), but no route reads or
  writes it yet.
- **LEGACY** -- no route reads or writes it, and it does not map onto
  any specific planned feature; a candidate for eventual removal once
  confirmed safe.

A table's *only* appearance being `src/auth/data_export_service.py`
(the GDPR-style self-service export at `GET /api/v1/auth/me/export`)
does not by itself make it ACTIVE -- that service enumerates every
user-owned table so an export is complete regardless of whether the
table has a product feature built on it yet. That appearance is noted
per table below but does not change the classification on its own.

## Market reference data

| Table | Classification | Basis |
|---|---|---|
| `stocks` | ACTIVE | Core reference table -- every route in `src/api/routes/stocks.py`, `market.py`, `portfolio.py` |
| `price_bars` | ACTIVE | `/stocks/{symbol}/history`, technical analysis, ingestion jobs |
| `market_snapshots` | ACTIVE | TASI/index snapshot ingestion + market intelligence |
| `fundamental_snapshots` | ACTIVE | `/stocks/{symbol}/fundamentals`, decision engines |
| `dividends` | ACTIVE | Ingestion job + fundamental analysis inputs |
| `ingestion_run_logs` | ACTIVE | `GET /ingestion/status` |

## Recommendations & outcomes

| Table | Classification | Basis |
|---|---|---|
| `backtest_runs` | ACTIVE | `/backtests/*` router |
| `recommendation_snapshots` | ACTIVE | Written by live scans + backtests; read by AI Evolution metrics |
| `recommendation_outcomes` | ACTIVE | `OutcomeEvaluationScheduler` (E2) |

## AI Evolution Layer

| Table | Classification | Basis |
|---|---|---|
| `confidence_calibration_models` | ACTIVE | `/admin/ai-evolution/calibration-status` |
| `discovered_patterns` | ACTIVE | `/admin/ai-evolution/patterns`, `PatternDiscoveryScheduler` |
| `reflection_reports` | ACTIVE | `/admin/ai-evolution/reflections`, `DailyReflectionScheduler` |
| `agent_opinions` | ACTIVE | Multi-agent panel (E7), read via Intelligence Dashboard |
| `debate_sessions` | ACTIVE | Multi-agent panel (E7), same as above |
| `daily_intelligence_snapshots` | ACTIVE | `/admin/ai-evolution/dashboard`, `DailyIntelligenceAggregationScheduler` |
| `calibration_configs` | ACTIVE | `/calibrations/*` router |

## Market Intelligence / Scanner

| Table | Classification | Basis |
|---|---|---|
| `market_scan_runs` | ACTIVE | `/market/scan*`, `/admin/system/summary` |
| `market_scan_progress` | ACTIVE | `/market/scan/{run_id}/progress`, owner dashboard |
| `symbol_intelligence_records` | ACTIVE | `/market/rankings`, `/market/top-buy`, etc. |
| `sector_intelligence_summaries` | ACTIVE | `/market/sectors` |
| `market_alerts` | ACTIVE | `/market/alerts` |
| `market_change_events` | ACTIVE | `/market/changes` |

## Portfolio

| Table | Classification | Basis |
|---|---|---|
| `portfolios` | ACTIVE | `/portfolio/*` router |
| `portfolio_holdings` | ACTIVE | Same |
| `portfolio_analysis_snapshots` | ACTIVE | Same |

## Auth / billing

| Table | Classification | Basis |
|---|---|---|
| `users` | ACTIVE | Core identity table |
| `user_sessions` | ACTIVE | `/auth/sessions*`, `/admin/sessions*` |
| `email_verification_tokens` | ACTIVE | `/auth/verify-email` |
| `password_reset_tokens` | ACTIVE | `/auth/forgot-password`, `/auth/reset-password` |
| `subscriptions` | ACTIVE | `/subscriptions/me`, `/admin/subscriptions*` |
| `invoices` | ACTIVE | `/admin/billing/users/{id}/invoices` (bookkeeping only -- no real payment gateway behind it, see Technical Baseline Report §24) |
| `payments` | ACTIVE | `/admin/billing/invoices/{id}/payments`, same caveat |

## Admin / platform

| Table | Classification | Basis |
|---|---|---|
| `audit_logs` | ACTIVE | `/admin/audit-log` |
| `feature_flags` | ACTIVE | `/admin/feature-flags*` |
| `announcements` | ACTIVE | `/admin/announcements*` |
| `global_settings` | **LEGACY** | Zero references anywhere outside its own model file -- not even in `data_export_service.py`. No route, no job, no planned feature maps onto it. |
| `notifications` | **RESERVED** | Written by `src/news_intelligence/portfolio_alerts.py`; no list/mark-read route exists yet. A natural, small follow-up (the write path already works) -- see roadmap below. |
| `user_watchlists` / `user_watchlist_items` | **RESERVED** | Personal watchlist management is an explicit missing-feature finding (Technical Baseline Report §22) -- distinct from the read-only, AI-generated `/market/watchlists`. Natural Phase 2 candidate. |
| `user_settings` | **RESERVED** | Only referenced by `data_export_service.py`; maps cleanly onto a future "preferences" feature, not clearly abandoned. |
| `feedback` | **RESERVED** | Only referenced by `data_export_service.py`; maps onto a plausible future in-app feedback feature. |
| `support_tickets` | **RESERVED** | Only referenced by `data_export_service.py`; maps onto a plausible future support-ticketing feature. |
| `ai_requests` | ACTIVE | Written by `src/analysis/ai_request_recorder.py`, read by `/admin/usage/ai` |
| `recommendation_history` | **LEGACY** | Nothing writes to it (no per-user "viewing log" instrumentation exists) -- `recommendation_snapshots` already serves the actual "what did we recommend and when" need this table's name suggests. Only referenced by `data_export_service.py`. |
| `reports` | **RESERVED** | Model + status enum exist, generator explicitly out of scope per its own docstring; maps directly onto the Complete Stock Intelligence Report Phase 2 pillar's likely need for a downloadable artifact. |

## News Intelligence

| Table | Classification | Basis |
|---|---|---|
| `news_events` | ACTIVE | `/news/*` router |
| `news_entities` | ACTIVE | Same |
| `news_source_reliability` | ACTIVE | `/news/sources` |
| `portfolio_news_alerts` | ACTIVE | `/portfolio/{id}/news-alerts*` |

## Decision Engine V2

| Table | Classification | Basis |
|---|---|---|
| `decision_v2_snapshots` | ACTIVE | Written by `/stocks/{symbol}/decision-v2` |

## Summary

| Classification | Count | Tables |
|---|---|---|
| ACTIVE | 39 | Everything above not listed as RESERVED/LEGACY |
| RESERVED | 8 | `notifications`, `user_watchlists`, `user_watchlist_items`, `user_settings`, `feedback`, `support_tickets`, `reports` (7 tables; `user_watchlists`+`user_watchlist_items` counted together as one feature, 8 rows) |
| LEGACY | 2 | `global_settings`, `recommendation_history` |

## Migration roadmap

No migration in this list is executed by this cleanup -- each is a
recommendation, sequenced by effort and product value, for a human
decision before it becomes a real migration.

1. **Wire `notifications` read access** (low effort -- the write path
   already exists). Add `GET /api/v1/notifications` and
   `POST /api/v1/notifications/{id}/read`, scoped to the requesting
   user. Promotes `notifications` from RESERVED to ACTIVE without a
   schema change.
2. **Wire `user_watchlists`/`user_watchlist_items` CRUD.** A natural
   Phase 2 candidate (Technical Baseline Report §27, "Portfolio
   Intelligence (deepening)" and the missing-features list, §22): add
   `POST/GET/DELETE /api/v1/watchlist` scoped to the requesting user,
   distinct from the existing AI-generated `/market/watchlists`. No
   schema change needed -- the table already has the right shape.
3. **Decide `user_settings`, `feedback`, `support_tickets`.** Each
   needs a product decision (is a preferences panel / in-app feedback
   form / support-ticket flow actually planned?) before engineering
   work, not a schema change. If none of the three is planned within,
   say, two more roadmap cycles, reclassify as LEGACY and follow the
   removal path below.
4. **Reports generation.** Blocked on Phase 2's Complete Stock
   Intelligence Report design (Technical Baseline Report §27) --
   revisit once that pillar's output format is decided; `reports` may
   turn out to be exactly the persistence layer it needs, or may need
   a different shape once real requirements exist.
5. **Retire `global_settings`.** No code path, no plan, and no
   customer-visible behavior depends on it. Recommended removal
   sequence (a future migration, not this one): confirm zero rows
   exist in production (`SELECT COUNT(*) FROM global_settings`), grep
   the deployed commit one more time immediately before the migration
   to catch any last-minute usage, then a migration that drops the
   table. Do not drop while any row exists without first confirming
   with the team why data is there if nothing writes to it in code.
6. **Retire `recommendation_history`.** Same reasoning and same
   removal sequence as `global_settings` -- confirm zero rows, confirm
   `data_export_service.py` is updated to stop referencing it (or
   confirm the removal there first, in its own change), then drop.
   `recommendation_snapshots` remains the real "what did we recommend"
   record; no functionality is lost by removing this table.

None of steps 5-6 are performed here. They are documented so a future,
explicitly-scoped cleanup migration can execute them deliberately, with
its own production-data verification step, rather than as a side
effect of unrelated feature work.
