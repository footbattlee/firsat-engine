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


def extract_price_mentions(text: str | None):
    """Return price mentions while ignoring coupon/reward amounts."""
    if not text:
        return []

    mentions = []
    lines = text.replace("\xa0", " ").splitlines()

    for line in lines:
        clean = line.strip()
        if not clean:
            continue

        lower = clean.casefold()
        # These TL amounts are benefits, not the product selling price.
        if any(word in lower for word in ["kupon", "cashback", "puan", "kazanç", "kazanc"]):
            continue

        for raw in re.findall(PRICE_PATTERN, clean, flags=re.I):
            value = to_float(raw)
            if value is not None:
                mentions.append({"value": value, "text": clean})

    return mentions


def extract_price_values(text: str | None):
    return [m["value"] for m in extract_price_mentions(text)]


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


def classify_prices(full_text: str, mentions):
    """
    Returns normal current price, old price and optional conditional price.

    Rules observed in current Trendyol cards:
    - 'Sepette 1.099,99 TL / 1.299,99 TL' -> current 1099.99, old 1299.99
    - '%15 983 TL / 1.159 TL' -> current 983, old 1159
    - '679 TL Trendyol Plus ile 645,05 TL' -> current 679, Plus price 645.05
    - '200 TL Kupon / 1.599,90 TL' -> coupon is ignored, current 1599.90
    """
    values = [m["value"] for m in mentions]
    if not values:
        return None, None, None, None

    lower = full_text.casefold()
    current = values[0]
    old = None
    conditional = None
    conditional_type = None

    # Membership-specific price should not be confused with old/current price.
    if "trendyol plus" in lower and len(values) >= 2:
        current = values[0]
        conditional = values[-1]
        conditional_type = "trendyol_plus"
        return current, None, conditional, conditional_type

    # Sepette price is an immediately obtainable selling price; keep higher shown
    # amount as comparison/old price when available.
    if "sepette" in lower and len(values) >= 2:
        current = values[0]
        if values[-1] > current:
            old = values[-1]
        return current, old, None, None

    # Discounted cards generally render current price first, crossed/list price last.
    if len(values) >= 2 and values[0] < values[-1]:
        current = values[0]
        old = values[-1]

    return current, old, conditional, conditional_type


async def extract_price_from_card(card):
    # Use full card context so coupon/Plus/sepette labels can be interpreted correctly.
    try:
        full_text = (await card.inner_text()).strip()
    except Exception:
        full_text = ""

    mentions = extract_price_mentions(full_text)
    price, old_price, conditional_price, conditional_price_type = classify_prices(full_text, mentions)

    # If full-card parsing did not find a price, try known price elements.
    price_text = await text_first(card, CURRENT_PRICE_SELECTORS)
    old_price_text = await text_first(card, OLD_PRICE_SELECTORS)

    if price is None:
        price = parse_price(price_text)

    if old_price is None:
        candidate = parse_price(old_price_text)
        if candidate is not None and price is not None and candidate > price:
            old_price = candidate

    # Keep compact diagnostics during test phase.
    debug_price_text = " | ".join(m["text"] for m in mentions)

    return (
        price,
        old_price,
        conditional_price,
        conditional_price_type,
        debug_price_text,
    )


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

    (
        price,
        old_price,
        conditional_price,
        conditional_price_type,
        price_text,
    ) = await extract_price_from_card(card)

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
        "conditional_price": conditional_price,
        "conditional_price_type": conditional_price_type,
        "image_url": image_url,
        "product_url": product_url,
        "query": DEFAULT_QUERY,
        "price_text": price_text,
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
