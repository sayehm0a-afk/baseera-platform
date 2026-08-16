"""Unit tests for the `RadarOpportunity` domain model (Basirah Radar V2,
Phase B forward-testing foundation) -- real SQLAlchemy ORM against an
in-memory SQLite DB, matching the discipline of
tests/unit/ai_evolution/test_decision_v2_outcome.py."""

from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.core.db.database import Base
from src.domain.models import DecisionV2Snapshot, RadarOpportunity, Stock


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", poolclass=StaticPool, connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def stock(session):
    row = Stock(symbol="2222", name_en="Stock 2222", sector="Energy")
    session.add(row)
    session.commit()
    return row


def _make_snapshot(session, stock, decision="BUY_CANDIDATE"):
    snapshot = DecisionV2Snapshot(
        stock_id=stock.id,
        symbol=stock.symbol,
        company_name_en=stock.name_en,
        decision=decision,
        decision_label_ar="شراء",
        confidence_score=70.0,
        opportunity_quality_score=60.0,
        risk_score=30.0,
        data_quality_score=90.0,
        data_freshness_status="LIVE",
        current_price=100.0,
        market_status="OPEN",
        decision_timestamp=datetime(2026, 1, 1, tzinfo=timezone.utc),
        analysis_version="2.0.0",
        data_source="test",
    )
    session.add(snapshot)
    session.commit()
    return snapshot


def _make_opportunity(session, stock, snapshot, **overrides):
    defaults = dict(
        symbol=stock.symbol,
        stock_id=stock.id,
        decision_v2_snapshot_id=snapshot.id,
        classification=snapshot.decision,
        classification_label_ar=snapshot.decision_label_ar,
        confidence_score=snapshot.confidence_score,
        price_at_signal=snapshot.current_price,
        stage1_rank=1,
        stage1_ranking_score=78.5,
        stage1_component_scores={"trend": 80.0, "momentum": 70.0},
        stage1_signals=[{"name": "trending", "detail_ar": "اتجاه قوي"}],
        emitted_at=datetime(2026, 1, 1, 0, 5, tzinfo=timezone.utc),
    )
    defaults.update(overrides)
    row = RadarOpportunity(**defaults)
    session.add(row)
    session.commit()
    return row


class TestPersistenceRoundTrip:
    def test_insert_and_read_back_every_field(self, session, stock):
        snapshot = _make_snapshot(session, stock)
        row = _make_opportunity(session, stock, snapshot, ranking_reason_ar="تصدر الترتيب بسبب قوة الاتجاه")

        reloaded = session.query(RadarOpportunity).filter_by(id=row.id).one()
        assert reloaded.symbol == "2222"
        assert reloaded.decision_v2_snapshot_id == snapshot.id
        assert reloaded.classification == "BUY_CANDIDATE"
        assert reloaded.stage1_rank == 1
        assert reloaded.stage1_ranking_score == 78.5
        assert reloaded.stage1_component_scores == {"trend": 80.0, "momentum": 70.0}
        assert reloaded.stage1_signals == [{"name": "trending", "detail_ar": "اتجاه قوي"}]
        assert reloaded.ranking_reason_ar == "تصدر الترتيب بسبب قوة الاتجاه"
        assert reloaded.superseded_by_id is None
        assert reloaded.created_at is not None

    def test_snapshot_and_stock_relationships_resolve(self, session, stock):
        snapshot = _make_snapshot(session, stock)
        row = _make_opportunity(session, stock, snapshot)

        assert row.snapshot.id == snapshot.id
        assert row.stock.id == stock.id


class TestUniqueSnapshotConstraint:
    def test_two_opportunities_cannot_share_one_snapshot(self, session, stock):
        snapshot = _make_snapshot(session, stock)
        _make_opportunity(session, stock, snapshot)

        duplicate = RadarOpportunity(
            symbol=stock.symbol,
            stock_id=stock.id,
            decision_v2_snapshot_id=snapshot.id,
            classification="BUY_CANDIDATE",
            classification_label_ar="شراء",
            confidence_score=70.0,
            emitted_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )
        session.add(duplicate)
        with pytest.raises(Exception):
            session.commit()
        session.rollback()


class TestSupersessionChain:
    def test_a_row_can_be_marked_superseded_by_a_later_one_without_editing_its_own_evidence(self, session, stock):
        """The anti-flapping/dedup mechanism: an old opportunity's own
        score/evidence must stay exactly as emitted -- only the pointer
        changes."""
        old_snapshot = _make_snapshot(session, stock)
        old = _make_opportunity(session, stock, old_snapshot, stage1_ranking_score=60.0)

        new_snapshot = _make_snapshot(session, stock)
        new = _make_opportunity(
            session, stock, new_snapshot,
            stage1_ranking_score=85.0,
            emitted_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        )

        old.superseded_by_id = new.id
        session.commit()

        reloaded_old = session.query(RadarOpportunity).filter_by(id=old.id).one()
        assert reloaded_old.superseded_by_id == new.id
        # The old row's own evidence is untouched by the supersession.
        assert reloaded_old.stage1_ranking_score == 60.0
        assert reloaded_old.superseded_by.id == new.id
