# Authentication Security (Phase 13, P13.3)

A production-grade audit of the full customer authentication flow
(`src/auth/`, `src/api/routes/auth.py`), extending — never rebuilding —
the architecture Phase 10 established. This document records what was
already strong, what this audit found and fixed, and what remains a
disclosed gap.

## 1. What was already correct (Phase 10, confirmed by this audit)

- **Refresh-token rotation with reuse detection.**
  `session_service.refresh_session()`: every `/auth/refresh` call
  revokes the presented token and issues a new one in the same
  `family_id`. Presenting an already-rotated-away token revokes the
  *entire* family — the standard stolen-refresh-token defense. Verified
  by `tests/integration/api/test_auth_routes.py::test_refresh_rotates_cookies_and_old_refresh_token_is_dead`.
- **Refresh tokens are stored hashed**, never in plaintext — `UserSession.refresh_token_jti`
  holds `hash_token(raw_token)` (`src/auth/token_hashing.py`), and the
  raw value is set only as the httpOnly cookie, never persisted, never
  returned in a JSON body.
- **Access tokens are short-lived, stateless JWTs**, algorithm-pinned
  (`algorithms=["HS256"]`, never derived from the token's own header —
  immune to the classic "alg: none" / algorithm-confusion attack
  classes), with an explicit `"type": "access"` claim checked on decode.
- **"Sign out everywhere" actually works**, including for
  already-issued, still-unexpired access tokens: `User.tokens_invalid_before`
  is the O(1) escape hatch `get_current_user` checks against every
  access-token JWT's `iat`, precisely because a stateless JWT can't be
  revoked by a session-table delete alone.
- **HttpOnly, `SameSite=Lax`, environment-aware `Secure` cookies** for
  access/refresh tokens; a non-httpOnly double-submit `csrf_token`
  cookie, verified against `X-CSRF-Token` by `CSRFMiddleware` on every
  non-GET `/api/v1/*` request.
- **Password reset flow already forces "sign out everywhere"**
  (`password_reset_service.reset_password()` calls
  `session_service.revoke_all_sessions()`) — a leaked-and-reset password
  can't be used to keep an attacker's existing session alive.
- **IDOR protection on session management**: `DELETE
  /auth/sessions/{id}` checks `user_session.user_id != current_user.id`
  and returns 404 (not 403) either way — `SessionNotFoundError`'s own
  docstring states the reasoning: a caller must never be able to
  distinguish "not yours" from "doesn't exist," which would otherwise
  let session IDs be enumerated across accounts.
- **`/auth/forgot-password` already returns the same generic message**
  regardless of whether the email is registered, by design (the route's
  own comment states this explicitly) — the base case of user-enumeration
  prevention was already correct for this endpoint.
- **Privilege escalation**: no self-service route lets a customer set
  their own or another user's `is_staff`/`staff_role`. `AuthRepository.set_staff_role()`
  exists but has no REST route calling it yet at all (see §5, a
  disclosed gap pointing to P13.4's RBAC/admin milestone, not a
  vulnerability — there is no exposed path to reach it from outside the
  codebase). Every admin route requiring elevated action
  (`delete_user`) is already gated `require_staff_role(StaffRole.OWNER)`.
- **Open redirect**: not applicable. Grepped the full backend and
  frontend for any redirect-target query parameter (`?next=`,
  `?redirect_uri=`, etc.) — none exists anywhere in this codebase.
  `RequireSession.tsx`'s redirect to `/login` is a hardcoded literal, not
  attacker-influenced input.

## 2. What this audit found and fixed

### 2.1 User-enumeration via login response timing (fixed)

`user_service.authenticate()` previously read:

```python
if user is None or not verify_password(password, user.password_hash):
```

Python's `or` short-circuits: `verify_password()` (a deliberately slow
bcrypt comparison) was **never called at all** when `user is None`. A
request for a non-existent email therefore returned measurably faster
than one for a registered email with a wrong password — a timing oracle
an attacker can use to enumerate registered addresses even though both
cases return the identical `invalid_credentials` message.

**Fix**: a real bcrypt verification now always runs, against a
precomputed dummy hash (`_DUMMY_PASSWORD_HASH`) when no user was found,
so the "unknown email" and "known email, wrong password" code paths do
the same amount of cryptographic work. Verified by
`test_authenticate_takes_a_real_password_verification_pass_for_an_unknown_email`
(spies on `verify_password` and asserts it was called with the dummy
hash, not skipped).

### 2.2 Missing rate limits (fixed)

Before this audit, `@limiter.limit(...)` was only applied to
`/auth/login`, `/auth/register`, `/auth/forgot-password`. Added:

| Route | Limit | Rationale |
|---|---|---|
| `/auth/verify-email` | 10/minute | Explicit P13.3 requirement; the token itself is a long random value (impractical to brute-force regardless), this is defense-in-depth |
| `/auth/refresh` | 30/minute | Each call is a DB write + Redis write; without a limit, a compromised or buggy client could hammer this endpoint |
| `/auth/reset-password` | 5/minute | The actual token-*consumption* endpoint (distinct from `/auth/forgot-password`, which only *issues* a token and was already limited) — guards against reset-token brute-forcing |

Verified by `tests/integration/api/test_auth_rate_limiting.py` (real
Redis-backed slowapi, not mocked — each test actually exceeds the
configured limit within the window and asserts a `429` appears).

### 2.3 Rate limiter's Redis connection didn't support authentication (fixed)

`src/api/middleware/rate_limiting.py` built its Redis `storage_uri` from
`settings.redis_host`/`settings.redis_port` directly, bypassing the
`REDIS_URL`/`REDIS_PASSWORD` support this same Phase 13 session added to
`Settings` in P13.2. Fixed to use `settings.redis_dsn` — one Redis
connection string derivation, used everywhere now.

### 2.4 No per-account lockout (fixed)

Only an IP-based rate limit existed (`/auth/login`, 10/minute) — an
attacker rotating source IPs was completely unconstrained against any
single target account. Added a genuinely separate, complementary
mechanism:

- `User.failed_login_attempts` (int, default 0), `User.locked_until`
  (nullable timestamp) — migration `a3f7c9e21b04`.
- `LOGIN_LOCKOUT_MAX_ATTEMPTS` (default 5), `LOGIN_LOCKOUT_DURATION_MINUTES`
  (default 15) — new `Settings` fields.
- A wrong password increments the counter; on reaching the threshold,
  `locked_until` is set and the counter resets to 0 (so unlocking
  requires the same number of *fresh* failures again, not an
  ever-accumulating count). A successful login resets both to their
  defaults.
- A locked account is rejected (`AccountLockedError`, HTTP 429, code
  `account_locked`) **before** any password check runs — no bcrypt work
  is spent on a login attempt against a currently-locked account.

**Disclosed trade-off**: `AccountLockedError`'s message and status code
necessarily differ from `InvalidCredentialsError`'s, and this differs
*only* for accounts that exist (a nonexistent email can never become
locked) — so once an account has failed enough logins to lock, its
existence becomes distinguishable from a non-existent one via this one
specific response. This is the standard, industry-accepted trade-off of
any account-lockout mechanism (Google, GitHub, and most other major
providers all have this same property) and is considered acceptable
here — the alternative (no lockout at all) is a strictly worse security
posture for a financial platform. Verified by
`test_repeated_wrong_passwords_lock_the_account` (unit) and
`test_repeated_wrong_passwords_lock_the_account_via_the_login_route`
(integration, real 429 through the actual route).

### 2.5 Session records were missing "last used time" (fixed)

The P13.3 requirement is explicit: session records must include
created/last-used/expiration/revoked time.
`UserSession` already had `issued_at`/`created_at`/`expires_at`/`revoked_at`
but no "last used." Added `UserSession.last_used_at` (migration
`a3f7c9e21b04`), defaulting to creation time — because refresh-token
rotation revokes the old row and creates a brand-new one on every
`/auth/refresh`, the *current* (non-revoked) row's own `issued_at` ==
`last_used_at` == the true time that rotation chain was last used,
without any extra "touch on use" write on the hot path. Exposed in both
`GET /auth/sessions` (`SessionOut.last_used_at`) and the admin `GET
/api/v1/admin/sessions` (`AdminSessionOut.last_used_at`).

## 3. Password policy

Enforced today (`src/api/schemas/auth.py`'s Pydantic validators — not
re-audited/changed in this pass, confirmed already present and
adequate): a minimum length requirement at the schema layer, and
`password_hashing.py`'s 72-byte bcrypt ceiling rejected explicitly
(never silently truncated, which would silently weaken a long
password). Hashing is real `bcrypt` (not `passlib`, which is
unmaintained and incompatible with current `bcrypt` releases per this
module's own docstring) with a fresh random salt per password
(`bcrypt.gensalt()`).

## 4. Authorization coverage (spot-audited, not exhaustively re-tested this pass)

Confirmed via direct code read, not new tests, given the scope of "one
test per protected API" across this entire platform:

- Every `/api/v1/admin/*` route requires `require_staff_role(...)`, at
  the minimum role the action warrants (`ADMIN` for suspend/view,
  `OWNER` for hard-delete).
- Every `/api/v1/portfolio/*` route scopes to the authenticated user via
  `_get_portfolio_or_404`, 404 (not 403) for another user's portfolio —
  the same IDOR-safe pattern session revocation uses.
- `require_active_subscription()` composes cleanly with
  `require_staff_role(...)` (staff bypass), confirmed by reading
  `src/auth/rbac.py` directly.

**Not done in this pass**: a full authorization test matrix (every
route × every role × every ownership combination) — a genuinely large
undertaking given the number of routes across nine registered routers.
Recommended as an explicit, scoped follow-up once P13.4 (RBAC/admin)
adds the still-missing staff-role-change route (§1's disclosed gap) and
the admin frontend, so the matrix can be built once against a stable
surface rather than twice.

## 5. Known gaps carried forward (disclosed)

- **No REST route exists yet to grant/revoke staff access**
  (`AuthRepository.set_staff_role()` is unreachable from any router
  today) — P13.4's explicit scope, not a P13.3 gap, since P13.3 is
  customer-authentication hardening and this is an owner/admin
  capability.
- **No email provider is wired** — `ConsoleEmailSender` logs the
  verification/reset link instead of sending it (disclosed in
  `docs/PRODUCTION_CONFIGURATION.md` §5) — a genuine external-account
  blocker, not something this audit resolves.
- **No MFA** — architecture-ready in the sense that `User`/session
  model additions here follow the same additive-migration pattern MFA
  would need (e.g. a `mfa_enabled`/`mfa_secret_encrypted` column pair
  and an extra verification step in `session_service.create_session()`),
  but not implemented — full production MFA depends on an external
  provider decision per the Phase 13 brief.
- **Full authorization test matrix** — see §4.

See `docs/THREAT_MODEL.md` for the structured threat inventory this
audit was organized against.
