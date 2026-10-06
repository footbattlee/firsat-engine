"""Campaign discovery independent of configured categories; detail prices only."""
import argparse
import ast
import json
import os
import re
import sys
from pathlib import Path
from urllib.parse import urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
from dotenv import load_dotenv
load_dotenv(ROOT / '.env')
from bs4 import BeautifulSoup
from collectors import hepsiburada_requests as hb, trendyol
from collectors.amazon_competitors import discover_competitors
from deals.refresh_competitor_offers import allowed_url, parse_verified, product_nodes, BROWSER_HEADERS
import run_category_collector as shared

PAGES = {
    'trendyol': [('Flaş Ürünler', 'https://www.trendyol.com/flas-indirimler'),
                ('Avantajlı Ürünler', 'https://www.trendyol.com/sr?tag=kirmizi_kampanya_urunu%2Cturuncu_kampanya_urunu%2Csari_kampanya_urunu&sst=SCORE')],
    'hepsiburada': [('Süper Fiyat Süper Teklif', 'https://www.hepsiburada.com/gunun-firsati-teklifi'),
                   ('En Avantajlı Fiyatlar', 'https://www.hepsiburada.com/kampanyalar/en-avantajli-fiyatlar')],
}


def product_urls(html, slug):
    urls = {}
    for anchor in BeautifulSoup(html, 'html.parser').select('a[href]'):
        url = urljoin(PAGES[slug][0][1], anchor['href']).split('?')[0].split('#')[0]
        if not allowed_url(url, slug):
            continue
        identity = (trendyol.merchant_product_id_from_url(url) if slug == 'trendyol'
                    else hb.merchant_product_id({}, url))
        if identity:
            urls.setdefault(identity, url)
    return list(urls.values())


def detail_product(html, url, slug):
    nodes = []
    for script in BeautifulSoup(html, 'html.parser').select('script[type="application/ld+json"]'):
        try:
            nodes.extend(product_nodes(json.loads(script.string or script.get_text())))
        except (ValueError, TypeError):
            continue
    if len(nodes) != 1:
        raise ValueError('ambiguous-product')
    product = nodes[0]
    # Used/refurbished stock must not enter comparisons with new products.
    offer = product.get('offers') or {}
    if isinstance(offer, list):
        if len(offer) != 1:
            raise ValueError('ambiguous-offer')
        offer = offer[0]
    condition = str(offer.get('itemCondition') or product.get('itemCondition') or '')
    if condition and condition.rstrip('/').rsplit('/', 1)[-1] != 'NewCondition':
        raise ValueError('non-new-condition')
    title = str(product.get('name') or '').strip()
    if re.search(r'yenilenmiş|yenilenmis|teşhir|teshir|ikinci el|outlet|refurbished', title, re.I):
        raise ValueError('non-new-title')
    identity = (trendyol.merchant_product_id_from_url(url) if slug == 'trendyol'
                else hb.merchant_product_id({}, url))
    if not title or not identity:
        raise ValueError('missing-identity')
    row = {'merchant': 'Trendyol' if slug == 'trendyol' else 'Hepsiburada',
           'source_store': slug, 'merchant_product_id': identity,
           'title': title, 'brand': hb.clean_brand(product),
           'image_url': hb.image_url(product), 'product_url': url,
           'gtin': hb.clean_gtin(product.get('gtin13') or product.get('gtin'))}
    image = row.get('image_url')
    if image and image.startswith('['):
        try:
            values = ast.literal_eval(image)
            row['image_url'] = values[0] if isinstance(values, list) and values else None
        except (ValueError, SyntaxError):
            row['image_url'] = None
    row.update(parse_verified(html, row, slug))
    if not row['in_stock']:
        raise ValueError('out-of-stock')
    return row


def collect(slug, limit):
    from playwright.sync_api import sync_playwright
    import requests
    urls = {}
    products = {}
    settings = shared.get_proxy_settings()
    shared.enable_requests_proxy(settings)
    with requests.Session() as session, sync_playwright() as pw:
        session.headers.update(BROWSER_HEADERS)
        launch = {'headless': True}
        # Use the same proxy configuration as existing collectors.
        from collectors import amazon
        proxy = amazon.proxy_url()
        if proxy:
            from urllib.parse import urlparse, unquote
            p = urlparse(proxy)
            launch['proxy'] = {'server': f'{p.scheme}://{p.hostname}:{p.port}'}
            if p.username:
                launch['proxy'].update(username=unquote(p.username), password=unquote(p.password or ''))
        browser = pw.chromium.launch(**launch)
        context = browser.new_context(locale='tr-TR', user_agent=BROWSER_HEADERS['User-Agent'])
        page = context.new_page()
        if slug == 'hepsiburada':
            try:
                page.goto('https://www.hepsiburada.com/', wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(2000)
            except Exception:
                pass
        for source, url in PAGES[slug]:
            try:
                listing = session.get(url, timeout=20)
                found = product_urls(listing.text, slug) if listing.ok else []
                if found:
                    for product_url in found[:limit]:
                        urls.setdefault(product_url, []).append(source)
                    print(f'DEAL DISCOVERY | {slug} | {source} | links={len(found)}', flush=True)
                    continue
                response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_timeout(2000)
                if response and response.status >= 400:
                    raise ValueError(f'campaign-http-{response.status}')
                for _ in range(4):
                    found = product_urls(page.content(), slug)
                    if len(found) >= limit:
                        break
                    page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
                    page.wait_for_timeout(700)
                for product_url in product_urls(page.content(), slug)[:limit]:
                    urls.setdefault(product_url, []).append(source)
                print(f'DEAL DISCOVERY | {slug} | {source} | links={len(product_urls(page.content(), slug))}', flush=True)
            except Exception as exc:
                print(f'DEAL DISCOVERY | {slug} | page failed | {type(exc).__name__}: {exc}', flush=True)
        for url, sources in urls.items():
            try:
                try:
                    response = session.get(url, timeout=20)
                    response.raise_for_status()
                    if urlsplit(response.url).path.rstrip('/') != urlsplit(url).path.rstrip('/'):
                        raise ValueError('product-path-changed')
                    row = detail_product(response.text, url, slug)
                except Exception:
                    response = page.goto(url, wait_until='domcontentloaded', timeout=30000)
                    page.wait_for_timeout(1200)
                    if (response and response.status >= 400) or urlsplit(page.url).path.rstrip('/') != urlsplit(url).path.rstrip('/'):
                        raise ValueError('product-path-changed-or-http-error')
                    row = detail_product(page.content(), url, slug)
                row['deal_source'] = ' + '.join(sources)
                identity = row['merchant_product_id']
                current = products.get(identity)
                if current is None or row['price'] < current['price']:
                    products[identity] = row
                if len(products) >= limit:
                    break
            except Exception as exc:
                print(f'DEAL DISCOVERY | {slug} | detail unverified | {type(exc).__name__}', flush=True)
        browser.close()
    return list(products.values())


def main(slug):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--find-competitors', action='store_true')
    parser.add_argument('--limit', type=int, default=int(os.getenv(f'{slug.upper()}_DEALS_LIMIT', '30')))
    parser.add_argument("--defer-competitors", action="store_true")
    args = parser.parse_args()
    from collectors.database_http import install
    install(trendyol if slug == "trendyol" else hb)
    rows = collect(slug, max(1, args.limit))
    if args.dry_run:
        print(json.dumps(rows[:20], ensure_ascii=False, indent=2))
        print(f'DEAL DISCOVERY DRY RUN | {slug} | total={len(rows)} | saved=0')
    else:
        module = trendyol if slug == 'trendyol' else hb
        if rows and module.save_products_to_supabase(rows) != len(rows):
            raise RuntimeError('Deal seed persistence incomplete')
        for row in rows:
            if row.get('brand'):
                module.supabase_request('PATCH', 'products',
                    params={'slug': f"eq.{slug}-{row['merchant_product_id'].lower()}"},
                    body={'brand': row['brand'], 'title': row['title'],
                          'normalized_title': module.normalize_text(row['title'])},
                    prefer='return=minimal')
    if args.find_competitors and args.defer_competitors:
        report = ROOT / "reports" / f"{slug}_deal_seeds.json"
        report.parent.mkdir(exist_ok=True)
        report.write_text(json.dumps({"scan_started_at": os.getenv("PIPELINE_STARTED_AT"), "rows": rows}, ensure_ascii=False), encoding="utf-8")
    if rows and args.find_competitors and not args.defer_competitors:
        statuses = discover_competitors(rows, apply=not args.dry_run,
            timeout=max(1, int(os.getenv('DEAL_COMPETITOR_TIMEOUT', '120'))),
            limit=max(1, int(os.getenv('DEAL_COMPETITOR_SEARCH_LIMIT', '5'))))
        report = ROOT / 'reports' / f'{slug}_competitor_search.json'
        report.parent.mkdir(exist_ok=True)
        report.write_text(json.dumps(statuses, ensure_ascii=False, indent=2), encoding='utf-8')
    if not rows:
        raise SystemExit(4)