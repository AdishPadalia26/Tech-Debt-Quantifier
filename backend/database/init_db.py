"""Database initialization script.

Run this after starting PostgreSQL via docker-compose:
    docker-compose up -d
    python -m database.init_db
"""

import logging
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database.connection import engine, Base, DB_AVAILABLE
from database.models import Repository, Scan, DebtItem

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def init_database() -> None:
    """Create all tables in PostgreSQL."""
    if not DB_AVAILABLE:
        logger.error("PostgreSQL is not available. Start docker-compose first.")
        sys.exit(1)

    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Database tables created successfully")
    logger.info("Tables: repositories, scans, debt_items")


if __name__ == "__main__":
    init_database()
