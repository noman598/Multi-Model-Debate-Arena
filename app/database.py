from typing import Generator
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, declarative_base, sessionmaker

from app.config import settings

# Normalize database URL if it has aiosqlite prefix
db_url = settings.DATABASE_URL
if db_url.startswith("sqlite+aiosqlite://"):
    db_url = db_url.replace("sqlite+aiosqlite://", "sqlite://")

# Engine for SQLite
engine = create_engine(
    db_url,
    echo=False,
    connect_args={"check_same_thread": False} if "sqlite" in db_url else {}
)

# Session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False
)

Base = declarative_base()


def init_db() -> None:
    """Creates database tables if they do not exist."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency providing a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
