import json
import os
import random
import re
import time
import unicodedata
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import quote_plus, urlencode, urljoin, urlparse
from urllib.request import Request, urlopen

import requests
from bs4 import BeautifulSoup

BASE_URL = "https://www.amazon.com.tr"
SEARCH_URL = BASE_URL + "/s?k={query}"
ALT_SEARCH_URL = BASE_URL + "/s/?field-keywords={query}"
DEFAULT_QUERY = os.getenv("AMAZON_QUERY", "termos").strip() or "termos"
LIMIT = int(os.getenv("AMAZON_LIMIT", "20"))
REQUEST_TIMEOUT = int(os.getenv("AMAZON_TIMEOUT", "25"))
REQUEST_DELAY_SECONDS = float(os.getenv("AMAZON_REQUEST_DELAY", "0.6"))
MAX_RETRIES = int(os.getenv("AMAZON_MAX_RETRIES", "2"))
SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
PROXY_SERVER = os.getenv("PROXY_SERVER", "").strip()
PROXY_USERNAME = os.getenv("PROXY_USERNAME", "").strip()
PROXY_PASSWORD = os.getenv("PROXY_PASSWORD", "").strip()
AMAZON_ASSOCIATE_TAG = os.getenv("AMAZON_ASSOCIATE_TAG", "anlikindirimr-21").strip()

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/151.0.0.0 Safari/537.36",
]
ASIN_RE = re.compile(r"/(?:dp|gp/product)/([A-Z0-9]{10})(?:[/?#]|$)", re.I)


def headers():
    return {
        "User-Agent": random.choice(USER_AGENTS),
        "Accept-Language": "tr-TR,tr;q=0.9,en-US;q=0.8,en;q=0.7",
        "Accept-Encoding": "gzip, deflate, br",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Referer": "https://www.google.com/",
        "Cache-Control": "max-age=0",
        "Connection": "keep-alive",
        "Upgrade-Insecure-Requests": "1",
    }


def proxy_url():
    if not PROXY_SERVER:
        return None
    server = PROXY_SERVER
    if "://" not in server:
        server = "http://" + server
    if PROXY_USERNAME and PROXY_PASSWORD:
        parsed = urlparse(server)
        host = parsed.netloc or parsed.path
        return f"{parsed.scheme or 'http'}://{quote_plus(PROXY_USERNAME)}:{quote_plus(PROXY_PASSWORD)}@{host}"
    return server


def configure_session_proxy(session):
    proxy = proxy_url()
    if proxy:
        session.proxies.update({"http": proxy, "https": proxy})
        print("AMAZON  | proxy enabled")
    return proxy


def normalize_text(value):
    value = unicodedata.normalize("NFKD", (value or "").casefold().strip())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = re.sub(r"[^a-z0-9çğıöşü]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def parse_try_price(raw):
    if not raw:
        return None
    text = str(raw).replace("\xa0", " ").strip()
    text = re.sub(r"(?i)(TL|TRY|₺)", "", text)
    m = re.search(r"(\d[\d\.\s]*(?:,\d{1,2})?)", text)
    if not m:
        return None
    number = m.group(1).replace(" ", "")
    if "," in number:
        number = number.replace(".", "").replace(",", ".")
    elif number.count(".") > 1 or (number.count(".") == 1 and len(number.rsplit(".", 1)[1]) == 3):
        number = number.replace(".", "")
    try:
        value = float(number)
        return value if value > 0 else None
    except ValueError:
        return None


def extract_asin(url):
    m = ASIN_RE.search(url or "")
    return m.group(1).upper() if m else None


def canonical_product_url(asin):
    return f"{BASE_URL}/dp/{asin}"


def affiliate_product_url(asin):
    """Build Amazon's simple tagged direct-product affiliate link."""
    if not AMAZON_ASSOCIATE_TAG:
        return None
    return f"{BASE_URL}/dp/{asin}/ref=nosim?tag={AMAZON_ASSOCIATE_TAG}"


def clean_brand(raw):
    """Normalize Amazon byline text to a plain brand name."""
    if not raw:
        return None
    brand = str(raw).strip()
    brand = re.sub(r"(?i)^marka:\s*", "", brand)
    brand = re.sub(r"(?i)^şu\s+mağazayı\s+ziyaret\s+edin:\s*", "", brand)
    brand = re.sub(r"(?i)\s+(?:store[’']?u|mağazası(?:nı)?)\s+ziyaret\s+edin\s*$", "", brand)
    brand = re.sub(r"(?i)\s+store\s*$", "", brand)
    brand = re.sub(r"\s+", " ", brand).strip(" :-")
    return brand or None


def looks_blocked(html):
    lower = (html or "").casefold()
    markers = (
        "captcha",
        "robot check",
        "automated access",
        "enter the characters you see below",
    )
    # "üzgünüz" tek başına blok göstergesi değildir; normal Amazon/çerez
    # metinlerinde de geçebiliyor ve gerçek arama sonuçlarını yanlış pozitif
    # olarak engellenmiş saymamıza neden oluyor.
    return any(x in lower for x in markers)


def looks_like_search_page(html):
    if not html:
        return False
    soup = BeautifulSoup(html, "html.parser")
    return bool(
        soup.select_one("[data-component-type='s-search-result'][data-asin]")
        or soup.select_one("[data-asin] h2 a")
        or soup.select_one("a.s-pagination-next")
    )


def save_debug_html(html, label):
    if not html:
        return
    try:
        from pathlib import Path
        path = Path(f"amazon_debug_{label}.html")
        path.write_text(html, encoding="utf-8")
        print(f"AMAZON  | debug html saved | {path}")
    except Exception as exc:
        print(f"AMAZON  | debug save failed | {exc}")


def fetch_requests(url, session):
    last = None
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(url, headers=headers(), timeout=REQUEST_TIMEOUT, allow_redirects=True)
            content_type = (r.headers.get("content-type") or "").lower()
            blocked = looks_blocked(r.text)
            print(f"AMAZON  | requests | status={r.status_code} | type={content_type.split(';')[0] or '?'} | url={r.url}")
            if r.status_code == 200 and "text/html" in content_type and r.text and not blocked:
                if "/s" in urlparse(r.url).path and not looks_like_search_page(r.text):
                    save_debug_html(r.text, "requests_search_unrecognized")
                    last = "HTTP 200 ama Amazon arama DOM'u bulunamadı"
                else:
                    return r.text
            else:
                last = "CAPTCHA/bot check" if blocked else f"HTTP {r.status_code} type={content_type or '?'}"
        except requests.RequestException as exc:
            last = str(exc)
        if attempt + 1 < MAX_RETRIES:
            time.sleep((2 ** attempt) + random.uniform(0.2, 0.8))
    print(f"AMAZON  | requests fallback needed | {last}")
    return None


def fetch_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("AMAZON  | Playwright kurulu değil")
        return None

    try:
        with sync_playwright() as pw:
            launch_kwargs = {
                "headless": True,
                "args": ["--disable-dev-shm-usage"],
            }
            purl = proxy_url()
            if purl:
                parsed_proxy = urlparse(purl)
                launch_kwargs["proxy"] = {
                    "server": f"{parsed_proxy.scheme}://{parsed_proxy.hostname}:{parsed_proxy.port}",
                }
                if parsed_proxy.username:
                    launch_kwargs["proxy"]["username"] = parsed_proxy.username
                if parsed_proxy.password:
                    launch_kwargs["proxy"]["password"] = parsed_proxy.password
            browser = pw.chromium.launch(**launch_kwargs)
            context = browser.new_context(
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
                user_agent=random.choice(USER_AGENTS),
                viewport={"width": 1365, "height": 900},
                extra_http_headers={"Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8"},
            )
            page = context.new_page()

            # Önce ana sayfayı ziyaret ederek Amazon oturum/cookie'lerini oluştur.
            warm = page.goto(
                BASE_URL + "/",
                wait_until="domcontentloaded",
                timeout=REQUEST_TIMEOUT * 1000,
            )
            page.wait_for_timeout(1500)
            print(
                f"AMAZON  | browser warmup | status={warm.status if warm else '?'} "
                f"| title={page.title()!r} | url={page.url}"
            )

            try:
                response = page.goto(
                    url,
                    wait_until="domcontentloaded",
                    timeout=REQUEST_TIMEOUT * 1000,
                )
            except Exception as nav_exc:
                if "Download is starting" not in str(nav_exc):
                    raise

                print("AMAZON  | direct search navigation download response; search box fallback")
                page.goto(
                    BASE_URL + "/",
                    wait_until="domcontentloaded",
                    timeout=REQUEST_TIMEOUT * 1000,
                )
                page.wait_for_timeout(1000)

                search_box = page.locator("#twotabsearchtextbox").first
                if not search_box.count():
                    raise RuntimeError("Amazon search box bulunamadı")

                keyword = ""
                for part in urlparse(url).query.split("&"):
                    if part.startswith("k="):
                        keyword = part[2:].replace("+", " ")
                        break
                if not keyword:
                    raise RuntimeError("Amazon arama sorgusu URL'den çözülemedi")

                search_box.fill(keyword)
                with page.expect_navigation(
                    wait_until="domcontentloaded",
                    timeout=REQUEST_TIMEOUT * 1000,
                ) as nav:
                    search_box.press("Enter")
                response = nav.value

            page.wait_for_timeout(2500)
            html = page.content()
            blocked = looks_blocked(html)

            # Diagnostic: distinguish a real bot/CAPTCHA block from cookie/consent
            # overlays or a false-positive marker while search results are present.
            lower_html = (html or "").casefold()
            block_markers = (
                "captcha",
                "robot check",
                "automated access",
                "enter the characters you see below",
                "üzgünüz",
            )
            matched_markers = [marker for marker in block_markers if marker in lower_html]
            search_result_count = page.locator(
                "[data-component-type='s-search-result'][data-asin]"
            ).count()
            asin_node_count = page.locator("[data-asin]").count()
            captcha_element_count = page.locator(
                "form[action*='validateCaptcha'], img[src*='captcha'], input[name*='captcha' i]"
            ).count()
            consent_element_count = page.locator(
                "#sp-cc, #sp-cc-accept, input[name='accept'], [data-cel-widget*='consent']"
            ).count()

            print(
                f"AMAZON  | browser search | status={response.status if response else '?'} "
                f"| blocked={blocked} | title={page.title()!r} | url={page.url}"
            )
            print(
                "AMAZON  | diagnostic | "
                f"markers={matched_markers or 'NONE'} | "
                f"captcha_elements={captcha_element_count} | "
                f"consent_elements={consent_element_count} | "
                f"search_results={search_result_count} | asin_nodes={asin_node_count}"
            )

            if blocked:
                body = (page.locator("body").inner_text(timeout=3000) or "").replace("\\n", " ")
                print(f"AMAZON  | browser block preview | {body[:500]!r}")
                save_debug_html(html, "browser_blocked")

            browser.close()
            if html and not blocked:
                if "/s" in urlparse(page.url).path and not looks_like_search_page(html):
                    save_debug_html(html, "browser_search_unrecognized")
                    print("AMAZON  | browser page alındı ama arama sonuç DOM'u tanınmadı")
                else:
                    return html
    except Exception as exc:
        print(f"AMAZON  | Playwright error | {type(exc).__name__}: {exc}")
    return None


def fetch_html(url, session, alternates=None):
    candidates = [url] + list(alternates or [])
    for candidate in candidates:
        html = fetch_requests(candidate, session)
        if html:
            return html
    for candidate in candidates:
        html = fetch_playwright(candidate)
        if html:
            return html
    return None


def first_text(node, selectors):
    for selector in selectors:
        el = node.select_one(selector)
        if el:
            text = el.get_text(" ", strip=True)
            if text:
                return text
    return None


def first_attr(node, selectors, attr):
    for selector in selectors:
        el = node.select_one(selector)
        if el and el.get(attr):
            return str(el.get(attr)).strip()
    return None


def parse_search_results(html, limit):
    soup = BeautifulSoup(html, "html.parser")
    products = []
    seen = set()
    cards = soup.select("[data-component-type='s-search-result'][data-asin]")
    if not cards:
        # Oxylabs örneğindeki daha genel listing yapısını da destekle.
        cards = []
        for link in soup.select("[data-asin] h2 a"):
            parent = link.find_parent(attrs={"data-asin": True})
            if parent:
                cards.append(parent)

    for card in cards:
        asin = (card.get("data-asin") or "").strip().upper()
        if not re.fullmatch(r"[A-Z0-9]{10}", asin) or asin in seen:
            continue

        title = first_text(card, [
            "h2 span",
            "h2 a span",
            "[data-cy='title-recipe'] span",
            "h2.a-size-mini span",
            "h2.a-size-base-plus span",
        ])
        price_text = first_text(card, [".a-price .a-offscreen", ".a-price-whole"])
        price = parse_try_price(price_text)
        if not title or price is None:
            continue

        image = first_attr(card, ["img.s-image", "img"], "src")
        old_text = first_text(card, [".a-text-price .a-offscreen", "[data-a-strike='true'] .a-offscreen"])
        old_price = parse_try_price(old_text)
        if old_price is not None and old_price <= price:
            old_price = None

        seen.add(asin)
        products.append({
            "merchant": "Amazon",
            "brand": None,
            "title": title,
            "asin": asin,
            "price": price,
            "old_price": old_price,
            "image_url": image,
            "product_url": canonical_product_url(asin),
            "affiliate_url": affiliate_product_url(asin),
        })
        if len(products) >= limit:
            break
    return products


def enrich_product(item, session):
    html = fetch_html(item["product_url"], session)
    if not html:
        return item
    soup = BeautifulSoup(html, "html.parser")

    title = first_text(soup, ["#productTitle", "#title", "h1.a-size-large"])
    if title:
        item["title"] = title.strip()

    brand_text = first_text(soup, ["#bylineInfo"])
    brand = clean_brand(brand_text)
    if brand:
        item["brand"] = brand

    image = first_attr(soup, ["#landingImage", "#imgBlkFront", "img.a-dynamic-image"], "data-old-hires")
    image = image or first_attr(soup, ["#landingImage", "#imgBlkFront", "img.a-dynamic-image"], "src")
    if image and image.startswith("http"):
        item["image_url"] = image

    price = None
    for selector in [
        "#corePrice_feature_div .a-price .a-offscreen",
        "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
        ".a-price .a-offscreen",
        "#price_inside_buybox",
    ]:
        price = parse_try_price(first_text(soup, [selector]))
        if price is not None:
            break
    if price is not None:
        item["price"] = price

    old_price = None
    for selector in [
        ".a-text-price[data-a-strike] .a-offscreen",
        ".basisPrice .a-offscreen",
        ".priceBlockStrikePriceString",
    ]:
        old_price = parse_try_price(first_text(soup, [selector]))
        if old_price is not None:
            break
    item["old_price"] = old_price if old_price and old_price > item["price"] else item.get("old_price")
    return item


def collect(query=DEFAULT_QUERY, limit=LIMIT):
    encoded_query = quote_plus(query)
    url = SEARCH_URL.format(query=encoded_query)
    alt_url = ALT_SEARCH_URL.format(query=encoded_query)
    session = requests.Session()
    configure_session_proxy(session)

    # Barath-207/Amazon-Price-Tracker yaklaşımı: önce normal HTTP, bloklanırsa
    # gerçek Chromium/Playwright fallback. Türkiye locale ve fiyat formatına uyarlandı.
    try:
        session.get(BASE_URL + "/", headers=headers(), timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        pass

    print(f"AMAZON  | opening | {url}")
    html = fetch_html(url, session, alternates=[alt_url])
    if not html:
        print("AMAZON  | search page alınamadı")
        return []

    products = parse_search_results(html, limit)
    print(f"AMAZON  | search results | {len(products)}")

    # Detay sayfası başlık/marka/görsel/fiyat doğrulaması sağlar.
    enriched = []
    for i, item in enumerate(products):
        enriched.append(enrich_product(item, session))
        if i + 1 < len(products):
            time.sleep(REQUEST_DELAY_SECONDS)
    return enriched


def supabase_request(method, table, *, params=None, body=None, prefer=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + urlencode(params, doseq=True, safe="(),.*:-")
    hdr = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        hdr["Prefer"] = prefer
    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=payload, headers=hdr, method=method)
    try:
        with urlopen(req, timeout=30) as response:
            raw = response.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {detail}") from exc


def get_or_create_merchant():
    rows = supabase_request("GET", "merchants", params={"slug": "eq.amazon", "select": "id", "limit": "1"})
    if rows:
        return rows[0]["id"]
    rows = supabase_request(
        "POST", "merchants",
        body={"name": "Amazon", "slug": "amazon", "domain": "amazon.com.tr", "active": True},
        prefer="return=representation",
    )
    return rows[0]["id"]


def find_offer(merchant_id, asin):
    rows = supabase_request(
        "GET", "offers",
        params={
            "merchant_id": f"eq.{merchant_id}",
            "merchant_product_id": f"eq.{asin}",
            "select": "id,product_variant_id",
            "limit": "1",
        },
    )
    return rows[0] if rows else None


def create_product_and_variant(item):
    asin = item["asin"]
    products = supabase_request(
        "POST", "products",
        params={"on_conflict": "slug"},
        body={
            "brand": item.get("brand"),
            "title": item["title"],
            "normalized_title": normalize_text(item["title"]),
            "image_url": item.get("image_url"),
            "slug": f"amazon-{asin.lower()}",
            "active": True,
        },
        prefer="resolution=merge-duplicates,return=representation",
    )
    product_id = products[0]["id"]
    variants = supabase_request(
        "POST", "product_variants",
        body={
            "product_id": product_id,
            "sku": f"amazon:{asin}",
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
        asin = item.get("asin")
        price = item.get("price")
        if not asin or price is None:
            continue

        offer = find_offer(merchant_id, asin)
        offer_body = {
            "price": price,
            "old_price": item.get("old_price"),
            "product_url": item["product_url"],
            "affiliate_url": item.get("affiliate_url"),
            "image_url": item.get("image_url"),
            "currency": "TRY",
            "in_stock": True,
            "last_checked_at": checked_at,
            "updated_at": checked_at,
        }

        if offer:
            offer_id = offer["id"]
            supabase_request(
                "PATCH", "offers",
                params={"id": f"eq.{offer_id}"},
                body=offer_body,
                prefer="return=minimal",
            )
        else:
            variant_id = create_product_and_variant(item)
            rows = supabase_request(
                "POST", "offers",
                body={
                    **offer_body,
                    "product_variant_id": variant_id,
                    "merchant_id": merchant_id,
                    "merchant_product_id": asin,
                },
                prefer="return=representation",
            )
            offer_id = rows[0]["id"]

        supabase_request(
            "POST", "price_history",
            body={
                "offer_id": offer_id,
                "price": price,
                "old_price": item.get("old_price"),
                "in_stock": True,
                "checked_at": checked_at,
            },
            prefer="return=minimal",
        )
        saved += 1

    print(f"Supabase: {saved} Amazon ürün/fiyat kaydı işlendi.")
    return saved


if __name__ == "__main__":
    rows = collect()
    print(json.dumps(rows, ensure_ascii=False, indent=2))
    save_products_to_supabase(rows)
