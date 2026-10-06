"""Refresh known competitor offers; direct execution is a read-only preview by default."""
import argparse
import json
import math
import os
import re
import sys
import time
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.parse import urlsplit

import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from deals import deal_engine as db

DOMAINS = {'amazon': 'amazon.com.tr', 'trendyol': 'trendyol.com',
           'n11': 'n11.com', 'hepsiburada': 'hepsiburada.com',
           'mediamarkt': 'mediamarkt.com.tr', 'vatan': 'vatanbilgisayar.com'}
BROWSER_HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/152.0.0.0 Safari/537.36'),
    'Accept-Language': 'tr-TR,tr;q=0.9,en;q=0.8',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
}
MAX_REFRESH_PRICE_DROP_PERCENT = float(os.getenv('MAX_REFRESH_PRICE_DROP_PERCENT', '60'))


def allowed_url(url, slug):
    p = urlsplit(url)
    domain = DOMAINS.get(slug)
    return bool(domain and p.scheme == 'https' and not p.username and
                p.port in (None, 443) and
                (p.hostname == domain or (p.hostname or '').endswith('.' + domain)))


def select_targets(canonical, matches, variants, offers, cutoff):
    # Include previously out-of-stock offers as refresh candidates, too.
    groups = db.build_offer_groups(canonical, matches, variants, offers)
    targets = {}
    for cid, rows in groups.items():
        fresh = {o['merchant_id'] for o in rows if o.get('in_stock') and
                 db.parse_dt(o.get('last_checked_at')) and
                 db.parse_dt(o['last_checked_at']) >= cutoff}
        if len(fresh) != 1:
            continue
        for o in rows:
            checked = db.parse_dt(o.get('last_checked_at'))
            if o['merchant_id'] not in fresh and (checked is None or checked < cutoff):
                targets[o['id']] = o
    return sorted(targets.values(), key=lambda o: (o.get('last_checked_at') or '', o['id']))


def product_nodes(value):
    if isinstance(value, list):
        for child in value:
            yield from product_nodes(child)
    elif isinstance(value, dict):
        kind = value.get('@type', [])
        if kind in ('Product', 'ProductGroup') or (isinstance(kind, list) and any(x in kind for x in ('Product', 'ProductGroup'))):
            yield value
        # Never select recommended products from ItemList/carousels.
        if '@graph' in value:
            yield from product_nodes(value['@graph'])


def parse_verified(html, target, slug):
    soup = BeautifulSoup(html, 'html.parser')
    if slug == 'mediamarkt':
        # MediaMarkt uses AggregateOffer on detail pages. Its collector already
        # handles that shape; keep the same parser, but require explicit stock.
        from collectors import mediamarkt
        product = mediamarkt.product_json_ld(html)
        offer = mediamarkt.first_offer((product or {}).get('offers'))
        status = str(offer.get('availability', '')).rstrip('/').rsplit('/', 1)[-1]
        currency = offer.get('priceCurrency')
        if status not in ('InStock', 'OutOfStock') or currency not in (None, 'TRY'):
            raise ValueError('mediamarkt-price-or-stock-unverified')
        item = mediamarkt.parse_product_page(target['product_url'], html)
        if not item:
            raise ValueError('mediamarkt-product-unverified')
        amount = float(item['price'])
        if not math.isfinite(amount) or amount <= 0:
            raise ValueError('invalid-price')
        return {'price': amount, 'currency': 'TRY',
                'in_stock': status == 'InStock'}
    if slug == 'amazon':
        # Independent detail-page reader; Amazon collector is unchanged.
        asin = soup.select_one('input#ASIN')
        title = soup.select_one('#productTitle')
        stock = soup.select_one('#availability')
        price = soup.select_one('#corePrice_feature_div .a-price .a-offscreen, #corePriceDisplay_desktop_feature_div .a-price .a-offscreen')
        if not asin or asin.get('value') != target['merchant_product_id'] or not title or not stock:
            raise ValueError('amazon-identity-or-stock-unverified')
        status = stock.get_text(' ', strip=True).casefold()
        if 'stokta' not in status or 'yok' in status or not price:
            raise ValueError('amazon-price-or-stock-unverified')
        from collectors.amazon import parse_try_price
        amount = parse_try_price(price.get_text())
        if not amount or not math.isfinite(amount) or amount <= 0:
            raise ValueError('invalid-price')
        return {'price': amount, 'currency': 'TRY', 'in_stock': True}
    nodes = []
    for script in soup.select('script[type="application/ld+json"]'):
        try:
            nodes.extend(product_nodes(json.loads(script.string or script.get_text())))
        except (ValueError, TypeError):
            continue
    valid = []
    for product in nodes:
        offers = product.get('offers', [])
        offers = offers if isinstance(offers, list) else [offers]
        # Ambiguous seller/variant prices and AggregateOffer are not evidence.
        if len(offers) != 1 or offers[0].get('@type') != 'Offer':
            continue
        offer = offers[0]
        status = str(offer.get('availability', '')).rstrip('/').rsplit('/', 1)[-1]
        if status not in ('InStock', 'OutOfStock') or offer.get('priceCurrency') != 'TRY':
            continue
        try:
            amount = float(offer['price'])
        except (ValueError, TypeError, KeyError):
            continue
        if not math.isfinite(amount) or amount <= 0:
            continue
        valid.append({'price': amount, 'currency': 'TRY', 'in_stock': status == 'InStock'})
    if len(valid) != 1:
        raise ValueError('identity-price-stock-not-uniquely-verified')
    return valid[0]


def fetch_verified(session, target, slug):
    original_url = target.get('product_url', '')
    url = original_url
    # Validate each redirect before following it.
    for _ in range(4):
        if not allowed_url(url, slug):
            raise ValueError('unexpected-product-domain')
        response = session.get(url, timeout=20, allow_redirects=False)
        if response.is_redirect:
            from urllib.parse import urljoin
            url = urljoin(url, response.headers['Location'])
            continue
        response.raise_for_status()
        original_path = urlsplit(original_url).path.rstrip('/').casefold()
        final_path = urlsplit(url).path.rstrip('/').casefold()
        if original_path != final_path:
            original_id = re.search(r'-p-(\d+)(?:/|$)', original_path)
            final_id = re.search(r'-p-(\d+)(?:/|$)', final_path)
            same_trendyol_product = (
                slug == 'trendyol' and original_id and final_id
                and original_id.group(1) == final_id.group(1)
            )
            if not same_trendyol_product:
                raise ValueError('product-path-changed')
        return parse_verified(response.text, target, slug)
    raise ValueError('too-many-redirects')


def append_price_history(row):
    response = requests.post(
        f'{db.SUPABASE_URL}/rest/v1/price_history',
        headers=db.headers({'Prefer': 'return=minimal'}),
        json=row,
        timeout=20,
    )
    response.raise_for_status()


def validate_price_change(target, new_price):
    """Reject one-shot price collapses before they can poison offers/history."""
    try:
        old_price = float(target.get('price') or 0)
        new_price = float(new_price)
    except (TypeError, ValueError):
        raise ValueError('invalid-price-change')
    if old_price <= 0 or new_price <= 0:
        raise ValueError('invalid-price-change')
    drop = ((old_price - new_price) / old_price) * 100
    if drop + 1e-9 >= MAX_REFRESH_PRICE_DROP_PERCENT:
        raise ValueError(
            f'suspicious-price-drop old={old_price:.2f} new={new_price:.2f} drop={drop:.2f}%'
        )


def refresh_one(session, target, slug, cutoff, apply=False):
    values = fetch_verified(session, target, slug)
    validate_price_change(target, values['price'])
    if apply:
        checked = datetime.now(timezone.utc).isoformat()
        # Update only the exact existing offer. Never create or relink products.
        db.sb_patch('offers', {'id': 'eq.' + target['id']},
                    dict(values, last_checked_at=checked, updated_at=checked))
        append_price_history(dict(offer_id=target['id'], price=values['price'],
                                  in_stock=values['in_stock'], checked_at=checked))
    return values


def refresh_targets(targets, merchants, cutoff, apply=False, *, budget=600, delay=0.35, workers=3):
    """Serial requests within each merchant; at most three merchant streams."""
    started = time.monotonic()
    streams = {}
    for index, target in enumerate(targets, 1):
        slug = merchants.get(target['merchant_id'], '')
        streams.setdefault(slug, []).append((index, target))
    def stream(slug, rows):
        ok = failed = 0
        with requests.Session() as session:
            session.headers.update(BROWSER_HEADERS)
            for index, target in rows:
                if time.monotonic() - started >= budget:
                    break
                try:
                    result = refresh_one(session, target, slug, cutoff, apply)
                    ok += 1
                    print(f'REFRESH | {index}/{len(targets)} | {slug} | {target["id"]} | VERIFIED | price={result["price"]} | stock={result["in_stock"]}', flush=True)
                except Exception as exc:
                    failed += 1
                    detail = str(exc).replace('|', '/').replace('\n', ' ')[:120]
                    print(f'REFRESH | {index}/{len(targets)} | {slug} | {target["id"]} | UNVERIFIED | {type(exc).__name__}: {detail}', flush=True)
                time.sleep(delay)
        return ok, failed
    totals = []
    with ThreadPoolExecutor(max_workers=min(3, max(1, workers))) as executor:
        futures = [executor.submit(stream, slug, rows) for slug, rows in streams.items()]
        for future in as_completed(futures):
            totals.append(future.result())
    return sum(x[0] for x in totals), sum(x[1] for x in totals)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args()
    cutoff = db.parse_dt(os.getenv('PIPELINE_STARTED_AT', ''))
    if cutoff is None:
        raise RuntimeError('PIPELINE_STARTED_AT gerekli; tüm veritabanı taranmaz.')
    canonical = db.sb_get('canonical_products', {'select': 'id', 'active': 'eq.true'})
    matches = db.sb_get('product_matches', {'select': 'canonical_product_id,product_id,status', 'status': 'eq.approved'})
    variants = db.sb_get('product_variants', {'select': 'id,product_id', 'active': 'eq.true'})
    offers = db.sb_get('offers', {'select': 'id,product_variant_id,merchant_id,merchant_product_id,price,in_stock,product_url,last_checked_at'})
    merchants = {m['id']: m['slug'] for m in db.sb_get('merchants', {'select': 'id,slug'})}
    targets = select_targets(canonical, matches, variants, offers, cutoff)
    limit = max(0, int(os.getenv('COMPETITOR_REFRESH_LIMIT', '300')))
    budget = max(0, int(os.getenv('COMPETITOR_REFRESH_SECONDS', '600')))
    delay = max(0.0, float(os.getenv('COMPETITOR_REFRESH_DELAY', '0.35')))
    print(f'REFRESH | targets={len(targets)} | limit={limit} | apply={args.apply}', flush=True)
    ok, failed = refresh_targets(targets[:limit], merchants, cutoff, args.apply,
                                 budget=budget, delay=delay)
    print(f'REFRESH | verified={ok} | failed={failed} | deferred={len(targets)-ok-failed}', flush=True)


if __name__ == '__main__':
    main()
