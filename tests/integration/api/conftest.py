"""Shared fixtures for API integration tests.

DB: in-memory SQLite with StaticPool -- plain "sqlite:///:memory:"
gives each new connection its own isolated database, which breaks the
moment a route (a different connection, via get_db) tries to read what
a test's seed session (yet another connection) just wrote. StaticPool
makes every session in a test share the exact same connection/database.

Providers: overridden directly with Dev*Provider instances rather than
routed through provider_factory's real network-aware selection --
hermetic (no dependency on env vars or provider_factory's process-wide
cache leaking across test files) and fast (no connectivity probe).
"""

from typing import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

import main
from src.api.dependencies import get_fundamental_provider, get_market_provider
from src.core.db.database import Base, get_db
from src.market_data.providers.dev_fundamental_data_provider import DevFundamentalDataProvider
from src.market_data.providers.dev_market_data_provider import DevMarketDataProvider


@pytest.fixture
def db_session() -> Iterator[Session]:
    engine = create_engine(
        "sqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session_factory = sessionmaker(bind=engine)
    session = session_factory()

    def _override_get_db():
        db = session_factory()
        try:
            yield db
        finally:
            db.close()

    main.app.dependency_overrides[get_db] = _override_get_db
    main.app.dependency_overrides[get_market_provider] = lambda: DevMarketDataProvider()
    main.app.dependency_overrides[get_fundamental_provider] = lambda: DevFundamentalDataProvider()

    yield session

    session.close()
    Base.metadata.drop_all(bind=engine)
    main.app.dependency_overrides.clear()


@pytest.fixture
def client(db_session) -> Iterator[TestClient]:
    # Not used as `with TestClient(app) as c:` -- entering the context
    # manager runs main.py's startup lifecycle (Redis message bus, DB
    # kernel init), which this environment doesn't have running and
    # which the routes under test don't need.
    yield TestClient(main.app)
