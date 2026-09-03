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

BASE_URL = "https://www.mediamarkt.com.tr"
SEARCH_URL = BASE_URL + "/tr/search.html?query={query}"
DEFAULT_QUERY = os.getenv("MEDIAMARKT_QUERY", "termos matara").strip() or "termos matara"
LIMIT = int(os.getenv("MEDIAMARKT_LIMIT", "20"))
REQUEST_TIMEOUT = 30
REQUEST_DELAY_SECONDS = float(os.getenv("MEDIAMARKT_REQUEST_DELAY", "0.35"))
REQUEST_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
}
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def canonical_url(url):
    p = urlparse(url)
    return urlunparse((p.scheme, p.netloc, p.path, "", "", ""))


def normalize_text(value):
    value = unicodedata.normalize("NFKD", (value or "").casefold().strip())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9çğıöşü]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def title_matches_query(title, query):
    title_tokens = set(normalize_text(title).split())
    query_tokens = [t for t in normalize_text(query).split() if len(t) >= 3]
    return not query_tokens or any(token in title_tokens for token in query_tokens)


def walk_json(value):
    if isinstance(value, dict):
        yield value
        for child in value.values(): yield from walk_json(child)
    elif isinstance(value, list):
        for child in value: yield from walk_json(child)


def product_json_ld(html):
    soup = BeautifulSoup(html, "html.parser")
    for script in soup.select('script[type="application/ld+json"]'):
        raw = script.string or script.get_text(strip=True)
        if not raw: continue
        try: parsed = json.loads(raw)
        except Exception: continue
        for item in walk_json(parsed):
            typ = item.get("@type")
            if typ == "Product" or (isinstance(typ, list) and "Product" in typ): return item
    return None


def extract_product_urls(html, max_candidates):
    soup = BeautifulSoup(html, "html.parser")
    out, seen = [], set()
    for a in soup.select("a[href]"):
        url = canonical_url(urljoin(BASE_URL, a.get("href", "")))
        p = urlparse(url)
        if p.netloc not in {"www.mediamarkt.com.tr", "mediamarkt.com.tr"}: continue
        if "/tr/product/" not in p.path.lower() or not p.path.lower().endswith(".html"): continue
        if url in seen: continue
        seen.add(url); out.append(url)
        if len(out) >= max_candidates: break
    return out


def first_offer(offers):
    if isinstance(offers, list):
        for offer in offers:
            if isinstance(offer, dict) and (offer.get("price") is not None or offer.get("lowPrice") is not None): return offer
        return offers[0] if offers and isinstance(offers[0], dict) else {}
    return offers if isinstance(offers, dict) else {}


def to_float(value):
    if value is None: return None
    s = str(value).replace("TL", "").replace("₺", "").strip()
    if "," in s: s = s.replace(".", "").replace(",", ".")
    try: return float(s)
    except ValueError: return None


def brand_name(product):
    brand = product.get("brand")
    if isinstance(brand, dict): brand = brand.get("name")
    if brand: return str(brand).strip()
    title = str(product.get("name") or "").strip()
    return title.split()[0] if title else None


def image_url(product):
    image = product.get("image")
    if isinstance(image, list): image = image[0] if image else None
    if isinstance(image, dict): image = image.get("url") or image.get("contentUrl")
    return str(image).strip() if image else None


def clean_gtin(product):
    for key in ("gtin14", "gtin13", "gtin12", "gtin8", "gtin"):
        value = product.get(key)
        if not value: continue
        m = re.search(r"(?<!\d)\d{8,14}(?!\d)", str(value))
        if m and len(m.group()) in (8, 12, 13, 14): return m.group()
    return None


def parse_product_page(product_url, html):
    product = product_json_ld(html)
    if not product: return None
    offer = first_offer(product.get("offers"))
    price = to_float(offer.get("price") or offer.get("lowPrice"))
    title = str(product.get("name") or "").strip()
    sku = str(product.get("sku") or product.get("productID") or product.get("mpn") or "").strip()
    if not title or price is None or not sku: return None
    availability = str(offer.get("availability") or "").casefold()
    return {"merchant":"MediaMarkt","merchant_product_id":sku,"brand":brand_name(product),"title":title,"price":price,"image_url":image_url(product),"product_url":canonical_url(product_url),"in_stock":"outofstock" not in availability,"gtin":clean_gtin(product)}


def fetch(session, url):
    r = session.get(url, timeout=REQUEST_TIMEOUT); r.raise_for_status(); return r


def collect(query=DEFAULT_QUERY, limit=LIMIT):
    session = requests.Session(); session.headers.update(REQUEST_HEADERS)
    search_url = SEARCH_URL.format(query=quote_plus(query))
    print("Opening search:", search_url)
    r = fetch(session, search_url); print("Search HTTP:", r.status_code)
    urls = extract_product_urls(r.text, max(limit * 10, 50)); print("Candidate product URLs:", len(urls))
    products=[]; seen_skus=set()
    for i,url in enumerate(urls,1):
        if len(products) >= limit: break
        try:
            time.sleep(REQUEST_DELAY_SECONDS)
            item=parse_product_page(url, fetch(session,url).text)
            if not item:
                print(f"[{i}/{len(urls)}] SKIP: {url}"); continue
            if not title_matches_query(item["title"], query):
                print(f"[{i}/{len(urls)}] IRRELEVANT: {item['title'][:80]}"); continue
            if item["merchant_product_id"] in seen_skus:
                print(f"[{i}/{len(urls)}] DUPLICATE SKU: {item['merchant_product_id']}"); continue
            seen_skus.add(item["merchant_product_id"]); products.append(item)
            print(f"[{i}/{len(urls)}] OK | {item['merchant_product_id']} | {item['price']:.2f} TRY | {item['title'][:80]}")
        except requests.RequestException as exc: print(f"[{i}/{len(urls)}] HTTP ERROR: {exc}")
    return products


def sb(method, table, params=None, body=None, prefer=None):
    if not SUPABASE_SERVICE_ROLE_KEY: raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil")
    url=f"{SUPABASE_URL}/rest/v1/{table}"
    if params: url += "?" + urlencode(params,doseq=True,safe="(),.*:-")
    headers={"apikey":SUPABASE_SERVICE_ROLE_KEY,"Authorization":f"Bearer {SUPABASE_SERVICE_ROLE_KEY}","Content-Type":"application/json"}
    if prefer: headers["Prefer"]=prefer
    payload=None if body is None else json.dumps(body,ensure_ascii=False).encode()
    req=Request(url,data=payload,headers=headers,method=method)
    try:
        with urlopen(req,timeout=30) as resp:
            raw=resp.read().decode(); return json.loads(raw) if raw else None
    except HTTPError as exc: raise RuntimeError(f"Supabase HTTP {exc.code}: {exc.read().decode(errors='replace')}") from exc


def get_or_create_merchant():
    rows=sb("GET","merchants",{"slug":"eq.mediamarkt","select":"id","limit":"1"})
    if rows:return rows[0]["id"]
    rows=sb("POST","merchants",body={"name":"MediaMarkt","slug":"mediamarkt","domain":"mediamarkt.com.tr","active":True},prefer="return=representation")
    return rows[0]["id"]


def find_offer(merchant_id,mpid):
    rows=sb("GET","offers",{"merchant_id":f"eq.{merchant_id}","merchant_product_id":f"eq.{mpid}","select":"id","limit":"1"})
    return rows[0] if rows else None


def create_variant(item):
    slug=f"mediamarkt-{re.sub(r'[^a-z0-9]+','-',item['merchant_product_id'].lower()).strip('-')}"
    rows=sb("POST","products",{"on_conflict":"slug"},{"brand":item.get("brand"),"title":item["title"],"normalized_title":normalize_text(item["title"]),"image_url":item.get("image_url"),"slug":slug,"active":True},"resolution=merge-duplicates,return=representation")
    product_id=rows[0]["id"]
    rows=sb("POST","product_variants",body={"product_id":product_id,"gtin":item.get("gtin"),"sku":f"mediamarkt:{item['merchant_product_id']}","image_url":item.get("image_url"),"active":True},prefer="return=representation")
    return rows[0]["id"]


def save_products_to_supabase(products):
    if not SUPABASE_SERVICE_ROLE_KEY:
        print("Supabase skipped: SUPABASE_SERVICE_ROLE_KEY tanımlı değil."); return 0
    merchant_id=get_or_create_merchant(); checked_at=datetime.now(timezone.utc).isoformat(); saved=0
    for item in products:
        offer=find_offer(merchant_id,item["merchant_product_id"])
        if offer:
            offer_id=offer["id"]
            sb("PATCH","offers",{"id":f"eq.{offer_id}"},{"price":item["price"],"product_url":item["product_url"],"image_url":item.get("image_url"),"currency":"TRY","in_stock":item["in_stock"],"last_checked_at":checked_at,"updated_at":checked_at},"return=minimal")
        else:
            variant_id=create_variant(item)
            rows=sb("POST","offers",body={"product_variant_id":variant_id,"merchant_id":merchant_id,"merchant_product_id":item["merchant_product_id"],"product_url":item["product_url"],"price":item["price"],"currency":"TRY","in_stock":item["in_stock"],"image_url":item.get("image_url"),"last_checked_at":checked_at},prefer="return=representation")
            offer_id=rows[0]["id"]
        sb("POST","price_history",body={"offer_id":offer_id,"price":item["price"],"in_stock":item["in_stock"],"checked_at":checked_at},prefer="return=minimal"); saved+=1
    print(f"Supabase: {saved} MediaMarkt ürün/fiyat kaydı işlendi."); return saved


def main():
    products=collect()
    print(json.dumps({"ok":bool(products),"source":"mediamarkt","query":DEFAULT_QUERY,"count":len(products),"products":products},ensure_ascii=False,indent=2))
    if products: save_products_to_supabase(products)
    else: raise SystemExit(2)

if __name__=="__main__": main()
