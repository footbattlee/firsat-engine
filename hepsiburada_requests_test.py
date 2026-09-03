import json
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse

BASE_URL = "https://www.hepsiburada.com"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) "
                  "Chrome/152.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}

TEST_URL = "https://www.hepsiburada.com/ara?q=stanley"


def fetch(url):
    response = requests.get(url, headers=HEADERS, timeout=30)

    print("URL:", response.url)
    print("HTTP:", response.status_code)
    print("Content-Type:", response.headers.get("content-type"))
    print("HTML length:", len(response.text))

    return response


def extract_product_urls(html):
    soup = BeautifulSoup(html, "html.parser")
    urls = []

    for a in soup.select("a[href]"):
        href = a.get("href")
        if not href:
            continue

        url = urljoin(BASE_URL, href)
        path = urlparse(url).path.lower()

        if "hepsiburada.com" not in url:
            continue

        if "-p-" in path or "-p/" in path:
            url = url.split("?")[0]
            if url not in urls:
                urls.append(url)

    return urls


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_json(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_json(child)


def extract_product_json_ld(html):
    soup = BeautifulSoup(html, "html.parser")

    for script in soup.select('script[type="application/ld+json"]'):
        try:
            data = json.loads(script.get_text(strip=True))
        except Exception:
            continue

        for item in walk_json(data):
            item_type = item.get("@type")

            if item_type == "Product":
                return item

            if isinstance(item_type, list) and "Product" in item_type:
                return item

    return None


print("=" * 70)
print("HEPSIBURADA REQUESTS TEST")
print("=" * 70)

response = fetch(TEST_URL)

print()
print("TITLE:")
soup = BeautifulSoup(response.text, "html.parser")

if soup.title:
    print(soup.title.get_text(strip=True))
else:
    print("Title yok")

print()
print("BODY PREVIEW:")
print(soup.get_text(" ", strip=True)[:500])

if response.status_code != 200:
    print()
    print("Arama sayfası erişilemedi.")
    raise SystemExit(1)

product_urls = extract_product_urls(response.text)

print()
print("Bulunan ürün URL sayısı:", len(product_urls))

for url in product_urls[:5]:
    print(url)

if not product_urls:
    print("HTML geldi ama ürün linki bulunamadı.")
    raise SystemExit(2)

print()
print("=" * 70)
print("İLK ÜRÜN TESTİ")
print("=" * 70)

product_url = product_urls[0]
product_response = fetch(product_url)

if product_response.status_code != 200:
    print("Ürün sayfası erişilemedi.")
    raise SystemExit(3)

product = extract_product_json_ld(product_response.text)

if not product:
    print("Product JSON-LD bulunamadı.")
    raise SystemExit(4)

print()
print("PRODUCT JSON-LD BULUNDU")
print("Name:", product.get("name"))
print("SKU:", product.get("sku"))
print("MPN:", product.get("mpn"))
print("GTIN:", product.get("gtin13") or product.get("gtin"))
print("Image:", product.get("image"))

offers = product.get("offers")

print()
print("Offers:")

if isinstance(offers, dict):
    print("Price:", offers.get("price"))
    print("Low price:", offers.get("lowPrice"))
    print("High price:", offers.get("highPrice"))
    print("Currency:", offers.get("priceCurrency"))
    print("Availability:", offers.get("availability"))
elif isinstance(offers, list):
    for offer in offers[:3]:
        print(offer)
else:
    print(offers)
