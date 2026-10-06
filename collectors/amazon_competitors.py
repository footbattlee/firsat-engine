"""Search other stores for deal products, independently of category searches."""
import argparse
import asyncio
import json
import math
import os
import re
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")
from matching import product_matcher as matcher
import run_category_collector as shared

STORES = {
    "trendyol": "trendyol.py",
    "hepsiburada": "hepsiburada_requests.py",
    "n11": "n11.py",
    "mediamarkt": "mediamarkt.py",
    "vatan": "vatan.py",
}


def competitor_stores(seed):
    source = seed.get("source_store", "amazon")
    return {slug: script for slug, script in {**STORES, "amazon": "amazon.py"}.items()
            if slug != source}


def search_query(seed):
    # Retain model, size, colour and pack evidence; no configured category gate.
    return re.sub(r"\s+", " ", str(seed.get("title") or "")).strip()


def same_product(seed, item, slug):
    try:
        price = float(item.get("price") or 0)
    except (ValueError, TypeError):
        return False
    if not math.isfinite(price) or price <= 0 or item.get("in_stock") is False:
        return False
    a = dict(seed, merchant_id=seed.get("source_store", "amazon"))
    b = dict(item, merchant_id=slug)
    if not a.get("title") or not b.get("title"):
        return False
    colors_a, colors_b = matcher.extract_colors(a["title"]), matcher.extract_colors(b["title"])
    if colors_a and colors_b and colors_a != colors_b:
        return False
    compatible, _reason = matcher.variant_evidence_compatible(a, b)
    if not compatible:
        return False
    score, _reason = matcher.pair_score(a, b)
    return score >= matcher.MIN_SCORE


def collect_candidates(module, seed, limit):
    query = search_query(seed)
    if callable(getattr(module, "collect", None)):
        return module.collect(query=query, limit=limit)
    captured = []
    module.DEFAULT_QUERY = query
    module.LIMIT = limit
    module.CATEGORY_FILTER = lambda _query, rows: rows
    module.save_products_to_supabase = lambda rows: captured.extend(rows) or 0
    asyncio.run(module.main())
    return captured


def search_store(seed, slug, apply=False, limit=5):
    module = shared.load_module(ROOT / "collectors" / ({**STORES, "amazon": "amazon.py"})[slug])
    settings = shared.get_proxy_settings()
    if callable(getattr(module, "collect", None)):
        shared.enable_requests_proxy(settings)
    else:
        shared.enable_playwright_proxy(module, settings)
    save = module.save_products_to_supabase
    candidates = collect_candidates(module, seed, limit)
    from deals.refresh_competitor_offers import fetch_verified, BROWSER_HEADERS
    import requests
    accepted = []
    with requests.Session() as session:
        session.headers.update(BROWSER_HEADERS)
        for item in candidates:
            if slug == "amazon":
                try:
                    item = module.enrich_product(dict(item), session)
                except Exception:
                    continue
            if not same_product(seed, item, slug):
                continue
            target = dict(item)
            if slug == "amazon":
                target["merchant_product_id"] = item.get("asin")
            if not target.get("merchant_product_id") and slug == "trendyol":
                target["merchant_product_id"] = module.merchant_product_id_from_url(item["product_url"])
            try:
                verified = fetch_verified(session, target, slug)
                current = dict(item, **verified)
                if same_product(seed, current, slug):
                    accepted.append(current)
            except Exception as exc:
                print(f"AMAZON COMPETITOR VERIFY | {slug} | unverified | {type(exc).__name__}")
    saved = save(accepted) if apply and accepted else 0
    if apply and saved != len(accepted):
        raise RuntimeError("Competitor persistence incomplete")
    return {
        "asin": seed.get("asin") or seed["merchant_product_id"],
        "source_store": seed.get("source_store", "amazon"), "store": slug, "query": search_query(seed),
        "status": "matched" if accepted else "unverified",
        "found": len(candidates), "matched": len(accepted), "saved": saved,
    }


def _search_job(seed, slug, apply, timeout, limit):
    command = [sys.executable, str(Path(__file__).resolve()), "--store", slug,
               "--limit", str(limit)]
    if apply:
        command.append("--apply")
    identity = seed.get("asin") or seed["merchant_product_id"]
    try:
        result = subprocess.run(command, input=json.dumps(seed, ensure_ascii=False),
            encoding="utf-8", errors="replace", capture_output=True, cwd=ROOT,
            timeout=timeout,
            env=dict(os.environ, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1"))
        marker = "AMAZON COMPETITOR RESULT | "
        summaries = [line[len(marker):] for line in result.stdout.splitlines()
                     if line.startswith(marker)]
        row = (json.loads(summaries[-1]) if not result.returncode and summaries else
               {"asin": identity, "store": slug, "status": "failed",
                "reason": "collector-error", "code": result.returncode})
    except subprocess.TimeoutExpired:
        row = {"asin": identity, "store": slug, "status": "unverified", "reason": "timeout"}
    row.setdefault("source_store", seed.get("source_store", "amazon"))
    prefix = "AMAZON COMPETITOR" if row["source_store"] == "amazon" else "DEAL COMPETITOR"
    print(prefix + " | " + json.dumps(row, ensure_ascii=False), flush=True)
    return row


def discover_competitors(seeds, apply=False, timeout=120, limit=5, fresh_pairs=None, deduplicate=False):
    # One sequential stream per merchant avoids duplicate offer/variant writes
    # and request bursts to the same store. At most three streams run together.
    streams = {}
    results = []
    seen = set()
    for seed in seeds:
        for slug in competitor_stores(seed):
            identity = seed.get("asin") or seed["merchant_product_id"]
            if (seed.get("source_store", "amazon"), identity, slug) in (fresh_pairs or set()):
                results.append({"asin": identity, "source_store": seed.get("source_store", "amazon"), "store": slug,
                                "status": "matched", "reason": "fresh-approved-offer", "saved": 0})
                continue
            key = (slug, search_query(seed).casefold(), str(seed.get("brand") or "").casefold(), str(seed.get("gtin") or ""))
            if deduplicate and key in seen:
                results.append({"asin": identity, "source_store": seed.get("source_store", "amazon"), "store": slug,
                                "status": "covered", "reason": "same-query-in-batch", "saved": 0})
                continue
            seen.add(key)
            streams.setdefault(slug, []).append(seed)
    workers = min(3, max(1, int(os.getenv("DEAL_COMPETITOR_WORKERS", "3"))))
    print(f"DEAL COMPETITOR | parallel workers={workers}", flush=True)
    def stream(slug, rows):
        return [_search_job(seed, slug, apply, timeout, limit) for seed in rows]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(stream, slug, rows) for slug, rows in streams.items()]
        for future in as_completed(futures):
            results.extend(future.result())
    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--store", choices=[*STORES, "amazon"], required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()
    seed = json.load(sys.stdin)
    if not search_query(seed) or not (seed.get("asin") or seed.get("merchant_product_id")) or args.limit < 1:
        raise ValueError("Valid deal product and positive limit required")
    result = search_store(seed, args.store, args.apply, args.limit)
    print("AMAZON COMPETITOR RESULT | " + json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
