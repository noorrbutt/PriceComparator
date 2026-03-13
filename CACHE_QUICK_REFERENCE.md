# PricePulse Cache Implementation - Quick Reference

## What Was Implemented

A SQLite cache layer with 30-minute TTL for the PricePulse price comparison API.

## Files Created

```
backend/
├── requirements.txt                    ← Updated dependencies
├── pricepulse.db                      ← Created on first startup
├── app/
│   ├── main.py                        ← Modified: added lifespan
│   ├── models/
│   │   ├── cache.py                   ← NEW: SearchCache model
│   │   ├── response.py                ← NEW: CompareResponse schema
│   │   └── __init__.py
│   ├── db/
│   │   ├── database.py                ← NEW: async engine
│   │   ├── cache_service.py           ← NEW: get/set cache functions
│   │   └── __init__.py
│   ├── api/
│   │   ├── routes.py                  ← Modified: added cache logic
│   │   └── __init__.py
│   └── scrapers/
│       └── (unchanged)
└── test_cache.py                      ← NEW: test script
```

## How It Works

```
User Request: GET /api/compare?q=iphone

1. Check cache for "iphone"
   ├─ Found & fresh?  → Return in <1s ✓
   └─ Not found/stale → Continue to step 2

2. Scrape (parallel):
   ├─ Daraz scraper (30-60s)
   └─ OLX scraper (30-60s)

3. Combine results & sort

4. Save to cache (for 30 minutes)

5. Return response with:
   - query: "iphone"
   - total: 45
   - results: [...]
   - cached: false
   - scraped_at: "2026-03-13T12:34:56"
```

## Performance

| Scenario | Time | Source |
|----------|------|--------|
| First request | 30-60s | Scrapers |
| Repeat (within 30m) | <1s | Cache |
| After 30m | 30-60s | Scrapers (expired) |

## Testing

### Step 1: Start Server
```bash
cd backend
python run.py
```

### Step 2: First Query (Cache Miss)
```bash
curl "http://127.0.0.1:8000/api/compare?q=iphone"
```
- Takes 30-60 seconds
- Returns `"cached": false`
- `pricepulse.db` created

### Step 3: Same Query Again (Cache Hit)
```bash
curl "http://127.0.0.1:8000/api/compare?q=iphone"
```
- Takes <1 second
- Returns `"cached": true`
- Same `scraped_at` timestamp

## Key Components

### 1. Cache Model (`app/models/cache.py`)
```python
class SearchCache(SQLModel, table=True):
    id: Optional[int]
    query_key: str              # normalized query
    source: str                 # 'all'
    results_json: str           # JSON results
    scraped_at: datetime        # timestamp
```

### 2. Cache Service (`app/db/cache_service.py`)
```python
# Check cache (returns None if miss/expired)
cached = await get_cached("iphone")

# Store results
await set_cache("iphone", results)
```

### 3. Routes Integration (`app/api/routes.py`)
```python
@router.get("/compare", response_model=CompareResponse)
async def compare_prices(q: str):
    # Try cache first
    cached = await get_cached(q)
    if cached:
        return {..., "cached": True}
    
    # Scrape & cache
    results = await scrape_both()
    await set_cache(q, results)
    return {..., "cached": False}
```

### 4. Startup (`app/main.py`)
```python
@asynccontextmanager
async def lifespan(app: FastAPI):
    await create_tables()  # Create DB on startup
    yield
    # shutdown cleanup
```

## Dependencies Added

- `sqlmodel==0.0.18` - ORM for SQLite
- `aiosqlite==0.19.0` - Async SQLite driver

All others already installed.

## Configuration

### TTL (Time To Live)
Edit in `app/db/cache_service.py`:
```python
TTL_MINUTES = 30  # Change this value
```

### Database Location
Edit in `app/db/database.py`:
```python
DATABASE_URL = "sqlite+aiosqlite:///./pricepulse.db"  # Change path
```

## Monitoring

### Check Database
```bash
sqlite3 pricepulse.db
sqlite> SELECT COUNT(*) FROM searchcache;
sqlite> SELECT query_key, scraped_at FROM searchcache;
```

### View Logs
Watch server output for:
- `[CACHE HIT]` - served from cache
- `[CACHE MISS]` - scraped fresh
- `[DB] Tables created successfully` - startup

### Clear Cache
```bash
sqlite3 pricepulse.db
sqlite> DELETE FROM searchcache;  # Clear all
sqlite> DELETE FROM searchcache WHERE query_key='iphone';  # Clear one
```

## Response Format

```json
{
  "query": "iPhone 15",
  "total": 45,
  "results": [
    {
      "title": "iPhone 15 Pro 256GB",
      "price": "Rs 299,999",
      "source": "Daraz",
      "url": "https://...",
      "image": "https://...",
      "price_normalized": 299999
    },
    ...
  ],
  "cached": false,
  "scraped_at": "2026-03-13T12:34:56.123456"
}
```

## Troubleshooting

### Database Not Created
- Check `backend/` folder for `pricepulse.db`
- Check server startup logs for "[DB] Tables created"
- Ensure `app/main.py` lifespan is called

### Cache Not Working
- Verify both queries use exact same case: "iPhone" vs "iphone" are different
- Check TTL: 30 minutes default
- Verify response has `"cached"` field

### Slow Requests
- First request always slow (scraping)
- Second request should be instant
- If second is also slow, cache may not be working
- Check server logs for `[CACHE MISS]` vs `[CACHE HIT]`

### Import Errors
```bash
cd backend
python -c "from app.db.cache_service import get_cached; print('OK')"
```

## Frontend Integration

The frontend already works! It calls:
```javascript
const API_BASE = 'http://127.0.0.1:8000/api';
// Automatically uses cached results when available
```

The response now includes cache status that could be displayed:
```javascript
if (data.cached) {
    console.log('Cached result');
} else {
    console.log('Fresh data scraped just now');
}
```

## Production Checklist

- [ ] Start server with no errors
- [ ] First query completes in 30-60 seconds
- [ ] Second query returns in <1 second
- [ ] `pricepulse.db` file exists in backend/
- [ ] Response includes `cached`, `total`, `scraped_at` fields
- [ ] Test different queries (each caches separately)
- [ ] Clear cache if needed with SQLite query
- [ ] Configure TTL if different from 30 min needed

---

**Status**: ✓ Complete and Ready for Testing
