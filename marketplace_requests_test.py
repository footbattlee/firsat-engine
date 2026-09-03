#!/usr/bin/env python3
"""Public-page diagnostics for Turkish marketplaces.

Tests whether plain requests + BeautifulSoup can reach search pages for
n11, Teknosa, MediaMarkt TR and Vatan, discovers likely product links, then
checks the first product page for Product JSON-LD.

No CAPTCHA/anti-bot bypass is attempted. If a site returns a security page,
we stop and report it.
"""

import json
import re
import time
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

SITES = [
    {
        "name": "n11",
        "base": "https://www.n11.com",
        "search": "https://www.n11.com/arama?q=stanley",
        "accept": lambda u: "n11.com/urun/" in u,
    },
    {
        "name": "Teknosa",
        "base": "https://www.teknosa.com",
        "search": "https://www.teknosa.com/arama/?s=stanley",
        "accept": lambda u: "teknosa.com/" in u and ("-p-" in u or "/p/" in u),
    },
    {
        "name": "MediaMarkt",
        "base": "https://www.mediamarkt.com.tr",
        "search": "https://www.mediamarkt.com.tr/tr/search.html?query=stanley",
        "accept": lambda u: "mediamarkt.com.tr/" in u and ("/product/" in u or ".html" in u),
    },
    {
        "name": "Vatan",
        "base": "https://www.vatanbilgisayar.com",
        "search": "https://www.vatanbilgisayar.com/arama/stanley/",
        "accept": lambda u: "vatanbilgisayar.com/" in u and (".html" in u or "/urun/" in u),
    },
]

BLOCK_MARKERS = (
    "just a moment",
    "are you a human",
    "captcha",
    "access denied",
    "güvenlik doğrulaması",
    "security check",
    "cloudflare",
)


def fetch(url: str):
    try:
        r = requests.get(url, headers=HEADERS, timeout=30, allow_redirects=True)
        return r
    except Exception as exc:
        print(f"REQUEST ERROR: {exc}")
        return None


def is_blocked(text: str, title: str) -> bool:
    haystack = f"{title}\n{text[:12000]}".lower()
    return any(m in haystack for m in BLOCK_MARKERS)


def discover_links(html: str, base: str, accept):
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.find_all("a", href=True):
        href = a.get("href", "").strip()
        if not href or href.startswith(("javascript:", "#", "mailto:")):
            continue
        url = urljoin(base, href).split("#", 1)[0]
        if accept(url) and url not in seen:
            seen.add(url)
            out.append(url)
    return out


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for v in value.values():
            yield from walk_json(v)
    elif isinstance(value, list):
        for v in value:
            yield from walk_json(v)


def find_product_jsonld(html: str):
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
        raw = script.string or script.get_text(" ", strip=True)
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except Exception:
            continue
        for obj in walk_json(data):
            typ = obj.get("@type")
            types = typ if isinstance(typ, list) else [typ]
            if "Product" in types:
                return obj
    return None


def first_offer(offers):
    if isinstance(offers, list):
        return offers[0] if offers else {}
    return offers if isinstance(offers, dict) else {}


def clean_price(value):
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().replace("TL", "").replace("₺", "")
    s = re.sub(r"\s+", "", s)
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def print_product_jsonld(product):
    if not product:
        print("Product JSON-LD: YOK")
        return
    brand = product.get("brand")
    if isinstance(brand, dict):
        brand = brand.get("name")
    image = product.get("image")
    if isinstance(image, list):
        image = image[0] if image else None
    offer = first_offer(product.get("offers"))
    price = offer.get("price") or offer.get("lowPrice")
    print("Product JSON-LD: VAR")
    print("  Name:", product.get("name"))
    print("  Brand:", brand)
    print("  SKU:", product.get("sku"))
    print("  GTIN:", product.get("gtin13") or product.get("gtin") or product.get("gtin12") or product.get("gtin14"))
    print("  Price:", clean_price(price))
    print("  Currency:", offer.get("priceCurrency"))
    print("  Availability:", offer.get("availability"))
    print("  Image:", image)


def run_site(site):
    print("\n" + "=" * 78)
    print(site["name"].upper())
    print("=" * 78)
    print("Search:", site["search"])

    r = fetch(site["search"])
    if r is None:
        return

    soup = BeautifulSoup(r.text, "html.parser")
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    print("HTTP:", r.status_code)
    print("Final URL:", r.url)
    print("Content-Type:", r.headers.get("content-type"))
    print("HTML length:", len(r.text))
    print("Title:", title[:180])

    if is_blocked(r.text, title):
        print("RESULT: BLOCKED / SECURITY PAGE")
        print("Preview:", soup.get_text(" ", strip=True)[:300])
        return

    links = discover_links(r.text, site["base"], site["accept"])
    print("Candidate product links:", len(links))
    for u in links[:5]:
        print(" ", u)

    if not links:
        print("RESULT: Search page accessible but no product link matched.")
        print("This may need site-specific HTML/API parsing.")
        return

    time.sleep(1.0)
    product_url = links[0]
    print("\nFirst product test:", product_url)
    p = fetch(product_url)
    if p is None:
        return
    psoup = BeautifulSoup(p.text, "html.parser")
    ptitle = psoup.title.get_text(" ", strip=True) if psoup.title else ""
    print("Product HTTP:", p.status_code)
    print("Product HTML length:", len(p.text))
    print("Product title:", ptitle[:180])

    if is_blocked(p.text, ptitle):
        print("Product RESULT: BLOCKED / SECURITY PAGE")
        return

    product = find_product_jsonld(p.text)
    print_product_jsonld(product)


if __name__ == "__main__":
    print("MARKETPLACE REQUESTS TEST")
    print("Plain requests + BeautifulSoup; no bypass/stealth.")
    for site in SITES:
        run_site(site)
