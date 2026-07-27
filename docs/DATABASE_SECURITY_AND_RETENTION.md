# Database Security & Data Retention (Phase 13, P13.6)

An audit of what customer data Baseerah actually stores, how it's
protected in transit and at rest, how long it's kept, and what a
customer can do about their own data -- referenced as a placeholder
from `docs/THREAT_MODEL.md`'s "explicitly out of scope" section; this
is that document.

## 1. PII inventory (what's actually stored)

Grepped every domain model in `src/domain/models/` for personally
identifiable fields. The surface is deliberately minimal:

| Model | PII fields | Notes |
|---|---|---|
| `User` | `email` (required), `full_name` (optional) | No phone number, national ID, or date of birth is collected anywhere in this codebase |
| `UserSession` | `ip_address`, `device_label` (User-Agent string) | Operational/security data (session review, abuse investigation), not marketing data |
| `AuditLog` | `ip_address` | Same -- who did what, from where, for incident response |
| `Portfolio`/`PortfolioHolding` | None beyond `user_id` ownership | Manual-entry only (Phase 8) -- no broker/bank account linkage exists anywhere, confirmed by grep across the whole `portfolio_intelligence` package. Cascades on account deletion (`docs/ACCOUNT_DELETION_AND_EXPORT.md` §3) |
| `Invoice`/`Payment` | `provider_reference`, `provider_transaction_id` | No card number, CVV, or bank account/IBAN field exists anywhere in the schema -- `provider="noop"` today (no real gateway); a real gateway integration (P13.6's sibling milestone, `docs/PAYMENT_PROVIDER_INTEGRATION.md`) must keep this true by using the gateway's own tokenized-checkout flow, never collecting raw card data server-side |
| `SupportTicket`/`Feedback` | Free-text `message` (customer-authored, may incidentally contain PII the customer chooses to include) | No structured PII field beyond `user_id` |

**Confirms the Phase 13 non-negotiable rule "never store bank or
brokerage credentials"** -- there is no field anywhere in the schema
that could hold one; this isn't a policy enforced by validation, it's
architecturally absent.

## 2. Encryption in transit

- **Browser <-> API**: cookies are marked `Secure` whenever
  `settings.is_production` is true (`src/api/routes/auth.py::
  _set_session_cookies`) -- forces HTTPS-only transmission in
  production; TLS termination itself is the deploying platform's
  responsibility (a reverse proxy/load balancer), not application code,
  consistent with how `docker-compose.yml` and the Dockerfile are
  structured (no TLS cert handling inside the app container).
- **API <-> Postgres**: `DATABASE_URL` is a plain connection string
  today (`postgresql://user:pass@host:port/db`) with no `sslmode`
  parameter hardcoded into `src/core/db/database.py`. This is correct,
  not a gap: every managed Postgres provider (RDS, Cloud SQL, Railway,
  Render, Supabase) issues a connection string with `?sslmode=require`
  (or stronger) already appended, and hardcoding a weaker default in
  code would silently override a stricter provider default. **Action
  required at deploy time** (documented here, not enforced by
  fail-fast in `Settings` since the correct value is
  provider-dependent, same posture as `TRUSTED_HOSTS`): confirm the
  production `DATABASE_URL` includes `sslmode=require` or the
  provider's equivalent before go-live -- tracked as a P13.15 (staging
  deployment) checklist item.
- **API <-> Redis**: same reasoning -- `REDIS_URL`/`rediss://` (TLS)
  is honored via `Settings.redis_dsn` (P13.2); whether the actual
  production value uses `rediss://` is a deploy-time configuration
  choice, not something this codebase can enforce at the network layer.

## 3. Encryption at rest

Handled entirely by the hosting platform's managed database offering
(volume/disk encryption) -- no column-level application encryption
exists for any field. This is a deliberate, currently-adequate choice
given the PII inventory in §1: nothing stored today (email, full name,
IP address, manual-entry portfolio holdings) rises to the level that
column-level encryption is the standard mitigation for (that's reserved
for national ID numbers, payment credentials, or health data -- none of
which this schema holds). Revisit this decision if/when a field like a
national ID (for regulatory KYC) is ever added.

## 4. Password and session data

Already audited in full in `docs/AUTHENTICATION_SECURITY.md` --
bcrypt-hashed passwords (never reversible, never logged --
`mask_dict_values` additionally masks any field named `password`/
`token`/etc. as defense-in-depth, P13.2), refresh tokens stored hashed
(`hash_token`, never the raw value), access tokens are stateless JWTs
never persisted at all. Not repeated here.

## 5. Backup and disaster recovery

Fully documented in `docs/architecture/backup-strategy.md` (Phase 10
M10.12): daily `pg_dump`, 7-day local retention, documented restore
procedure, explicit disclosure of what's out of scope (PITR, off-host
storage) and why. Reviewed as part of this audit and found still
accurate and adequate for the platform's current stage (pre-revenue,
no paying customers yet) -- no changes made.

## 6. Data retention and the right to deletion/access

**New in P13.6**: `DELETE /api/v1/auth/me` (self-service account
deletion, with a real per-category referential-integrity policy --
CASCADE/SET NULL/RESTRICT depending on data type, never one blanket
default), `GET /api/v1/auth/me/export` (self-service data export), and
`src/auth/retention_cleanup_service.py` (idempotent cleanup of stale
sessions/tokens). Before this milestone, the *only* way to delete a
customer's data was the admin-only, OWNER-gated `DELETE /api/v1/admin/
users/{id}` route (Phase 10), there was no export path at all, and
nearly every foreign key to `users.id` had no `ON DELETE` policy,
meaning self-service deletion would have failed for almost any account
that had actually used the product.

Full detail -- the exact per-table CASCADE/SET NULL/RESTRICT policy,
every guard on the deletion route (staff-account block, password
re-check, billing-history block, idempotency), the complete data-export
contents/exclusions table, the retention-cleanup windows and their
`Settings` fields, and the audit-trail logging design -- lives in
**`docs/ACCOUNT_DELETION_AND_EXPORT.md`**, not repeated here.

**Suspension vs. deletion, restated for this document's scope**:
`is_active=False` (admin suspend) is the *reversible*, audit-preserving
action; hard delete (admin or self-service) is the *irreversible* one.

**Known limitations** (disclosed, see `docs/ACCOUNT_DELETION_AND_
EXPORT.md` §6 for the full list): no soft-delete/anonymization
alternative yet for accounts blocked by billing history, no
admin-triggered export on a customer's behalf, and the retention
windows are engineering defaults pending a real legal review
(`docs/LEGAL_AND_DISCLOSURES.md`, P13.17).

## 7. Migration safety

Confirmed (re-verified as part of this audit, not new work): every
migration in `migrations/versions/` has a real `downgrade()`, the
Alembic revision chain is linear and single-headed (`alembic history`
shows no branches, matching the P13.1 branch-integrity finding), and
`docker-entrypoint.sh` runs `alembic upgrade head` before starting the
app, aborting startup on migration failure (Phase 10 M10.12) --
correctness is enforced at the deployment level, not left to an
operator remembering to run it manually.

See `docs/AUTHENTICATION_SECURITY.md` and `docs/ADMIN_AND_RBAC.md` for
the account-security and staff-access sides of data protection this
document doesn't repeat.
