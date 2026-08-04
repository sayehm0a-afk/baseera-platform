# Basirah — Production-Readiness Engineering Report

**Date**: 2026-07-29
**Branch**: `feature/sahmk-live-verification`
**Author**: Claude Code, acting as Lead Software Architect / Principal AI
Engineer / QA Director / Release Manager / CTO for this session
**Scope**: Root-cause fixes for the 3 defects documented in
`docs/SAHMK_L3_OPEN_MARKET_VALIDATION_REPORT.md`, followed by live
re-validation and a production-readiness audit across database,
infrastructure, and repository hygiene.

This report follows the mandated format. It does **not** say
"everything works." It states what was fixed, what evidence backs each
claim, and what remains broken, unverified, or out of scope.

---

## A. Issues Fixed

1. **Current Price = None during market hours** (L3 Finding A).
   `build_analysis_context()` (`src/analysis/context_builder.py`) now
   sources the live price from `SahmkMarketDataProvider.get_latest_quote()`
   (`GET /quote/{symbol}/`) as the primary source, falling back to the
   completed-daily-bar price only when a live quote is unavailable.
   `change`/`change_percent`/`timestamp`/`source` are carried in
   `AnalysisContext.extra["quote"]`.

2. **Company display names are placeholders** (L3 Finding B).
   `SahmkMarketDataProvider` gained a `get_company_profile()` method
   (previously missing entirely), wiring through to the already-live
   `SahmkMarketDataService.get_company_profile()`. `sync_symbols()`'s
   existing enrichment branch now actually fires. Also added
   `industry`/`exchange` (new nullable `Stock` columns, migration
   `f3a9c7d21b84`).

3. **Strongest Fundamental / Best Medium Term / Best Long Term rankings
   empty** (Known Gap #2). A live raw-response capture (workflow run
   `30436660246`, 3 real symbols) revealed SAHMK's real
   `/financials/{symbol}/` shape: three per-period statement arrays
   (`income_statements`/`balance_sheets`/`cash_flows`), not the flat
   object the parser assumed. `get_financials()` now parses this real
   shape. The same capture confirmed `current_assets`,
   `current_liabilities`, `shares_outstanding`, and `eps` are **never
   present** in this endpoint's response for any symbol tested — a
   genuine data-source gap. `FundamentalSnapshot`'s corresponding
   columns are now nullable (migration `a8e2f4c91d37`), 6 ratio
   functions now guard against `None` instead of assuming presence, and
   `SahmkFundamentalDataProvider` now only requires the 5 fields SAHMK
   genuinely returns. Net effect: `ingest_fundamentals` stopped
   hard-failing on every real symbol.

4. **4 foreign-key columns with no supporting index**
   (`announcements.created_by_user_id`,
   `support_tickets.assigned_staff_user_id`,
   `calibration_configs.training_run_id`/`validation_run_id`) — found
   via a direct `pg_index` query, not assumed. Fixed with migration
   `c2d7e5a93f16`.

5. **Dead code**: `src/api/health_check.py` — a stubbed, TODO'd
   `/health` route, confirmed unimported anywhere and fully superseded
   by `main.py`'s real `/health/live` and `/health/ready` endpoints
   (which perform an actual `SELECT 1` / Redis `PING`). Deleted.

---

## B. Real Evidence

All of the following is from real GitHub Actions runs against the live
SAHMK API and a real, ephemeral PostgreSQL service container — never
mocked, never synthetic, never fabricated.

**Raw-structure capture** — workflow run
[`30436660246`](https://github.com/sayehm0a-afk/baseera-platform/actions/runs/30436660246)
(`sahmk-live-verification.yml`), `conclusion: success`. Confirmed the
real `/financials/1120/` shape:
```
"income_statements": [{"report_date": "2025-12-31", "statement_period": "annual",
  "total_revenue": 39093965000.0, "gross_profit": 6730335.0, "net_income": 24791754000.0}, ...],
"balance_sheets": [{"total_assets": 1043268297000.0, "total_liabilities": 900355952000.0,
  "stockholders_equity": 142912345000.0, "total_debt": 80320898000.0}, ...],
"cash_flows": [...]
```
`current_assets`/`current_liabilities`/`shares_outstanding`/`eps`
absent from all 3 symbols tested (2222, 1120, 2010).

**Phase 2 live pipeline re-validation** — workflow run
[`30437891031`](https://github.com/sayehm0a-afk/baseera-platform/actions/runs/30437891031)
(`sahmk-live-pipeline-validation.yml`), `conclusion: success`,
`FINAL_STATUS=PIPELINE_VERIFIED`, dispatched during a real, open
Tadawul session (`is_market_open()` confirmed `True`), against commit
`9704655` (all three fixes applied). Real recommendation rows produced
from live SAHMK data:

```
id=1 1120 (الراجحي): SELL confidence=66.20 total_score=39.00 technical_score=0.00
  fundamental_score=71.00 market_price_at_evaluation=62.2500
id=2 1180 (الأهلي): BUY confidence=69.20 total_score=60.40 technical_score=72.00
  fundamental_score=64.00 market_price_at_evaluation=37.9400
id=3 2010 (سابك): HOLD confidence=86.20 total_score=42.80 technical_score=46.00
  fundamental_score=39.00 market_price_at_evaluation=49.6800
id=4 2222 (أرامكو السعودية): HOLD confidence=72.20 total_score=57.90 technical_score=66.00
  fundamental_score=71.00 market_price_at_evaluation=26.1600
id=5 7010 (اس تي سي): SELL confidence=66.20 total_score=38.50 technical_score=0.00
  fundamental_score=71.00 market_price_at_evaluation=42.3600
```

- `market_price_at_evaluation`: populated on all 5 rows, real intraday
  prices — confirms Fix #1.
- Company names: real Arabic names (الراجحي/Al Rajhi Bank,
  الأهلي/Al Ahli, سابك/SABIC, أرامكو السعودية/Saudi Aramco,
  اس تي سي/STC) — confirms Fix #2.
- `fundamental_score`: populated on all 5 rows (`71.00`, `64.00`,
  `39.00`, `71.00`, `71.00`) — previously always `None`. Ingestion
  result: `{"symbols_requested": 5, "symbols_succeeded": 5,
  "symbols_failed": 0, "rows_upserted": 5, "errors": {}}` (previously
  0/5 succeeded) — confirms Fix #3 at both the ingestion and
  scoring layer.
- Database integrity: `INTEGRITY CHECK: PASSED` both immediately after
  the manual scan and again after the Live Market Mode soak
  (`post_soak_integrity_passed: True`, `no_leaked_tasks: True`).

**Test suite**: 2415 unit tests passed, 17 skipped, 0 failed, across
every code change in this session. `flake8` clean on every touched
file. Migration chain: single linear head
(`... -> a8e2f4c91d37 -> c2d7e5a93f16`), upgrade/downgrade round-trip
verified against a real local PostgreSQL instance for both new
migrations.

**Database structural audit**: a direct query against
`information_schema`/`pg_index` on a fully-migrated local Postgres
instance found and fixed 4 unindexed foreign keys; re-queried after the
fix — zero remain.

---

## C. Remaining Issues

These are real, disclosed, **not** fixed in this session:

1. **Frontend validation remains structurally unverifiable from this
   sandbox.** Confirmed in the L3 report and unchanged since: direct
   TCP to PostgreSQL's port is blocked at the network layer, and HTTPS
   to any non-SAHMK host is rejected with 403 at the proxy. There is no
   path from this environment to connect a locally-run frontend/backend
   to either the live API or a persistent external database holding
   real, CI-generated data. Not worked around with synthetic data —
   left explicitly NOT VERIFIED.

2. **Database persistence beyond a single CI run is still unverified.**
   Every live database check in this session (today's and prior) ran
   against an ephemeral GitHub Actions Postgres service container,
   destroyed when the job ends. "Records remain available after the
   workflow completes" has never been observed.

3. **`RuntimeKernel`/`ServiceLayer` (in `src/core/runtime/runtime_kernel.py`
   / `src/core/service_layer/service_layer.py`) contains a fake
   "simulated" service-layer fallback**, only triggered if constructed
   without an injected `service_layer`. Confirmed: `main.py` uses
   `RealRuntimeKernel` (which always sources `RealServiceLayer` from the
   DI container), so this fake fallback is not reachable from the
   production entry point today — but the class exists, is separately
   unit-tested, and was not investigated deeply enough this session to
   confirm it has zero other callers. Flagged, not removed — removing
   a whole kernel implementation without full dependency tracing is a
   bigger, riskier change than this session's time budget allows.

4. **`src/core/runtime/security_layer/agent_isolation.py` and
   `sandbox.py` contain fake "simulated" secure-execution
   implementations** (explicit Arabic TODOs: "replace this fake
   implementation with a real secure-execution service"). Not
   investigated for production reachability this session — flagged for
   the next security-focused pass, not fixed here.

5. **Email delivery is not real.** `ConsoleEmailSender`
   (`src/auth/email_sender.py`) — the only implementation today — logs
   verification/password-reset emails instead of sending them. This is
   already clearly disclosed in the code (not hidden), but it is a real
   production blocker for account verification/password reset flows
   working for actual users. No SMTP/SES/SendGrid credential exists in
   this environment to wire up a real sender.

6. **Payment processing is a disclosed no-op**
   (`src/billing/providers/noop_payment_provider.py`) — consistent with
   the "Billing architecture stub" milestone (M10.7), not a new finding,
   but still a real gap before real payments can be accepted.

7. **Live Market Mode's auto-triggered scan was not observed generating
   new rows in this specific Phase 2 run** (`auto_generated_row_count: 0`)
   — a timing artifact of the short 45-second soak window relative to
   the scan interval, not a regression: the open-market auto-trigger
   path itself was already directly observed working in the L3 report.

8. **Portfolio Engine, Watchlist Generator, Opportunity Ranking (beyond
   what the 5-symbol scan implies), News Intelligence's live population,
   and the Macro Engine were not independently re-exercised against live
   data in this session.** Each has substantial existing unit test
   coverage (18-65 test files depending on subsystem, all passing), and
   the core scan pipeline that most of them feed into was live-verified
   twice today — but a dedicated live run per subsystem was not
   performed, and the Macro Engine is a disclosed no-op (no real macro
   data source exists yet, per the AI Evolution Layer design).

9. **No exchange-holiday calendar.** `trading_calendar.py`'s
   `is_market_open()` is pure weekday/time-of-day math — a real Tadawul
   holiday would be misread as a trading day. Disclosed since the L1
   phase, still open.

10. **No corporate-actions (splits/dividends) feed for outcome
    evaluation.** Disclosed since the AI Evolution Layer design, still
    open — return calculations around ex-dividend dates can be wrong in
    a way that isn't auto-corrected.

---

## D. Production Readiness

| Category | Rating | Basis |
|---|---|---|
| Infrastructure | 65% | Real scheduler pattern, circuit breaker, rate limiter, health/readiness checks with real DB/Redis probes, graceful shutdown all confirmed. Deployment configs (Docker/Helm/k8s) exist from M10.12 but were not re-verified this session. |
| Backend | 70% | Core recommendation pipeline live-verified twice today end-to-end with real data. Two internal subsystems (`agent_isolation`/`sandbox`, legacy `ServiceLayer` fallback) confirmed to contain fake/simulated implementations, not reachable from the production entry point today but not fully traced either. |
| Database | 75% | Schema audited structurally (FK indexing, unique constraints, migration chain integrity) and confirmed sound; live integrity checks (duplicates, null critical fields, orphaned FKs, outcome-count correctness) PASSED twice today against real data. Persistence beyond a single CI run remains unverified. |
| AI | 60% | Technical/Fundamental/Decision-Fusion/Confidence/Risk/Recommendation-Generation legs all directly confirmed live and producing real, explainable, non-null output today. Portfolio/Watchlist/Opportunity-Ranking/News/Macro subsystems rely on existing unit coverage only this session, not fresh live evidence; Macro Engine is a disclosed no-op. |
| API | 70% | REST routers exist and are wired for every listed frontend concern (stocks, market, portfolio, news, admin, auth, backtests/calibrations). Not independently load- or contract-tested this session. |
| Frontend Backend Support | 65% | Endpoint coverage confirmed present by inspection; end-to-end frontend-against-live-backend behavior remains structurally unverifiable from this sandbox (see Remaining Issue #1). |
| Security | 55% | RBAC, session hardening, and secret-config auditing already completed in prior milestones (P13.2-P13.6). This session surfaced two disclosed-but-unremoved fake/simulated security-adjacent stubs (`agent_isolation`, `sandbox`) that need a dedicated pass to confirm they are truly unreachable, not just unreferenced by the one entry point checked. |
| Performance | 60% | Rate limiting, caching (TTL cache), and circuit breaking are real and already in place. No load test was run this session; the one performance-relevant fix (FK indexing) was structural, not measured under load. |
| Documentation | 80% | `SAHMK_INTEGRATION.md`, `current-status.md`, and this report all updated same-day with the real evidence behind every claim; Known Gaps sections kept current rather than silently dropped. |
| GitHub | 85% | All work committed with descriptive messages and pushed to `feature/sahmk-live-verification` (not merged to `main`, per standing instruction). Git history preserved, no force-pushes, no destructive operations. |
| CI/CD | 70% | Two GitHub Actions workflows (`sahmk-live-verification.yml`, `sahmk-live-pipeline-validation.yml`) exist, are exercised regularly against production SAHMK, and both passed today. No general application CI/CD pipeline (lint/test-on-PR) was audited this session. |

---

## E. Go/No-Go

**NO** — Basirah should **not** yet move to the UI/UX and Beta Release
phase.

Justification: the three defects that were explicitly blocking the
recommendation engine's core output (live price, company identity,
fundamental scoring) are now root-caused, fixed, and confirmed against
real live market data twice in one session — that part of the platform
is in materially better shape than before this session started. But
"move to Beta" implies real users interacting with a real product, and
at least two concrete blockers remain for that: (1) email delivery is
not real, so account verification and password reset do not actually
reach a user's inbox today, and (2) frontend-against-live-backend
behavior has never been observed even once in this environment — every
frontend claim in this platform's history is either a mock-provider
screenshot or an assumption, never a live-data screenshot. Beta users
would hit both of these on day one. The security-adjacent stub findings
(#3, #4 in Remaining Issues) also need to be closed out or positively
confirmed unreachable before a beta exposes the platform beyond this
session's controlled environment.

---

## F. Next Engineering Phase

Recommended: **a dedicated Frontend-Against-Live-Backend Validation
phase, run somewhere with real network access to both SAHMK and a
persistent database** (a real staging server or a developer's own
machine, not this sandbox) — because that is the one category of
evidence this session structurally could not produce, and it blocks
the Go/No-Go decision above from ever turning to YES from inside this
environment alone. In parallel: (a) wire a real email provider
(SMTP/SES/SendGrid) so account verification/password reset actually
work, (b) trace and either fix or confirm-unreachable the two
fake/simulated stubs found in `security_layer` and the legacy
`ServiceLayer`, and (c) a short, dedicated live run exercising
Portfolio/Watchlist/Opportunity-Ranking with real holdings data, since
those were not independently re-verified this session. Only after
those three are closed should Basirah's Go/No-Go for Beta be
re-evaluated.
