# PricePulse (Price Comparator)

[![Python](https://img.shields.io/badge/python-3.11+-blue)]()
[![FastAPI](https://img.shields.io/badge/FastAPI-0.104-009688)]()
[![Status](https://img.shields.io/badge/status-prototype-orange)]()

A real time price comparison tool for the Pakistani market. Search once, and PricePulse concurrently pulls live listings from Daraz and OLX, normalizes the prices, and returns a single ranked list with thumbnails and direct links to each product.

This is a prototype: functional end to end, but scoped to two sources and built without authentication, rate limiting, or a production deployment target in mind.

## How it works

```
Browser (frontend/index.html)
        |
        v
GET /api/compare?q=<query>
        |
        v
FastAPI (backend/app/api/routes.py)
        |
   check SQLite cache (30 min TTL)
        |
   cache hit? -----> return cached results
        |
   cache miss
        |
        +--> scrape_daraz()   httpx call to Daraz's internal catalog JSON API
        +--> scrape_olx_sync() Playwright headless browser, run in a thread pool
        |
   both run concurrently via asyncio.gather with a 120s timeout
        |
   normalize prices, sort ascending, write to cache
        |
        v
   JSON response: query, total, results, cached, scraped_at
```

**Why two different scraping strategies.** Daraz exposes an internal, undocumented JSON endpoint behind its search page, so a plain HTTP request with the right headers returns structured data directly, no browser needed, typically in 1 to 3 seconds. OLX has no equivalent, so its listings are scraped from the rendered DOM using Playwright, which is far slower (30 to 60 seconds) since it launches a real headless Chromium instance, waits for one of several known selectors, and evaluates JavaScript against the live page. Running these two scrapers concurrently, rather than sequentially, keeps total response time close to whichever one is slower rather than the sum of both.

**Why cache at all.** OLX's Playwright scrape is the bottleneck, and identical searches within a short window are common. Results are cached in SQLite by a normalized (lowercased, trimmed) query key for 30 minutes, so a repeated search returns instantly instead of re running a 30 to 60 second browser scrape.

## Feature surface

- Concurrent scraping of Daraz and OLX for a single search query
- Price normalization across sources, handling formats like `Rs 45,000`, `12.5 lac`, and missing prices, then sorting all results ascending by price
- SQLite backed response cache with a 30 minute TTL, keyed by normalized query
- An image proxy endpoint (`/api/image`) that fetches product thumbnails server side with the correct `Referer` header, since both Daraz and OLX block direct hotlinking from a browser
- A single page, dependency free frontend (`frontend/index.html`): plain HTML, CSS, and JavaScript, no build step, no framework

## Known limitations

This section exists because a prototype that hides its rough edges is less trustworthy than one that names them.

- **OLX scraping is DOM selector based**, matched against class names observed in OLX's current markup (for example `article._84ba2e24`). These are unstable, auto generated CSS classes that OLX can change at any time without notice, which will silently break the OLX scraper until the selectors are updated.
- **Daraz relies on an internal, undocumented API**, not a published one. Daraz can change or restrict this endpoint at any time.
- **No retry or backoff logic** on either scraper. A single failed request or timeout for either source returns an empty list for that source rather than retrying.
- **No authentication, rate limiting, or request throttling.** The API is open, and repeated fast queries from a client will drive real scraping load against Daraz and OLX.
- **Windows specific event loop handling** (`WindowsProactorEventLoopPolicy`) is required for `asyncio` subprocess support that Playwright depends on; this is set explicitly in both `main.py` and `run.py`.
- **CORS is fully open** (`allow_origins=["*"]`), appropriate for local prototyping, not for a public deployment.
- **`test_cache.py` is a manual smoke test script**, run directly with `python test_cache.py`, not a pytest suite and not wired into any CI pipeline.

## Tech stack

| Layer | Technology | Role |
|---|---|---|
| API | FastAPI | Async request handling, request/response validation via Pydantic |
| Daraz scraping | httpx | Calls Daraz's internal catalog JSON endpoint directly |
| OLX scraping | Playwright (sync API, run in a thread pool) | Headless Chromium, DOM scraping and selector matching |
| Cache | SQLite via SQLModel and aiosqlite | Async ORM access to a local, file based cache with TTL expiry |
| Frontend | Plain HTML, CSS, JavaScript | No framework, no bundler, no dependencies |

## Local development

### Prerequisites

- Python 3.11 or newer
- Playwright's Chromium browser binary (installed separately, see below)

### Backend setup

```bash
cd backend
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt
playwright install chromium
```

Run the server:

```bash
python run.py
```

This starts uvicorn with auto reload at `http://127.0.0.1:8000`. On startup, a local SQLite file (`pricepulse.db`) is created automatically for the cache table.

### Verify the cache layer

A manual smoke test script checks imports, database creation, a cache write and read cycle, route registration, and the response schema:

```bash
python test_cache.py
```

### Frontend

`frontend/index.html` is a static file with no build step. Open it directly in a browser, or serve it with any static file server. It expects the backend to be running and reachable at the API base URL defined near the top of its script section.

### Try it

```
GET http://127.0.0.1:8000/api/compare?q=iphone+15
```

First request scrapes both sources live. Any repeat of the same query within 30 minutes returns instantly from cache, with `"cached": true` in the response.

## Project structure

```
backend/
  app/
    main.py              FastAPI app setup, CORS, lifespan (creates DB tables on startup)
    api/routes.py         /api/compare, /api/image endpoints, both scrapers, price normalization
    scrapers/              Placeholder module directory for scraper organization
    models/
      response.py          Pydantic response schema for /api/compare
      cache.py              SQLModel table definition for the cache
    db/
      database.py           Async SQLite engine and session setup
      cache_service.py      get_cached and set_cache, TTL logic
  run.py                   Local dev entrypoint (uvicorn, auto reload)
  test_cache.py             Manual smoke test for the cache layer
  requirements.txt
frontend/
  index.html               Single page UI: search, results grid, loading states
```

## Roadmap, if this moves past prototype

- Replace OLX's brittle CSS selector scraping with a more resilient extraction strategy, or an official API if one becomes available
- Add retry with backoff for both scrapers
- Add basic rate limiting on `/api/compare` to protect both this service and the upstream sites
- Convert `test_cache.py` into an actual pytest suite and add it to CI
- Add more sources beyond Daraz and OLX
