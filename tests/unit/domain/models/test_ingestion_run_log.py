"""Unit tests for the IngestionRunLog model -- round-trip persistence,
no network."""

from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.core.db.database import Base
from src.domain.models import IngestionJobStatus, IngestionRunLog


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    db = session_factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_run_log_defaults_on_insert(session):
    started = datetime.now(timezone.utc)
    log = IngestionRunLog(job_name="ohlcv", started_at=started)
    session.add(log)
    session.commit()

    fetched = session.query(IngestionRunLog).one()
    assert fetched.job_name == "ohlcv"
    assert fetched.status == IngestionJobStatus.RUNNING
    assert fetched.finished_at is None
    assert fetched.symbols_requested == 0
    assert fetched.symbols_succeeded == 0
    assert fetched.symbols_failed == 0
    assert fetched.rows_upserted == 0
    assert fetched.retry_count == 0


def test_run_log_updated_in_place_on_completion(session):
    started = datetime.now(timezone.utc)
    log = IngestionRunLog(job_name="ohlcv", started_at=started)
    session.add(log)
    session.commit()
    log_id = log.id

    finished = started + timedelta(seconds=12)
    log.finished_at = finished
    log.duration_seconds = 12.5
    log.symbols_requested = 10
    log.symbols_succeeded = 9
    log.symbols_failed = 1
    log.rows_upserted = 450
    log.retry_count = 2
    log.status = IngestionJobStatus.PARTIAL
    log.error_summary = "1120: SahmkRequestError: ..."
    session.commit()

    fetched = session.query(IngestionRunLog).filter_by(id=log_id).one()
    assert fetched.status == IngestionJobStatus.PARTIAL
    assert fetched.symbols_succeeded == 9
    assert fetched.symbols_failed == 1
    assert fetched.rows_upserted == 450
    assert fetched.retry_count == 2
    assert float(fetched.duration_seconds) == 12.5
    assert "1120" in fetched.error_summary


def test_run_log_success_status_round_trips(session):
    log = IngestionRunLog(
        job_name="fundamentals",
        started_at=datetime.now(timezone.utc),
        status=IngestionJobStatus.SUCCESS,
    )
    session.add(log)
    session.commit()
    assert session.query(IngestionRunLog).one().status == IngestionJobStatus.SUCCESS


def test_multiple_runs_of_the_same_job_are_independent_rows(session):
    for _ in range(3):
        session.add(IngestionRunLog(job_name="dividends", started_at=datetime.now(timezone.utc)))
    session.commit()
    assert session.query(IngestionRunLog).filter_by(job_name="dividends").count() == 3
