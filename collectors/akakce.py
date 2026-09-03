import asyncio
import json
import re
from pathlib import Path
from urllib.parse import quote, urljoin

from playwright.async_api import async_playwright

BASE_URL = "https://www.akakce.com"
DEFAULT_QUERY = "termos matara"
PRODUCT_LIMIT = 20
OFFER_LIMIT = 25

PRICE_RE = re.compile(r"(?<!\d)(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:TL|₺)", re.I)


def parse_price_tr(text: str | None):
    if not text:
        return None
    m = PRICE_RE.search(text.replace("\xa0", " "))
    if not m:
        return None
    raw = m.group(1)
    if "," in raw:
        raw = raw.replace(".", "").replace(",", ".")
    else:
        parts = raw.split(".")
        if len(parts) > 1 and all(len(p) == 3 for p in parts[1:]):
            raw = "".join(parts)
    try:
        return float(raw)
    except ValueError:
        return None


def normalize_space(value: str | None) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def is_product_url(href: str) -> bool:
    return bool(re.search(r",\d+\.html(?:$|[?#])", href or "", re.I))


async def wait_normal_page(page):
    await page.wait_for_timeout(2500)
    return await page.title()


async def discover_products(page, query: str, limit: int):
    search_url = f"{BASE_URL}/arama/?q={quote(query)}"
    print(f"Opening search: {search_url}")
    response = await page.goto(search_url, wait_until="domcontentloaded", timeout=45000)
    print(f"HTTP status: {response.status if response else 'N/A'}")
    title = await wait_normal_page(page)
    print(f"Page title: {title}")

    links = await page.locator("a[href]").evaluate_all(
        """
        els => els.map(a => ({
          href: a.href || '',
          title: (a.getAttribute('title') || a.textContent || '').trim()
        }))
        """
    )

    seen = set()
    products = []
    for item in links:
        href = item.get("href") or ""
        if not is_product_url(href) or href in seen:
            continue
        title_text = normalize_space(item.get("title"))
        if len(title_text) < 3:
            continue
        seen.add(href)
        products.append({"title": title_text, "akakce_url": href})
        if len(products) >= limit:
            break

    print(f"Discovered products: {len(products)}")
    return products


async def extract_product(page, product: dict):
    url = product["akakce_url"]
    print(f"\nProduct: {product['title']}")
    print(f"Opening: {url}")
    response = await page.goto(url, wait_until="domcontentloaded", timeout=45000)
    print(f"HTTP status: {response.status if response else 'N/A'}")
    await wait_normal_page(page)

    page_title = normalize_space(await page.title())

    # Product title: prefer H1, then discovered title.
    title = product["title"]
    h1 = page.locator("h1").first
    if await h1.count():
        txt = normalize_space(await h1.text_content())
        if txt:
            title = txt

    # Akakce offer list is generally under #PL. Keep extraction intentionally
    # generic so we can inspect the first real run before tightening selectors.
    offer_rows = page.locator("#PL li")
    if await offer_rows.count() == 0:
        offer_rows = page.locator("#PL > *")

    offers = []
    count = min(await offer_rows.count(), OFFER_LIMIT)
    for i in range(count):
        row = offer_rows.nth(i)
        try:
            text = normalize_space(await row.inner_text())
        except Exception:
            continue
        price = parse_price_tr(text)
        if price is None:
            continue

        merchant = None
        seller = None
        target_url = None

        anchors = row.locator("a[href]")
        anchor_count = await anchors.count()
        for j in range(min(anchor_count, 12)):
            a = anchors.nth(j)
            href = await a.get_attribute("href")
            atxt = normalize_space(await a.inner_text())
            title_attr = normalize_space(await a.get_attribute("title"))
            label = title_attr or atxt
            if href and not target_url:
                target_url = urljoin(BASE_URL, href)
            if label and len(label) >= 2:
                low = label.lower()
                if not any(x in low for x in ["satıcıya git", "saticiya git", "siteye git", "ürüne git", "urune git"]):
                    if merchant is None:
                        merchant = label
                    elif seller is None and label != merchant:
                        seller = label

        offers.append(
            {
                "merchant": merchant,
                "seller_name": seller,
                "price": price,
                "url": target_url,
                "raw_text": text[:500],
            }
        )

    offers.sort(key=lambda x: x["price"])
    cheapest = offers[0]["price"] if offers else None

    return {
        "title": title,
        "akakce_url": url,
        "page_title": page_title,
        "current_lowest_price": cheapest,
        "offer_count": len(offers),
        "offers": offers,
    }


async def main():
    query = DEFAULT_QUERY
    output_path = Path("akakce_products.json")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="tr-TR",
            timezone_id="Europe/Istanbul",
            viewport={"width": 1366, "height": 900},
        )
        page = await context.new_page()

        try:
            products = await discover_products(page, query, PRODUCT_LIMIT)
            results = []
            for product in products:
                try:
                    item = await extract_product(page, product)
                    results.append(item)
                    print(
                        f"  -> offers={item['offer_count']} "
                        f"lowest={item['current_lowest_price']}"
                    )
                except Exception as exc:
                    print(f"  ERROR: {exc}")

            payload = {
                "ok": bool(results),
                "source": "akakce",
                "query": query,
                "count": len(results),
                "products": results,
            }
            output_path.write_text(
                json.dumps(payload, ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            print(f"\nSaved: {output_path}")
            print(json.dumps({"ok": payload["ok"], "count": payload["count"]}, ensure_ascii=False))

            if not products:
                body = normalize_space(await page.locator("body").inner_text())
                print(f"Body preview: {body[:800]}")
        finally:
            await context.close()
            await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
