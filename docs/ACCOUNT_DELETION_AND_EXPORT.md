# Account Deletion, Data Export & Retention (Phase 13, P13.6)

The complete, authoritative reference for what happens when a Baseerah
customer deletes their account, what they can export, what's retained
and why, and how stale data is cleaned up over time. `docs/DATABASE_
SECURITY_AND_RETENTION.md` covers the broader PII/encryption/backup
picture and cross-references this document for everything below.

**A note on legal framing**: this document describes engineering
behavior and configurable policy defaults. It is not legal advice and
does not represent a confirmed determination of what Saudi Arabia's
Personal Data Protection Law (PDPL), or any other jurisdiction's law,
requires. Retention periods below are deliberately implemented as
configuration (`Settings.session_retention_days`, `Settings.
token_retention_days`), not hardcoded, specifically so a real legal
review can change them without a code change. See `docs/LEGAL_AND_
DISCLOSURES.md` (Phase 13 P13.17, not yet written) for that review.

## 1. Self-service account deletion -- `DELETE /api/v1/auth/me`

### Request

```
DELETE /api/v1/auth/me
X-CSRF-Token: <csrf_token cookie value>
{"password": "<current account password>"}
```

### Preconditions and guards

1. **Authentication required.** No session cookie -> `401
   unauthenticated`.
2. **Staff accounts are blocked outright.** `is_staff=True` (SUPPORT/
   ADMIN/OWNER) -> `403 staff_account_self_deletion_blocked`,
   regardless of the password supplied. Staff identities are
   operational, not customer accounts, and this route has no concept
   of "is there still at least one OWNER left" the way a deliberate
   staff off-boarding process would need -- an OWNER self-deleting here
   could leave the platform with zero OWNERs and no path back in
   (mirrors `CannotModifyOwnStaffRoleError`'s reasoning,
   `docs/ADMIN_AND_RBAC.md` §3). Revoking staff access first (`POST
   /api/v1/admin/users/{id}/staff-role`, another OWNER, required) is
   the only path to ever making this account eligible for self-service
   deletion.
3. **Password re-authentication required.** Wrong password -> `401
   invalid_credentials`, account untouched. This is a real credential
   check, not "you have a valid session, click delete" -- a
   hijacked-but-not-fully-compromised browser session (e.g. an
   unattended unlocked laptop) cannot destroy the account outright.
4. **Billing/audit history blocks the delete.** If the account has any
   `Invoice` row (ever billed, regardless of payment outcome) or is the
   actor on any `AuditLog` entry, the database's own foreign-key
   `RESTRICT` blocks the delete -> `409 account_has_billing_history`,
   with customer-facing wording pointing at support. See §3 for why
   this is deliberate, not a bug.

### What happens on success

- The `User` row is hard-deleted (`session.delete(user)`), and every
  table with an `ON DELETE CASCADE`/`SET NULL` policy toward `users.id`
  reacts accordingly -- see §3 for the full table-by-table breakdown.
- All session cookies (`access_token`, `refresh_token`, `csrf_token`)
  are cleared on the response.
- No separate "revoke all sessions" step is needed for correctness:
  `get_current_user` looks the user up by ID on every request, so once
  the row is gone, any still-unexpired access token from a different
  device is rejected on its very next use (`401 unauthenticated`) --
  the same idempotency this gives for free: **a second `DELETE
  /api/v1/auth/me` call with the same now-stale cookie 401s cleanly,
  never a 500, and never "succeeds" against nothing.**

### Verified by

- `tests/unit/auth/test_user_service.py` -- wrong password, correct
  password, billing-history block, staff-account block.
- `tests/integration/api/test_auth_routes.py` -- full route behavior
  including idempotency (`test_deleting_an_already_deleted_account_is_
  a_clean_401_not_a_500`), cross-user isolation (`test_delete_own_
  account_can_never_target_another_user`,
  `test_delete_own_account_ignores_an_injected_target_user_id_in_the_
  request_body`), and the staff block
  (`test_delete_own_account_blocks_a_staff_account`).
- `tests/unit/auth/test_account_deletion_data_policies.py` -- the FK
  policy itself (§3), including a manual, one-off verification run
  against real PostgreSQL 16 during development (upgrade, downgrade,
  round-trip, and the actual CASCADE/SET NULL/RESTRICT behavior end to
  end -- not just structural migration-chain checks).

## 2. Data export -- `GET /api/v1/auth/me/export`

Returns a single JSON document (`src/auth/data_export_service.py`)
built entirely in memory -- nothing is ever written to a temp file, so
there is no "expired export" state to manage or clean up. Rate-limited
(5/minute) and authenticated exactly like every other `/auth/*` route;
always scoped to `get_current_user`'s own resolved identity, never a
caller-suppliable id.

### Contents

| Section | Source | Notes |
|---|---|---|
| `profile` | `User` | id, email, full_name, is_email_verified, created_at, last_login_at |
| `subscription` | `Subscription` | plan, status, trial/period dates, cancel_at_period_end |
| `sessions` | `UserSession` | device_label, ip_address, issued_at, last_used_at, expires_at, revoked_at |
| `portfolios` | `Portfolio` + `PortfolioHolding` + `PortfolioNewsAlert` | name, cash_balance, holdings, news alerts, nested per portfolio |
| `watchlists` | `UserWatchlist` + `UserWatchlistItem` | name, symbols, nested per watchlist |
| `settings` | `UserSetting` | raw `preferences_json` |
| `notifications` | `Notification` | type, title, body, read_at |
| `invoices` | `Invoice` + `Payment` | amount, currency, status, dates; payments nested per invoice |
| `feedback` | `Feedback` | category, message, page_context |
| `support_tickets` | `SupportTicket` | subject, message, status |
| `recommendation_history` | `RecommendationHistory` | symbol, recommendation, confidence, source, viewed_at |
| `reports` | `Report` | report_type, title, status, file_url |

### Deliberately excluded

- `User.password_hash` (never leaves the system in any form).
- `UserSession.refresh_token_jti`/`family_id` -- internal token
  material, even though `refresh_token_jti` is itself a one-way hash,
  not the raw token.
- `EmailVerificationToken`/`PasswordResetToken` rows -- token hashes,
  no customer-facing value.
- `AIRequest` rows -- aggregate platform cost/usage accounting
  (`GET /api/v1/admin/usage/ai`), not a customer-facing product
  feature.
- Any other user's data -- every query is filtered by the caller's own
  `user.id`; there is no code path that accepts a different id.

### Properties proven by tests

- **Deterministic**: two calls against unmodified data produce
  byte-identical JSON (`test_export_is_deterministic`) -- every list is
  explicitly `.order_by()`'d, nothing depends on unordered DB iteration.
- **JSON-serializable** by construction (`test_export_is_json_
  serializable`) -- `Decimal`/`datetime`/enum values are all converted
  to `float`/ISO-8601 string/`.value` before being placed in the
  export dict, never left as a raw SQLAlchemy type.
- **Cross-user isolation**: `test_export_never_includes_another_users_
  data` (unit) and `test_export_own_data_never_leaks_another_users_
  email` (integration) seed a second user's data and assert none of it
  appears anywhere in the caller's own export.

## 3. Referential integrity: what happens to each table when a user is deleted

Before Phase 13 P13.6, **every** foreign key referencing `users.id`
(except `user_sessions`/`subscriptions`, which already cascaded at the
SQLAlchemy ORM level) had no `ON DELETE` clause at all -- Postgres's
implicit default, `NO ACTION`, functionally identical to `RESTRICT`.
That's correct for financial/audit records, but it meant deleting an
account -- admin or self-service -- would fail for almost any customer
who had ever actually used the product: one portfolio, one watchlist,
a single notification was enough to block it outright.

Migration `c4d8e6f19a2b_add_user_deletion_fk_policies` assigns a
deliberate policy per data category instead:

| Category | Tables | Policy | Reasoning |
|---|---|---|---|
| Purely personal | `notifications`, `user_watchlists` (+ `user_watchlist_items`), `user_settings`, `recommendation_history`, `reports`, `portfolios` (+ `portfolio_holdings`, `portfolio_analysis_snapshots`, `portfolio_news_alerts`) | **CASCADE** | No independent retention value once the owning user is gone -- these rows exist only to serve that one customer |
| Independently valuable | `ai_requests.user_id`, `feedback.user_id`, `support_tickets.user_id` (made nullable in this migration), `support_tickets.assigned_staff_user_id` | **SET NULL** | The row has value beyond who the user was: aggregate AI cost/usage accounting, product feedback content, a support conversation's substance for quality review. Retained, anonymized. |
| Financial / security-audit | `invoices.user_id`, `audit_logs.actor_user_id` | **Unchanged (`NO ACTION`/`RESTRICT`)** | Must never be silently discarded or anonymized away -- deleting an account with either blocks the delete outright, exactly as already tested since Phase 10 (`test_owner_cannot_delete_a_user_with_non_cascading_related_records`) |

Every cell in that table was verified twice: once as a fast SQLite
regression suite (`tests/unit/auth/test_account_deletion_data_
policies.py`, `PRAGMA foreign_keys=ON`, run on every CI build) and once
by hand against a real PostgreSQL 16 instance during development
(seed one row per category, delete the user, assert CASCADE rows are
gone / SET NULL rows survive with `user_id IS NULL` / RESTRICT raises
`IntegrityError`) -- SQLite's own FK enforcement is standard SQL and
matches Postgres's here, but the real-Postgres pass is the one that
actually matters for production correctness.

## 4. Retention and cleanup -- `src/auth/retention_cleanup_service.py`

Beyond the account-deletion cascades in §3, two categories of data
naturally accumulate over time regardless of whether anyone ever
deletes their account, and are purged by a separate, idempotent
cleanup pass:

| What | Retention window (default) | Setting |
|---|---|---|
| Revoked or quietly-expired `UserSession` rows | 30 days | `SESSION_RETENTION_DAYS` |
| Expired `EmailVerificationToken`/`PasswordResetToken` rows (consumed or not) | 7 days | `TOKEN_RETENTION_DAYS` |

Both are pure storage reclamation, never a behavior change: a revoked/
expired session is already excluded from every "list my active
sessions" read path the moment it's revoked or expires, and an expired
token can never be redeemed regardless (`email_verification_service`/
`password_reset_service` both reject it on expiry before this cleanup
ever runs). Deleting the row destroys no functionality, only stale
data that would otherwise grow forever.

**Idempotent by construction**: every delete is a plain `WHERE
<column> < cutoff` condition. Running the cleanup twice in a row (or
concurrently) always converges to "every stale row is gone" -- the
second run deletes zero additional rows
(`test_running_cleanup_twice_in_a_row_is_idempotent`).

**Invocation**: `scripts/run_retention_cleanup.py` (a standalone CLI,
`DATABASE_URL=... python3 scripts/run_retention_cleanup.py`) or call
`run_retention_cleanup(session)` directly. **Not wired to a live
scheduler in this milestone** -- the same "build the callable service
now, wire scheduling later" pattern this codebase already used for
`src.market_data.ingestion.scheduler`/`src.market_intelligence.
scheduler`, both of which existed as plain functions before either got
an actual scheduler on top. A future milestone can add a periodic job
(reusing the existing `IngestionScheduler` pattern) with zero change to
the underlying service.

**Explicitly not covered**: `Invoice`/`Payment`/`AuditLog` retention --
financial and security-audit records are retained deliberately (§3);
a retention *cleanup* job must never be the mechanism that discards
them. "Expired temporary exports" (mentioned in the original P13.6
brief) does not apply to this implementation -- §2's export has no
temp-file/persisted state to expire in the first place.

## 5. Audit trail

Every self-service action here is logged via structured application
logging (`logging.getLogger(__name__)`, formatted through the same
`JSONFormatter`/`mask_dict_values` pipeline every other log line in
this codebase already goes through -- P13.2):

- `"Self-service account deletion requested."` -- logged before the
  password check even runs, so a blocked/failed attempt is still
  visible.
- `"Self-service account deletion blocked -- staff account."`
- `"Self-service account deletion blocked by retained billing/audit
  history."`
- `"Self-service account deletion completed."`
- `"Self-service data export requested."` / `"...completed."`

Every one of these log calls carries exactly one extra field --
`user_id` (an integer, never PII) -- proven by
`tests/unit/auth/test_account_deletion_export_log_redaction.py`, which
captures real log output through the actual `JSONFormatter` (not a
mock) and asserts no line ever contains the password, the password
hash, or any field beyond `user_id`.

**Why not the `AuditLog` SQL table?** `AuditLog` is explicitly scoped
to admin/staff actions (its own docstring says so), and more
fundamentally, `AuditLog.actor_user_id` is a `NOT NULL` foreign key to
`users.id` with no cascade (§3, deliberately RESTRICT) -- a row saying
"user X deleted themselves" could never coexist with user X's own row
actually being gone. Representing this event there would require
either violating that FK or weakening the exact RESTRICT guarantee
P13.4/P13.6 depend on elsewhere for real audit integrity. Structured
logs have no such constraint. Every *admin*-initiated action (staff
role changes, bulk session revocation, subscription cancellation, user
suspend/delete) already goes through `AuditLog` via `record_admin_
action` -- unchanged by this milestone, see `docs/ADMIN_AND_RBAC.md`.

## 6. Known limitations (disclosed, not implemented in this milestone)

- **No soft-delete/anonymization path for accounts blocked by billing
  history.** A customer with real invoices who wants to be forgotten
  currently must contact support, who has no built-in "anonymize this
  account" admin action yet (only suspend and hard-delete exist). If a
  future legal review determines erasure must always be possible
  regardless of billing history, this is the gap to close --
  deliberately deferred as a policy question (`docs/LEGAL_AND_
  DISCLOSURES.md`, P13.17), not an engineering one.
- **No admin-triggered export** -- only the account owner can export
  their own data; there's no `GET /api/v1/admin/users/{id}/export` for
  a support agent fulfilling a request on a customer's behalf.
- **Retention windows are engineering defaults**, not a confirmed legal
  requirement for any specific jurisdiction (see the note at the top of
  this document).

See `docs/DATABASE_SECURITY_AND_RETENTION.md` for the PII inventory,
encryption posture, and backup strategy this document doesn't repeat,
and `docs/ADMIN_AND_RBAC.md` for the admin-side (non-self-service)
account management surface.
