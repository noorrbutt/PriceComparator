from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field


class SearchCache(SQLModel, table=True):
    """Cache table for storing search results with TTL."""

    id: Optional[int] = Field(default=None, primary_key=True)
    query_key: str = Field(index=True)  # normalized (lowercased, stripped) search query
    source: str = Field(index=True)  # 'daraz', 'olx', or 'all'
    results_json: str  # JSON-serialized list of product dicts
    scraped_at: datetime = Field(default_factory=datetime.utcnow)
