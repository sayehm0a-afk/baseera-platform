import os
import logging
from sqlalchemy import create_engine, pool
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.orm import declarative_base

logger = logging.getLogger(__name__)

# Use synchronous PostgreSQL connection for production
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://postgres:postgres@localhost:5432/basirah")

# Create engine with connection pooling for production
engine = create_engine(
    DATABASE_URL,
    poolclass=pool.QueuePool,
    pool_size=10,
    max_overflow=20,
    pool_pre_ping=True,  # Verify connections before using them
    echo=False,  # Set to True for debugging
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine, class_=Session)
Base = declarative_base()

def get_db():
    """Get database session for dependency injection."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def init_db():
    """Initialize database (for development/testing only)."""
    Base.metadata.create_all(bind=engine)
    logger.info("Database initialized and tables created.")

def drop_db():
    """Drop all tables (for development/testing only)."""
    Base.metadata.drop_all(bind=engine)
    logger.warning("All database tables dropped.")

def get_session() -> Session:
    """Get a synchronous database session."""
    return SessionLocal()

def close_session(session: Session):
    """Close a database session."""
    if session:
        session.close()
