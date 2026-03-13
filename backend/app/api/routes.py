import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from fastapi import APIRouter, Response
import httpx
from playwright.sync_api import sync_playwright

from app.db.cache_service import get_cached, set_cache
from app.models.response import CompareResponse

router = APIRouter()
executor = ThreadPoolExecutor(max_workers=2)


def normalize_price(price_str: str):
    if not price_str or price_str == "N/A":
        return None
    cleaned = price_str.replace("Rs.", "").replace("Rs", "").replace(",", "").strip()
    if "lac" in cleaned.lower():
        cleaned = cleaned.lower().replace("lac", "").strip()
        try:
            return float(cleaned) * 100000
        except ValueError:
            return None
    match = re.search(r"[\d.]+", cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


async def scrape_daraz(query: str):
    """Scrape Daraz using their internal JSON API (1-3 seconds vs 40-60 with browser)."""
    products = []
    try:
        url = f"https://www.daraz.pk/catalog/?ajax=true&isFirstRequest=true&page=1&q={query.replace(' ', '+')}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://www.daraz.pk/",
            "X-Requested-With": "XMLHttpRequest",
        }
        print(f"[Daraz] Scraping API: {url}")
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(url, headers=headers)
            data = resp.json()

            # Extract products from API response
            if "mods" in data and "listItems" in data["mods"]:
                for item in data["mods"]["listItems"]:
                    try:
                        product = {
                            "title": item.get("name", "N/A"),
                            "price": f"Rs {item.get('price', 'N/A')}",
                            "image": item.get("image", ""),
                            "url": f"https://www.daraz.pk{item.get('itemUrl', '')}",
                            "source": "Daraz",
                        }
                        if product["title"] != "N/A" and product["price"] != "Rs N/A":
                            products.append(product)
                    except Exception as e:
                        continue

        print(f"[Daraz] Found {len(products)} products")
    except Exception as e:
        print(f"[Daraz] Error: {e}")

    return products


def scrape_olx_sync(query: str):
    products = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-PK",
        )
        url = f"https://www.olx.com.pk/items/q-{query.replace(' ', '-')}"
        print(f"[OLX] Scraping: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # From debug: real card selector is article._84ba2e24 inside li._511d219f
            matched = None
            for selector in [
                "article._84ba2e24",
                "li._511d219f",
                "li[data-aut-id]",
                "[data-aut-id='itemBox']",
            ]:
                try:
                    page.wait_for_selector(selector, timeout=12000)
                    matched = selector
                    print(f"[OLX] Matched selector: {selector}")
                    break
                except:
                    continue

            if not matched:
                print("[OLX] No selector matched, waiting 4s...")
                page.evaluate("window.scrollTo(0, 600)")
                time.sleep(4)

            products = page.evaluate(
                """() => {
                let cards = document.querySelectorAll("article._84ba2e24");
                if (!cards.length) cards = document.querySelectorAll("li._511d219f article");
                if (!cards.length) cards = document.querySelectorAll("li[data-aut-id]");

                const results = [];
                cards.forEach(card => {
                    const title = card.querySelector("h2._6aaa9e3e")?.innerText?.trim() ||
                                  card.querySelector("h2, h3")?.innerText?.trim() || "";

                    const price = card.querySelector("span.cb7e1f7d")?.innerText?.trim() ||
                                  card.querySelector("[class*='price']")?.innerText?.trim() || "";

                    const imgEl = card.querySelector("img");
                    const src = imgEl?.getAttribute('data-src') || imgEl?.getAttribute('src') || '';
                    const image = src.startsWith('http') && (src.includes('olxcdn') || src.includes('olx.com')) ? src : '';

                    const link = card.closest("a") || card.querySelector("a");
                    const rawUrl = link?.getAttribute("href") || "";
                    const url = rawUrl.startsWith("/") ? "https://www.olx.com.pk" + rawUrl : rawUrl;

                    // Location: any leaf span that isn't price/title/delivery
                    let location = "";
                    card.querySelectorAll("span").forEach(el => {
                        if (el.children.length === 0) {
                            const t = el.innerText?.trim() || "";
                            if (t && !t.startsWith("Rs") && t !== "Delivery" && t.length > 3 && t.length < 60) {
                                location = t;
                            }
                        }
                    });

                    if (title && price) results.push({ title, price, image, url, location });
                });
                return results;
            }"""
            )
            print(f"[OLX] Found {len(products)} products")
        except Exception as e:
            print(f"[OLX] Error: {e}")
        finally:
            browser.close()
    for prod in products:
        prod["source"] = "OLX"
    return products


@router.get("/image")
async def proxy_image(url: str):
    """Proxy images from Daraz/OLX to avoid hotlink blocking."""
    REFERERS = {
        "daraz.pk": "https://www.daraz.pk/",
        "olx.com.pk": "https://www.olx.com.pk/",
    }
    referer = "https://www.google.com/"
    for domain, ref in REFERERS.items():
        if domain in url:
            referer = ref
            break

    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": referer,
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }
    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            resp = await client.get(url, headers=headers)
            content_type = resp.headers.get("content-type", "image/jpeg")
            return Response(
                content=resp.content,
                media_type=content_type,
                headers={"Cache-Control": "public, max-age=86400"},
            )
    except Exception as e:
        print(f"[ImageProxy] Error: {e}")
        return Response(status_code=404)


@router.get("/compare", response_model=CompareResponse)
async def compare_prices(q: str):
    print(f"[API] Searching for: {q}")

    # Try to get cached results first
    cached_results = await get_cached(q)
    if cached_results:
        print(f"[API] Cache hit for: {q}")
        return {
            "query": q,
            "total": len(cached_results),
            "results": cached_results,
            "cached": True,
            "scraped_at": datetime.utcnow().isoformat(),
        }

    print(f"[API] Cache miss for: {q}, running scrapers...")
    scraped_at = datetime.utcnow()
    loop = asyncio.get_event_loop()

    # Daraz uses our new async API scraper (fast: 1-3s)
    daraz_coro = scrape_daraz(q)
    # OLX still uses Playwright via executor (slow: 30-40s)
    olx_future = loop.run_in_executor(executor, scrape_olx_sync, q)

    # Run both in parallel using asyncio.gather with timeout
    try:
        results = await asyncio.wait_for(
            asyncio.gather(daraz_coro, olx_future, return_exceptions=True),
            timeout=120,
        )
    except asyncio.TimeoutError:
        print(f"[API] Scrapers timeout after 120s")
        results = [
            asyncio.TimeoutError("Daraz timeout"),
            asyncio.TimeoutError("OLX timeout"),
        ]

    daraz_results = results[0] if not isinstance(results[0], Exception) else []
    olx_results = results[1] if not isinstance(results[1], Exception) else []

    if isinstance(results[0], Exception):
        print(f"[API] Daraz error: {results[0]}")
    if isinstance(results[1], Exception):
        print(f"[API] OLX error: {results[1]}")

    all_products = daraz_results + olx_results

    for product in all_products:
        product["price_normalized"] = normalize_price(product.get("price", ""))

    all_products.sort(
        key=lambda x: (
            x["price_normalized"] if x["price_normalized"] is not None else float("inf")
        )
    )

    # Cache the results
    await set_cache(q, all_products)
    print(f"[API] Cached results for: {q}")

    return {
        "query": q,
        "total": len(all_products),
        "results": all_products,
        "cached": False,
        "scraped_at": scraped_at.isoformat(),
    }
