import asyncio
import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin, urlparse

from playwright.async_api import async_playwright

BASE_URL = "https://www.trendyol.com"
SEARCH_URL = BASE_URL + "/sr?q={query}"
DEFAULT_QUERY = "termos matara"
LIMIT = 20

CARD_SELECTORS = [
    ".p-card-wrppr",
    "[data-testid='product-card-wrapper']",
    ".product-card",
]

PRICE_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:TL|₺)",
    flags=re.I,
)

# Bu kelimeleri içeren satırlardaki TL tutarları ürün fiyatı değildir.
IGNORE_PRICE_WORDS = (
    "indirim",
    "kupon",
    "puan",
    "cashback",
    "kazanç",
    "kazanc",
    "trendyol plus",
)


def to_float(raw: str | None):
    if not raw:
        return None
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extract_current_price(text: str | None):
    """Karttaki ilk gerçek satış fiyatını döndürür.

    Eski fiyat, kupon, indirim tutarı ve Plus fiyatı ile ilgilenmez.
    Fiyat geçmişini biz kendi veritabanımızda tutacağız.
    """
    if not text:
        return None

    for line in text.replace("\xa0", " ").splitlines():
        clean = line.strip()
        if not clean:
            continue

        lower = clean.casefold()
        if any(word in lower for word in IGNORE_PRICE_WORDS):
            continue

        match = PRICE_PATTERN.search(clean)
        if not match:
            continue

        value = to_float(match.group(1))
        if value is not None:
            return value

    return None


async def text_first(card, selectors):
    for selector in selectors:
        try:
            loc = card.locator(selector).first
            if await loc.count():
                text = (await loc.inner_text()).strip()
                if text:
                    return text
        except Exception:
            pass
    return None


async def attr_first(card, selectors, attr):
    for selector in selectors:
        try:
            loc = card.locator(selector).first
            if await loc.count():
                value = await loc.get_attribute(attr)
                if value:
                    return value
        except Exception:
            pass
    return None


async def get_product_href(card):
    try:
        if await card.evaluate("el => el.tagName.toLowerCase()") == "a":
            href = await card.get_attribute("href")
            if href:
                return href
    except Exception:
        pass

    for selector in ["a[href*='-p-']", "a[href*='/p-']", "a[href]"]:
        try:
            loc = card.locator(selector).first
            if await loc.count():
                href = await loc.get_attribute("href")
                if href and not href.startswith("javascript:"):
                    return href
        except Exception:
            pass

    return None


def clean_brand(brand_text: str | None, title: str | None, product_url: str):
    # Trendyol bazı kartlarda brand alanına "Marka + Ürün adı" veriyor.
    # Ürün adını sondan çıkararak sadece markayı bırakıyoruz.
    if brand_text and title and brand_text.endswith(title):
        brand = brand_text[: -len(title)].strip()
        if brand:
            return brand

    if brand_text and title and brand_text != title:
        return brand_text.strip()

    # Fallback: URL'deki ilk path segmenti genellikle marka slug'ıdır.
    parts = [p for p in urlparse(product_url).path.split("/") if p]
    if parts:
        return parts[0].replace("-", " ").title()

    return brand_text


async def extract_card(card):
    href = await get_product_href(card)
    if not href:
        return None

    product_url = urljoin(BASE_URL, href.split("?")[0])

    brand_text = await text_first(card, [
        ".prdct-desc-cntnr-ttl",
        "[class*='brand']",
        "[data-testid*='brand']",
    ])

    title = await text_first(card, [
        ".prdct-desc-cntnr-name",
        ".prdct-desc-cntnr",
        "[class*='product-name']",
        "[class*='title']",
        "[data-testid*='name']",
    ])

    if not title:
        title = await attr_first(card, ["img"], "alt")

    try:
        card_text = (await card.inner_text()).strip()
    except Exception:
        card_text = ""

    price = extract_current_price(card_text)

    image_url = await attr_first(card, ["img"], "src")
    if not image_url:
        image_url = await attr_first(card, ["img"], "data-src")
    if image_url and image_url.startswith("//"):
        image_url = "https:" + image_url

    brand = clean_brand(brand_text, title, product_url)

    return {
        "merchant": "Trendyol",
        "brand": brand,
        "title": title,
        "price": price,
        "image_url": image_url,
        "product_url": product_url,
    }


async def main():
    url = SEARCH_URL.format(query=quote_plus(DEFAULT_QUERY))

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            locale="tr-TR",
            viewport={"width": 1365, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/140.0.0.0 Safari/537.36"
            ),
        )
        page = await context.new_page()

        print(f"Opening: {url}")
        response = await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        print("HTTP status:", response.status if response else None)

        await page.wait_for_timeout(4000)
        await page.evaluate("window.scrollTo(0, document.body.scrollHeight / 3)")
        await page.wait_for_timeout(2000)

        card_locator = None
        used_selector = None

        for selector in CARD_SELECTORS:
            locator = page.locator(selector)
            count = await locator.count()
            print(f"Selector {selector!r}: {count}")
            if count:
                card_locator = locator
                used_selector = selector
                break

        if card_locator is None:
            title = await page.title()
            body_text = (await page.locator("body").inner_text())[:1000]
            print("No product cards found.")
            print("Page title:", title)
            print("Body preview:", body_text)
            Path("trendyol_products.json").write_text("[]", encoding="utf-8")
            await browser.close()
            raise SystemExit(2)

        products = []
        seen = set()
        count = min(await card_locator.count(), 80)

        for i in range(count):
            item = await extract_card(card_locator.nth(i))
            if not item or not item["product_url"] or item["product_url"] in seen:
                continue

            seen.add(item["product_url"])
            products.append(item)

            if len(products) >= LIMIT:
                break

        result = {
            "ok": len(products) > 0,
            "source": "trendyol",
            "query": DEFAULT_QUERY,
            "selector": used_selector,
            "count": len(products),
            "products": products,
        }

        output = json.dumps(result, ensure_ascii=False, indent=2)
        print(output)
        Path("trendyol_products.json").write_text(output, encoding="utf-8")

        await browser.close()

        if not products:
            raise SystemExit(3)


if __name__ == "__main__":
    asyncio.run(main())
