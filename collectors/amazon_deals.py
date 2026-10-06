import argparse
import json
import os
import random
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
load_dotenv(ROOT / ".env")

from collectors import amazon


DEAL_PAGES = (
    ("Fırsatlar", "https://www.amazon.com.tr/deals"),
    ("Çok Al Az Öde", "https://www.amazon.com.tr/b?node=26248552031"),
    ("Fiyatları Dondurduk", "https://www.amazon.com.tr/b?node=219537822031"),
)
DEFAULT_LIMIT = max(1, int(os.getenv("AMAZON_DEALS_LIMIT", "150")))
PAGE_LIMIT = max(1, int(os.getenv("AMAZON_DEALS_PAGE_LIMIT", "100")))


def _exact_class(token):
    return lambda value: bool(value and token in str(value).split())


def _line_title(link, card):
    title = amazon.first_text(
        card,
        [
            ".dcl-product-title",
            "[data-testid='product-title']",
            "h2",
            "h3",
        ],
    )
    if title:
        return title

    image = link.select_one("img") or card.select_one("img")
    if image and image.get("alt"):
        return str(image.get("alt")).strip()

    lines = [line.strip() for line in link.get_text("\n", strip=True).splitlines() if line.strip()]
    return lines[0] if lines else None


def _card_for_link(link):
    card = link.find_parent("div", class_=_exact_class("dcl-product"))
    if card:
        return card

    # Amazon zaman zaman sınıf adlarını değiştiriyor. En yakın, tek bir ürüne
    # ait fiyat ve görsel içeren kapsayıcıyı kontrollü bir yedek olarak bul.
    parent = link.parent
    for _ in range(8):
        if parent is None:
            break
        product_links = {
            amazon.extract_asin(a.get("href"))
            for a in parent.select("a[href*='/dp/'], a[href*='/gp/product/']")
        }
        product_links.discard(None)
        if (
            parent.select_one(".a-price .a-offscreen")
            and parent.select_one("img")
            and len(product_links) == 1
        ):
            return parent
        if len(product_links) > 3:
            break
        parent = parent.parent
    return None


def _product_from_link(link, source):
    asin = amazon.extract_asin(link.get("href"))
    if not asin:
        return None
    card = _card_for_link(link)
    if card is None:
        return None

    title = _line_title(link, card)
    price = amazon.parse_try_price(
        amazon.first_text(card, [".a-price .a-offscreen", "[data-a-color='price'] .a-offscreen"])
    )
    if not title or price is None:
        return None

    old_price = amazon.parse_try_price(
        amazon.first_text(
            card,
            [
                ".a-text-price .a-offscreen",
                "[data-a-strike='true'] .a-offscreen",
                ".basisPrice .a-offscreen",
            ],
        )
    )
    if old_price is not None and old_price <= price:
        old_price = None

    image = amazon.first_attr(card, ["img"], "src")
    if not image:
        image = amazon.first_attr(card, ["img"], "data-src")

    return {
        "merchant": "Amazon",
        "brand": None,
        "title": title,
        "asin": asin,
        "price": price,
        "old_price": old_price,
        "image_url": image,
        "product_url": amazon.canonical_product_url(asin),
        "affiliate_url": amazon.affiliate_product_url(asin),
        "deal_source": source,
    }


def parse_deal_page(html, source, limit=PAGE_LIMIT):
    soup = BeautifulSoup(html or "", "html.parser")
    links = soup.select(
        ".dcl-product a.dcl-product-link[href*='/dp/'], "
        ".dcl-product a[href*='/dp/'], "
        ".dcl-product a[href*='/gp/product/']"
    )
    if not links:
        links = soup.select("a[href*='/dp/'], a[href*='/gp/product/']")

    products = []

    for link in links:
        item = _product_from_link(link, source)
        if not item:
            continue

        products.append(item)
    # Inspect all cards before limiting so later duplicates can lower the price.
    return merge_products([products], limit)


def _quality(item):
    return (
        -float(item.get("price") or float("inf")),
        int(bool(item.get("old_price"))),
        int(bool(item.get("image_url"))),
        len(item.get("title") or ""),
    )


def merge_products(groups, limit=DEFAULT_LIMIT):
    merged = {}
    order = []
    for products in groups:
        for item in products:
            asin = item["asin"]
            if asin not in merged:
                merged[asin] = item
                order.append(asin)
                continue
            current = merged[asin]
            sources = list(
                dict.fromkeys(
                    str(current.get("deal_source", "")).split(" + ")
                    + str(item.get("deal_source", "")).split(" + ")
                )
            )
            better = item if _quality(item) > _quality(current) else current
            better = dict(better)
            better["deal_source"] = " + ".join(filter(None, sources))
            merged[asin] = better
    return [merged[asin] for asin in order[:limit]]


def _looks_like_deal_page(html):
    if not html or amazon.looks_blocked(html):
        return False
    soup = BeautifulSoup(html, "html.parser")
    return bool(soup.select_one("a[href*='/dp/'], a[href*='/gp/product/']"))


def _fetch_playwright(url):
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("AMAZON DEALS | Playwright kurulu değil")
        return None

    try:
        with sync_playwright() as pw:
            launch = {"headless": True, "args": ["--disable-dev-shm-usage"]}
            proxy = amazon.proxy_url()
            if proxy:
                parsed = urlparse(proxy)
                launch["proxy"] = {"server": f"{parsed.scheme}://{parsed.hostname}:{parsed.port}"}
                if parsed.username:
                    launch["proxy"]["username"] = parsed.username
                if parsed.password:
                    launch["proxy"]["password"] = parsed.password
            browser = pw.chromium.launch(**launch)
            context = browser.new_context(
                locale="tr-TR",
                timezone_id="Europe/Istanbul",
                user_agent=random.choice(amazon.USER_AGENTS),
                viewport={"width": 1365, "height": 900},
            )
            page = context.new_page()
            response = page.goto(
                url,
                wait_until="domcontentloaded",
                timeout=amazon.REQUEST_TIMEOUT * 1000,
            )
            page.wait_for_timeout(1800)
            # Fırsatlar sayfası ilk görünümden sonra kartları tembel yükler.
            # Sınırlı kaydırma, sonsuz listeyi zorlamadan görünen vitrini tamamlar.
            for _ in range(4):
                before = page.locator("a[href*='/dp/']").count()
                page.evaluate("window.scrollTo(0, document.body.scrollHeight)")
                page.wait_for_timeout(700)
                after = page.locator("a[href*='/dp/']").count()
                if after <= before:
                    break
            html = page.content()
            product_count = page.locator("a[href*='/dp/']").count()
            print(
                f"AMAZON DEALS | browser | status={response.status if response else '?'} "
                f"| products={product_count}"
            )
            browser.close()
            return html if _looks_like_deal_page(html) else None
    except Exception as exc:
        print(f"AMAZON DEALS | Playwright error | {type(exc).__name__}: {exc}")
        return None


def collect(limit=DEFAULT_LIMIT):
    session = requests.Session()
    amazon.configure_session_proxy(session)
    groups = []

    for index, (source, url) in enumerate(DEAL_PAGES):
        if index:
            time.sleep(amazon.REQUEST_DELAY_SECONDS)
        print(f"AMAZON DEALS | opening | {source} | {url}")
        html = amazon.fetch_requests(url, session)
        if html and not _looks_like_deal_page(html):
            html = None
        if not html:
            html = _fetch_playwright(url)
        if not html:
            print(f"AMAZON DEALS | page failed | {source}")
            continue

        products = parse_deal_page(html, source, min(PAGE_LIMIT, limit))
        print(f"AMAZON DEALS | {source} | found={len(products)}")
        groups.append(products)

    products = merge_products(groups, limit)
    print(f"AMAZON DEALS | unique products={len(products)}")
    return products


def main():
    parser = argparse.ArgumentParser(description="Amazon Türkiye fırsat vitrinlerini tara.")
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Supabase'e yazmadan ayrıştırmayı test et.",
    )
    parser.add_argument("--find-competitors", action="store_true",
                        help="Her fırsat ürününü diğer mağazalarda ayrıca ara.")
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument("--defer-competitors", action="store_true")
    args = parser.parse_args()
    from collectors.database_http import install
    install(amazon)

    rows = collect(max(1, args.limit))
    if args.find_competitors:
        # Read brand/title from the Amazon detail page for strict identity checks.
        # Preserve the lowest live deal-card price established during collection.
        session = requests.Session()
        amazon.configure_session_proxy(session)
        for row in rows:
            try:
                detail = amazon.enrich_product(dict(row), session)
                for field in ("brand", "title", "image_url"):
                    if detail.get(field):
                        row[field] = detail[field]
            except Exception as exc:
                print(f"AMAZON IDENTITY | {row['asin']} | unverified | {type(exc).__name__}")
    if args.dry_run:
        preview = rows[: min(20, len(rows))]
        print(json.dumps(preview, ensure_ascii=False, indent=2))
        print(f"AMAZON DEALS DRY RUN | total={len(rows)} | saved=0")
    else:
        saved = amazon.save_products_to_supabase(rows)
        if rows and saved != len(rows):
            raise RuntimeError("Amazon seed persistence incomplete")
        if args.find_competitors:
            # Existing offers otherwise retain the old product's missing brand.
            for row in rows:
                if row.get("brand"):
                    amazon.supabase_request(
                        "PATCH", "products", params={"slug": f"eq.amazon-{row['asin'].lower()}"},
                        body={"brand": row["brand"], "title": row["title"],
                              "normalized_title": amazon.normalize_text(row["title"])},
                        prefer="return=minimal",
                    )
    if args.find_competitors and args.defer_competitors:
        report = ROOT / "reports" / "amazon_deal_seeds.json"
        report.parent.mkdir(exist_ok=True)
        report.write_text(json.dumps({"scan_started_at": os.getenv("PIPELINE_STARTED_AT"), "rows": rows}, ensure_ascii=False), encoding="utf-8")
    if args.find_competitors and rows and not args.defer_competitors:
        from collectors.amazon_competitors import discover_competitors
        statuses = discover_competitors(
            rows, apply=not args.dry_run,
            timeout=max(1, int(os.getenv("AMAZON_COMPETITOR_TIMEOUT", "120"))),
            limit=max(1, int(os.getenv("AMAZON_COMPETITOR_SEARCH_LIMIT", "5"))),
        )
        report = ROOT / "reports" / "amazon_competitor_search.json"
        report.parent.mkdir(exist_ok=True)
        report.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"AMAZON COMPETITOR | report={report} | searches={len(statuses)}")
    if not rows:
        raise SystemExit(4)


if __name__ == "__main__":
    main()
