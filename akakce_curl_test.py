#!/usr/bin/env python3
import html
import json
import re
import subprocess
import time
import urllib.parse

UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
BASE = "https://www.akakce.com"
SEARCH_URL = "https://www.akakce.com/arama/?q={q}"

MARKETPLACES = [
    ("trendyol.com", "Trendyol"),
    ("hepsiburada.com", "Hepsiburada"),
    ("amazon.com.tr", "Amazon"),
    ("n11.com", "n11"),
    ("pttavm.com", "PttAVM"),
    ("idefix.com", "idefix"),
    ("pazarama.com", "Pazarama"),
    ("mediamarkt.com.tr", "MediaMarkt"),
    ("vatanbilgisayar.com", "Vatan"),
    ("teknosa.com", "Teknosa"),
]


def fetch(url: str, referer: str = "https://www.akakce.com/", retries: int = 3) -> str:
    args = [
        "curl",
        "-sL",
        "--max-time",
        "30",
        "-A",
        UA,
        "-H",
        "Accept-Language: tr-TR,tr;q=0.9",
    ]
    if referer:
        args += ["-H", f"Referer: {referer}"]

    body = ""
    for attempt in range(retries):
        result = subprocess.run(
            args + [url],
            capture_output=True,
            text=True,
            timeout=45,
        )
        body = result.stdout
        print(
            f"Fetch attempt {attempt + 1}/{retries} | "
            f"exit={result.returncode} | html={len(body)}"
        )
        if len(body) > 50000:
            return body
        if result.stderr.strip():
            print("curl stderr:", result.stderr.strip()[:300])
        if attempt < retries - 1:
            time.sleep(5 * (attempt + 1))
    return body


def parse_products(raw_html: str) -> list[dict]:
    decoded = html.unescape(raw_html)
    products = []

    blocks = re.findall(
        r'\[0,\{&quot;code&quot;:\[0,\d+\].*?\}\]',
        raw_html,
    )
    if not blocks:
        blocks = re.findall(
            r'\[0,\{"code":\[0,\d+\].*?\}\]',
            decoded,
        )

    for block in blocks:
        block = html.unescape(block)
        name = re.search(r'"name":\[0,"([^"]{5,200})"\]', block)
        price = re.search(r'"price":\[0,([0-9.]+)\]', block)
        if not name or not price:
            continue

        product = {
            "name": name.group(1),
            "price": float(price.group(1)),
        }

        for key in ("imageUrl", "url", "mkName", "vdName"):
            match = re.search(rf'"{key}":\[0,"([^"]+)"\]', block)
            if not match:
                continue
            if key == "mkName":
                product["brand"] = match.group(1)
            elif key == "vdName":
                product["vendor"] = match.group(1)
            else:
                product[key.lower()] = match.group(1)

        code = re.search(r'"code":\[0,(\d+)\]', block)
        if code:
            product["code"] = code.group(1)

        if product.get("url", "").startswith("/"):
            product["url"] = BASE + product["url"]

        products.append(product)

    seen = set()
    unique = []
    for product in products:
        key = product.get("url") or product["name"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(product)
    return unique


def marketplace_from_url(url: str) -> str:
    for domain, name in MARKETPLACES:
        if domain in url:
            return name
    return "Other"


def parse_offers(product_url: str):
    raw = fetch(product_url, referer="https://www.akakce.com/")
    decoded = html.unescape(raw)

    pattern = (
        r'"@type":"Offer","availability":"[^"]*","price":"([0-9.]+)",'
        r'"url":"([^"]+)","seller":\{"@type":"Organization","name":"([^"]+)"'
    )

    offers = []
    for price, url, seller in re.findall(pattern, decoded):
        value = float(price)
        if value <= 0 or not url.startswith("http") or "akakce.com" in url:
            continue
        offers.append(
            {
                "price": value,
                "seller": seller.split("/")[-1],
                "marketplace": marketplace_from_url(url),
                "url": url,
            }
        )

    seen = set()
    unique = []
    for offer in offers:
        key = offer["url"].split("?")[0]
        if key in seen:
            continue
        seen.add(key)
        unique.append(offer)

    unique.sort(key=lambda item: item["price"])
    return unique


def main():
    query = "stanley"
    search_url = SEARCH_URL.format(q=urllib.parse.quote(query))

    print("AKAKCE CURL TEST")
    print("Search:", search_url)

    raw = fetch(search_url)
    print("Search HTML length:", len(raw))

    if len(raw) < 50000:
        print("FAIL: Gercek Akakce sayfasi gelmedi.")
        print("Preview:", raw[:500].replace("\n", " "))
        return

    products = parse_products(raw)
    print("Products found:", len(products))

    if not products:
        print("FAIL: Urun kartlari parse edilemedi.")
        return

    print("\nFirst 5 products:")
    for product in products[:5]:
        print(
            f"- {product.get('price')} TL | "
            f"{product.get('vendor', '?')} | "
            f"{product.get('name', '')[:80]}"
        )

    first = products[0]
    print("\nFIRST PRODUCT")
    print(json.dumps(first, ensure_ascii=False, indent=2))

    product_url = first.get("url")
    if not product_url:
        print("FAIL: Ilk urunde URL yok.")
        return

    print("\nOFFERS")
    print("Product URL:", product_url)
    offers = parse_offers(product_url)
    print("Direct offers found:", len(offers))

    if not offers:
        print("FAIL: Dogrudan magaza teklifi bulunamadi.")
        return

    for offer in offers[:10]:
        print(
            f"{offer['price']:.2f} TL | "
            f"{offer['marketplace']:12} | "
            f"{offer['seller'][:30]:30} | "
            f"{offer['url']}"
        )

    amazon = [o for o in offers if o["marketplace"] == "Amazon"]
    hb = [o for o in offers if o["marketplace"] == "Hepsiburada"]
    trendyol = [o for o in offers if o["marketplace"] == "Trendyol"]

    print("\nSUMMARY")
    print("Amazon offers:", len(amazon))
    print("Hepsiburada offers:", len(hb))
    print("Trendyol offers:", len(trendyol))
    print("Cheapest:", json.dumps(offers[0], ensure_ascii=False))


if __name__ == "__main__":
    main()
