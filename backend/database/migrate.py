import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# Load .env first
from dotenv import load_dotenv
load_dotenv()

from database.connection import engine, Base
from database.models import Repository, Scan, DebtItem
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def create_tables():
    logger.info("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Tables created successfully:")
    logger.info("  - repositories")
    logger.info("  - scans")
    logger.info("  - debt_items")
    
    # Verify tables exist
    from sqlalchemy import inspect
    inspector = inspect(engine)
    tables = inspector.get_table_names()
    logger.info(f"Verified tables in DB: {tables}")

if __name__ == "__main__":
    create_tables()
