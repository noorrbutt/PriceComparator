from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlmodel import SQLModel
import os

# Database URL - SQLite database file in backend root
DATABASE_URL = "sqlite+aiosqlite:///./pricepulse.db"

# Create async engine
engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    future=True,
    connect_args={"check_same_thread": False},
)

# Session factory
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def create_tables():
    """Create all database tables on startup."""
    async with engine.begin() as conn:
        await conn.run_sync(SQLModel.metadata.create_all)
    print("[DB] Tables created successfully")


async def get_session() -> AsyncSession:
    """Get async database session."""
    async with async_session() as session:
        yield session
