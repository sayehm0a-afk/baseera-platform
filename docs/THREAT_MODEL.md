# Threat Model (Phase 13, P13.3)

A structured threat inventory for Baseerah's authentication and account
layer, in the format this platform's `AuthRepository`/`session_service`/
`user_service` were actually audited against. This is the P13.3 slice
(auth-specific); the full-platform security review (SQLi, XSS, SSRF,
webhook forgery, etc.) is `docs/SECURITY_AUDIT_PHASE_13.md` (Phase 13
P13.14, not yet written as of this document).

## Assets

- Customer credentials (email + bcrypt hash — never plaintext, never
  reversible).
- Session state (refresh tokens, hashed in Postgres; access-token JWTs,
  stateless, signed with `SECRET_KEY`).
- Customer PII (email, full name — minimal today, see
  `docs/DATABASE_SECURITY_AND_RETENTION.md`, Phase 13 P13.7, not yet
  written).
- Subscription/entitlement state (who has paid access).
- Staff/admin privilege (`is_staff`/`staff_role`).

## Actors

- **Anonymous attacker** — no account, targets registration/login/
  password-reset surfaces.
- **Authenticated customer, malicious** — has a real account, targets
  other customers' data or tries to escalate privilege.
- **Compromised customer session** — an attacker who has stolen a
  cookie/token, not credentials.
- **Malicious/compromised staff account** — has legitimate elevated
  access, targets audit-evadable actions.
- **Network attacker (MITM)** — between customer and Baseerah, relevant
  to cookie/TLS posture.

## Threats and mitigations

| # | Threat | Actor | Mitigation | Status |
|---|---|---|---|---|
| T1 | Brute-force a specific account's password | Anonymous | Per-IP rate limit (`/auth/login`, 10/min) + per-account lockout (5 failures / 15 min) | **Mitigated** (P13.3 added lockout) |
| T2 | Enumerate registered emails via `/auth/register` | Anonymous | Distinct `email_already_registered` (409) is an intentional, disclosed exception — required so a real user gets a clear "you already have an account" message; `/auth/login`/`/auth/forgot-password` do NOT have this property (see T3/T4) | **Accepted, disclosed** (see `docs/AUTHENTICATION_SECURITY.md` §1) |
| T3 | Enumerate registered emails via `/auth/login` response timing | Anonymous | Constant-work password verification regardless of account existence (dummy-hash comparison) | **Mitigated** (P13.3, §2.1) |
| T4 | Enumerate registered emails via `/auth/forgot-password` | Anonymous | Always returns the same generic message + rate-limited | **Already mitigated** (Phase 10) |
| T5 | Enumerate registered emails via account-lockout response | Anonymous, targeted | A locked-account response differs from a wrong-password response, and only an existing account can lock | **Accepted, disclosed trade-off** (standard industry behavior — see §2.4 in AUTHENTICATION_SECURITY.md) |
| T6 | Steal a refresh token and replay it after the legitimate client rotates past it | Network/compromised-device attacker | Rotation-with-reuse-detection: presenting an already-rotated token revokes the entire session family | **Mitigated** (Phase 10) |
| T7 | Steal an access token and use it after logout | Compromised session | `tokens_invalid_before` instant-kill on logout/logout-all/password-reset | **Mitigated** (Phase 10) |
| T8 | CSRF against a cookie-authenticated mutating request | Malicious website the victim visits | Double-submit `csrf_token` cookie verified against `X-CSRF-Token` header by `CSRFMiddleware` on every non-GET `/api/v1/*` call; `SameSite=Lax` cookies as defense-in-depth | **Mitigated** (Phase 10) |
| T9 | Session fixation (attacker pre-sets a session ID, victim logs in, attacker reuses it) | Network attacker | Not directly applicable — sessions are server-issued opaque tokens on every login, never accepted as client input; a login always issues a fresh `family_id` | **Not applicable to this architecture** |
| T10 | JWT algorithm confusion (`alg: none`, HS256↔RS256 confusion) | Network/forgery attacker | `jwt.decode(..., algorithms=["HS256"])` — explicit single-algorithm allowlist, never derived from the token's own header | **Mitigated** (Phase 10) |
| T11 | IDOR: read/revoke another user's session | Authenticated malicious customer | `DELETE /auth/sessions/{id}` ownership-checked, 404 (not 403) either way | **Mitigated** (Phase 10) |
| T12 | IDOR: read/modify another user's portfolio | Authenticated malicious customer | `_get_portfolio_or_404` ownership-scoped, same 404-not-403 pattern | **Mitigated** (Phase 8/10) |
| T13 | Privilege escalation: customer grants themselves staff access | Authenticated malicious customer | `POST /api/v1/admin/users/{id}/staff-role` (P13.4) requires an existing OWNER and refuses to let an OWNER modify their own row — no code path lets a non-staff customer reach this at all, and no staff member can silently self-escalate | **Mitigated** (P13.4 — see `docs/ADMIN_AND_RBAC.md` §2–3) |
| T14 | Open redirect via a login-flow redirect parameter | Anonymous, phishing-adjacent | No redirect-target parameter exists anywhere in this codebase | **Not applicable** |
| T15 | Denial of service via unbounded `/auth/refresh` calls | Anonymous or compromised client | Now rate-limited (30/min) — was previously unlimited | **Mitigated** (P13.3, §2.2) |
| T16 | Denial of service / brute-force via unbounded `/auth/verify-email`, `/auth/reset-password` | Anonymous | Now rate-limited (10/min, 5/min respectively) — were previously unlimited | **Mitigated** (P13.3, §2.2) |
| T17 | Rate limiter itself becomes ineffective under multi-worker/multi-instance deployment | Anonymous, distributed | Redis-backed (not in-process) `Limiter` — shared budget across every worker/instance, not per-process | **Mitigated** (Phase 10) |
| T18 | Host-header injection (cache poisoning, poisoned password-reset link) | Network/application-layer attacker | `TrustedHostMiddleware`, gated on `TRUSTED_HOSTS` — added in P13.2, **not yet configured** for any real deployment | **Partially mitigated — requires deployment-time configuration** |
| T19 | Cross-origin credentialed request from an untrusted site | Malicious website | `CORS_ALLOWED_ORIGINS` explicit allowlist, never a wildcard with `allow_credentials=True` | **Mitigated** (Phase 10) |
| T20 | Secret leaked into logs (API key, password, token) | Insider/log-access attacker | `mask_dict_values()`/`is_sensitive_field_name()` in structured logging (P13.2) masks any suspiciously-named log field | **Mitigated** (P13.2) |
| T21 | Secret committed to Git history | Insider/repo-access attacker | Full `git log --all -p` scan (P13.2) — no real secret found; ongoing risk requires a pre-commit secret scanner, not yet added | **Audited clean; no ongoing automated prevention yet** |

## Explicitly out of scope for this document

- Payment/webhook forgery — `docs/PAYMENT_PROVIDER_INTEGRATION.md`
  (P13.6).
- SAHMK/OpenAI credential compromise — `docs/SECRET_ROTATION.md`
  (P13.2).
- Infrastructure-level threats (DDoS at the network layer, cloud
  provider compromise) — outside this application's control surface.
- Full OWASP Top 10 sweep (SQLi, XSS, SSRF, insecure deserialization,
  mass assignment) — `docs/SECURITY_AUDIT_PHASE_13.md` (P13.14).

## Residual risk summary

Of 21 threats enumerated: 16 mitigated (T13 moved from "not reachable"
to "mitigated" in P13.4 once the staff-role route was actually built —
see `docs/ADMIN_AND_RBAC.md`), 2 explicitly accepted and disclosed (the
unavoidable minimum enumeration surface any lockout/
duplicate-registration-detection mechanism has), 2 not applicable to
this architecture, 1 partially mitigated pending deployment-time
configuration (`TRUSTED_HOSTS`). No unmitigated Critical or High threat
was found in this specific slice (authentication/session/account) — the
broader platform sweep (P13.14) may surface others outside this
document's scope, including the unauthenticated root-level ops-status
endpoints disclosed in `docs/ADMIN_AND_RBAC.md` §5.
