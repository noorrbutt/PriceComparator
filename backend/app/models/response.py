from pydantic import BaseModel


class CompareResponse(BaseModel):
    """Response model for the /api/compare endpoint."""

    query: str
    total: int
    results: list[dict]
    cached: bool
    scraped_at: str  # ISO format datetime string
