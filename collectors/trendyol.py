import asyncio
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.parse import quote, quote_plus, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

from playwright.async_api import async_playwright

BASE_URL = "https://www.trendyol.com"
SEARCH_URL = BASE_URL + "/sr?q={query}"
DEFAULT_QUERY = "termos matara"
LIMIT = 20

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://cmexmobjpeavlppmffqi.supabase.co",
).rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()

CARD_SELECTORS = [
    ".p-card-wrppr",
    "[data-testid='product-card-wrapper']",
    ".product-card",
]

PRICE_PATTERN = re.compile(
    r"(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:TL|₺)",
    flags=re.I,
)

PROMO_WORDS = (
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


def parse_first_price(text: str | None):
    if not text:
        return None
    match = PRICE_PATTERN.search(text.replace("\xa0", " "))
    return to_float(match.group(1)) if match else None


def fallback_price_from_text(text: str | None):
    if not text:
        return None

    for line in text.replace("\xa0", " ").splitlines():
        clean = line.strip()
        if not clean:
            continue
        lower = clean.casefold()
        if any(word in lower for word in PROMO_WORDS):
            continue
        value = parse_first_price(clean)
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


async def extract_current_price(card):
    """Karttaki güncel satış fiyatını doğrudan fiyat DOM elemanlarından seçer."""
    try:
        candidates = await card.evaluate(
            r"""
            card => {
              const nodes = [...card.querySelectorAll(
                "[data-testid*='price'], [class*='price'], [class*='Price'], " +
                "[class*='prc-'], [class*='selling'], [class*='discounted']"
              )];

              const promoWords = ['indirim','kupon','puan','cashback','kazanç','kazanc','trendyol plus'];
              const goodWords = ['current','selling','discounted','sale','prc-box-dscntd','prc-box-sllng'];
              const badWords = ['old','original','list','strike','crossed','campaign','coupon','benefit'];
              const moneyRe = /(\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?|\d+(?:,\d{1,2})?)\s*(?:TL|₺)/i;

              const result = [];
              for (let i = 0; i < nodes.length; i++) {
                const el = nodes[i];
                const style = window.getComputedStyle(el);
                if (style.display === 'none' || style.visibility === 'hidden') continue;

                const text = (el.innerText || el.textContent || '').trim();
                if (!moneyRe.test(text)) continue;

                const cls = String(el.className || '').toLowerCase();
                const testid = String(el.getAttribute('data-testid') || '').toLowerCase();
                const meta = cls + ' ' + testid;
                const own = text.toLowerCase();
                const parent = (el.parentElement?.innerText || '').toLowerCase();

                let score = 0;
                if (goodWords.some(w => meta.includes(w))) score += 100;
                if (meta.includes('price')) score += 35;
                if (badWords.some(w => meta.includes(w))) score -= 140;
                if (promoWords.some(w => own.includes(w))) score -= 180;
                if (promoWords.some(w => parent.includes(w)) && !goodWords.some(w => meta.includes(w))) score -= 80;
                if (el.children.length === 0) score += 20;
                if ((text.match(/TL|₺/gi) || []).length === 1) score += 15;

                result.push({ text, score, order: i });
              }

              result.sort((a, b) => (b.score - a.score) || (a.order - b.order));
              return result.slice(0, 20);
            }
            """
        )
    except Exception:
        candidates = []

    for candidate in candidates:
        value = parse_first_price(candidate.get("text"))
        if value is not None and candidate.get("score", 0) >= 0:
            return value

    try:
        card_text = (await card.inner_text()).strip()
    except Exception:
        card_text = ""

    return fallback_price_from_text(card_text)


def clean_brand(brand_text: str | None, title: str | None, product_url: str):
    if brand_text and title and brand_text.endswith(title):
        brand = brand_text[: -len(title)].strip()
        if brand:
            return brand

    if brand_text and title and brand_text != title:
        return brand_text.strip()

    parts = [p for p in urlparse(product_url).path.split("/") if p]
    if parts:
        return parts[0].replace("-", " ").title()

    return brand_text


def merchant_product_id_from_url(product_url: str):
    match = re.search(r"-p-(\d+)(?:$|[/?#])", product_url)
    return match.group(1) if match else None


def normalize_text(value: str | None):
    if not value:
        return ""
    value = value.casefold().strip()
    value = re.sub(r"[^a-z0-9çğıöşü]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def supabase_request(method: str, table: str, *, params=None, body=None, prefer=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil")

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + urlencode(params, doseq=True, safe="(),.*:-")

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=payload, headers=headers, method=method)

    try:
        with urlopen(request, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {detail}") from exc


def get_or_create_merchant():
    rows = supabase_request(
        "GET",
        "merchants",
        params={"slug": "eq.trendyol", "select": "id", "limit": "1"},
    )
    if rows:
        return rows[0]["id"]

    rows = supabase_request(
        "POST",
        "merchants",
        body={
            "name": "Trendyol",
            "slug": "trendyol",
            "domain": "trendyol.com",
            "active": True,
        },
        prefer="return=representation",
    )
    return rows[0]["id"]


def find_offer(merchant_id: str, merchant_product_id: str):
    rows = supabase_request(
        "GET",
        "offers",
        params={
            "merchant_id": f"eq.{merchant_id}",
            "merchant_product_id": f"eq.{merchant_product_id}",
            "select": "id,product_variant_id",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def create_product_and_variant(item, merchant_product_id: str):
    slug = f"trendyol-{merchant_product_id}"
    products = supabase_request(
        "POST",
        "products",
        params={"on_conflict": "slug"},
        body={
            "brand": item.get("brand"),
            "title": item["title"],
            "normalized_title": normalize_text(item["title"]),
            "image_url": item.get("image_url"),
            "slug": slug,
            "active": True,
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    product_id = products[0]["id"]

    variants = supabase_request(
        "POST",
        "product_variants",
        body={
            "product_id": product_id,
            "sku": f"trendyol:{merchant_product_id}",
            "image_url": item.get("image_url"),
            "active": True,
        },
        prefer="return=representation",
    )
    return variants[0]["id"]


def save_products_to_supabase(products):
    if not SUPABASE_SERVICE_ROLE_KEY:
        print("Supabase skipped: SUPABASE_SERVICE_ROLE_KEY tanımlı değil.")
        return 0

    merchant_id = get_or_create_merchant()
    checked_at = datetime.now(timezone.utc).isoformat()
    saved = 0

    for item in products:
        if item.get("price") is None:
            continue

        merchant_product_id = merchant_product_id_from_url(item["product_url"])
        if not merchant_product_id:
            print(f"Supabase skipped: product id bulunamadı -> {item['product_url']}")
            continue

        offer = find_offer(merchant_id, merchant_product_id)

        if offer:
            offer_id = offer["id"]
            supabase_request(
                "PATCH",
                "offers",
                params={"id": f"eq.{offer_id}"},
                body={
                    "price": item["price"],
                    "product_url": item["product_url"],
                    "image_url": item.get("image_url"),
                    "currency": "TRY",
                    "in_stock": True,
                    "last_checked_at": checked_at,
                    "updated_at": checked_at,
                },
                prefer="return=minimal",
            )
        else:
            variant_id = create_product_and_variant(item, merchant_product_id)
            rows = supabase_request(
                "POST",
                "offers",
                body={
                    "product_variant_id": variant_id,
                    "merchant_id": merchant_id,
                    "merchant_product_id": merchant_product_id,
                    "product_url": item["product_url"],
                    "price": item["price"],
                    "currency": "TRY",
                    "in_stock": True,
                    "image_url": item.get("image_url"),
                    "last_checked_at": checked_at,
                },
                prefer="return=representation",
            )
            offer_id = rows[0]["id"]

        # Her çalıştırmada saatlik fiyat snapshot'ı tutulur.
        supabase_request(
            "POST",
            "price_history",
            body={
                "offer_id": offer_id,
                "price": item["price"],
                "in_stock": True,
                "checked_at": checked_at,
            },
            prefer="return=minimal",
        )
        saved += 1

    print(f"Supabase: {saved} ürün/fiyat kaydı işlendi.")
    return saved


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

    price = await extract_current_price(card)

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

    save_products_to_supabase(products)


if __name__ == "__main__":
    asyncio.run(main())
