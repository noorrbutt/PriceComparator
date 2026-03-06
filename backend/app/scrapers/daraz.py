from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import asyncio


async def scrape_daraz(query: str):
    products = []

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-blink-features=AutomationControlled",
                "--disable-dev-shm-usage",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1366, "height": 768},
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            locale="en-PK",
            timezone_id="Asia/Karachi",
        )

        try:
            # Apply stealth to the context, then open a page from it
            await Stealth().apply_stealth_async(context)
            page = await context.new_page()

            url = f"https://www.daraz.pk/catalog/?q={query.replace(' ', '+')}"
            print(f"[Daraz] Scraping: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            try:
                await page.wait_for_selector(
                    '[data-qa-locator="product-item"], .no-result', timeout=20000
                )
            except Exception:
                await page.evaluate("window.scrollTo(0, 500)")
                await asyncio.sleep(2)

            products = await page.evaluate(
                """() => {
                const cards = document.querySelectorAll('[data-qa-locator="product-item"]');
                return Array.from(cards).map(card => {
                    const titleEl = card.querySelector(".RfADt a");
                    const title = titleEl?.getAttribute("title") || titleEl?.innerText?.trim() || "N/A";
                    const price = card.querySelector(".ooOxS")?.innerText?.trim() || "N/A";
                    const image = card.querySelector("img")?.src || "";
                    const rawUrl = card.querySelector("a")?.getAttribute("href") || "";
                    const url = rawUrl.startsWith("//") ? "https:" + rawUrl : rawUrl;
                    return { title, price, image, url };
                });
            }"""
            )

            print(f"[Daraz] Found {len(products)} products")

        except Exception as e:
            print(f"[Daraz] Error: {e}")
        finally:
            await browser.close()

    for item in products:
        item["source"] = "Daraz"

    return products


if __name__ == "__main__":
    results = asyncio.run(scrape_daraz("iphone 15"))
    for r in results:
        print(r)
