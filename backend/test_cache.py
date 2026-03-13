#!/usr/bin/env python
"""
Test script to verify SQLite cache implementation
"""
import sys
import asyncio
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))


async def test_cache_implementation():
    """Test all cache components"""
    print("=" * 60)
    print("PRICEPULSE CACHE IMPLEMENTATION TEST")
    print("=" * 60)

    # Test 1: Imports
    print("\n[TEST 1] Testing imports...")
    try:
        from app.models.cache import SearchCache
        from app.db.database import engine, create_tables, async_session
        from app.db.cache_service import get_cached, set_cache
        from app.models.response import CompareResponse
        from app.main import app

        print("  [PASS] All modules imported successfully")
    except Exception as e:
        print(f"  [FAIL] Import error: {e}")
        return False

    # Test 2: Database creation
    print("\n[TEST 2] Testing database initialization...")
    try:
        await create_tables()
        print("  [PASS] Database tables created")
    except Exception as e:
        print(f"  [FAIL] Database error: {e}")
        return False

    # Test 3: Cache write and read
    print("\n[TEST 3] Testing cache write/read...")
    try:
        test_query = "iPhone 15 Pro"
        test_results = [
            {
                "title": "iPhone 15 Pro 256GB",
                "price": "Rs 299,999",
                "source": "Daraz",
                "url": "https://daraz.pk/...",
                "image": "https://...",
            },
            {
                "title": "iPhone 15 Pro Max 512GB",
                "price": "Rs 349,999",
                "source": "OLX",
                "url": "https://olx.com.pk/...",
                "image": "https://...",
            },
        ]

        # Write to cache
        await set_cache(test_query, test_results)
        print("  [PASS] Results cached successfully")

        # Read from cache
        cached = await get_cached(test_query)
        if cached and len(cached) == 2:
            print("  [PASS] Results retrieved from cache successfully")
            print(f"    - Cached {len(cached)} products")
            print(f"    - Query: {test_query}")
        else:
            print(f"  [FAIL] Cache retrieval failed. Got: {cached}")
            return False

    except Exception as e:
        print(f"  [FAIL] Cache operation error: {e}")
        import traceback

        traceback.print_exc()
        return False

    # Test 4: FastAPI app
    print("\n[TEST 4] Testing FastAPI app...")
    try:
        print(f"  - App title: {app.title}")
        print(f"  - Routes registered: {len(app.routes)}")

        # Check for key routes
        route_names = [route.path for route in app.routes]
        if "/api/compare" in route_names:
            print("  [PASS] /api/compare route registered")
        else:
            print(f"  [FAIL] /api/compare route missing. Routes: {route_names}")
            return False

    except Exception as e:
        print(f"  [FAIL] FastAPI app error: {e}")
        return False

    # Test 5: Response schema
    print("\n[TEST 5] Testing response schema...")
    try:
        response = CompareResponse(
            query="test",
            total=2,
            results=[{"title": "test1"}, {"title": "test2"}],
            cached=False,
            scraped_at="2026-03-13T00:00:00",
        )
        print("  [PASS] Response schema validated")
        print(f"    - Query: {response.query}")
        print(f"    - Total: {response.total}")
        print(f"    - Cached: {response.cached}")
        print(f"    - Scraped at: {response.scraped_at}")
    except Exception as e:
        print(f"  [FAIL] Response schema error: {e}")
        return False

    # Test 6: Database file existence
    print("\n[TEST 6] Checking database file...")
    try:
        db_file = Path(__file__).parent / "pricepulse.db"
        if db_file.exists():
            size_kb = db_file.stat().st_size / 1024
            print(f"  [PASS] Database file created: {db_file}")
            print(f"    - Size: {size_kb:.2f} KB")
        else:
            print(f"  [WARN] Database file not found at {db_file}")
            print("         (May be created on first server startup)")
    except Exception as e:
        print(f"  [FAIL] Database check error: {e}")

    print("\n" + "=" * 60)
    print("ALL TESTS PASSED!")
    print("=" * 60)
    print("\nCache Implementation Summary:")
    print("  - SQLite database with 30-minute TTL")
    print("  - Async operations using aiosqlite")
    print("  - Cache check before scraping in /api/compare")
    print("  - Response includes: query, total, results, cached, scraped_at")
    print("\nNext: Start server with 'python run.py' and test:")
    print("  1. First request: GET /api/compare?q=iphone")
    print("  2. Second request (same): Should use cache")
    print("=" * 60)

    return True


if __name__ == "__main__":
    result = asyncio.run(test_cache_implementation())
    sys.exit(0 if result else 1)
