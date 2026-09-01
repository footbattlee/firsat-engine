import asyncio
import json
import re
from pathlib import Path
from urllib.parse import quote_plus, urljoin

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

CURRENT_PRICE_SELECTORS = [
    "[data-testid='price-current-price']",
    ".price-current-price",
    ".prc-box-dscntd",
    ".prc-box-sllng",
    ".product-price",
    "[class~='discounted-price']",
    "[class~='selling-price']",
]

OLD_PRICE_SELECTORS = [
    "[data-testid='price-original-price']",
    ".price-original-price",
    ".prc-box-orgnl",
    ".original-price",
    "[class~='old-price']",
]

PRICE_PATTERN = r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:TL|₺)"


def to_float(raw: str | None):
    if not raw:
        return None
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def extract_price_values(text: str | None):
    if not text:
        return []
    text = text.replace("\xa0", " ").strip()
    raws = re.findall(PRICE_PATTERN, text, flags=re.I)
    result = []
    for raw in raws:
        value = to_float(raw)
        if value is not None:
            result.append(value)
    return result


def parse_price(text: str | None):
    values = extract_price_values(text)
    if values:
        return values[0]

    if not text:
        return None

    raw_match = re.search(
        r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?",
        text,
    )
    return to_float(raw_match.group(0)) if raw_match else None


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


async def extract_price_from_card(card):
    price_text = await text_first(card, CURRENT_PRICE_SELECTORS)
    old_price_text = await text_first(card, OLD_PRICE_SELECTORS)

    price_values = extract_price_values(price_text)
    old_price_values = extract_price_values(old_price_text)

    price = price_values[0] if price_values else parse_price(price_text)
    old_price = old_price_values[0] if old_price_values else parse_price(old_price_text)

    # Trendyol bazı kartlarda aynı element içinde iki fiyat gösteriyor:
    # ilk değer güncel/sepette/indirimli fiyat, son değer normal-eski fiyat.
    # Örn: "983 TL\n1.159 TL" veya "Sepette\n1.099,99 TL\n1.299,99 TL".
    if len(price_values) >= 2:
        price = price_values[0]
        if old_price is None:
            old_price = price_values[-1]
            old_price_text = price_text

    # Selector ile bulunamazsa kart içindeki TL/₺ metinlerini topla.
    if price is None:
        try:
            full_text = (await card.inner_text()).strip()
            values = extract_price_values(full_text)
            if values:
                price = values[0]
                price_text = full_text
                if old_price is None and len(values) >= 2:
                    old_price = values[-1]
                    old_price_text = full_text
        except Exception:
            pass

    # Eski fiyat güncel fiyattan düşük/eşitse anlamsızdır; boş bırak.
    if price is not None and old_price is not None and old_price <= price:
        old_price = None
        old_price_text = None

    return price, old_price, price_text, old_price_text


async def extract_card(card):
    href = await get_product_href(card)
    if not href:
        return None

    product_url = urljoin(BASE_URL, href.split("?")[0])

    brand = await text_first(card, [
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

    price, old_price, price_text, old_price_text = await extract_price_from_card(card)

    image_url = await attr_first(card, ["img"], "src")
    if not image_url:
        image_url = await attr_first(card, ["img"], "data-src")
    if image_url and image_url.startswith("//"):
        image_url = "https:" + image_url

    return {
        "merchant": "Trendyol",
        "brand": brand,
        "title": title,
        "price": price,
        "old_price": old_price,
        "image_url": image_url,
        "product_url": product_url,
        "query": DEFAULT_QUERY,
        "price_text": price_text,
        "old_price_text": old_price_text,
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
