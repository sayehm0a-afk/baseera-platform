"""Unit tests for src/auth/bootstrap_service.py -- the atomic
zero-owner-precondition create used by POST /api/v1/bootstrap/owner.

SQLite (in-memory, this file's `session` fixture) has no
`pg_advisory_xact_lock`, so bootstrap_first_owner's dialect guard skips
the advisory lock here -- these tests exercise the check-then-create
logic and its guard conditions, not cross-transaction locking (which
only PostgreSQL provides and only matters under real concurrency).
"""

from typing import Iterator

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from src.auth.bootstrap_service import bootstrap_first_owner
from src.auth.exceptions import EmailAlreadyRegisteredError, OwnerBootstrapAlreadyCompleteError
from src.auth.password_hashing import verify_password
from src.core.db.database import Base
from src.domain.models import StaffRole, User


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_creates_the_first_owner_when_none_exists(session):
    user = bootstrap_first_owner(session, "OWNER@Example.com", "a-strong-password-123")

    assert user.id is not None
    assert user.email == "owner@example.com"  # normalized lowercase, matching AuthRepository convention
    assert user.is_staff is True
    assert user.staff_role == StaffRole.OWNER
    assert user.is_email_verified is True
    assert verify_password("a-strong-password-123", user.password_hash)


def test_refuses_when_an_owner_already_exists(session):
    session.add(User(email="existing-owner@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER))
    session.commit()

    with pytest.raises(OwnerBootstrapAlreadyCompleteError):
        bootstrap_first_owner(session, "new-owner@example.com", "a-strong-password-123")


def test_non_owner_staff_accounts_do_not_block_bootstrap(session):
    """Only an existing OWNER disables the route -- an ADMIN/SUPPORT
    account (or a plain consumer account) must not."""
    session.add(User(email="admin@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.ADMIN))
    session.commit()

    user = bootstrap_first_owner(session, "owner@example.com", "a-strong-password-123")
    assert user.staff_role == StaffRole.OWNER


def test_refuses_a_duplicate_email(session):
    session.add(User(email="taken@example.com", password_hash="hashed"))
    session.commit()

    with pytest.raises(EmailAlreadyRegisteredError):
        bootstrap_first_owner(session, "taken@example.com", "a-strong-password-123")


def test_leaves_no_partial_state_when_it_refuses(session):
    """The zero-owner check must run before any row is written -- a
    refused call leaves the users table exactly as it found it."""
    session.add(User(email="existing-owner@example.com", password_hash="hashed", is_staff=True, staff_role=StaffRole.OWNER))
    session.commit()

    with pytest.raises(OwnerBootstrapAlreadyCompleteError):
        bootstrap_first_owner(session, "new-owner@example.com", "a-strong-password-123")

    assert session.query(User).count() == 1
