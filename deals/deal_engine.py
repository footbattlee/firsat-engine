import json
import os
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
DEAL_THRESHOLD_PERCENT = float(os.getenv("DEAL_THRESHOLD_PERCENT", "15"))
HISTORY_DROP_THRESHOLD_PERCENT = float(os.getenv("HISTORY_DROP_THRESHOLD_PERCENT", "5"))


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
        url += "?" + urlencode(params, doseq=True, safe="(),.*:-+")
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
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urlencode(filters, safe=".*:-+")
    req = Request(
        url,
        data=json.dumps(values).encode(),
        headers=headers({"Prefer": "return=minimal"}),
        method="PATCH",
    )
    with urlopen(req, timeout=45):
        return True


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


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

    # Price history'yi REST tarafında tarih filtresine sokmuyoruz.
    # Bazı PostgREST tarih parametreleri HTTP 400 döndürebildiği için
    # kayıtları alıp 90 günlük filtreyi Python tarafında uyguluyoruz.
    history_all = sb_get(
        "price_history",
        {
            "select": "offer_id,price,checked_at",
            "order": "checked_at.desc",
        },
    )
    since_90d = datetime.now(timezone.utc) - timedelta(days=90)
    history = []
    for row in history_all:
        checked_at = parse_dt(row.get("checked_at"))
        if checked_at and checked_at >= since_90d:
            history.append(row)

    return canonical, matches, variants, offers, merchants, existing, history


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


def build_history_map(history):
    out = defaultdict(list)
    for row in history:
        price = float(row.get("price") or 0)
        checked_at = parse_dt(row.get("checked_at"))
        if price <= 0 or not checked_at:
            continue
        out[row["offer_id"]].append({"price": price, "checked_at": checked_at})

    for rows in out.values():
        rows.sort(key=lambda x: x["checked_at"], reverse=True)
    return out


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


def price_drop_percent(current, reference):
    if not reference or reference <= 0 or current >= reference:
        return 0.0
    return ((reference - current) / reference) * 100.0


def analyze_history(offer_id, current_price, history_map):
    now = datetime.now(timezone.utc)
    rows_90 = history_map.get(offer_id, [])
    rows_30 = [x for x in rows_90 if x["checked_at"] >= now - timedelta(days=30)]

    points = len(rows_90)
    avg_30 = sum(x["price"] for x in rows_30) / len(rows_30) if rows_30 else None
    low_90 = min((x["price"] for x in rows_90), default=None)

    previous_distinct = None
    for row in rows_90:
        if abs(row["price"] - current_price) > 0.01:
            previous_distinct = row["price"]
            break

    prev_drop = price_drop_percent(current_price, previous_distinct)
    avg_drop = price_drop_percent(current_price, avg_30)
    strongest_drop = max(prev_drop, avg_drop)

    if points < 2:
        status = "insufficient_history"
        verified = False
    elif strongest_drop + 1e-9 >= HISTORY_DROP_THRESHOLD_PERCENT:
        status = "price_drop"
        verified = True
    elif previous_distinct is None:
        status = "no_observed_drop"
        verified = False
    else:
        status = "no_significant_drop"
        verified = False

    return {
        "history_status": status,
        "history_points": points,
        "history_avg_30d": round(avg_30, 2) if avg_30 is not None else None,
        "history_low_90d": round(low_90, 2) if low_90 is not None else None,
        "previous_distinct_price": round(previous_distinct, 2) if previous_distinct is not None else None,
        "history_drop_percent": round(strongest_drop, 2),
        "history_threshold_percent": HISTORY_DROP_THRESHOLD_PERCENT,
        "verified": verified,
    }


def history_label(info):
    status = info["history_status"]
    if status == "price_drop":
        return f"DOĞRULANDI (%{info['history_drop_percent']:.2f} geçmiş fiyat düşüşü)"
    if status == "insufficient_history":
        return f"YETERSİZ VERİ ({info['history_points']} geçmiş kayıt)"
    if status == "no_observed_drop":
        return "FİYAT DÜŞÜŞÜ HENÜZ GÖRÜLMEDİ"
    return f"ANLAMLI DÜŞÜŞ YOK (%{info['history_drop_percent']:.2f})"


def main():
    canonical, matches, variants, offers, merchants, existing, history = load_data()
    merchant_map = {m["id"]: (m.get("name") or m.get("slug") or m["id"]) for m in merchants}
    canonical_map = {c["id"]: c for c in canonical}
    existing_by_canonical = {x["canonical_product_id"]: x for x in existing}
    grouped = build_offer_groups(canonical, matches, variants, offers)
    history_map = build_history_map(history)

    print("=" * 88)
    print("DEAL ENGINE - CROSS STORE + PRICE HISTORY")
    print("=" * 88)
    print(f"Canonical ürün: {len(canonical)}")
    print(f"Rakip fiyat eşiği: %{DEAL_THRESHOLD_PERCENT:.2f}")
    print(f"Geçmiş fiyat düşüş eşiği: %{HISTORY_DROP_THRESHOLD_PERCENT:.2f}")
    print("Kural 1: en ucuz teklif, ikinci en ucuz farklı mağazadan en az %15 ucuzsa fırsat adayıdır.")
    print("Kural 2: geçmiş fiyatında en az %5 düşüş görülürse fırsat doğrulanır.\n")

    candidates = 0
    verified_count = 0
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
                sb_patch("deal_candidates", {"canonical_product_id": f"eq.{cid}"}, {"status": "expired", "verified": False, "verified_at": None, "updated_at": now})
            continue

        cheapest = store_offers[0]
        competitor = store_offers[1]
        gap = percent_cheaper(cheapest["price"], competitor["price"])

        cheapest_name = merchant_map.get(cheapest["merchant_id"], cheapest["merchant_id"])
        competitor_name = merchant_map.get(competitor["merchant_id"], competitor["merchant_id"])

        if gap + 1e-9 >= DEAL_THRESHOLD_PERCENT:
            history_info = analyze_history(cheapest["id"], cheapest["price"], history_map)
            verified_at = now if history_info["verified"] else None
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
                "verified_at": verified_at,
                **history_info,
            }
            if cid not in existing_by_canonical:
                row["detected_at"] = now
            sb_upsert("deal_candidates", row, "canonical_product_id")

            candidates += 1
            if history_info["verified"]:
                verified_count += 1
                prefix = "DOĞRULANMIŞ FIRSAT"
            else:
                prefix = "FIRSAT ADAYI"

            print(f"{prefix} | rakipten %{gap:.2f} ucuz | {title}")
            print(f"  {cheapest_name:<16} {cheapest['price']:>10.2f} TRY  <-- EN UCUZ")
            print(f"  {competitor_name:<16} {competitor['price']:>10.2f} TRY  <-- RAKİP")
            print(f"  Geçmiş kontrolü: {history_label(history_info)}")
            if history_info["history_avg_30d"] is not None:
                print(f"  30 gün ort.: {history_info['history_avg_30d']:.2f} TRY | 90 gün dip: {history_info['history_low_90d']:.2f} TRY")
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
                        "verified": False,
                        "verified_at": None,
                        "updated_at": now,
                    },
                )

    print("\n" + "=" * 88)
    print(f"Fırsat adayı: {candidates}")
    print(f"Geçmiş fiyatla doğrulanan: {verified_count}")
    print(f"Eşik altı: {not_candidates}")
    print(f"Yetersiz mağaza: {insufficient}")
    print("=" * 88)


if __name__ == "__main__":
    main()
