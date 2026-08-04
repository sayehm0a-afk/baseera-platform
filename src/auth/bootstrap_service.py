"""bootstrap_first_owner: the one atomic operation behind
POST /api/v1/bootstrap/owner (src/api/routes/bootstrap.py) -- see that
route's docstring for the full threat model and why this exists at
all (no direct database access to run scripts/bootstrap_owner.py).

Atomicity: on PostgreSQL, a transaction-scoped advisory lock
(`pg_advisory_xact_lock`) serializes concurrent calls so two requests
racing to create "the first" OWNER can't both pass the zero-owner
check before either commits -- the second waits for the first
transaction to finish, then re-checks and correctly refuses. Skipped
on non-PostgreSQL dialects (the test suite's in-memory SQLite) since
`pg_advisory_xact_lock` doesn't exist there and a single-threaded test
process has no real race to protect against anyway.

The zero-owner check, the email-uniqueness check, and the insert all
happen in one transaction with a single commit at the end -- unlike
AuthRepository's other methods (each of which commits immediately),
this must not leave a partial state (e.g. a user row created but not
yet OWNER) if the process were interrupted mid-sequence.
"""

import sqlalchemy as sa
from sqlalchemy.orm import Session

from src.auth.exceptions import EmailAlreadyRegisteredError, OwnerBootstrapAlreadyCompleteError
from src.auth.password_hashing import hash_password
from src.auth.repository import AuthRepository
from src.domain.models import StaffRole, User

_repository = AuthRepository()

# Arbitrary fixed key for the advisory lock -- only needs to be
# consistent across calls to this one function, never collide with any
# other advisory lock use in this codebase (there is none today).
_BOOTSTRAP_LOCK_KEY = 0x42415345  # "BASE" as hex, just a memorable constant


def bootstrap_first_owner(session: Session, email: str, password: str) -> User:
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        session.execute(sa.text("SELECT pg_advisory_xact_lock(:key)"), {"key": _BOOTSTRAP_LOCK_KEY})

    if _repository.count_owners(session) > 0:
        raise OwnerBootstrapAlreadyCompleteError("An OWNER account already exists -- bootstrap is disabled.")

    normalized_email = email.strip().lower()
    if _repository.get_user_by_email(session, normalized_email) is not None:
        raise EmailAlreadyRegisteredError(f"'{normalized_email}' is already registered.")

    password_hash = hash_password(password)
    user = User(
        email=normalized_email,
        password_hash=password_hash,
        is_email_verified=True,
        is_staff=True,
        staff_role=StaffRole.OWNER,
    )
    session.add(user)
    session.commit()
    return user
