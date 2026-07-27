"""RetentionCleanupService: purges auth-layer records that have
outlived their usefulness (Phase 13 P13.6 -- data retention). A thin
orchestration layer over `AuthRepository`'s own delete methods, exactly
the "business rules in one service, persistence in one repository"
split every other package in this codebase already uses.

Covers:
- Revoked/expired `UserSession` rows older than
  `settings.session_retention_days` (default 30) -- already excluded
  from every "active sessions" read path the moment they're revoked or
  expired; this only reclaims the storage, it changes no visible
  behavior.
- Expired `EmailVerificationToken`/`PasswordResetToken` rows older than
  `settings.token_retention_days` (default 7) -- an expired token can
  never be redeemed regardless (both services reject it on expiry
  before this cleanup ever runs), so deleting it destroys no
  functionality, only stale data.

Explicitly NOT covered here (see docs/DATABASE_SECURITY_AND_RETENTION.md
for the full reasoning, not repeated per-function below):
- Temporary export files -- there are none. `GET /api/v1/auth/me/export`
  (`data_export_service.py`) builds its JSON response entirely in
  memory and returns it directly; nothing is ever written to disk, so
  there is no "expired export" state to clean up.
- `Invoice`/`Payment`/`AuditLog` -- financial and security-audit
  records are retained deliberately (see the FK RESTRICT policy in
  migration `c4d8e6f19a2b`); a retention *cleanup* job must never be
  the thing that discards them.

Idempotency: every delete below is a plain `WHERE <column> < cutoff`
condition -- running this function twice in a row (or twice
concurrently) always converges to "every stale row is gone," and a
second run simply deletes zero additional rows. Safe to call from a
one-off script, a future scheduled job (not wired to a live scheduler
in this milestone -- see `scripts/run_retention_cleanup.py`), or a
test, with no state to reset between calls.
"""

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session

from src.auth.repository import AuthRepository
from src.core.config import settings

_repository = AuthRepository()


@dataclass(frozen=True)
class RetentionCleanupSummary:
    sessions_deleted: int
    email_verification_tokens_deleted: int
    password_reset_tokens_deleted: int

    @property
    def total_deleted(self) -> int:
        return self.sessions_deleted + self.email_verification_tokens_deleted + self.password_reset_tokens_deleted


def run_retention_cleanup(session: Session) -> RetentionCleanupSummary:
    """Runs every configured cleanup pass once and returns a summary of
    what was deleted -- the return value is the whole point of this
    being a function and not a fire-and-forget script: a caller (a
    scheduled job, an admin-triggered run, a test) can assert on it."""
    now = datetime.now(timezone.utc)
    session_cutoff = now - timedelta(days=settings.session_retention_days)
    token_cutoff = now - timedelta(days=settings.token_retention_days)

    sessions_deleted = _repository.delete_stale_sessions(session, session_cutoff)
    email_tokens_deleted = _repository.delete_stale_email_verification_tokens(session, token_cutoff)
    reset_tokens_deleted = _repository.delete_stale_password_reset_tokens(session, token_cutoff)

    return RetentionCleanupSummary(
        sessions_deleted=sessions_deleted,
        email_verification_tokens_deleted=email_tokens_deleted,
        password_reset_tokens_deleted=reset_tokens_deleted,
    )
