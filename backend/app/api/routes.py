import asyncio
import re
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi import APIRouter, Response
import httpx
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
            # Strip Daraz thumbnail suffix e.g. _200x200q80.avif → original jpg/png
            for prod in products:
                if prod.get("image"):
                    prod["image"] = re.sub(r"_\d+x\d+q\d+\.\w+$", "", prod["image"])
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

                    const img = card.querySelector("img");
                    const image = img?.src?.startsWith("http") ? img.src : "";

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


@router.get("/compare")
async def compare_prices(q: str):
    print(f"[API] Searching for: {q}")
    loop = asyncio.get_event_loop()

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
