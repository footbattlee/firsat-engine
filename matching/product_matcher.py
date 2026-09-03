import json
import os
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher
from urllib.parse import urlencode
from urllib.request import Request, urlopen

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
MIN_SCORE = float(os.getenv("MATCH_MIN_SCORE", "78"))
MAX_GROUPS = int(os.getenv("MATCH_MAX_GROUPS", "30"))
VOLUME_TOLERANCE_ML = int(os.getenv("MATCH_VOLUME_TOLERANCE_ML", "5"))

STOPWORDS = {
    "termos", "matara", "bardak", "mug", "kupa", "pipetli", "paslanmaz", "celik",
    "fiyatlari", "ozellikleri", "the", "ve", "ile", "lt", "litre", "liter", "ml", "oz",
    "suluk", "bottle", "tumbler", "classic", "klasik", "renk", "renkli",
}

COLORS = {
    "siyah", "black", "beyaz", "white", "krem", "cream", "pembe", "pink", "rose",
    "quartz", "mavi", "blue", "azure", "lacivert", "navy", "yesil", "green", "gri",
    "gray", "grey", "mor", "purple", "bordo", "kirmizi", "red", "turuncu", "orange",
    "sari", "yellow", "mercan", "coral", "leylak", "lilac", "somon", "kahverengi", "brown",
    "haki", "khaki", "mint", "bej", "beige", "gold", "altin", "gumus", "silver",
}

COLOR_FAMILIES = {
    "siyah": "black", "black": "black",
    "beyaz": "white", "white": "white",
    "krem": "cream", "cream": "cream", "bej": "cream", "beige": "cream",
    "pembe": "pink", "pink": "pink", "rose": "pink", "quartz": "pink",
    "mavi": "blue", "blue": "blue", "azure": "blue", "lacivert": "navy", "navy": "navy",
    "yesil": "green", "green": "green", "mint": "green", "haki": "khaki", "khaki": "khaki",
    "gri": "gray", "gray": "gray", "grey": "gray",
    "mor": "purple", "purple": "purple", "leylak": "purple", "lilac": "purple",
    "bordo": "burgundy", "kirmizi": "red", "red": "red",
    "turuncu": "orange", "orange": "orange", "mercan": "coral", "coral": "coral", "somon": "coral",
    "sari": "yellow", "yellow": "yellow",
    "kahverengi": "brown", "brown": "brown",
    "gold": "gold", "altin": "gold", "gumus": "silver", "silver": "silver",
}


def sb_get(table, params=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil")
    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + urlencode(params, doseq=True, safe="(),.*:-")
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    req = Request(url, headers=headers, method="GET")
    with urlopen(req, timeout=45) as resp:
        raw = resp.read().decode()
        return json.loads(raw) if raw else []


def normalize_text(value):
    value = unicodedata.normalize("NFKD", (value or "").casefold().strip())
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.replace("ı", "i")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_brand(value):
    return normalize_text(value).replace(" ", "")


def tokens(value):
    return [t for t in normalize_text(value).split() if len(t) >= 2]


def meaningful_tokens(value):
    out = []
    for token in tokens(value):
        if token in STOPWORDS:
            continue
        if token.isdigit() and len(token) <= 2:
            continue
        out.append(token)
    return out


def extract_volume_ml(title):
    raw = (title or "").casefold()

    # 500 ml / 500ml
    matches = re.findall(r"(?<!\d)(\d{2,4}(?:[\.,]\d+)?)\s*ml\b", raw)
    if matches:
        try:
            return int(round(float(matches[0].replace(",", "."))))
        except ValueError:
            pass

    # 0.47 L / 0,89 LT / 1.1 litre
    m = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)\s*l(?:t|itre|iter)?\b", raw)
    if m:
        try:
            return int(round(float(m.group(1).replace(",", ".")) * 1000))
        except ValueError:
            pass

    # 12 oz / 16oz
    m = re.search(r"(?<!\d)(\d+(?:[\.,]\d+)?)\s*oz\b", raw)
    if m:
        try:
            return int(round(float(m.group(1).replace(",", ".")) * 29.5735))
        except ValueError:
            pass

    return None


def extract_colors(title):
    ts = set(tokens(title)).intersection(COLORS)
    return {COLOR_FAMILIES.get(x, x) for x in ts}


def extract_model_tokens(title):
    """Üretici/model koduna benzeyen kuvvetli tokenları çıkarır.

    Örn: 10-13062-013, ST-206, CKR2127, PNG-1200P, 10787-217.
    Sadece hacim/sayı ifadelerini model saymamak için en az bir harf veya tire ister.
    """
    raw = unicodedata.normalize("NFKD", (title or "").upper())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))
    raw = raw.replace("İ", "I")

    candidates = re.findall(r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+\b|\b[A-Z]{1,8}\d{2,}[A-Z0-9]*\b", raw)
    result = set()
    for token in candidates:
        compact = re.sub(r"[^A-Z0-9]", "", token)
        if len(compact) < 4:
            continue
        if not any(c.isalpha() for c in compact):
            # 10-13062-013 gibi Stanley kodları tamamen rakam+tire olabilir.
            if token.count("-") < 2:
                continue
        result.add(token)
    return result


def valid_gtin(value):
    if not value:
        return None
    digits = re.sub(r"\D", "", str(value))
    if len(digits) not in (8, 12, 13, 14):
        return None
    nums = [int(c) for c in digits]
    check = nums[-1]
    body = nums[:-1]
    total = 0
    for i, n in enumerate(reversed(body)):
        total += n * (3 if i % 2 == 0 else 1)
    expected = (10 - (total % 10)) % 10
    return digits if expected == check else None


def jaccard(a, b):
    sa, sb = set(a), set(b)
    if not sa or not sb:
        return 0.0
    return len(sa & sb) / len(sa | sb)


def title_similarity(a, b):
    na, nb = normalize_text(a), normalize_text(b)
    seq = SequenceMatcher(None, na, nb).ratio()
    jac = jaccard(meaningful_tokens(a), meaningful_tokens(b))
    return (seq * 0.45) + (jac * 0.55)


def model_overlap(a, b):
    explicit_a, explicit_b = extract_model_tokens(a), extract_model_tokens(b)
    if explicit_a and explicit_b:
        return len(explicit_a & explicit_b) / min(len(explicit_a), len(explicit_b))

    def model_tokens(title):
        result = set()
        for t in meaningful_tokens(title):
            if any(ch.isdigit() for ch in t) or len(t) >= 5:
                result.add(t)
        return result

    ma, mb = model_tokens(a), model_tokens(b)
    if not ma or not mb:
        return 0.0
    return len(ma & mb) / min(len(ma), len(mb))


def pair_score(a, b):
    if a["merchant_id"] == b["merchant_id"]:
        return 0.0, "same-merchant"

    gtin_a = valid_gtin(a.get("gtin"))
    gtin_b = valid_gtin(b.get("gtin"))
    if gtin_a and gtin_b:
        if gtin_a == gtin_b:
            return 100.0, "gtin"
        return 0.0, "gtin-conflict"

    brand_a = normalize_brand(a.get("brand"))
    brand_b = normalize_brand(b.get("brand"))
    if not brand_a or not brand_b or brand_a != brand_b:
        return 0.0, "brand"

    vol_a = extract_volume_ml(a["title"])
    vol_b = extract_volume_ml(b["title"])
    if vol_a is not None and vol_b is not None and abs(vol_a - vol_b) > VOLUME_TOLERANCE_ML:
        return 0.0, "volume-conflict"

    colors_a = extract_colors(a["title"])
    colors_b = extract_colors(b["title"])
    if colors_a and colors_b and colors_a.isdisjoint(colors_b):
        return 0.0, "color-conflict"

    models_a = extract_model_tokens(a["title"])
    models_b = extract_model_tokens(b["title"])
    if models_a and models_b and models_a.isdisjoint(models_b):
        return 0.0, "model-conflict"

    sim = title_similarity(a["title"], b["title"])
    model = model_overlap(a["title"], b["title"])

    score = 48.0
    score += sim * 34.0
    score += model * 12.0
    if vol_a is not None and vol_b is not None and abs(vol_a - vol_b) <= VOLUME_TOLERANCE_ML:
        score += 6.0
    if models_a and models_b and not models_a.isdisjoint(models_b):
        score += 5.0

    return min(score, 99.0), "heuristic"


def load_rows():
    merchants = sb_get("merchants", {"select": "id,name,slug"})
    products = sb_get("products", {"select": "id,brand,title,slug,active"})
    variants = sb_get("product_variants", {"select": "id,product_id,gtin,sku,active"})
    offers = sb_get("offers", {"select": "id,product_variant_id,merchant_id,merchant_product_id,price,currency,in_stock,product_url", "in_stock": "eq.true"})

    merchant_map = {x["id"]: x for x in merchants}
    product_map = {x["id"]: x for x in products}
    variant_map = {x["id"]: x for x in variants}

    rows = []
    for offer in offers:
        variant = variant_map.get(offer.get("product_variant_id"))
        if not variant:
            continue
        product = product_map.get(variant.get("product_id"))
        merchant = merchant_map.get(offer.get("merchant_id"))
        if not product or not merchant:
            continue
        rows.append({
            "offer_id": offer["id"],
            "variant_id": variant["id"],
            "product_id": product["id"],
            "merchant_id": merchant["id"],
            "merchant": merchant.get("name") or merchant.get("slug"),
            "merchant_product_id": offer.get("merchant_product_id"),
            "brand": product.get("brand"),
            "title": product.get("title") or "",
            "gtin": variant.get("gtin"),
            "sku": variant.get("sku"),
            "price": float(offer.get("price") or 0),
            "currency": offer.get("currency") or "TRY",
            "product_url": offer.get("product_url"),
        })
    return rows


def build_groups(rows):
    """Tam-bağlantı (complete-linkage) ile güvenli canonical gruplar oluşturur.

    Eski connected-component yaklaşımında A~B ve B~C eşleşmesi A ile C uyumsuz olsa
    bile üçünü aynı gruba taşıyabiliyordu. Burada iki grup ancak gruplar arasındaki
    TÜM çapraz çiftler MIN_SCORE üstündeyse birleşir. Böylece hacim/renk/model farkı
    transitive bridge üzerinden gruba sızamaz.
    """
    pair_cache = {}
    accepted_edges = []

    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            score, reason = pair_score(rows[i], rows[j])
            pair_cache[(i, j)] = (score, reason)
            if score >= MIN_SCORE:
                accepted_edges.append((score, reason, i, j))

    accepted_edges.sort(key=lambda x: -x[0])
    groups = [{i} for i in range(len(rows))]
    group_of = {i: i for i in range(len(rows))}

    def cached_pair(i, j):
        key = (i, j) if i < j else (j, i)
        return pair_cache.get(key, (0.0, "missing"))

    for score, reason, i, j in accepted_edges:
        gi = group_of[i]
        gj = group_of[j]
        if gi == gj:
            continue

        left = groups[gi]
        right = groups[gj]
        if not left or not right:
            continue

        # Aynı mağazadan iki farklı listing'i tek canonical varyanta sokma.
        merchant_ids = [rows[x]["merchant_id"] for x in (left | right)]
        if len(merchant_ids) != len(set(merchant_ids)):
            continue

        compatible = True
        for a in left:
            for b in right:
                cross_score, _ = cached_pair(a, b)
                if cross_score < MIN_SCORE:
                    compatible = False
                    break
            if not compatible:
                break

        if not compatible:
            continue

        merged = left | right
        groups[gi] = merged
        groups[gj] = set()
        for idx in merged:
            group_of[idx] = gi

    result = []
    for indexes_set in groups:
        if len(indexes_set) < 2:
            continue
        indexes = sorted(indexes_set)
        if len({rows[i]["merchant_id"] for i in indexes}) < 2:
            continue

        edges = []
        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1:]:
                score, reason = cached_pair(i, j)
                if score >= MIN_SCORE:
                    edges.append((score, reason, i, j))

        best_score = max((e[0] for e in edges), default=0.0)
        result.append((best_score, indexes, edges))

    result.sort(key=lambda x: (-x[0], -len(x[1])))
    return result


def print_groups(rows, groups):
    print("\n" + "=" * 88)
    print("PRODUCT MATCHER - DRY RUN")
    print("=" * 88)
    print(f"Aktif offer: {len(rows)}")
    print(f"Minimum eşleşme skoru: {MIN_SCORE:.1f}")
    print(f"Hacim toleransı: {VOLUME_TOLERANCE_ML} ml")
    print("Grup kuralı: complete-linkage; gruptaki her ürün diğer tüm ürünlerle uyumlu olmalı.")
    print(f"Bulunan cross-store grup: {len(groups)}")
    print("NOT: Bu sürüm veritabanını değiştirmez; sadece eşleşme adaylarını gösterir.\n")

    for no, (best_score, indexes, edges) in enumerate(groups[:MAX_GROUPS], 1):
        members = [rows[i] for i in indexes]
        members.sort(key=lambda x: (x["price"], x["merchant"]))
        cheapest = members[0]

        print("-" * 88)
        print(f"MATCH #{no} | best_score={best_score:.1f}")
        print(f"{cheapest['brand'] or '-'} | {cheapest['title']}")
        for m in members:
            mark = "  <-- EN UCUZ" if m is cheapest else ""
            gtin = valid_gtin(m.get("gtin")) or "-"
            vol = extract_volume_ml(m["title"])
            vol_text = f"{vol} ml" if vol else "-"
            models = ",".join(sorted(extract_model_tokens(m["title"]))) or "-"
            colors = ",".join(sorted(extract_colors(m["title"]))) or "-"
            print(
                f"  {m['merchant']:<14} {m['price']:>10.2f} {m['currency']} | "
                f"GTIN {gtin} | HACİM {vol_text} | MODEL {models} | RENK {colors} | {m['title']}{mark}"
            )
        if len(members) > 1:
            highest = max(m["price"] for m in members)
            print(f"  Fiyat farkı: {highest - cheapest['price']:.2f} TRY")

        if edges:
            reasons = sorted({reason for _, reason, _, _ in edges})
            print("  Match reason:", ", ".join(reasons))

    if len(groups) > MAX_GROUPS:
        print(f"\n... {len(groups) - MAX_GROUPS} grup daha var. MATCH_MAX_GROUPS ile artırabilirsin.")


def main():
    rows = load_rows()
    groups = build_groups(rows)
    print_groups(rows, groups)


if __name__ == "__main__":
    main()
