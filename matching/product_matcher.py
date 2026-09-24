import argparse
import json
import os
import re
import unicodedata
from difflib import SequenceMatcher
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
MIN_SCORE = float(os.getenv("MATCH_MIN_SCORE", "75"))
MAX_GROUPS = int(os.getenv("MATCH_MAX_GROUPS", "30"))
DEBUG_REJECTS = os.getenv("MATCH_DEBUG_REJECTS", "0").strip().lower() in ("1", "true", "yes", "on")
DEBUG_LIMIT = int(os.getenv("MATCH_DEBUG_LIMIT", "80"))
DEBUG_MIN_SCORE = float(os.getenv("MATCH_DEBUG_MIN_SCORE", "60"))
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

VOLUME_CONTEXT_WORDS = {
    "termos", "matara", "bardak", "mug", "kupa", "bottle", "suluk", "tumbler",
    "iceflow", "aerolight", "fliptop", "quencher",
}


def sb_get(table, params=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil")

    # PostgREST responses are capped by the project API row limit (commonly 1000).
    # Fetch every page explicitly; otherwise matcher silently sees only the first
    # slice of products/variants/offers and newer categories such as technology
    # can disappear from the matching inventory.
    base_url = f"{SUPABASE_URL}/rest/v1/{table}"
    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }
    page_size = 1000
    offset = 0
    rows = []

    while True:
        query = dict(params or {})
        query["limit"] = page_size
        query["offset"] = offset
        url = base_url + "?" + urlencode(query, doseq=True, safe="(),.*:-")
        req = Request(url, headers=headers, method="GET")
        with urlopen(req, timeout=45) as resp:
            raw = resp.read().decode()
            page = json.loads(raw) if raw else []

        rows.extend(page)
        if len(page) < page_size:
            break
        offset += page_size

    return rows


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


def _decimal_to_float(raw):
    raw = raw.replace(",", ".")
    if raw.startswith("."):
        raw = "0" + raw
    return float(raw)


def extract_volume_ml(title):
    raw = (title or "").casefold()

    # 500 ml / 500ml
    m = re.search(r"(?<![\d.,])(\d{2,4}(?:[\.,]\d+)?)\s*ml\b", raw)
    if m:
        try:
            return int(round(_decimal_to_float(m.group(1))))
        except ValueError:
            pass

    # 0.47L / .35L / 0,89 LT / 1.1 litre
    m = re.search(r"(?<![\d.,])((?:\d+[\.,]\d+)|(?:[\.,]\d+)|\d+)\s*l(?:t|itre|iter)?\b", raw)
    if m:
        try:
            liters = _decimal_to_float(m.group(1))
            if 0 < liters <= 20:
                return int(round(liters * 1000))
        except ValueError:
            pass

    # 12 oz / 16oz
    m = re.search(r"(?<![\d.,])((?:\d+[\.,]\d+)|\d+)\s*oz\b", raw)
    if m:
        try:
            return int(round(_decimal_to_float(m.group(1)) * 29.5735))
        except ValueError:
            pass

    # Bazı mağazalar başlıkta birimi atıyor: "Termos Bardak 0,89" / "Mug 0.47".
    # Bunu yalnızca termos/matara bağlamında uygula; diğer kategorilerde rastgele ondalıkları hacim sayma.
    norm_tokens = set(tokens(title))
    if norm_tokens.intersection(VOLUME_CONTEXT_WORDS):
        candidates = re.findall(r"(?<![\d.,])((?:\d+[\.,]\d+)|(?:[\.,]\d+))(?![\d.,])", raw)
        for candidate in candidates:
            try:
                liters = _decimal_to_float(candidate)
            except ValueError:
                continue
            if 0.10 <= liters <= 5.0:
                return int(round(liters * 1000))

    return None


def extract_colors(title):
    found = set(tokens(title)).intersection(COLORS)
    return {COLOR_FAMILIES.get(x, x) for x in found}


def extract_model_tokens(title):
    raw = unicodedata.normalize("NFKD", (title or "").upper())
    raw = "".join(ch for ch in raw if not unicodedata.combining(ch))

    candidates = re.findall(
        r"\b[A-Z]{1,8}\d{2,}[A-Z0-9]*(?:/\d{1,4})?\b|"
        r"\b[A-Z0-9]+(?:-[A-Z0-9]+)+(?:/\d{1,4})?\b",
        raw,
    )
    result = set()
    color_words = {x.upper() for x in COLORS}

    for token in candidates:
        parts = [p for p in token.split("-") if p]
        if parts and all(p in color_words for p in parts):
            continue

        compact = re.sub(r"[^A-Z0-9]", "", token)
        if len(compact) < 4:
            continue

        # Ordinary hyphenated phrases such as LEAK-PROOF are not model codes.
        if not any(ch.isdigit() for ch in token):
            continue

        result.add(token)
    return result


def extract_age_ranges(title):
    raw = normalize_text(title)
    ranges = set()
    # normalize_text turns "6-18 ay" into "6 18 ay".
    for lo, hi in re.findall(r"\b(\d{1,2})\s+(\d{1,2})\s*ay\b", raw):
        ranges.add((int(lo), int(hi)))
    return ranges


def extract_pack_counts(title):
    raw = normalize_text(title)
    values = set()
    for value in re.findall(r"\b(\d{1,4})\s*(?:adet|li paket|li)\b", raw):
        amount = int(value)
        if 2 <= amount <= 1000:
            values.add(amount)
    return values


def model_evidence_compatible(a, b):
    # Technology products use their own family/model compatibility rules.
    # Applying the generic one-sided SKU rule after a valid tech-family match
    # blocks real matches such as Q20i vs Q20i A3004 or iPhone family names.
    if technology_profile(a["title"]) or technology_profile(b["title"]):
        return True, None

    models_a = extract_model_tokens(a["title"])
    models_b = extract_model_tokens(b["title"])

    if models_a and models_b and models_a.isdisjoint(models_b):
        return False, "model-conflict"

    if bool(models_a) != bool(models_b):
        return False, "model-missing-one-side"

    return True, None


def variant_evidence_compatible(a, b):
    ages_a, ages_b = extract_age_ranges(a["title"]), extract_age_ranges(b["title"])
    if ages_a and ages_b and ages_a.isdisjoint(ages_b):
        return False, "age-range-conflict"

    packs_a, packs_b = extract_pack_counts(a["title"]), extract_pack_counts(b["title"])
    if packs_a and packs_b and packs_a.isdisjoint(packs_b):
        return False, "pack-count-conflict"

    return True, None


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
    ma, mb = extract_model_tokens(a), extract_model_tokens(b)
    if ma and mb:
        return len(ma & mb) / min(len(ma), len(mb))
    return 0.0


def extract_storage_gb(title):
    raw = normalize_text(title)
    values = set()
    for amount, unit in re.findall(r"\b(\d{1,4})\s*(tb|gb)\b", raw):
        value = int(amount) * (1024 if unit == "tb" else 1)
        if 16 <= value <= 8192:
            values.add(value)
    return values


def extract_ram_gb(title):
    raw = normalize_text(title)
    values = set()
    patterns = [
        r"\b(\d{1,3})\s*gb\s*ram\b",
        r"\bram\s*(\d{1,3})\s*gb\b",
        r"\b(\d{1,3})\s*gb\s*(?:ddr[345]|lpddr[45x]*)\b",
    ]
    for pattern in patterns:
        for value in re.findall(pattern, raw):
            amount = int(value)
            if 2 <= amount <= 256:
                values.add(amount)
    return values


def extract_cpu_tokens(title):
    raw = normalize_text(title)
    patterns = [
        r"\b(?:i[3579]-?\d{4,5}[a-z]{0,2})\b",
        r"\b(?:ryzen\s*[3579]\s*\d{4}[a-z]{0,2})\b",
        r"\b(?:m[1234](?:\s*(?:pro|max|ultra))?)\b",
    ]
    return {re.sub(r"\s+", "", x) for p in patterns for x in re.findall(p, raw)}


def extract_screen_inches(title):
    raw = normalize_text(title)
    values = set()
    for value in re.findall(r"\b(\d{2}(?:[.,]\d)?)\s*(?:inc|inch|\")", raw):
        try:
            size = float(value.replace(",", "."))
            if 10 <= size <= 100:
                values.add(round(size, 1))
        except ValueError:
            pass
    return values


def extract_phone_family(title):
    norm = normalize_text(title)
    patterns = [
        r"\biphone\s+(\d{1,2})\s*(pro max|pro|plus|mini)?\b",
        r"\bgalaxy\s+([asz]\d{1,3}(?:\s*(?:ultra|plus|fe))?)\b",
        r"\b(redmi|poco)\s+([a-z0-9]+(?:\s+[a-z0-9]+){0,2})\b",
    ]
    for idx, pattern in enumerate(patterns):
        m = re.search(pattern, norm)
        if not m:
            continue
        if idx == 0:
            return "iphone " + m.group(1) + ((" " + m.group(2)) if m.group(2) else "")
        return " ".join(x for x in m.groups() if x)
    return None


def generic_tech_family_keys(title):
    norm = normalize_text(title)
    keys = set()

    # Common consumer families where a generic certification/spec token (IP67,
    # wattage, DPI, etc.) must never become the product identity.
    patterns = [
        r"\b(jbl\s+)?(go\s*\d+)\b",
        r"\b(jbl\s+)?(charge\s*\d+)\b",
        r"\b(jbl\s+)?(flip\s*\d+)\b",
        r"\b(freebuds\s+se\s*\d+(?:\s+anc)?)\b",
        r"\b(odyssey\s+g\d+)\b",
        r"\b(deebot\s+[a-z]*\d+[a-z]*)\b",
    ]
    for pattern in patterns:
        for m in re.finditer(pattern, norm):
            value = m.group(m.lastindex or 0)
            if value:
                keys.add("FAMILY:" + re.sub(r"\s+", "", value).upper())
    return keys


def extract_critical_variant_suffixes(title):
    norm = normalize_text(title)
    tokens = set(norm.split())
    # Product-family suffixes that materially change the model. Colors are
    # deliberately excluded because Fiyatzade may compare different colors.
    return tokens & {"pro", "plus", "max", "ultra", "mini", "lite", "gen", "ae", "ce"}


def tech_model_keys(title):
    keys = set(extract_model_tokens(title))
    norm = normalize_text(title)

    # These are specifications/certifications, not product model identities.
    noisy_patterns = (
        r"^IP\\d{2}$", r"^BT\\d+$", r"^BT\\d+\\d+$", r"^USB\\d+$",
        r"^\\d+DPI$", r"^\\d+HZ$", r"^\\d+W$",
    )
    keys = {k for k in keys if not any(re.match(p, k.upper()) for p in noisy_patterns)}
    keys.update(generic_tech_family_keys(title))

    # Consumer model names such as Q20i/R50i may contain only one digit and
    # are intentionally not covered by the stricter general SKU extractor.
    for token in re.findall(r"\b[a-z]{1,8}\d{1,5}[a-z0-9]*\b", norm):
        if len(token) >= 3:
            keys.add(token.upper())

    phone = extract_phone_family(title)
    if phone:
        keys.add("PHONE:" + phone.upper())

    phrase = consumer_model_phrase(title)
    if phrase:
        keys.add("MODEL:" + phrase.upper())
    return keys


def consumer_model_phrase(title):
    norm = normalize_text(title)
    patterns = [
        r"\bsoundcore\s+(q\d+[a-z0-9]*|r\d+[a-z0-9]*|space\s+(?:one|\d+)|liberty\s+\d+)\b",
        r"\b(airpods\s+(?:pro\s*)?\d*)\b",
    ]
    for pattern in patterns:
        m = re.search(pattern, norm)
        if m:
            return re.sub(r"\s+", " ", m.group(1)).strip()
    return None


def technology_profile(title):
    norm = normalize_text(title)
    # normalize_text() removes Turkish diacritics but keeps dotless-i as "i".
    # Match normalized ASCII phrases here; otherwise titles such as
    # "Kulaklık", "Dizüstü" and "Akıllı Saat" silently miss the tech path.
    if any(x in norm for x in ("iphone", "galaxy", "xiaomi", "redmi", "poco", "telefon")):
        return "phone"
    if any(x in norm for x in ("laptop", "notebook", "macbook", "dizustu", "tasinabilir bilgisayar")):
        return "laptop"
    if re.search(r"\bssd\b", norm):
        return "storage"
    if re.search(r"\b(televizyon|television|tv)\b", norm):
        return "tv"
    if any(x in norm for x in (
        "kulaklik", "hoparlor", "akilli saat", "monitor", "klavye", "mouse",
        "oyun kolu", "robot supurge", "dikey supurge", "kahve makinesi",
        "airfryer", "blender", "tost makinesi", "kettle", "su isitici",
        "sac kurutma", "tiras makinesi", "elektrikli dis fircasi",
    )):
        return "model"
    return None

def strict_technology_compatible(a, b):
    profile_a = technology_profile(a["title"])
    profile_b = technology_profile(b["title"])
    profile = profile_a if profile_a == profile_b else None
    if profile_a or profile_b:
        if profile is None:
            return False, "tech-profile-conflict"

        models_a = tech_model_keys(a["title"])
        models_b = tech_model_keys(b["title"])
        if not models_a or not models_b:
            return False, "tech-model-required"

        suffix_a = extract_critical_variant_suffixes(a["title"])
        suffix_b = extract_critical_variant_suffixes(b["title"])
        if suffix_a != suffix_b and (suffix_a or suffix_b):
            return False, "tech-variant-suffix-conflict"

        semantic_a = {x for x in models_a if x.startswith(("FAMILY:", "MODEL:", "PHONE:"))}
        semantic_b = {x for x in models_b if x.startswith(("FAMILY:", "MODEL:", "PHONE:"))}
        if semantic_a or semantic_b:
            if not semantic_a or not semantic_b or semantic_a.isdisjoint(semantic_b):
                return False, "tech-family-conflict"
        elif models_a.isdisjoint(models_b):
            return False, "tech-model-required"

        storage_a = extract_storage_gb(a["title"])
        storage_b = extract_storage_gb(b["title"])
        if profile in ("phone", "storage") and (not storage_a or not storage_b or storage_a.isdisjoint(storage_b)):
            return False, "tech-storage-required"

        if profile == "laptop":
            ram_a, ram_b = extract_ram_gb(a["title"]), extract_ram_gb(b["title"])
            cpu_a, cpu_b = extract_cpu_tokens(a["title"]), extract_cpu_tokens(b["title"])
            if not ram_a or not ram_b or ram_a.isdisjoint(ram_b):
                return False, "tech-ram-required"
            if not cpu_a or not cpu_b or cpu_a.isdisjoint(cpu_b):
                return False, "tech-cpu-required"
            if storage_a and storage_b and storage_a.isdisjoint(storage_b):
                return False, "tech-storage-conflict"

        if profile == "tv":
            size_a, size_b = extract_screen_inches(a["title"]), extract_screen_inches(b["title"])
            if size_a and size_b and size_a.isdisjoint(size_b):
                return False, "tech-screen-conflict"

    return True, None


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

    tech_ok, tech_reason = strict_technology_compatible(a, b)
    if not tech_ok:
        return 0.0, tech_reason

    vol_a = extract_volume_ml(a["title"])
    vol_b = extract_volume_ml(b["title"])
    if vol_a is not None and vol_b is not None and abs(vol_a - vol_b) > VOLUME_TOLERANCE_ML:
        return 0.0, "volume-conflict"

    # Color is not a product-identity blocker for Fiyatzade. Different colors
    # of the same model may be compared; model/capacity/GTIN/critical variants
    # remain protected by the stricter checks below.

    model_ok, model_reason = model_evidence_compatible(a, b)
    if not model_ok:
        return 0.0, model_reason

    variant_ok, variant_reason = variant_evidence_compatible(a, b)
    if not variant_ok:
        return 0.0, variant_reason

    models_a = extract_model_tokens(a["title"])
    models_b = extract_model_tokens(b["title"])

    sim = title_similarity(a["title"], b["title"])
    model = model_overlap(a["title"], b["title"])

    tech_profile = technology_profile(a["title"])
    tech_bonus = 0.0
    if tech_profile and tech_profile == technology_profile(b["title"]):
        tech_keys_a = tech_model_keys(a["title"])
        tech_keys_b = tech_model_keys(b["title"])
        if tech_keys_a and tech_keys_b and not tech_keys_a.isdisjoint(tech_keys_b):
            tech_bonus = 12.0

    score = 48.0 + (sim * 34.0) + (model * 12.0) + tech_bonus
    if vol_a is not None and vol_b is not None and abs(vol_a - vol_b) <= VOLUME_TOLERANCE_ML:
        score += 6.0
    if models_a and models_b and not models_a.isdisjoint(models_b):
        score += 5.0

    return min(score, 99.0), "heuristic"


def load_rows():
    merchants = sb_get("merchants", {"select": "id,name,slug"})
    products = sb_get("products", {"select": "id,brand,title,slug,active"})
    variants = sb_get("product_variants", {"select": "id,product_id,gtin,sku,active"})
    offer_params = {
        "select": "id,product_variant_id,merchant_id,merchant_product_id,price,currency,in_stock,product_url,last_checked_at",
        "in_stock": "eq.true",
    }
    pipeline_started_at = os.getenv("PIPELINE_STARTED_AT", "").strip()
    if pipeline_started_at:
        offer_params["last_checked_at"] = f"gte.{pipeline_started_at}"
        print(f"MATCH SCOPE | only offers refreshed since {pipeline_started_at}")
    offers = sb_get("offers", offer_params)

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
    # pair_score() can only accept pairs from different merchants with the same
    # normalized brand. Bucket up front instead of evaluating every offer
    # against every other offer in the database (O(n^2)).
    brand_buckets = {}
    for idx, row in enumerate(rows):
        brand = normalize_brand(row.get("brand"))
        if not brand:
            continue
        brand_buckets.setdefault(brand, []).append(idx)

    pair_cache = {}
    accepted_edges = []

    for indexes in brand_buckets.values():
        if len(indexes) < 2:
            continue
        merchants = {rows[i]["merchant_id"] for i in indexes}
        if len(merchants) < 2:
            continue

        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1:]:
                if rows[i]["merchant_id"] == rows[j]["merchant_id"]:
                    continue
                score, reason = pair_score(rows[i], rows[j])
                pair_cache[(i, j)] = (score, reason)
                if score >= MIN_SCORE:
                    accepted_edges.append((score, reason, i, j))

    accepted_edges.sort(key=lambda x: -x[0])

    # Only rows participating in an accepted edge need group state.
    active_indexes = {i for _, _, i, j in accepted_edges for i in (i, j)}
    groups = {i: {i} for i in active_indexes}
    group_of = {i: i for i in active_indexes}

    def cached_pair(i, j):
        key = (i, j) if i < j else (j, i)
        return pair_cache.get(key, (0.0, "missing"))

    for _, _, i, j in accepted_edges:
        gi, gj = group_of[i], group_of[j]
        if gi == gj:
            continue
        left, right = groups[gi], groups[gj]
        if not left or not right:
            continue

        merchant_ids = [rows[x]["merchant_id"] for x in (left | right)]
        if len(merchant_ids) != len(set(merchant_ids)):
            continue

        if any(cached_pair(a, b)[0] < MIN_SCORE for a in left for b in right):
            continue

        merged = left | right
        groups[gi] = merged
        groups[gj] = set()
        for idx in merged:
            group_of[idx] = gi

    result = []
    for indexes_set in groups.values():
        if len(indexes_set) < 2:
            continue
        indexes = sorted(indexes_set)
        edges = []
        for pos, i in enumerate(indexes):
            for j in indexes[pos + 1:]:
                score, reason = cached_pair(i, j)
                if score >= MIN_SCORE:
                    edges.append((score, reason, i, j))
        if not edges:
            continue
        result.append((max(e[0] for e in edges), indexes, edges))

    result.sort(key=lambda x: (-x[0], -len(x[1])))
    return result

def print_technology_inventory(rows):
    if not DEBUG_REJECTS:
        return

    tech_rows = [(idx, row, technology_profile(row["title"])) for idx, row in enumerate(rows) if technology_profile(row["title"])]
    print("\n" + "=" * 88)
    print("TECH INVENTORY")
    print("=" * 88)
    print(f"Matcher icindeki teknoloji offer: {len(tech_rows)}")

    unclassified_focus = [row for row in rows if any(x in normalize_text(row["title"]) for x in ("q20i", "q30", "space one", "liberty 5", "iphone 17", "aspire lite")) and not technology_profile(row["title"])]
    if unclassified_focus:
        print(f"Siniflandirilamayan odak teknoloji offer: {len(unclassified_focus)}")
        for row in unclassified_focus[:DEBUG_LIMIT]:
            print(f"  UNCLASSIFIED | {row['merchant']} | {row.get('brand') or '-'} | {row['title']}")

    by_profile = {}
    for _, _, profile in tech_rows:
        by_profile[profile] = by_profile.get(profile, 0) + 1
    for profile, count in sorted(by_profile.items()):
        print(f"  {profile:<12} {count:>5}")

    interesting = ("q20i", "q30", "space one", "liberty 5", "iphone 17", "aspire lite")
    focus = [(idx, row, profile) for idx, row, profile in tech_rows if any(x in normalize_text(row["title"]) for x in interesting)]
    print(f"\nOdak teknoloji offer: {len(focus)}")
    for _, row, profile in focus:
        print("-" * 88)
        print(f"{row['merchant']} | {row.get('brand') or '-'} | profile={profile}")
        print(f"  {row['title']}")
        print(f"  tech_keys={sorted(tech_model_keys(row['title']))} storage={sorted(extract_storage_gb(row['title']))} ram={sorted(extract_ram_gb(row['title']))} cpu={sorted(extract_cpu_tokens(row['title']))}")

    print("\nOdak cross-store pair sonuclari:")
    shown = 0
    for x in range(len(focus)):
        ia, a, pa = focus[x]
        for y in range(x + 1, len(focus)):
            ib, b, pb = focus[y]
            if a["merchant_id"] == b["merchant_id"]:
                continue
            if normalize_brand(a.get("brand")) != normalize_brand(b.get("brand")):
                continue
            score, reason = pair_score(a, b)
            print("-" * 88)
            print(f"{score:5.1f} | {reason} | {a['merchant']} <-> {b['merchant']}")
            print(f"  A: {a['title']}")
            print(f"  B: {b['title']}")
            shown += 1
            if shown >= DEBUG_LIMIT:
                return


def print_rejection_diagnostics(rows):
    if not DEBUG_REJECTS:
        return

    reasons = {}
    near_threshold = []
    technology_rejects = []

    for i in range(len(rows)):
        for j in range(i + 1, len(rows)):
            a, b = rows[i], rows[j]
            if a["merchant_id"] == b["merchant_id"]:
                continue

            score, reason = pair_score(a, b)
            reasons[reason] = reasons.get(reason, 0) + 1

            same_brand = normalize_brand(a.get("brand")) and normalize_brand(a.get("brand")) == normalize_brand(b.get("brand"))
            if DEBUG_MIN_SCORE <= score < MIN_SCORE:
                near_threshold.append((score, reason, a, b))

            tech = technology_profile(a["title"]) or technology_profile(b["title"])
            if tech and same_brand and score < MIN_SCORE:
                technology_rejects.append((score, reason, tech, a, b))

    near_threshold.sort(key=lambda x: -x[0])
    technology_rejects.sort(key=lambda x: (-x[0], x[1]))

    print("\n" + "=" * 88)
    print("MATCHER DIAGNOSTIC")
    print("=" * 88)
    print(f"Esik: {MIN_SCORE:.1f} | Debug alt siniri: {DEBUG_MIN_SCORE:.1f}")
    print("Red nedenleri (cross-store pair):")
    for reason, count in sorted(reasons.items(), key=lambda x: -x[1]):
        print(f"  {reason:<28} {count:>6}")

    print(f"\n{DEBUG_MIN_SCORE:.1f}-{MIN_SCORE - 0.01:.2f} arasi esik alti aday: {len(near_threshold)}")
    for score, reason, a, b in near_threshold[:DEBUG_LIMIT]:
        print("-" * 88)
        print(f"NEAR | score={score:.1f} | reason={reason}")
        print(f"  {a['merchant']} | {a.get('brand') or '-'} | {a['title']}")
        print(f"  {b['merchant']} | {b.get('brand') or '-'} | {b['title']}")

    print(f"\nTeknoloji redleri (ayni marka, cross-store): {len(technology_rejects)}")
    for score, reason, profile, a, b in technology_rejects[:DEBUG_LIMIT]:
        print("-" * 88)
        print(f"TECH-RED | profile={profile} | score={score:.1f} | reason={reason}")
        print(f"  {a['merchant']} | {a.get('brand') or '-'} | {a['title']}")
        print(f"    tech_keys={sorted(tech_model_keys(a['title']))} storage={sorted(extract_storage_gb(a['title']))} ram={sorted(extract_ram_gb(a['title']))} cpu={sorted(extract_cpu_tokens(a['title']))}")
        print(f"  {b['merchant']} | {b.get('brand') or '-'} | {b['title']}")
        print(f"    tech_keys={sorted(tech_model_keys(b['title']))} storage={sorted(extract_storage_gb(b['title']))} ram={sorted(extract_ram_gb(b['title']))} cpu={sorted(extract_cpu_tokens(b['title']))}")


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
            vol_text = f"{vol} ml" if vol is not None else "-"
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
            print("  Match reason:", ", ".join(sorted({reason for _, reason, _, _ in edges})))

    if len(groups) > MAX_GROUPS:
        print(f"\n... {len(groups) - MAX_GROUPS} grup daha var. MATCH_MAX_GROUPS ile artırabilirsin.")


def main():
    global DEBUG_REJECTS
    parser = argparse.ArgumentParser()
    parser.add_argument("--debug-rejects", action="store_true", help="Esik alti ve teknoloji redlerini goster")
    args, _ = parser.parse_known_args()
    if args.debug_rejects:
        DEBUG_REJECTS = True

    rows = load_rows()
    groups = build_groups(rows)
    print_groups(rows, groups)
    print_rejection_diagnostics(rows)
    print_technology_inventory(rows)


if __name__ == "__main__":
    main()
