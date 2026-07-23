import os
import logging
from typing import Optional
from sqlalchemy import create_engine, pool
from sqlalchemy.engine import Engine
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# Use synchronous PostgreSQL connection for production
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/basirah")

# Base has no I/O side effects (it only builds a metadata registry), so it
# stays a module-level object built at import time. `engine` and
# `SessionLocal` are lazy: constructing an Engine imports the DB driver and,
# depending on the driver, can touch the connection URL, so that work is
# deferred to explicit initialization instead of happening as a side effect
# of `import database`. Both names stay None until init_engine() runs.
Base = declarative_base()

engine: Optional[Engine] = None
SessionLocal: Optional[sessionmaker] = None


def init_engine(database_url: Optional[str] = None) -> Engine:
    """Create the SQLAlchemy engine and session factory if they don't exist yet.

    This is the explicit startup step: call it once during application
    startup (or let get_engine()/get_session() call it on first use).
    Safe to call multiple times; only constructs the engine once.
    """
    global engine, SessionLocal
    if engine is None:
        url = database_url or DATABASE_URL
        engine = create_engine(
            url,
            poolclass=pool.QueuePool,
            pool_size=10,
            max_overflow=20,
            pool_pre_ping=True,  # Verify connections before using them
            echo=False,  # Set to True for debugging
        )
        SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)
        logger.info("Database engine initialized.")
    return engine


def get_engine() -> Engine:
    """Return the active engine, initializing it on first use."""
    return init_engine()


def get_session_factory() -> sessionmaker:
    """Return the active session factory, initializing the engine on first use."""
    init_engine()
    return SessionLocal


def shutdown_engine() -> None:
    """Dispose of the engine and clear cached state.

    Explicit shutdown counterpart to init_engine(), intended to be called
    from application shutdown lifecycle hooks.
    """
    global engine, SessionLocal
    if engine is not None:
        engine.dispose()
        logger.info("Database engine disposed.")
    engine = None
    SessionLocal = None


def get_db():
    """Get database session for dependency injection (FastAPI-style generator)."""
    session_factory = get_session_factory()
    db = session_factory()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Initialize database (for development/testing only)."""
    Base.metadata.create_all(bind=get_engine())
    logger.info("Database initialized and tables created.")


def drop_db() -> None:
    """Drop all tables (for development/testing only)."""
    Base.metadata.drop_all(bind=get_engine())
    logger.warning("All database tables dropped.")


def get_session() -> Session:
    """Get a synchronous database session, initializing the engine if needed."""
    return get_session_factory()()


def close_session(session: Session) -> None:
    """Close a database session."""
    if session:
        session.close()
