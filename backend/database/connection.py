import os
import logging
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

logger = logging.getLogger(__name__)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./techdebt.db")

# SQLite needs special config — no async driver needed
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False
    )
    logger.info(f"Using SQLite database: {DATABASE_URL}")
else:
    # PostgreSQL
    engine = create_engine(DATABASE_URL, echo=False)
    logger.info(f"Using PostgreSQL database")

SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

DB_AVAILABLE = True
Base = declarative_base()

def get_db():
    """DB session dependency."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
