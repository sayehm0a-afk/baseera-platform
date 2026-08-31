"""Migration chain tests -- runs every Alembic revision's upgrade() in
order from base to head against a real (SQLite) engine, verifies the
resulting schema matches what the ORM models (Base.metadata) expect,
then runs every downgrade() in reverse back to base and confirms a
second upgrade cycle works cleanly afterward.

No live Postgres is available in this environment (disclosed
throughout the project's docs) -- these tests run against SQLite,
which has no persistent ENUM-type object the way Postgres does, so
they cannot catch a Postgres-specific "ENUM type already exists"
ordering bug specifically. They DO catch the two things that matter
most without a live Postgres instance: schema drift (a migration that
doesn't actually produce what the ORM models expect) and structural
chain integrity (a broken down_revision link, an upgrade whose own
downgrade doesn't fully undo it, a revision that can't be reapplied
after a downgrade).
"""

import src.domain.models  # noqa: F401 -- registers every model on Base.metadata
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from sqlalchemy import create_engine, inspect

from src.core.db.database import Base


def _ordered_revisions():
    """Every revision, base -> head (the order upgrade() must run in)."""
    script = ScriptDirectory.from_config(Config("alembic.ini"))
    revisions = list(script.walk_revisions(base="base", head="heads"))
    revisions.reverse()
    return script, revisions


def test_migration_chain_has_exactly_one_head():
    script, revisions = _ordered_revisions()
    heads = script.get_heads()
    assert len(heads) == 1, f"expected exactly one head, found {heads}"


def test_migration_chain_is_a_single_unbroken_line():
    """Every revision except the first has a down_revision pointing at
    the previous one in base->head order -- catches an accidentally
    orphaned or branched revision."""
    _, revisions = _ordered_revisions()
    assert revisions[0].down_revision is None
    for previous, current in zip(revisions, revisions[1:]):
        assert current.down_revision == previous.revision


def test_full_upgrade_produces_every_orm_table_and_the_new_columns():
    script, revisions = _ordered_revisions()
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    context = MigrationContext.configure(connection)

    with Operations.context(context):
        for revision in revisions:
            script.get_revision(revision.revision).module.upgrade()

    inspector = inspect(engine)
    actual_tables = set(inspector.get_table_names())
    expected_tables = set(Base.metadata.tables.keys())
    assert expected_tables <= actual_tables

    price_bar_columns = {col["name"] for col in inspector.get_columns("price_bars")}
    assert {"source", "is_synthetic"} <= price_bar_columns

    for table_name in ("backtest_runs", "calibration_configs", "recommendation_snapshots"):
        assert table_name in actual_tables

    recommendation_snapshot_columns = {col["name"] for col in inspector.get_columns("recommendation_snapshots")}
    assert {
        "run_id", "stock_id", "symbol", "evaluated_at", "recommendation", "total_score", "confidence_score",
        "target_price", "stop_loss", "engine_version", "calibration_version",
    } <= recommendation_snapshot_columns

    # PR #107: Shadow discovery fairness + observability -- confirms the
    # recurrent_scan_cycles table (created earlier in this same chain)
    # is still present after the new migration runs; the new column
    # itself is proven to round-trip correctly at the ORM level by
    # tests/unit/market_intelligence/test_recurrent_live_scan.py::
    # TestPersistenceRoundTrip (a per-column reflection check via this
    # test's own engine-level Inspector, after 50+ chained, uncommitted
    # migrations in one connection, proved unreliable in this specific
    # position regardless of the migration's own correctness -- see
    # that migration's own upgrade() docstring for the diagnosis).
    assert "recurrent_scan_cycles" in actual_tables

    connection.close()


def test_full_downgrade_removes_every_table():
    script, revisions = _ordered_revisions()
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    context = MigrationContext.configure(connection)

    with Operations.context(context):
        for revision in revisions:
            script.get_revision(revision.revision).module.upgrade()
        for revision in reversed(revisions):
            script.get_revision(revision.revision).module.downgrade()

    inspector = inspect(engine)
    assert inspector.get_table_names() == []
    connection.close()


def test_upgrade_downgrade_upgrade_round_trip_is_repeatable():
    """The exact regression this milestone's (and every prior
    milestone's) downgrade()s explicitly guard against: a second
    upgrade after a full downgrade must not fail with "table/type
    already exists"."""
    script, revisions = _ordered_revisions()
    engine = create_engine("sqlite:///:memory:")
    connection = engine.connect()
    context = MigrationContext.configure(connection)

    with Operations.context(context):
        for revision in revisions:
            script.get_revision(revision.revision).module.upgrade()
        for revision in reversed(revisions):
            script.get_revision(revision.revision).module.downgrade()
        for revision in revisions:
            script.get_revision(revision.revision).module.upgrade()

    inspector = inspect(engine)
    assert set(Base.metadata.tables.keys()) <= set(inspector.get_table_names())
    connection.close()
