import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter
from playwright.sync_api import sync_playwright

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


def scrape_daraz_sync(query: str):
    products = []
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-blink-features=AutomationControlled"],
        )
        page = browser.new_page()
        page.set_extra_http_headers(
            {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            }
        )
        url = f"https://www.daraz.pk/catalog/?q={query.replace(' ', '+')}"
        print(f"[Daraz] Scraping: {url}")
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            try:
                page.wait_for_selector(
                    '[data-qa-locator="product-item"]', timeout=20000
                )
            except:
                pass
            products = page.evaluate(
                """() => {
                const cards = document.querySelectorAll('[data-qa-locator="product-item"]');
                return Array.from(cards).map(card => {
                    const titleEl = card.querySelector(".RfADt a");
                    const title = titleEl?.getAttribute("title") || titleEl?.innerText?.trim() || "N/A";
                    const price = card.querySelector(".ooOxS")?.innerText?.trim() || "N/A";
                    const img = card.querySelector("img");
                    const rawImg = img?.getAttribute("data-src") || img?.src || "";
                    const image = rawImg.startsWith("http") ? rawImg : "";
                    const rawUrl = card.querySelector("a")?.getAttribute("href") || "";
                    const url = rawUrl.startsWith("//") ? "https:" + rawUrl : rawUrl;
                    return { title, price, image, url };
                }).filter(p => p.title !== "N/A");
            }"""
            )
            print(f"[Daraz] Found {len(products)} products")
        except Exception as e:
            print(f"[Daraz] Error: {e}")
        finally:
            browser.close()
    for prod in products:
        prod["source"] = "Daraz"
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
            # networkidle is too slow — domcontentloaded + manual wait is faster
            page.goto(url, wait_until="domcontentloaded", timeout=60000)

            # Try selectors in order of reliability
            matched = None
            for selector in [
                "li[data-aut-id]",
                "[data-aut-id='itemBox']",
                "._8b88d490",
                ".EIR5N li",
            ]:
                try:
                    page.wait_for_selector(selector, timeout=12000)
                    matched = selector
                    print(f"[OLX] Matched selector: {selector}")
                    break
                except:
                    continue

            if not matched:
                print("[OLX] No selector matched, falling back to scroll+wait")
                page.evaluate("window.scrollTo(0, 600)")
                time.sleep(3)

            products = page.evaluate(
                """() => {
                // Try card selectors from most to least specific
                let cards = document.querySelectorAll("li[data-aut-id]");
                if (!cards.length) cards = document.querySelectorAll("[data-aut-id='itemBox']");
                if (!cards.length) cards = document.querySelectorAll("._8b88d490");
                if (!cards.length) cards = document.querySelectorAll(".EIR5N li");

                const results = [];
                cards.forEach(card => {
                    // Title — multiple fallbacks
                    const title =
                        card.querySelector("[data-aut-id='itemTitle']")?.innerText?.trim() ||
                        card.querySelector("h2")?.innerText?.trim() ||
                        card.querySelector("h3")?.innerText?.trim() ||
                        card.querySelector("._1093b649")?.innerText?.trim() ||
                        "";

                    // Price — multiple fallbacks
                    const price =
                        card.querySelector("[data-aut-id='itemPrice']")?.innerText?.trim() ||
                        card.querySelector("._2Ks63")?.innerText?.trim() ||
                        card.querySelector(".f83175ac")?.innerText?.trim() ||
                        // Generic: find any element containing "Rs"
                        (() => {
                            const els = card.querySelectorAll("*");
                            for (const el of els) {
                                if (el.children.length === 0 && el.innerText?.includes("Rs")) {
                                    return el.innerText.trim();
                                }
                            }
                            return "";
                        })();

                    // Image — only real URLs, no base64
                    const img = card.querySelector("img");
                    const rawImg = img?.getAttribute("data-src") || img?.src || "";
                    const image = rawImg.startsWith("http") ? rawImg : "";

                    // URL
                    const rawUrl = card.querySelector("a")?.getAttribute("href") || "";
                    const url = rawUrl.startsWith("/")
                        ? "https://www.olx.com.pk" + rawUrl
                        : rawUrl;

                    // Location
                    const location =
                        card.querySelector("[data-aut-id='item-location']")?.innerText?.trim() ||
                        card.querySelector(".f047db22")?.innerText?.replace("•", "").trim() ||
                        "";

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


@router.get("/compare")
async def compare_prices(q: str):
    print(f"[API] Searching for: {q}")
    loop = asyncio.get_event_loop()

    # No timeout limit on executor — let scrapers run as long as needed
    daraz_future = loop.run_in_executor(executor, scrape_daraz_sync, q)
    olx_future = loop.run_in_executor(executor, scrape_olx_sync, q)

    try:
        daraz_results = await asyncio.wait_for(daraz_future, timeout=120)
    except Exception as e:
        print(f"[API] Daraz error: {e}")
        daraz_results = []

    try:
        olx_results = await asyncio.wait_for(olx_future, timeout=120)
    except Exception as e:
        print(f"[API] OLX error: {e}")
        olx_results = []

    all_products = daraz_results + olx_results

    for product in all_products:
        product["price_normalized"] = normalize_price(product.get("price", ""))

    all_products.sort(
        key=lambda x: (
            x["price_normalized"] if x["price_normalized"] is not None else float("inf")
        )
    )

    return {"query": q, "total": len(all_products), "results": all_products}
