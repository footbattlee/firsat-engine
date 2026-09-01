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

PRICE_PATTERN = re.compile(
    r"(?P<raw>\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:TL|₺)",
    flags=re.I,
)

PROMO_WORDS = (
    "kupon",
    "indirim",
    "cashback",
    "puan",
    "kazanç",
    "kazanc",
)


def to_float(raw: str | None):
    if not raw:
        return None
    try:
        return float(raw.replace(".", "").replace(",", "."))
    except ValueError:
        return None


def is_promo_price(text: str, start: int, end: int) -> bool:
    """Decide whether a TL amount belongs to a campaign label instead of product price."""
    lower = text.casefold()

    # Check a tight context around the amount so one promo phrase on the same line
    # does not cause real product prices later in the line to be discarded.
    left = lower[max(0, start - 35):start]
    right = lower[end:min(len(lower), end + 35)]
    around = left + " " + right

    if any(word in around for word in PROMO_WORDS):
        return True

    # Common forms: "750 TL'ye 150 TL indirim", "200 TL kupon".
    tail = lower[end:min(len(lower), end + 50)]
    if "tl'ye" in lower[max(0, start - 5):min(len(lower), end + 8)]:
        return True
    if any(word in tail for word in PROMO_WORDS):
        return True

    return False


def extract_price_mentions(text: str | None):
    """Extract actual product price mentions and ignore coupon/discount amounts."""
    if not text:
        return []

    normalized = text.replace("\xa0", " ")
    mentions = []

    for match in PRICE_PATTERN.finditer(normalized):
        if is_promo_price(normalized, match.start(), match.end()):
            continue

        value = to_float(match.group("raw"))
        if value is None:
            continue

        mentions.append(
            {
                "value": value,
                "text": match.group(0).strip(),
                "start": match.start(),
            }
        )

    # DOM may repeat the same label/price. Remove only immediately repeated values.
    deduped = []
    for mention in mentions:
        if deduped and mention["value"] == deduped[-1]["value"]:
            continue
        deduped.append(mention)

    return deduped


def parse_price(text: str | None):
    mentions = extract_price_mentions(text)
    return mentions[0]["value"] if mentions else None


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
    values = [m["value"] for m in mentions]
    if not values:
        return None, None, None, None

    lower = full_text.casefold()
    current = values[0]
    old = None
    conditional = None
    conditional_type = None

    # Normal price + Trendyol Plus special price.
    if "trendyol plus" in lower and len(values) >= 2:
        current = values[0]
        conditional = values[-1]
        conditional_type = "trendyol_plus"
        return current, None, conditional, conditional_type

    # Current discounted/sepette price first, comparison/list price last.
    if len(values) >= 2 and values[-1] > values[0]:
        current = values[0]
        old = values[-1]

    return current, old, conditional, conditional_type


async def extract_price_from_card(card):
    try:
        full_text = (await card.inner_text()).strip()
    except Exception:
        full_text = ""

    mentions = extract_price_mentions(full_text)
    price, old_price, conditional_price, conditional_price_type = classify_prices(
        full_text, mentions
    )

    # Fallback only when full-card context yielded nothing.
    if price is None:
        price_text = await text_first(card, CURRENT_PRICE_SELECTORS)
        price = parse_price(price_text)

    if old_price is None and price is not None:
        old_price_text = await text_first(card, OLD_PRICE_SELECTORS)
        candidate = parse_price(old_price_text)
        if candidate is not None and candidate > price:
            old_price = candidate

    debug_price_text = " | ".join(
        f"{m['value']:.2f}" for m in mentions
    )

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
