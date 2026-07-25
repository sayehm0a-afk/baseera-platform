import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from src.analysis.ai_request_recorder import record_ai_request
from src.core.db.database import Base
from src.domain.models import AIRequestStatus


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(bind=engine)
    factory = sessionmaker(bind=engine)
    db = factory()
    yield db
    db.close()
    Base.metadata.drop_all(bind=engine)


def test_record_ai_request_persists_every_field(session):
    request = record_ai_request(
        session,
        feature="analyst_narration:technical_reasoning",
        status=AIRequestStatus.SUCCESS,
        user_id=1,
        symbol="2222",
        model="gpt-4",
        prompt_tokens=100,
        completion_tokens=50,
        total_tokens=150,
        latency_ms=842.5,
        estimated_cost_usd=0.0012,
    )
    assert request.id is not None
    assert request.status == AIRequestStatus.SUCCESS
    assert request.total_tokens == 150


def test_record_ai_request_allows_a_null_user_and_minimal_fields(session):
    request = record_ai_request(session, feature="market_scan", status=AIRequestStatus.SUCCESS)
    assert request.user_id is None
    assert request.symbol is None
