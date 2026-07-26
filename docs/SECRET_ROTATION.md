# Secret Rotation Procedures (Phase 13, P13.2)

Every credential this platform depends on, what rotating it breaks,
and the exact steps to rotate it safely. None of these have real
production values configured yet (no staging/production deployment
exists as of this document) — this is the procedure to follow once
they do.

## General principles

- Rotate in a maintenance window when possible for anything that
  invalidates live sessions (SECRET_KEY) or briefly interrupts a
  dependent service (DATABASE_URL, REDIS_URL).
- Never log, screenshot, paste into chat, or commit a real secret value
  during rotation — every value below should move directly from the
  provider's dashboard into the deployment platform's secret store.
- After rotating, verify with the **masked** value only (see
  `src/core/monitoring/secret_masking.py`'s `mask_secret()` — the same
  masking a future admin diagnostics endpoint should use to show "yes,
  a key is configured" without ever displaying it).
- Update the deployment platform's environment variable, then restart
  the affected service. `Settings` is read once at process start
  (`@lru_cache`), so a running process never picks up a rotated value
  without a restart.

## SECRET_KEY (JWT signing)

**Blast radius: rotating this invalidates every currently-issued access
token immediately, and every refresh token on next use** (since
`src/auth/jwt_service.py` signs with it and refresh-token validation
paths that touch it — see `docs/AUTHENTICATION_SECURITY.md` for the
exact token architecture). Every logged-in user is forced to log in
again.

1. Generate a new value: `python3 -c "import secrets; print(secrets.token_urlsafe(64))"`.
2. Set it in the deployment platform's secret store as `SECRET_KEY`.
3. Restart the backend service.
4. Confirm `GET /health/ready` returns healthy and a fresh
   register/login flow succeeds.
5. Communicate to users (if this is an unplanned/incident rotation)
   that they'll need to log in again.

Rotate immediately (not on a schedule) if: the value was ever
accidentally logged, committed, or shared; a staff member with access
to it leaves; or any suspected compromise.

## DATABASE_URL (PostgreSQL credentials)

**Blast radius: every backend process needs the new value
simultaneously, or writes start failing for whichever processes still
hold the old one.**

1. In the Postgres provider, create a new role/password (don't just
   change the existing role's password without a rollback plan, unless
   the provider's rotation flow is atomic).
2. Update `DATABASE_URL` in the deployment platform's secret store.
3. Roll the backend service (rolling restart, not all-at-once, if
   running more than one instance).
4. Revoke the old role's password once every instance is confirmed on
   the new one.

## REDIS_URL / REDIS_PASSWORD

**Blast radius: every active refresh-token session lookup
(`src/auth/token_store.py`) and every message-bus/task-queue consumer
needs the new value.** A brief Redis reconnect blip degrades to "every
session needs to re-authenticate" (documented in `token_store.py`'s
own module docstring as the deliberate safe-degradation behavior of
the allowlist design) — it does **not** revalidate an already-revoked
session, so this is safe to rotate without a security regression, just
a availability blip.

1. Rotate the password/DSN at the Redis provider.
2. Update `REDIS_URL` (preferred) or `REDIS_PASSWORD` in the deployment
   platform's secret store.
3. Restart the backend and any worker/scheduler process.

## OPENAI_API_KEY

**Blast radius: none for existing sessions/data.** The News
Intelligence analyzer (`src/news_intelligence/analyzer.py`) already
treats a missing/invalid key as "unavailable" and degrades honestly
(persists collected-but-unanalyzed events, never fabricates a
classification) rather than crashing — so a rotation gap is a
temporary loss of new analysis, not an outage.

1. Generate a new key in the OpenAI dashboard.
2. Update `OPENAI_API_KEY` in the deployment platform's secret store.
3. Restart the backend.
4. Revoke the old key in the OpenAI dashboard once confirmed working
   (`POST /api/v1/news/refresh`'s `analyzer_available: true` in the
   response, staff-only route).

## SAHMK_API_KEY

**Blast radius: none for existing data.** Same honest-degradation
posture as `OPENAI_API_KEY` — an invalid/missing key makes
`src/market_data/provider_factory.py` fall back to
`DevMarketDataProvider` (clearly labeled synthetic data), never a
crash and never silently-presented-as-live data.

1. Generate a new key via the sahmk.sa account dashboard.
2. Update `SAHMK_API_KEY` in the deployment platform's secret store.
3. Restart the backend.
4. Confirm via `GET /api/v1/stocks/{symbol}/quote` for a known symbol
   that `is_synthetic: false` and `source` reflects the real provider.
5. Revoke the old key at sahmk.sa once confirmed.

## Email / payment provider credentials

Not yet applicable — no real email provider (`src/auth/email_sender.py`
is console-only) or payment provider (`src/billing/` is a no-op stub)
is wired as of this document. Once either is integrated, this document
must be updated with their specific rotation procedure before
production use — tracked as a prerequisite in
`docs/PAYMENT_PROVIDER_INTEGRATION.md` and the email-provider gap noted
in `docs/PRODUCTION_CONFIGURATION.md` §5.

## Emergency rotation (suspected compromise)

If any credential above is suspected compromised:

1. Rotate that credential immediately, following its section above,
   without waiting for a maintenance window.
2. For `SECRET_KEY` specifically: rotating it is itself the
   session-invalidation mechanism — no separate "revoke all sessions"
   step is needed on top of it, since every existing JWT stops
   verifying the moment the key changes.
3. For `DATABASE_URL`/`REDIS_URL`: rotate, then audit
   `AuditLog`/`AIRequest` (existing tables — see
   `docs/DATABASE_SECURITY_AND_RETENTION.md`) for activity in the
   suspected compromise window.
4. Document the incident per `docs/OBSERVABILITY_AND_INCIDENT_RESPONSE.md`
   once written (Phase 13 P13.14).
