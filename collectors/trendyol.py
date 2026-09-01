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

# Fiyat için özellikle fiyat değerini taşıyan alanları kullanıyoruz.
# Generic [class*='price'] kaldırıldı; kampanya/taksit tutarlarını fiyat sanabiliyordu.
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


def parse_price(text: str | None):
    if not text:
        return None

    text = text.replace("\xa0", " ").strip()

    # Önce TL/₺ ile doğrudan ilişkili değerleri yakala.
    matches = re.findall(
        r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:TL|₺)",
        text,
        flags=re.I,
    )

    # Element sadece "1.299,90" gibi çıplak değer döndürürse de destekle.
    if not matches:
        matches = re.findall(
            r"\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?",
            text,
        )

    if not matches:
        return None

    raw = matches[-1]
    value = raw.replace(".", "").replace(",", ".")

    try:
        return float(value)
    except ValueError:
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

    for selector in [
        "a[href*='-p-']",
        "a[href*='/p-']",
        "a[href]",
    ]:
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
    # 1) En güvenilir yol: doğrudan mevcut fiyat elementi.
    price_text = await text_first(card, CURRENT_PRICE_SELECTORS)
    price = parse_price(price_text)

    # 2) Eski fiyat ayrı alanda varsa al.
    old_price_text = await text_first(card, OLD_PRICE_SELECTORS)
    old_price = parse_price(old_price_text)

    # 3) Selector bulunamazsa yalnızca TL/₺ içeren metin düğümlerini tara.
    # Kampanya metinlerindeki "15", "200" gibi çıplak sayıları artık fiyat saymıyoruz.
    if price is None:
        try:
            tl_nodes = card.locator("text=/\\d[\\d.,]*\\s*(TL|₺)/i")
            values = []
            count = min(await tl_nodes.count(), 20)
            for i in range(count):
                try:
                    txt = (await tl_nodes.nth(i).inner_text()).strip()
                    val = parse_price(txt)
                    if val is not None:
                        values.append((val, txt))
                except Exception:
                    pass

            # Kartta fiyatlar genellikle eski fiyat -> yeni fiyat şeklinde görünür.
            # Son TL değerini mevcut fiyat kabul ediyoruz.
            if values:
                price = values[-1][0]
                price_text = values[-1][1]
                if old_price is None and len(values) > 1:
                    candidate = values[-2][0]
                    if candidate > price:
                        old_price = candidate
                        old_price_text = values[-2][1]
        except Exception:
            pass

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
        # Test aşamasında fiyatın hangi metinden geldiğini görelim.
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
