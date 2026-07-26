# Production Configuration (Phase 13, P13.2)

This document is the authoritative map of every backend and frontend
configuration variable this codebase reads, what it controls, what
happens if it's missing, and what changed in this audit. It is not a
duplicate of `.env.example`/`frontend/.env.example` (those are for
copy-pasting into a real `.env`); this is for understanding *why* each
one exists and what its absence means.

## 1. Architecture

- **Backend**: `src/core/config/settings.py`'s `Settings`
  (`pydantic-settings`, `BaseSettings`) is the single source of truth
  for connectivity/security/auth/subscription/billing/monitoring
  config. It is built once at import time as the module-level
  `settings` singleton (`@lru_cache` on `get_settings()`), so a broken
  production configuration fails at process boot, not at the first
  request that happens to touch it.
- **Everything else stays where it already was.** Per-subsystem
  business-logic tuning (`src/backtesting/config.py`,
  `src/market_intelligence/config.py`,
  `src/portfolio_intelligence/config.py`,
  `src/news_intelligence/config.py`,
  `src/market_data/ingestion/config.py`) keeps reading its own env vars
  via plain `os.getenv()`, exactly as every prior phase built it. This
  audit did not fold those into `Settings` — none of them are secrets
  or connectivity concerns, each already has a safe default, and
  centralizing them would be unrelated churn, not a security or
  production-readiness improvement.
- **Frontend**: Next.js's built-in `NEXT_PUBLIC_*` convention. There is
  no server-only frontend config today — the frontend never talks to
  SAHMK/OpenAI/the database directly, only to the backend API.

## 2. Fail-fast guarantees

Two, both enforced by `Settings`'s `@model_validator`/`@field_validator`,
both verified by `tests/unit/core/config/test_settings.py`:

1. **`BASEERA_ENV` must be exactly `development`, `staging`, or
   `production`** — any other value raises at boot.
2. **`SECRET_KEY` cannot be unset (or left at the published insecure
   development default) while `BASEERA_ENV=production`** — raises
   immediately with an explicit message, before the app ever accepts a
   request.

Nothing else in `Settings` is fail-fast-enforced today. `TRUSTED_HOSTS`
in particular is **not** hard-required in production (see §4) because
the correct value depends on deployment topology (reverse proxy,
platform-generated domain) that `Settings` cannot know at its own
definition time — it must be set explicitly before staging/production
sign-off (tracked as a Gate B/Gate P item in
`docs/LAUNCH_READINESS_REPORT.md` once written), but an empty value
degrades to "not enforced," not a crash.

## 3. Full variable reference (backend)

| Variable | Field | Default | Production requirement |
|---|---|---|---|
| `BASEERA_ENV` | `environment` | `development` | Must be `production` in prod (obviously) |
| `DATABASE_URL` | `database_url` | local Postgres | Real managed Postgres DSN |
| `REDIS_URL` | `redis_url` | unset | Preferred single-DSN form for managed Redis (Railway/Render/Upstash/Redis Cloud/ElastiCache) |
| `REDIS_HOST`/`REDIS_PORT`/`REDIS_PASSWORD` | `redis_host`/`redis_port`/`redis_password` | `localhost`/`6379`/unset | Fallback when `REDIS_URL` unset |
| `SECRET_KEY` | `secret_key` | insecure dev default | **Required** — see §2 |
| `CORS_ALLOWED_ORIGINS` | `cors_allowed_origins_raw` | empty (no CORS) | Set to the real frontend origin(s) |
| `TRUSTED_HOSTS` | `trusted_hosts_raw` | empty (not enforced) | **Should** be set — see §4 |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | `access_token_expire_minutes` | 15 | — |
| `REFRESH_TOKEN_EXPIRE_DAYS` | `refresh_token_expire_days` | 30 | — |
| `EMAIL_VERIFICATION_TOKEN_EXPIRE_HOURS` | `email_verification_token_expire_hours` | 24 | — |
| `PASSWORD_RESET_TOKEN_EXPIRE_HOURS` | `password_reset_token_expire_hours` | 1 | — |
| `TRIAL_LENGTH_DAYS` | `trial_length_days` | 14 | Business decision, not a secret |
| `BILLING_NOOP_AUTO_APPROVE` | `billing_noop_auto_approve` | `true` | Must be replaced by a real provider before real payments — see `docs/PAYMENT_PROVIDER_INTEGRATION.md` |
| `RATE_LIMIT_ENABLED` | `rate_limit_enabled` | `true` | Keep enabled |
| `LOG_LEVEL` | `log_level` | `INFO` | — |
| `SENTRY_DSN` | `sentry_dsn` | unset (opt-in) | Recommended for production |
| `OPENAI_API_KEY` | `openai_api_key` | unset | Required for real News Intelligence analysis; unset degrades to an honest "unavailable" state, never a fabricated result |

Everything under `SAHMK_*`, `INGESTION_*`, `MARKET_*`,
`PORTFOLIO_*`, `NEWS_*` (other than `NEWS_LLM_MODEL`, listed above via
`OPENAI_API_KEY`'s section), and `BACKTEST_*` is a per-subsystem
`os.getenv`-based tuning knob, not part of `Settings` — see each
subsystem's own `config.py` for its full list and defaults.

## 4. This audit's changes

1. **`REDIS_URL`/`REDIS_PASSWORD` support added.** Before this audit,
   `token_store.py` (session revocation — an auth-critical path) could
   only connect to an unauthenticated `host:port` Redis; no code path
   supported a password at all for it, and `RealTaskQueue` had the same
   gap. Every managed Redis provider requires a password (or a full
   authenticated DSN). Fixed via `Settings.redis_dsn` (prefers
   `REDIS_URL`, else assembles `redis://[:password@]host:port/0`) used
   by `token_store.get_redis_client()`, and a `password` parameter
   added to `RealTaskQueue.__init__` (mirroring `RedisMessageBus`,
   which already supported it) wired through
   `dependency_injection.py`. No existing test's constructor call
   signature changed.
2. **`TrustedHostMiddleware` added**, gated on `Settings.trusted_hosts`
   (empty by default — not enforced, so every existing deployment keeps
   working unchanged). Defends against Host-header injection (cache
   poisoning, a spoofed `Host` in a password-reset link). **This is a
   real gap that must be closed before production sign-off** — set
   `TRUSTED_HOSTS` to the real API domain(s) once that's known.
3. **CORS reading de-duplicated.** `main.py` previously re-parsed
   `CORS_ALLOWED_ORIGINS` via its own independent `os.getenv` call
   instead of using `Settings.cors_allowed_origins` (which already
   existed and does the same parsing). Now there is exactly one place
   this list is derived from the env var. This is a **behavior
   change**: previously, `main.py`'s CORS decision ignored a `.env`
   *file* entirely (only real process env vars), because raw
   `os.getenv` doesn't read `.env` files — only `pydantic-settings`
   does. Now it's consistent with every other `Settings` field: a
   `.env` file value is honored exactly like a real env var. This is
   the more correct behavior (one config-loading mechanism, not two),
   and is covered by `tests/integration/api/test_cors.py`.
4. **Secret masking added to structured logging.**
   `src/core/monitoring/secret_masking.py` (new) provides
   `mask_secret()`/`mask_dict_values()`/`is_sensitive_field_name()`.
   `JSONFormatter.format()` (`structured_logging.py`) now masks any
   `extra_fields` value whose key name looks sensitive (contains
   `secret`, `password`, `api_key`, `token`, `credential`,
   `authorization`, `dsn`, `connection_string`, case-insensitive)
   before it's written to a log line — defense in depth against a
   future call site accidentally passing a raw secret into
   `logger.info(**extra_fields)`. Verified: no existing code path
   currently logs a full secret (grepped for `logger`/`print` calls
   referencing `database_url`/`secret_key`/`SAHMK_API_KEY`/
   `OPENAI_API_KEY` — none found).
5. **`init_logging()` now respects `LOG_LEVEL`** — previously hardcoded
   to `"INFO"` regardless of `Settings.log_level`.
6. **`.gitignore` hardened**: `.env.local`/`.env.production` (two
   specific names) replaced with a `.env.*` catch-all (plus
   `!.env.example` to keep the example trackable) — now also correctly
   ignores `.env.staging`, `.env.test`, any future `.env.<name>`.
   Added `*.pem`, `*.key`, `*.crt`, `*.p12`, `*.pfx`, `id_rsa*`,
   `id_ed25519*`, `credentials.json`, `*-credentials.json`,
   `service-account*.json`, and database dump/backup patterns
   (`*.dump`, `*.sql.gz`, `*.backup`, `pgdata/`, `pg_dump_*/`).
7. **`.env.example` rewritten** to be complete and current: every
   `Settings` field now has a documented entry; two dead variables from
   an earlier revision (`API_KEY`, `OPENAI_MODEL` — neither read by any
   code path) were removed; `TADAWUL_API_KEY` (also unread — SAHMK
   fully superseded it) was removed. `frontend/.env.example` created
   (previously did not exist).
8. **Git history secret scan (P13.2 requirement)**: searched the full
   `git log --all -p` for OpenAI-style keys (`sk-...`), AWS access key
   IDs (`AKIA...`), PEM private key headers, any committed `.env` file
   (as opposed to `.env.example`), and non-placeholder `SECRET_KEY`/
   `SAHMK_API_KEY`/`password=`/embedded-credential `DATABASE_URL`
   assignments. **Result: no real secret found anywhere in this
   repository's history** — every match was a clearly-labeled
   placeholder (`your_..._here`, `password`, `your_db_password`) in
   `.env.example`, a Helm values template, or a deployment script.

## 5. Known gaps carried forward (disclosed, not fixed in this pass)

- **`TRUSTED_HOSTS` is not yet set anywhere** — it must be configured
  with the real staging/production domain before those environments go
  live; until then Host-header validation is not enforced (matches this
  repo's every other "secure-by-default-once-configured, permissive
  until then" pattern — CORS, SAHMK live-data, the ingestion
  scheduler).
- **No real email provider is wired** (`src/auth/email_sender.py`'s
  `ConsoleEmailSender` — logs the verification/reset link instead of
  sending it, explicitly not for production use). Closing this
  requires an external account decision (SES, SendGrid, Postmark, or a
  Saudi-based provider) — a genuine external blocker, not something
  this audit can complete without that decision.
- **No real payment provider is wired** — see
  `docs/PAYMENT_PROVIDER_INTEGRATION.md` (Phase 13 P13.6).
- **Per-subsystem tuning knobs remain scattered `os.getenv` calls**,
  not part of `Settings`. This is a deliberate architectural choice
  (§1), not an oversight, but it does mean there is no single
  `Settings`-level validation for e.g. `BACKTEST_MAX_SYMBOLS` being a
  sane integer — each subsystem already validates its own env vars at
  its own read site.
