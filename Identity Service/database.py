import os

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

_database_url = os.getenv("DATABASE_URL", "")

if not _database_url:
    raise RuntimeError(
        "DATABASE_URL is not set. "
        "Add it to your .env file. "
        "Example: DATABASE_URL=postgresql://ecom_user:password@db:5432/ecom_db"
    )

SQLALCHEMY_DATABASE_URL: str = _database_url
engine = create_engine(SQLALCHEMY_DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


# Dependency to get a database session for each request
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
