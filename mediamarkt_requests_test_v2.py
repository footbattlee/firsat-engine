#!/usr/bin/env python3
import json
import re
from urllib.parse import urljoin, urlparse, urlunparse

import requests
from bs4 import BeautifulSoup

BASE = "https://www.mediamarkt.com.tr"
SEARCH = BASE + "/tr/search.html?query=stanley"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}


def canonical(url):
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def product_objects(html):
    soup = BeautifulSoup(html, "html.parser")
    out = []
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text(strip=True)
        if not raw:
            continue
        try:
            parsed = json.loads(raw)
        except Exception:
            continue
        for obj in walk_json(parsed):
            typ = obj.get("@type")
            if typ == "Product" or (isinstance(typ, list) and "Product" in typ):
                out.append(obj)
    return out


def likely_product_url(url):
    p = urlparse(url)
    if "mediamarkt.com.tr" not in p.netloc:
        return False
    path = p.path.lower()
    if "/category/" in path or "/search" in path:
        return False
    # MediaMarkt ürün URL'leri zamanla değişebildiği için kategori dışı .html
    # bağlantılarını aday al, sonra JSON-LD Product ile doğrula.
    return path.endswith(".html")


def first_offer(offers):
    if isinstance(offers, list):
        for x in offers:
            if isinstance(x, dict) and (x.get("price") is not None or x.get("lowPrice") is not None):
                return x
        return offers[0] if offers and isinstance(offers[0], dict) else {}
    return offers if isinstance(offers, dict) else {}


def main():
    session = requests.Session(); session.headers.update(HEADERS)
    print("MEDIAMARKT TEST V2")
    print("Search:", SEARCH)
    r = session.get(SEARCH, timeout=30)
    print("Search HTTP:", r.status_code)
    print("HTML length:", len(r.text))
    r.raise_for_status()

    soup = BeautifulSoup(r.text, "html.parser")
    candidates, seen = [], set()
    for a in soup.select("a[href]"):
        url = canonical(urljoin(BASE, a.get("href", "")))
        if likely_product_url(url) and url not in seen:
            seen.add(url); candidates.append(url)

    print("Filtered .html candidates:", len(candidates))
    for u in candidates[:20]:
        print(" ", u)

    print("\nValidating candidates via Product JSON-LD...")
    valid = []
    for i, url in enumerate(candidates[:40], 1):
        try:
            p = session.get(url, timeout=30)
            if p.status_code != 200:
                print(f"[{i}] HTTP {p.status_code} {url}")
                continue
            products = product_objects(p.text)
            if not products:
                continue
            # Ürün sayfasında ilk Product nesnesini al.
            obj = products[0]
            name = obj.get("name")
            offer = first_offer(obj.get("offers"))
            price = offer.get("price") or offer.get("lowPrice")
            # Kategori sayfasındaki ItemList/Product nesnelerini yanlış pozitif saymamak için
            # sayfa title ile ürün adının bir miktar örtüşmesini bekle.
            title = BeautifulSoup(p.text, "html.parser").title
            title_text = title.get_text(" ", strip=True).casefold() if title else ""
            name_text = str(name or "").casefold()
            tokens = [t for t in re.findall(r"[a-z0-9çğıöşü]{4,}", name_text) if t not in {"urun","fiyat","model"}]
            overlap = sum(1 for t in tokens[:8] if t in title_text)
            if not name or price is None or overlap < 2:
                continue
            valid.append((url, obj, offer))
            print(f"VALID {len(valid)} | {price} {offer.get('priceCurrency')} | {name}")
            print(" URL:", url)
            if len(valid) >= 5:
                break
        except requests.RequestException as exc:
            print(f"[{i}] ERROR {exc}")

    print("\nSUMMARY")
    print("Valid product pages:", len(valid))
    for url, obj, offer in valid:
        brand = obj.get("brand")
        if isinstance(brand, dict): brand = brand.get("name")
        image = obj.get("image")
        if isinstance(image, list): image = image[0] if image else None
        print("-", obj.get("name"))
        print("  Brand:", brand)
        print("  SKU:", obj.get("sku") or obj.get("productID") or obj.get("mpn"))
        print("  GTIN:", obj.get("gtin14") or obj.get("gtin13") or obj.get("gtin12") or obj.get("gtin"))
        print("  Price:", offer.get("price") or offer.get("lowPrice"))
        print("  Stock:", offer.get("availability"))
        print("  Image:", image)
        print("  URL:", url)

    if not valid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
