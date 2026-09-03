import json
import os
import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote_plus, urlencode, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.hepsiburada.com"
SEARCH_URL = BASE_URL + "/ara?q={query}"
DEFAULT_QUERY = os.getenv("HB_QUERY", "termos matara").strip() or "termos matara"
LIMIT = int(os.getenv("HB_LIMIT", "20"))
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = float(os.getenv("HB_REQUEST_DELAY", "0.35"))

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

SUPABASE_URL = os.getenv(
    "SUPABASE_URL",
    "https://cmexmobjpeavlppmffqi.supabase.co",
).rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def canonical_url(url: str) -> str:
    parsed = urlparse(url)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", "", ""))


def normalize_text(value: str | None) -> str:
    if not value:
        return ""
    value = value.casefold().strip()
    value = unicodedata.normalize("NFKD", value)
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9çğıöşü]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def clean_brand(product: dict) -> str | None:
    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    elif isinstance(brand, list) and brand:
        first = brand[0]
        brand = first.get("name") if isinstance(first, dict) else first
    if brand:
        return str(brand).strip() or None

    title = str(product.get("name") or "").strip()
    return title.split()[0] if title else None


def clean_gtin(value) -> str | None:
    if value is None:
        return None

    if isinstance(value, list):
        candidates = value
    else:
        candidates = [value]

    for candidate in candidates:
        # Hepsiburada JSON-LD bazen "1210001903470 -1" gibi ek metin taşıyabiliyor.
        for digits in re.findall(r"(?<!\d)\d{8,14}(?!\d)", str(candidate)):
            if len(digits) in (8, 12, 13, 14):
                return digits
    return None


def image_url(product: dict) -> str | None:
    image = product.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    elif isinstance(image, dict):
        image = image.get("url") or image.get("contentUrl")
    if not image:
        return None
    return str(image).strip() or None


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def product_json_ld(html: str) -> dict | None:
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except json.JSONDecodeError:
            continue
        for item in walk_json(parsed):
            item_type = item.get("@type")
            if item_type == "Product" or (isinstance(item_type, list) and "Product" in item_type):
                return item
    return None


def extract_product_urls(html: str, limit: int) -> list[str]:
    soup = BeautifulSoup(html, "html.parser")
    urls: list[str] = []
    seen: set[str] = set()

    for anchor in soup.select("a[href]"):
        href = anchor.get("href")
        if not href:
            continue

        url = canonical_url(urljoin(BASE_URL, href))
        parsed = urlparse(url)
        if parsed.netloc not in {"www.hepsiburada.com", "hepsiburada.com"}:
            continue

        path = parsed.path.lower()
        if "-p-" not in path and "-p/" not in path:
            continue

        if url in seen:
            continue

        seen.add(url)
        urls.append(url)
        if len(urls) >= limit:
            break

    return urls


def get_offer(product: dict) -> dict:
    offers = product.get("offers") or {}
    if isinstance(offers, list):
        # İlk geçerli fiyatlı teklifi seç.
        for offer in offers:
            if isinstance(offer, dict) and (offer.get("price") is not None or offer.get("lowPrice") is not None):
                return offer
        return offers[0] if offers and isinstance(offers[0], dict) else {}
    return offers if isinstance(offers, dict) else {}


def to_float(value) -> float | None:
    if value is None:
        return None
    text = str(value).strip().replace("₺", "").replace("TL", "").strip()
    if not text:
        return None

    if "," in text:
        text = text.replace(".", "").replace(",", ".")

    try:
        return float(text)
    except ValueError:
        return None


def merchant_product_id(product: dict, product_url: str) -> str | None:
    for candidate in (product.get("sku"), product.get("productID"), product.get("mpn")):
        if candidate:
            match = re.search(r"\b(HB(?:CV|V)?[A-Z0-9]+)\b", str(candidate), flags=re.I)
            if match:
                return match.group(1).upper()

    match = re.search(r"-p-([A-Z0-9]+)(?:$|[/?#])", product_url, flags=re.I)
    return match.group(1).upper() if match else None


def parse_product_page(product_url: str, html: str) -> dict | None:
    product = product_json_ld(html)
    if not product:
        return None

    offer = get_offer(product)
    price = to_float(offer.get("price") or offer.get("lowPrice"))
    title = str(product.get("name") or "").strip()
    sku = merchant_product_id(product, product_url)

    if not title or price is None or not sku:
        return None

    availability = str(offer.get("availability") or "").casefold()
    in_stock = "outofstock" not in availability

    gtin = clean_gtin(
        product.get("gtin14")
        or product.get("gtin13")
        or product.get("gtin12")
        or product.get("gtin8")
        or product.get("gtin")
    )

    return {
        "merchant": "Hepsiburada",
        "merchant_product_id": sku,
        "brand": clean_brand(product),
        "title": title,
        "price": price,
        "image_url": image_url(product),
        "product_url": canonical_url(product_url),
        "in_stock": in_stock,
        "gtin": gtin,
    }


def fetch(session: requests.Session, url: str) -> requests.Response:
    response = session.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response


def collect(query: str = DEFAULT_QUERY, limit: int = LIMIT) -> list[dict]:
    search_url = SEARCH_URL.format(query=quote_plus(query))
    session = requests.Session()
    session.headers.update(REQUEST_HEADERS)

    print(f"Opening search: {search_url}")
    response = fetch(session, search_url)
    print("Search HTTP:", response.status_code)
    print("Search HTML length:", len(response.text))

    product_urls = extract_product_urls(response.text, limit)
    print(f"Discovered products: {len(product_urls)}")

    products: list[dict] = []
    for index, product_url in enumerate(product_urls, start=1):
        try:
            time.sleep(REQUEST_DELAY_SECONDS)
            product_response = fetch(session, product_url)
            item = parse_product_page(product_url, product_response.text)
            if not item:
                print(f"[{index}/{len(product_urls)}] SKIP: ürün verisi okunamadı -> {product_url}")
                continue

            products.append(item)
            print(
                f"[{index}/{len(product_urls)}] OK | "
                f"{item['merchant_product_id']} | {item['price']:.2f} TRY | {item['title'][:80]}"
            )
        except requests.RequestException as exc:
            print(f"[{index}/{len(product_urls)}] HTTP ERROR: {exc}")

    return products


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


def get_or_create_merchant() -> str:
    rows = supabase_request(
        "GET",
        "merchants",
        params={"slug": "eq.hepsiburada", "select": "id", "limit": "1"},
    )
    if rows:
        return rows[0]["id"]

    rows = supabase_request(
        "POST",
        "merchants",
        body={
            "name": "Hepsiburada",
            "slug": "hepsiburada",
            "domain": "hepsiburada.com",
            "active": True,
        },
        prefer="return=representation",
    )
    return rows[0]["id"]


def find_offer(merchant_id: str, merchant_product_id_value: str):
    rows = supabase_request(
        "GET",
        "offers",
        params={
            "merchant_id": f"eq.{merchant_id}",
            "merchant_product_id": f"eq.{merchant_product_id_value}",
            "select": "id,product_variant_id",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def create_product_and_variant(item: dict) -> str:
    merchant_product_id_value = item["merchant_product_id"]
    slug = f"hepsiburada-{merchant_product_id_value.lower()}"

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
            "gtin": item.get("gtin"),
            "sku": f"hepsiburada:{merchant_product_id_value}",
            "image_url": item.get("image_url"),
            "active": True,
        },
        prefer="return=representation",
    )
    return variants[0]["id"]


def save_products_to_supabase(products: list[dict]) -> int:
    if not SUPABASE_SERVICE_ROLE_KEY:
        print("Supabase skipped: SUPABASE_SERVICE_ROLE_KEY tanımlı değil.")
        return 0

    merchant_id = get_or_create_merchant()
    checked_at = datetime.now(timezone.utc).isoformat()
    saved = 0

    for item in products:
        offer = find_offer(merchant_id, item["merchant_product_id"])

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
                    "in_stock": item["in_stock"],
                    "last_checked_at": checked_at,
                    "updated_at": checked_at,
                },
                prefer="return=minimal",
            )
        else:
            variant_id = create_product_and_variant(item)
            rows = supabase_request(
                "POST",
                "offers",
                body={
                    "product_variant_id": variant_id,
                    "merchant_id": merchant_id,
                    "merchant_product_id": item["merchant_product_id"],
                    "product_url": item["product_url"],
                    "price": item["price"],
                    "currency": "TRY",
                    "in_stock": item["in_stock"],
                    "image_url": item.get("image_url"),
                    "last_checked_at": checked_at,
                },
                prefer="return=representation",
            )
            offer_id = rows[0]["id"]

        supabase_request(
            "POST",
            "price_history",
            body={
                "offer_id": offer_id,
                "price": item["price"],
                "in_stock": item["in_stock"],
                "checked_at": checked_at,
            },
            prefer="return=minimal",
        )
        saved += 1

    print(f"Supabase: {saved} Hepsiburada ürün/fiyat kaydı işlendi.")
    return saved


def main():
    products = collect(DEFAULT_QUERY, LIMIT)

    result = {
        "ok": bool(products),
        "source": "hepsiburada",
        "query": DEFAULT_QUERY,
        "count": len(products),
        "products": products,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if products:
        save_products_to_supabase(products)
    else:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
