from playwright.async_api import async_playwright
from playwright_stealth import Stealth
import asyncio


async def scrape_olx(query: str):
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

            url = f"https://www.olx.com.pk/items/q-{query.replace(' ', '-')}"
            print(f"[OLX] Scraping: {url}")

            await page.goto(url, wait_until="domcontentloaded", timeout=60000)

            try:
                await page.wait_for_selector(
                    "._8b88d490, [data-aut-id='itemBox'], li[data-aut-id]",
                    timeout=20000,
                )
            except Exception:
                await page.evaluate("window.scrollTo(0, 500)")
                await asyncio.sleep(2)

            products = await page.evaluate(
                """() => {
                let cards = document.querySelectorAll("._8b88d490");
                if (cards.length === 0) {
                    cards = document.querySelectorAll("li[data-aut-id]");
                }

                return Array.from(cards).map(card => {
                    const title =
                        card.querySelector("._1093b649")?.innerText?.trim() ||
                        card.querySelector("[data-aut-id='itemTitle']")?.innerText?.trim() ||
                        "N/A";

                    const price =
                        card.querySelector(".f83175ac")?.innerText?.trim() ||
                        card.querySelector("[data-aut-id='itemPrice']")?.innerText?.trim() ||
                        "N/A";

                    const img = card.querySelector("img");
                    const image = img?.getAttribute("data-src") || img?.src || "";

                    const rawUrl = card.querySelector("a")?.getAttribute("href") || "";
                    const url = rawUrl.startsWith("/")
                        ? "https://www.olx.com.pk" + rawUrl
                        : rawUrl;

                    const location =
                        card.querySelector(".f047db22")?.innerText?.trim() ||
                        card.querySelector("[data-aut-id='item-location']")?.innerText?.trim() ||
                        "";

                    return { title, price, image, url, location };
                }).filter(item => item.title !== "N/A");
            }"""
            )

            print(f"[OLX] Found {len(products)} products")

        except Exception as e:
            print(f"[OLX] Error: {e}")
        finally:
            await browser.close()

    for item in products:
        item["source"] = "OLX"

    return products


if __name__ == "__main__":
    results = asyncio.run(scrape_olx("iphone 15"))
    for r in results:
        print(r)
