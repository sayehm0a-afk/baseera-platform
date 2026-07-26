# Admin & RBAC (Phase 13, P13.4)

The complete picture of who can do what on Baseerah, and every admin
capability actually exposed today. Extends -- never rebuilds -- the
RBAC architecture Phase 10 established (`src/auth/rbac.py`,
`src/api/routes/admin/*`); this document records what already existed,
what P13.4 added to close the disclosed gaps, and what remains
explicitly out of scope for this milestone.

## 1. The two orthogonal axes

Baseerah's access model is deliberately **two separate columns, not one
combined role enum** (Phase 10 plan, decision 1):

- **`User.is_staff` + `User.staff_role`** -- *who works at Baseerah*.
  Rare, hand-assigned, ranked `OWNER > ADMIN > SUPPORT`
  (`src/auth/rbac.py::_ROLE_RANK`). `require_staff_role(StaffRole.ADMIN)`
  also admits an `OWNER`, never a `SUPPORT`.
- **`Subscription.status`** -- *what a customer's account currently is*.
  Automatic, time-driven: `TRIALING, ACTIVE, PAST_DUE, CANCELED, EXPIRED`.

Conflating these breaks the moment a subscription is
canceled-vs-expired-vs-past-due, or a staff member also wants a paid
account. They compose independently: `require_active_subscription()`
gives staff an unconditional bypass (an internal account
reviewing/support-testing a premium feature is not a billing concern),
confirmed unchanged by this audit.

### Subscription lifecycle (as of P13.4)

```
TRIALING --(period ends, lazily)--> EXPIRED
ACTIVE   --(period ends, lazily)--> EXPIRED
CANCELED --(period ends, lazily)--> EXPIRED   <- new in P13.4, see below
```

`_ENTITLED_STATUSES` (`src/subscriptions/subscription_service.py`) now
reads `(TRIALING, ACTIVE, CANCELED)` -- **P13.4 added `CANCELED`**. This
was a real gap, not a style choice: before this fix, an admin
cancelling a subscription (`cancel_subscription(..., immediately=False)`,
the standard "cancel at period end" behavior) would have stripped the
customer's access *immediately*, contradicting both the function's own
intent and standard subscription-product behavior (a customer who paid
for a month keeps that month). `get_effective_subscription()`'s
existing lazy-downgrade-on-read mechanism (Phase 10 decision 9) needed
no change at all to correctly demote a `CANCELED` subscription to
`EXPIRED` once its `current_period_end` actually passes -- the same
code path already used for `TRIALING`/`ACTIVE` handles it uniformly.
`immediately=True` cuts access off right now by pulling
`current_period_end` back to the current time, so the very next read
lazily expires it.

## 2. Every `/api/v1/admin/*` capability

All staff-gated via `require_staff_role(...)`; every mutating action is
recorded to `AuditLog` via `src.admin.audit_log.record_admin_action`.
Minimum role noted per route; `OWNER` implicitly satisfies any `ADMIN`
requirement.

| Router | Route | Min. role | Notes |
|---|---|---|---|
| `users.py` | `GET /users`, `GET /users/{id}` | ADMIN | |
| | `POST /users/{id}/suspend` \| `/unsuspend` | ADMIN | |
| | `POST /users/{id}/staff-role` | **OWNER** | **New in P13.4** -- grants/revokes `is_staff`/`staff_role`. Blocks an OWNER from changing their own row (`CannotModifyOwnStaffRoleError`, 409) -- see §3. |
| | `DELETE /users/{id}` | OWNER | Hard delete; DB `RESTRICT` blocks it if the user has real financial/audit history (`user_has_related_records`, 409) -- suspend instead. |
| `subscriptions.py` | `GET /subscriptions`, `GET /subscriptions/{user_id}` | ADMIN | |
| | `POST /subscriptions/{user_id}/extend-trial` | ADMIN | |
| | `POST /subscriptions/{user_id}/activate` | ADMIN | Explicit admin override (comped account / payment confirmed outside the system) -- never fabricates an Invoice/Payment. |
| | `POST /subscriptions/{user_id}/cancel` | ADMIN | **New in P13.4** -- `{"immediately": false}` (default) keeps access until period end; `{"immediately": true}` cuts it off now. See §1's lifecycle fix. |
| `sessions.py` | `GET /sessions`, `GET /sessions/user/{user_id}` | ADMIN | |
| | `DELETE /sessions/{session_id}` | ADMIN | Revokes one session (e.g. a reported stolen device). |
| | `DELETE /sessions/user/{user_id}` | ADMIN | **New in P13.4** -- revokes every active session for a user in one call, reusing `session_service.revoke_all_sessions` (the same "sign out everywhere" logout-all/password-reset already use), so it also instantly invalidates any already-issued access token via `User.tokens_invalid_before`, not just the DB rows. Pairs naturally with `suspend`. |
| `billing.py` | `GET /billing/users/{user_id}/invoices` | ADMIN | **New in P13.4** -- read-only invoice history. |
| | `GET /billing/invoices/{invoice_id}/payments` | ADMIN | **New in P13.4** -- read-only payment-attempt history for one invoice. No route in this file can create/mutate billing state -- only `billing_service` (a real webhook, or the production-blocked `simulate_dev_payment_success`) ever does. |
| `announcements.py` | `GET/POST/PATCH/DELETE /announcements*` | ADMIN | Platform-wide banners. |
| `feature_flags.py` | `GET/POST/PATCH /feature-flags*` | ADMIN | Runtime on/off switches, distinct from env-level `Settings`. |
| `audit_log.py` | `GET /audit-log` | ADMIN | Filterable by `actor_user_id`/`action`. |
| `usage.py` | `GET /usage/ai` | ADMIN | Real `AIRequest` aggregates (tokens, cost, success/fail/timeout, by feature). |
| `analytics.py` | `GET /analytics` | ADMIN | Real `COUNT()` aggregates: users by staff role, subscriptions by status/plan, portfolios, backtest runs. |
| `system.py` | `GET /system/health` | ADMIN | Live DB (`SELECT 1`) + Redis (`PING`) probes. |
| | `GET /system/summary` | ADMIN | **New in P13.4** -- consolidated dashboard landing view: app version, `DEPLOYMENT_COMMIT` (honest `null` if unset -- never fabricated), environment, DB/Redis health, ingestion + market-intelligence scheduler running state, market-data provider + its health, new users (24h/7d), logins (24h), currently-locked accounts. |

Every route above was exercised by `tests/integration/api/test_admin_routes.py`
(44 tests as of P13.4) against real FastAPI routing + in-memory SQLite,
not mocked at the route layer.

## 3. Owner bootstrap

`POST /users/{id}/staff-role` is `OWNER`-only by design -- it is the
one route that can create another `OWNER`, so it must require an
existing `OWNER` to call it. This is correct but creates a genuine
bootstrap problem: **a brand-new deployment has no `OWNER` yet**, and
no route can ever grant one to itself.

**New in P13.4**: `scripts/bootstrap_owner.py`, an operator-run CLI
(never exposed over HTTP) that either creates a new `OWNER` account or
promotes an existing one:

```bash
DATABASE_URL=postgresql://... python3 scripts/bootstrap_owner.py --email owner@baseerah.sa
```

The password is always read interactively via `getpass` when creating
a new account -- never accepted as a CLI argument or environment
variable, so it never lands in shell history or a process listing.
Promoting an already-existing account needs no password at all. Run
this once, immediately after the first production database migration,
by whoever holds deploy access.

**Self-modification is blocked**: `set_staff_role` additionally refuses
to let an `OWNER` change their own `is_staff`/`staff_role`
(`CannotModifyOwnStaffRoleError`, 409) -- without this, a single
mis-clicked call could strip every `OWNER` from the platform with no
path back in except re-running the bootstrap script directly against
production, which is a far worse failure mode than requiring a second
`OWNER` (or the bootstrap script) to make the change instead.

## 4. What this milestone found and closed

Audited against the full P13.4 capability checklist (RBAC correctness,
subscription lifecycle correctness, and every "admin can..." action a
real Baseerah operator needs day one):

1. **`is_entitled()` didn't honor `CANCELED` until period end** -- a
   real correctness bug in the *default* cancellation path, not a
   missing feature. Fixed (§1).
2. **No route could grant/revoke staff access at all** -- disclosed as
   a gap in `docs/AUTHENTICATION_SECURITY.md` §5 and
   `docs/THREAT_MODEL.md` T13 (Phase 10/P13.3 both correctly identified
   this as *not reachable*, i.e. not currently exploitable, but also
   not yet *usable* by a real owner). Closed (§2).
3. **No way to force-logout every session for one user in a single
   call** -- only single-session revoke existed; suspending a
   compromised account didn't also kill its live sessions. Closed
   (§2).
4. **No path to the very first `OWNER` account** -- `set_staff_role`
   being `OWNER`-gated is correct, but with zero code to bootstrap the
   first one, a fresh deployment would have had no way to ever reach
   the admin API at all. Closed (§3).
5. **No consolidated "is everything OK" view** for an operator --
   `system/health` existed but only covered DB/Redis; nothing
   surfaced scheduler state, provider health, or recent
   registration/login/lockout activity in one call. Closed (§2,
   `system/summary`).
6. **`Invoice`/`Payment` models existed with no admin visibility** --
   billing rows could be created by `billing_service` but no staff
   member could ever see them without a raw DB query. Closed (§2,
   `billing.py`).

## 5. Explicitly out of scope for this milestone

- **Admin frontend UI** -- tracked separately (Phase 10 plan M10.14);
  every capability above is currently API-only. A functional (not
  pixel-gold-plated, per the Phase 9 standard) `frontend/src/app/(admin)/`
  route group is the next piece of work.
- **Full authorization test matrix** (every route x every role x every
  ownership combination) -- `docs/AUTHENTICATION_SECURITY.md` §4
  already disclosed this as a P13.4-or-later follow-up; still not done
  as an exhaustive matrix, though every admin route's minimum-role gate
  is now covered by at least one direct test.
- **Unauthenticated ops-status endpoints at the FastAPI app root**
  (`GET /ingestion/status`, `GET /stats`, `GET /market-data-provider/status`
  in `main.py`) -- discovered incidentally while building
  `system/summary`. These predate Phase 10's RBAC layer entirely, sit
  outside `/api/v1/admin/*`, and carry no `require_staff_role` gate, so
  they currently leak internal operational detail (scheduler state,
  provider selection) to an unauthenticated caller. Not a P13.4 change
  (out of this milestone's scope: RBAC/admin-capability gaps, not a
  general endpoint audit) -- flagged here as a concrete, disclosed item
  for the P13.14 full security sweep.
- **`SUSPENDED`/`COMPLIMENTARY` subscription statuses** -- mentioned in
  the Phase 13 spec's target state; the current five (`TRIALING,
  ACTIVE, PAST_DUE, CANCELED, EXPIRED`) fully cover every capability
  built in this milestone (suspension is modeled at the `User.is_active`
  level, not the subscription level, and no comped-account flow needs
  a distinct status beyond the existing `admin_activate_subscription`
  override). Deferred to whichever future milestone actually needs the
  distinction, rather than adding unused enum values now.

See `docs/AUTHENTICATION_SECURITY.md` for the customer-authentication
audit this document's RBAC section builds on, and
`docs/THREAT_MODEL.md` for the structured threat inventory (T13,
staff-privilege-escalation, is updated by this milestone from "not
reachable" to "reachable only by an existing OWNER, self-modification
blocked").
