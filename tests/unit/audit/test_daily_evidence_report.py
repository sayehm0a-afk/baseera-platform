"""Inventory must preserve unknowns, Saudi day boundaries and ambiguous outcomes."""
from datetime import date, datetime

import pytest
from sqlalchemy import Boolean, Column, DateTime, Integer, MetaData, String, Table, create_engine

from scripts.audit.daily_evidence_report import build_report, write_report


@pytest.fixture
def ledger():
    engine = create_engine("sqlite://")
    metadata = MetaData()
    snapshots = Table("decision_v2_snapshots", metadata,
        Column("id", Integer, primary_key=True), Column("decision", String),
        Column("decision_timestamp", DateTime), Column("engine_sha", String),
        Column("config_hash", String), Column("quote_timestamp", DateTime),
        Column("is_real_data", Boolean), Column("is_synthetic", Boolean))
    outcomes = Table("decision_v2_outcomes", metadata,
        Column("id", Integer, primary_key=True), Column("decision_v2_snapshot_id", Integer),
        Column("status", String), Column("entry_triggered", Boolean),
        Column("is_independent_signal", Boolean), Column("last_checked_at", DateTime))
    metadata.create_all(engine)
    with engine.begin() as connection:
        for identifier, stamp in enumerate(["2026-09-08T20:59:59", "2026-09-08T21:00:00",
                                           "2026-09-09T20:59:59", "2026-09-09T21:00:00"], 1):
            connection.execute(snapshots.insert().values(id=identifier, decision="BUY_CANDIDATE",
                decision_timestamp=datetime.fromisoformat(stamp)))
        connection.execute(outcomes.insert().values(id=1, decision_v2_snapshot_id=2,
            status="PARTIAL", entry_triggered=True, is_independent_signal=True))
    yield engine, outcomes
    engine.dispose()


def test_day_boundary_and_unknowns_not_fabricated_performance(ledger):
    engine, _ = ledger
    with engine.connect() as connection:
        report = build_report(connection, date(2026, 9, 9))
    assert report["counts"]["decision_snapshots"] == 2
    assert report["counts"]["actionable_without_outcome"] == 1
    assert report["counts"]["missing_quote_timestamp"] == 2
    assert report["counts"]["real_data_not_confirmed"] == 2
    assert report["outcome_status_counts"] == {"PARTIAL": 1}
    assert report["performance"]["win_rate"] is None
    assert report["latest_outcome_check_at"] is None


def test_duplicate_linkage_fails_closed(ledger):
    engine, outcomes = ledger
    with engine.begin() as connection:
        connection.execute(outcomes.insert().values(id=2, decision_v2_snapshot_id=2, status="TARGET_1_HIT"))
    with engine.connect() as connection, pytest.raises(ValueError, match="Duplicate"):
        build_report(connection, date(2026, 9, 9))


def test_empty_day_is_no_evidence_not_zero_success(ledger):
    engine, _ = ledger
    with engine.connect() as connection:
        report = build_report(connection, date(2026, 9, 11))
    assert report["counts"]["decision_snapshots"] == 0
    assert report["performance"]["win_rate"] is None


def test_previous_observation_cannot_be_overwritten(tmp_path):
    destination = tmp_path / "report.json"
    write_report({"first": True}, destination)
    with pytest.raises(FileExistsError):
        write_report({"first": False}, destination)
    assert '"first": true' in destination.read_text()
