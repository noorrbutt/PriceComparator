# backend/app/scrapers/olx.py

from playwright.async_api import async_playwright
import asyncio

async def scrape_olx(query: str):
    """
    OLX is a classifieds site — unlike Daraz, listings are from
    individual sellers, not retailers. This means:
    - Prices are negotiable and inconsistent
    - Same product can have wildly different prices
    - No guaranteed stock or shipping
    We label it clearly so the frontend can show users the difference.
    """

    products = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        url = f"https://www.olx.com.pk/items/q-{query.replace(' ', '-')}"
        print(f"[OLX] Scraping: {url}")
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        await page.wait_for_selector('._8b88d490', timeout=15000)
        products = await page.evaluate('''() => {
            const cards = document.querySelectorAll('._8b88d490');

            return Array.from(cards).map(card => {
                // Title is in h2 with class _1093b649
                const title = card.querySelector('._1093b649')?.innerText?.trim() || "N/A";

                // Price is in span with class f83175ac
                const price = card.querySelector('.f83175ac')?.innerText?.trim() || "N/A";

                // Image — OLX lazy loads, so we check data-src first, then src
                const img = card.querySelector('img');
                const image = img?.getAttribute('data-src') || img?.src || "";

                // URL is relative (/item/...) so we prepend the domain
                const rawUrl = card.querySelector('a')?.getAttribute('href') || "";
                const url = rawUrl.startsWith('/') ? 'https://www.olx.com.pk' + rawUrl : rawUrl;

                // Location — useful for OLX since it's classifieds
                const location = card.querySelector('.f047db22')?.innerText?.replace('•', '').trim() || "";

                return { title, price, image, url, location };
            });
        }''')

        print(f"[OLX] Found {len(products)} products")
        await browser.close()

    for p in products:
        p["source"] = "OLX"

    return products


if __name__ == "__main__":
    results = asyncio.run(scrape_olx("iphone 15"))
    for r in results:
        print(r)