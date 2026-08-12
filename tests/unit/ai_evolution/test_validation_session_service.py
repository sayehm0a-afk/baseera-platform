"""M10 unit tests: `ValidationSession` lifecycle -- create/close/get-active,
with the concurrency guard (one RUNNING session per is_dry_run kind) and
the hard is_dry_run separation that keeps dry-run evidence from ever
being mistaken for real validation evidence.
"""

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.ai_evolution.validation_session_service import (
    close_validation_session,
    create_validation_session,
    get_active_validation_session_id,
)
from src.core.db.database import Base
from src.domain.models import ValidationSession, ValidationSessionStatus


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


class TestCreateValidationSession:
    def test_creates_running_session(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)

        assert record.id is not None
        assert record.status == ValidationSessionStatus.RUNNING
        assert record.is_dry_run is False
        assert record.started_at is not None

    def test_captures_market_regime_snapshot(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)

        assert record.market_regime_at_start is not None
        assert "market_status" in record.market_regime_at_start
        assert "captured_at" in record.market_regime_at_start

    def test_rejects_second_running_session_of_same_kind(self, session):
        create_validation_session(session, "Session 1", is_dry_run=False)

        with pytest.raises(ValueError, match="already RUNNING"):
            create_validation_session(session, "Session 2", is_dry_run=False)

    def test_allows_concurrent_real_and_dry_run_sessions(self, session):
        real = create_validation_session(session, "Real", is_dry_run=False)
        dry = create_validation_session(session, "Dry", is_dry_run=True)

        assert real.id != dry.id
        assert real.is_dry_run is False
        assert dry.is_dry_run is True

    def test_allows_new_session_after_closing_prior_one(self, session):
        first = create_validation_session(session, "Session 1", is_dry_run=False)
        close_validation_session(session, first.id)

        second = create_validation_session(session, "Session 2", is_dry_run=False)

        assert second.id != first.id
        assert second.status == ValidationSessionStatus.RUNNING


class TestCloseValidationSession:
    def test_closes_running_session(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)

        closed = close_validation_session(session, record.id)

        assert closed.status == ValidationSessionStatus.CLOSED
        assert closed.ended_at is not None

    def test_aborted_flag_sets_aborted_status(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)

        aborted = close_validation_session(session, record.id, aborted=True)

        assert aborted.status == ValidationSessionStatus.ABORTED

    def test_raises_when_not_running(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)
        close_validation_session(session, record.id)

        with pytest.raises(ValueError, match="not RUNNING"):
            close_validation_session(session, record.id)


class TestGetActiveValidationSessionId:
    def test_returns_none_when_no_session_open(self, session):
        assert get_active_validation_session_id(session) is None

    def test_returns_id_of_running_real_session(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)

        assert get_active_validation_session_id(session, is_dry_run=False) == record.id

    def test_does_not_cross_dry_run_boundary(self, session):
        create_validation_session(session, "Dry", is_dry_run=True)

        assert get_active_validation_session_id(session, is_dry_run=False) is None

    def test_returns_none_after_session_closed(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)
        close_validation_session(session, record.id)

        assert get_active_validation_session_id(session, is_dry_run=False) is None

    def test_direct_query_reflects_status(self, session):
        record = create_validation_session(session, "Session 1", is_dry_run=False)
        row = session.query(ValidationSession).filter_by(id=record.id).one()
        assert row.status == ValidationSessionStatus.RUNNING
