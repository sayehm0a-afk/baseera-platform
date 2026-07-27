#!/usr/bin/env python3
"""Owner-bootstrap CLI (Phase 13, P13.4).

Creates the very first OWNER account, or promotes an existing account
to OWNER. This exists because the RBAC design (src/auth/rbac.py,
src/api/routes/admin/users.py's `set_staff_role` route) deliberately
has no self-service path to OWNER -- granting OWNER always requires an
existing OWNER to call the admin API. On a brand-new deployment there
is no OWNER yet, so this script is the one, explicit, operator-run
escape hatch -- run directly against the production database by
whoever holds deploy access, never exposed over HTTP.

Usage:
    DATABASE_URL=postgresql://... python3 scripts/bootstrap_owner.py --email owner@baseerah.sa

The password is always read interactively (getpass) when creating a
new user -- never accepted as a CLI argument or environment variable,
so it never ends up in shell history or process listings. Promoting an
already-existing account to OWNER needs no password at all.
"""

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.auth.password_hashing import PasswordTooLongError, hash_password  # noqa: E402
from src.auth.repository import AuthRepository  # noqa: E402
from src.core.db.database import get_session_factory  # noqa: E402
from src.domain.models import StaffRole  # noqa: E402

_repository = AuthRepository()


def _read_new_password() -> str:
    while True:
        password = getpass.getpass("Set a password for the new OWNER account: ")
        confirm = getpass.getpass("Confirm password: ")
        if password != confirm:
            print("Passwords did not match -- try again.", file=sys.stderr)
            continue
        if len(password) < 8:
            print("Password must be at least 8 characters -- try again.", file=sys.stderr)
            continue
        return password


def bootstrap_owner(email: str) -> None:
    normalized_email = email.strip().lower()
    session_factory = get_session_factory()
    session = session_factory()
    try:
        user = _repository.get_user_by_email(session, normalized_email)

        if user is not None:
            if user.is_staff and user.staff_role == StaffRole.OWNER:
                print(f"'{normalized_email}' is already an OWNER. Nothing to do.")
                return
            _repository.set_staff_role(session, user.id, True, StaffRole.OWNER)
            print(f"Promoted existing account '{normalized_email}' to OWNER.")
            return

        password = _read_new_password()
        try:
            password_hash = hash_password(password)
        except PasswordTooLongError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            sys.exit(1)

        user = _repository.create_user(session, email=normalized_email, password_hash=password_hash)
        _repository.set_email_verified(session, user.id)
        _repository.set_staff_role(session, user.id, True, StaffRole.OWNER)
        print(f"Created new OWNER account '{normalized_email}'.")
    finally:
        session.close()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--email", required=True, help="Email address of the account to create or promote.")
    args = parser.parse_args()
    bootstrap_owner(args.email)


if __name__ == "__main__":
    main()
