# Security + Production Readiness Audit (CONT Phase 12)

## Scope

A re-verification pass over auth, RBAC, secret handling, CORS, and
rate-limiting, performed fresh at the end of this continuation mandate
rather than assuming the earlier P13.2/P13.4/M6.16 audits (from prior
mandates on this same repository) still hold. Where this pass finds the
same conclusion those audits already reached, it says so and cites the
existing evidence rather than re-doing the work; it does not re-litigate
every finding those audits already made.

## 1. Repo-wide secret scan (fresh, this phase)

Full tracked-file scan for common real-secret shapes (`sk-[A-Za-z0-9]{20,}`,
AWS `AKIA...`, PEM private-key headers, Slack tokens): the only matches
were in `tests/unit/core/monitoring/test_secret_masking.py`, using the
obviously-synthetic fixture value `sk-abcdefghijklmnopqrstuvwxyz` to test
the masking function itself -- not a real credential.

`kubernetes/openai-secret.yaml` contains only the literal placeholder
string `<base64_encoded_openai_api_key>`, never a real value.

No `.env` file (or any `.env.*` variant other than the checked-in
`.env.example` templates) is tracked by git; `.gitignore` and
`frontend/.gitignore` both exclude `.env`/`.env.*` while explicitly
allow-listing `.env.example`.

**Type/location only, no values printed, per the mandate's own
instruction** -- summary: zero real secrets found in the repository.

## 2. Frontend secret exposure

Every `NEXT_PUBLIC_*` variable actually referenced in `frontend/src`
was enumerated: `NEXT_PUBLIC_SITE_URL`, `NEXT_PUBLIC_DEPLOYMENT_COMMIT`,
`NEXT_PUBLIC_API_BASE_URL`. All three are public-by-design values (a
site URL, a public commit SHA already shown in the OWNER dashboard, and
the backend's own public base URL) -- none is a credential.
`frontend/.env.example` itself documents the exact rule being followed:
"Next.js inlines any `NEXT_PUBLIC_*` variable into client code at build
time, so nothing prefixed `NEXT_PUBLIC_` may ever hold a [secret]."

## 3. Production secret-key guard (re-verified, not new)

`src/core/config/settings.py`: `secret_key` defaults to a clearly-named
`_DEV_INSECURE_SECRET_KEY` sentinel, and `Settings` refuses to start
in `is_production` mode while that sentinel is still active (line
~146-149) -- a real startup-time guard, not just a comment, preventing
the single most common "forgot to set SECRET_KEY in prod" failure mode.

## 4. CORS (re-verified, not new)

`main.py` wires `CORSMiddleware` with `allow_origins=settings.cors_allowed_origins`,
sourced from the `CORS_ALLOWED_ORIGINS` env var and defaulting to an
**empty list** (deny-all) when unset -- no wildcard `*` default exists
anywhere in the codebase.

## 5. Rate limiting (re-verified, not new)

`slowapi`'s `Limiter` is wired at app level in `main.py`
(`RateLimitExceeded` exception handler registered), and the heavy
market-data/decision routes (`/opportunities`, `/decision-v2`,
`/technical`) were already rate-limited in a prior mandate (Phase 3H).

## 6. RBAC re-verified this phase

Beyond the personal-performance OWNER-only check already re-verified in
Phase 11 of this continuation (`docs/OWNER_PERFORMANCE_CALIBRATION_AUDIT.md`),
this phase confirms every admin route file under `src/api/routes/admin/`
gates on either `require_staff_role(...)` or `require_any_staff_role(...)`
-- no admin route was found with an unauthenticated or under-scoped
dependency. The `/decision-intelligence` route intentionally uses the
broader `require_any_staff_role(ANALYST, ADMIN, OWNER)` (a general staff
dashboard, correctly not OWNER-restricted), which is the deliberate,
correct contrast against the `/personal-performance` route's strict
OWNER-only gate.

## 7. Full regression suites (this phase, after every code change above and in Phases 9-11)

- Backend: **3581 passed**, 4 skipped, 4 xfailed (`python3 -m pytest -q`).
- flake8: clean on every file touched this continuation mandate.
- Frontend: **169 passed** (`npx vitest run`), typecheck (`npx tsc --noEmit`)
  clean, lint (`npx eslint`) clean on every touched file, production
  build (`npm run build`) succeeded with all 39 routes generated
  (including the new `/more` route from Phase 7).

## Verdict

No new security issue was found in this phase; the repository's secret
handling, CORS policy, rate limiting, and RBAC gating were all
re-verified fresh rather than assumed, and all pass. Combined with the
Phase 9/10/11 audits (ranking integrity, outcome-tracking integrity,
owner-dashboard calibration), the codebase's security and integrity
posture is unchanged-and-confirmed-sound going into Phase 13
(commit/deploy/production-verify).
