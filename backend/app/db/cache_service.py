import json
from datetime import datetime, timedelta
from sqlalchemy import select, delete
from sqlmodel import Session

from app.models.cache import SearchCache
from app.db.database import async_session

# TTL in minutes
TTL_MINUTES = 30


async def get_cached(query: str) -> list | None:
    """
    Retrieve cached results for a query if they exist and are fresh.

    Args:
        query: The search query string

    Returns:
        List of cached products or None if cache miss/expired
    """
    query_key = query.lower().strip()

    async with async_session() as session:
        statement = select(SearchCache).where(SearchCache.query_key == query_key)
        result = await session.execute(statement)
        cache_row = result.scalars().first()

        if cache_row:
            # Check if cache is still fresh
            elapsed = datetime.utcnow() - cache_row.scraped_at
            if elapsed < timedelta(minutes=TTL_MINUTES):
                return json.loads(cache_row.results_json)

    return None


async def set_cache(query: str, results: list) -> None:
    """
    Store or update cache for a query result.

    Args:
        query: The search query string
        results: List of product dicts to cache
    """
    query_key = query.lower().strip()

    async with async_session() as session:
        # Delete any existing cache entry for this query
        delete_stmt = delete(SearchCache).where(SearchCache.query_key == query_key)
        await session.execute(delete_stmt)

        # Insert new cache entry
        cache_row = SearchCache(
            query_key=query_key,
            source="all",
            results_json=json.dumps(results),
            scraped_at=datetime.utcnow(),
        )
        session.add(cache_row)
        await session.commit()
