import os
import time
from sqlalchemy import create_engine
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import sessionmaker, declarative_base

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://appuser:apppass@db:5432/appdb",
)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
Base = declarative_base()


def wait_for_db(retries: int = 20, delay: float = 1.5) -> None:
    """Block until Postgres accepts connections (it can start after the API)."""
    for attempt in range(1, retries + 1):
        try:
            with engine.connect():
                return
        except OperationalError:
            print(f"Database not ready ({attempt}/{retries}), retrying...")
            time.sleep(delay)
    raise RuntimeError("Could not connect to the database")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
