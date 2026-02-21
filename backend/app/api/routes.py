import asyncio
import re
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter
from playwright.sync_api import sync_playwright  # use sync instead of async

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
    match = re.search(r'[\d.]+', cleaned)
    if match:
        try:
            return float(match.group())
        except ValueError:
            return None
    return None


def scrape_daraz_sync(query: str):
    products = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        url = f"https://www.daraz.pk/catalog/?q={query.replace(' ', '+')}"
        print(f"[Daraz] Scraping: {url}")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        try:
            page.wait_for_selector('[data-qa-locator="product-item"]', timeout=15000)
        except:
            pass
        products = page.evaluate('''() => {
            const cards = document.querySelectorAll('[data-qa-locator="product-item"]');
            return Array.from(cards).map(card => {
                const titleEl = card.querySelector('.RfADt a');
                const title = titleEl?.getAttribute('title') || titleEl?.innerText?.trim() || "N/A";
                const price = card.querySelector('.ooOxS')?.innerText?.trim() || "N/A";
                const img = card.querySelector('img');
                const image = img?.getAttribute('data-src') || img?.src || "";
                const rawUrl = card.querySelector('a')?.getAttribute('href') || "";
                const url = rawUrl.startsWith('//') ? 'https:' + rawUrl : rawUrl;
                return { title, price, image, url };
            });
        }''')
        print(f"[Daraz] Found {len(products)} products")
        browser.close()
    for p in products:
        p["source"] = "Daraz"
    return products


def scrape_olx_sync(query: str):
    products = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        url = f"https://www.olx.com.pk/items/q-{query.replace(' ', '-')}"
        print(f"[OLX] Scraping: {url}")
        page.goto(url)
        page.wait_for_load_state("networkidle")
        try:
            page.wait_for_selector('._8b88d490', timeout=15000)
        except:
            pass
        products = page.evaluate('''() => {
            const cards = document.querySelectorAll('._8b88d490');
            return Array.from(cards).map(card => {
                const title = card.querySelector('._1093b649')?.innerText?.trim() || "N/A";
                const price = card.querySelector('.f83175ac')?.innerText?.trim() || "N/A";
                const img = card.querySelector('img');
                const image = img?.getAttribute('data-src') || img?.src || "";
                const rawUrl = card.querySelector('a')?.getAttribute('href') || "";
                const url = rawUrl.startsWith('/') ? 'https://www.olx.com.pk' + rawUrl : rawUrl;
                const location = card.querySelector('.f047db22')?.innerText?.replace('•', '').trim() || "";
                return { title, price, image, url, location };
            });
        }''')
        print(f"[OLX] Found {len(products)} products")
        browser.close()
    for p in products:
        p["source"] = "OLX"
    return products


@router.get("/compare")
async def compare_prices(q: str):
    print(f"[API] Searching for: {q}")
    loop = asyncio.get_event_loop()

    # Run both sync scrapers in separate threads simultaneously
    daraz_future = loop.run_in_executor(executor, scrape_daraz_sync, q)
    olx_future = loop.run_in_executor(executor, scrape_olx_sync, q)

    try:
        daraz_results = await daraz_future
    except Exception as e:
        print(f"[API] Daraz error: {e}")
        daraz_results = []

    try:
        olx_results = await olx_future
    except Exception as e:
        print(f"[API] OLX error: {e}")
        olx_results = []

    all_products = daraz_results + olx_results

    for product in all_products:
        product["price_normalized"] = normalize_price(product.get("price", ""))

    all_products.sort(
        key=lambda x: x["price_normalized"] if x["price_normalized"] is not None else float('inf')
    )

    return {
        "query": q,
        "total": len(all_products),
        "results": all_products
    }