import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
DEAL_THRESHOLD_PERCENT = float(os.getenv("DEAL_THRESHOLD_PERCENT", "15"))


def headers(extra=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil")
    out = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if extra:
        out.update(extra)
    return out


def sb_get(table, params=None):
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + urlencode(params, doseq=True, safe="(),.*:-")
    req = Request(url, headers=headers(), method="GET")
    with urlopen(req, timeout=45) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else []


def sb_upsert(table, row, on_conflict):
    url = f"{SUPABASE_URL}/rest/v1/{table}?on_conflict={on_conflict}"
    req = Request(
        url,
        data=json.dumps(row).encode(),
        headers=headers({"Prefer": "resolution=merge-duplicates,return=representation"}),
        method="POST",
    )
    with urlopen(req, timeout=45) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else []


def sb_patch(table, filters, values):
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urlencode(filters, safe=".*:-")
    req = Request(
        url,
        data=json.dumps(values).encode(),
        headers=headers({"Prefer": "return=minimal"}),
        method="PATCH",
    )
    with urlopen(req, timeout=45):
        return True


def load_data():
    canonical = sb_get("canonical_products", {"select": "id,brand,title,active", "active": "eq.true"})
    matches = sb_get("product_matches", {"select": "canonical_product_id,product_id,status", "status": "eq.approved"})
    variants = sb_get("product_variants", {"select": "id,product_id,active", "active": "eq.true"})
    offers = sb_get(
        "offers",
        {
            "select": "id,product_variant_id,merchant_id,price,currency,in_stock,product_url",
            "in_stock": "eq.true",
        },
    )
    merchants = sb_get("merchants", {"select": "id,name,slug"})
    existing = sb_get("deal_candidates", {"select": "id,canonical_product_id,status"})
    return canonical, matches, variants, offers, merchants, existing


def build_offer_groups(canonical, matches, variants, offers):
    canonical_ids = {c["id"] for c in canonical}

    products_by_canonical = defaultdict(set)
    for m in matches:
        cid = m.get("canonical_product_id")
        pid = m.get("product_id")
        if cid in canonical_ids and pid:
            products_by_canonical[cid].add(pid)

    canonical_by_product = {}
    for cid, product_ids in products_by_canonical.items():
        for pid in product_ids:
            canonical_by_product[pid] = cid

    canonical_by_variant = {}
    for variant in variants:
        cid = canonical_by_product.get(variant.get("product_id"))
        if cid:
            canonical_by_variant[variant["id"]] = cid

    grouped = defaultdict(list)
    for offer in offers:
        cid = canonical_by_variant.get(offer.get("product_variant_id"))
        if not cid:
            continue
        price = float(offer.get("price") or 0)
        if price <= 0:
            continue
        row = dict(offer)
        row["price"] = price
        grouped[cid].append(row)

    return grouped


def best_offer_per_merchant(offers):
    by_merchant = {}
    for offer in offers:
        merchant_id = offer["merchant_id"]
        current = by_merchant.get(merchant_id)
        if current is None or offer["price"] < current["price"]:
            by_merchant[merchant_id] = offer
    return sorted(by_merchant.values(), key=lambda x: x["price"])


def percent_cheaper(cheapest, competitor):
    if competitor <= 0:
        return 0.0
    return ((competitor - cheapest) / competitor) * 100.0


def main():
    canonical, matches, variants, offers, merchants, existing = load_data()
    merchant_map = {m["id"]: (m.get("name") or m.get("slug") or m["id"]) for m in merchants}
    canonical_map = {c["id"]: c for c in canonical}
    existing_by_canonical = {x["canonical_product_id"]: x for x in existing}
    grouped = build_offer_groups(canonical, matches, variants, offers)

    print("=" * 88)
    print("DEAL ENGINE - CROSS STORE")
    print("=" * 88)
    print(f"Canonical ürün: {len(canonical)}")
    print(f"Fırsat eşiği: %{DEAL_THRESHOLD_PERCENT:.2f}")
    print("Kural: en ucuz teklif, ikinci en ucuz farklı mağazadan en az %15 ucuzsa fırsat adayıdır.\n")

    candidates = 0
    not_candidates = 0
    insufficient = 0
    now = datetime.now(timezone.utc).isoformat()

    for cid, cproduct in canonical_map.items():
        store_offers = best_offer_per_merchant(grouped.get(cid, []))
        title = cproduct.get("title") or cid

        if len(store_offers) < 2:
            insufficient += 1
            print(f"SKIP | {title} | en az 2 farklı mağaza teklifi yok")
            if cid in existing_by_canonical and existing_by_canonical[cid].get("status") == "candidate":
                sb_patch("deal_candidates", {"canonical_product_id": f"eq.{cid}"}, {"status": "expired", "updated_at": now})
            continue

        cheapest = store_offers[0]
        competitor = store_offers[1]
        gap = percent_cheaper(cheapest["price"], competitor["price"])

        cheapest_name = merchant_map.get(cheapest["merchant_id"], cheapest["merchant_id"])
        competitor_name = merchant_map.get(competitor["merchant_id"], competitor["merchant_id"])

        if gap + 1e-9 >= DEAL_THRESHOLD_PERCENT:
            row = {
                "canonical_product_id": cid,
                "cheapest_offer_id": cheapest["id"],
                "cheapest_merchant_id": cheapest["merchant_id"],
                "cheapest_price": round(cheapest["price"], 2),
                "competitor_offer_id": competitor["id"],
                "competitor_merchant_id": competitor["merchant_id"],
                "competitor_price": round(competitor["price"], 2),
                "gap_percent": round(gap, 2),
                "threshold_percent": DEAL_THRESHOLD_PERCENT,
                "status": "candidate",
                "updated_at": now,
            }
            if cid not in existing_by_canonical:
                row["detected_at"] = now
            sb_upsert("deal_candidates", row, "canonical_product_id")
            candidates += 1
            print(f"FIRSAT | %{gap:.2f} ucuz | {title}")
            print(f"  {cheapest_name:<16} {cheapest['price']:>10.2f} TRY  <-- EN UCUZ")
            print(f"  {competitor_name:<16} {competitor['price']:>10.2f} TRY  <-- RAKİP")
        else:
            not_candidates += 1
            print(f"NORMAL | %{gap:.2f} ucuz | {title}")
            print(f"  {cheapest_name:<16} {cheapest['price']:>10.2f} TRY")
            print(f"  {competitor_name:<16} {competitor['price']:>10.2f} TRY")
            if cid in existing_by_canonical:
                sb_patch(
                    "deal_candidates",
                    {"canonical_product_id": f"eq.{cid}"},
                    {
                        "cheapest_offer_id": cheapest["id"],
                        "cheapest_merchant_id": cheapest["merchant_id"],
                        "cheapest_price": round(cheapest["price"], 2),
                        "competitor_offer_id": competitor["id"],
                        "competitor_merchant_id": competitor["merchant_id"],
                        "competitor_price": round(competitor["price"], 2),
                        "gap_percent": round(gap, 2),
                        "threshold_percent": DEAL_THRESHOLD_PERCENT,
                        "status": "expired",
                        "updated_at": now,
                    },
                )

    print("\n" + "=" * 88)
    print(f"Fırsat adayı: {candidates}")
    print(f"Eşik altı: {not_candidates}")
    print(f"Yetersiz mağaza: {insufficient}")
    print("=" * 88)


if __name__ == "__main__":
    main()
