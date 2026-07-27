"""Phase 13 P13.6: proves the audit-trail logging added to
user_service.delete_own_account and data_export_service.build_user_data_export
never lets a password or other sensitive value reach a log line, end
to end through the real JSONFormatter (not just unit-testing
mask_dict_values in isolation) -- a regression guard against a future
change that carelessly adds e.g. `password=password` to one of these
log calls' `extra_fields`.
"""

import json
import logging

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.auth import data_export_service, user_service
from src.auth.password_hashing import hash_password
from src.core.db.database import Base
from src.core.monitoring.structured_logging import JSONFormatter
from src.domain.models import User

_SECRET_PASSWORD = "hunter2-super-secret-password"


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def user(session):
    u = User(email="redaction-check@example.com", password_hash=hash_password(_SECRET_PASSWORD))
    session.add(u)
    session.commit()
    return u


class _CapturingHandler(logging.Handler):
    """Renders every record through the real JSONFormatter (the exact
    formatter main.py's init_logging() attaches in production) and
    keeps the resulting JSON strings for assertion."""

    def __init__(self):
        super().__init__()
        self.setFormatter(JSONFormatter())
        self.lines: list[str] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.lines.append(self.format(record))


@pytest.fixture
def captured_logs():
    handler = _CapturingHandler()
    logger = logging.getLogger("src.auth.user_service")
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    export_logger = logging.getLogger("src.auth.data_export_service")
    export_logger.addHandler(handler)
    export_logger.setLevel(logging.INFO)
    yield handler
    logger.removeHandler(handler)
    export_logger.removeHandler(handler)


def test_deleting_an_account_never_logs_the_password(session, user, captured_logs):
    user_service.delete_own_account(session, user, _SECRET_PASSWORD)

    assert captured_logs.lines, "expected at least one log line"
    for line in captured_logs.lines:
        assert _SECRET_PASSWORD not in line
        payload = json.loads(line)
        assert "password" not in payload


def test_a_failed_deletion_attempt_never_logs_the_attempted_password(session, user, captured_logs):
    from src.auth.exceptions import InvalidCredentialsError

    with pytest.raises(InvalidCredentialsError):
        user_service.delete_own_account(session, user, "wrong-password-attempt")

    for line in captured_logs.lines:
        assert "wrong-password-attempt" not in line
        assert _SECRET_PASSWORD not in line


def test_exporting_data_never_logs_the_password_hash(session, user, captured_logs):
    data_export_service.build_user_data_export(session, user)

    assert captured_logs.lines, "expected at least one log line"
    for line in captured_logs.lines:
        assert user.password_hash not in line
        payload = json.loads(line)
        assert "password_hash" not in payload


def test_account_deletion_and_export_log_lines_only_ever_carry_the_user_id(session, user, captured_logs):
    data_export_service.build_user_data_export(session, user)

    for line in captured_logs.lines:
        payload = json.loads(line)
        # every field this module logs beyond the formatter's own
        # fixed keys (timestamp/level/logger/message/module/function/
        # line/request_id) must be exactly user_id -- nothing else
        # ever rides along.
        extra_keys = set(payload) - {
            "timestamp", "level", "logger", "message", "module", "function", "line", "request_id",
        }
        assert extra_keys <= {"user_id"}, f"unexpected fields in log line: {extra_keys}"
