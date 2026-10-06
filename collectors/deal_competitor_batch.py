"""Search only rivals still missing after category scans, across all deal sources."""
import json
import os
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from collectors.amazon_competitors import discover_competitors, same_product, competitor_stores
from deals import deal_engine as db

ROOT = Path(__file__).resolve().parents[1]


def fresh_competitor_pairs(seeds, offers, variants, products, matches, merchants, cutoff):
    variant_by_id = {v['id']: v for v in variants}
    product_by_id = {p['id']: p for p in products}
    slug_by_id = {m['id']: m['slug'] for m in merchants}
    approved = {}
    for match in matches:
        if match.get('status') == 'approved':
            approved.setdefault(match['product_id'], set()).add(match['canonical_product_id'])
    by_identity = {}
    by_canonical = {}
    for offer in offers:
        checked = db.parse_dt(offer.get('last_checked_at'))
        if not checked or checked < cutoff:
            continue
        slug = slug_by_id.get(offer['merchant_id'])
        variant = variant_by_id.get(offer['product_variant_id'], {})
        product = product_by_id.get(variant.get('product_id'), {})
        canonical = approved.get(product.get('id'), set())
        # Multiple canonical assignments are ambiguous evidence.
        if len(canonical) != 1:
            continue
        cid = next(iter(canonical))
        by_identity[(slug, offer.get('merchant_product_id'))] = cid
        if offer.get('in_stock') and float(offer.get('price') or 0) > 0:
            item = dict(product, price=offer['price'], in_stock=True, gtin=variant.get('gtin'))
            by_canonical.setdefault(cid, []).append((slug, item))
    fresh = set()
    for seed in seeds:
        source = seed.get('source_store', 'amazon')
        identity = seed.get('asin') or seed['merchant_product_id']
        cid = by_identity.get((source, identity))
        for slug, item in by_canonical.get(cid, []):
            if slug in competitor_stores(seed) and same_product(seed, item, slug):
                fresh.add((source, identity, slug))
    return fresh


def main():
    started = os.getenv('PIPELINE_STARTED_AT', '')
    cutoff = db.parse_dt(started)
    if cutoff is None:
        raise RuntimeError('PIPELINE_STARTED_AT required')
    seeds = []
    for slug in ('amazon', 'trendyol', 'hepsiburada'):
        path = ROOT / 'reports' / f'{slug}_deal_seeds.json'
        if path.exists():
            report = json.loads(path.read_text(encoding='utf-8'))
            if report.get('scan_started_at') == started:
                seeds.extend(report.get('rows', []))
    if not seeds:
        print('DEAL COMPETITOR BATCH | no verified seeds from this scan')
        return
    offers = db.sb_get('offers', {'select':'merchant_id,merchant_product_id,product_variant_id,price,in_stock,last_checked_at', 'last_checked_at':'gte.'+started})
    variants = db.sb_get('product_variants', {'select':'id,product_id,gtin', 'active':'eq.true'})
    products = db.sb_get('products', {'select':'id,title,brand', 'active':'eq.true'})
    matches = db.sb_get('product_matches', {'select':'product_id,canonical_product_id,status', 'status':'eq.approved'})
    merchants = db.sb_get('merchants', {'select':'id,slug'})
    fresh = fresh_competitor_pairs(seeds, offers, variants, products, matches, merchants, cutoff)
    total = sum(len(competitor_stores(seed)) for seed in seeds)
    print(f'DEAL COMPETITOR BATCH | seeds={len(seeds)} | pairs={total} | fresh-approved={len(fresh)} | workers=3', flush=True)
    rows = discover_competitors(seeds, apply=True,
        timeout=max(1, int(os.getenv('DEAL_COMPETITOR_TIMEOUT', '120'))),
        limit=max(1, int(os.getenv('DEAL_COMPETITOR_SEARCH_LIMIT', '5'))),
        fresh_pairs=fresh, deduplicate=True)
    path = ROOT / 'reports' / 'batch_competitor_search.json'
    path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f'DEAL COMPETITOR BATCH | actual-searches={sum(r.get("reason") not in ("fresh-approved-offer","same-query-in-batch") for r in rows)}', flush=True)


if __name__ == '__main__':
    main()
