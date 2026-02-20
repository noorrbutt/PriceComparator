from playwright.async_api import async_playwright
import asyncio

async def scrape_daraz(query: str):
    products = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()

        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })

        url = f"https://www.daraz.pk/catalog/?q={query.replace(' ', '+')}"
        print(f"[Daraz] Scraping: {url}")
        await page.goto(url)
        await page.wait_for_load_state("networkidle")

        products = await page.evaluate('''() => {
            const cards = document.querySelectorAll('[data-qa-locator="product-item"]');
            
            return Array.from(cards).map(card => {
                // Title is in the <a> tag's title attribute inside .RfADt
                // This is more reliable than innerText because innerText
                // also grabs the badge icon text
                const titleEl = card.querySelector('.RfADt a');
                const title = titleEl?.getAttribute('title') || titleEl?.innerText?.trim() || "N/A";

                // Price is inside .ooOxS
                const price = card.querySelector('.ooOxS')?.innerText?.trim() || "N/A";

                // Image src is a real URL (not lazy loaded at card level)
                const image = card.querySelector('img')?.src || "";

                // URL — note daraz uses // instead of https:// so we add it
                const rawUrl = card.querySelector('a')?.getAttribute('href') || "";
                const url = rawUrl.startsWith('//') ? 'https:' + rawUrl : rawUrl;

                return { title, price, image, url };
            });
        }''')

        print(f"[Daraz] Found {len(products)} products")
        await browser.close()

    for p in products:
        p["source"] = "Daraz"

    return products


if __name__ == "__main__":
    results = asyncio.run(scrape_daraz("iphone 15"))
    for r in results:
        print(r)