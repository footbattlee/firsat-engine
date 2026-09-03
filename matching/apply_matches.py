import json
import os
from datetime import datetime, timezone
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from product_matcher import (
    SUPABASE_URL,
    SUPABASE_SERVICE_ROLE_KEY,
    build_groups,
    extract_colors,
    extract_volume_ml,
    load_rows,
    normalize_text,
    valid_gtin,
)

AUTO_APPROVE_MIN = float(os.getenv("MATCH_AUTO_APPROVE_MIN", "88"))


def sb(method, table, params=None, body=None, prefer=None):
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanımlı değil")

    url = f"{SUPABASE_URL}/rest/v1/{table}"
    if params:
        url += "?" + urlencode(params, doseq=True, safe="(),.*:-")

    headers = {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
        "Content-Type": "application/json",
    }
    if prefer:
        headers["Prefer"] = prefer

    payload = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = Request(url, data=payload, headers=headers, method=method)

    try:
        with urlopen(req, timeout=45) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw else None
    except HTTPError as exc:
        detail = exc.read().decode(errors="replace")
        raise RuntimeError(f"Supabase HTTP {exc.code}: {detail}") from exc


def clean_title(title):
    value = (title or "").strip()
    suffixes = (
        " Fiyatları ve Özellikleri",
        " Fiyatlari ve Ozellikleri",
    )
    for suffix in suffixes:
        if value.casefold().endswith(suffix.casefold()):
            value = value[: -len(suffix)].strip(" -")
    return value


def choose_title(members):
    titles = [clean_title(m.get("title")) for m in members if clean_title(m.get("title"))]
    if not titles:
        return "Eşleştirilmiş ürün"
    return min(titles, key=lambda x: (len(x), x.casefold()))


def choose_brand(members):
    counts = {}
    original = {}
    for member in members:
        brand = (member.get("brand") or "").strip()
        if not brand:
            continue
        key = normalize_text(brand).replace(" ", "")
        if not key:
            continue
        counts[key] = counts.get(key, 0) + 1
        original.setdefault(key, brand)
    if not counts:
        return None
    key = max(counts, key=lambda k: (counts[k], len(original[k])))
    return original[key]


def choose_gtin(members):
    gtins = [valid_gtin(m.get("gtin")) for m in members]
    gtins = [g for g in gtins if g]
    if not gtins:
        return None
    if len(set(gtins)) == 1:
        return gtins[0]
    return None


def choose_color(members):
    color_sets = [extract_colors(m.get("title") or "") for m in members]
    color_sets = [s for s in color_sets if s]
    if not color_sets:
        return None
    common = set.intersection(*color_sets) if len(color_sets) > 1 else color_sets[0]
    if not common:
        return None
    return sorted(common)[0]


def existing_match(product_id):
    rows = sb(
        "GET",
        "product_matches",
        {"product_id": f"eq.{product_id}", "select": "id,canonical_product_id,status", "limit": "1"},
    )
    return rows[0] if rows else None


def create_canonical(members):
    title = choose_title(members)
    volume_values = [extract_volume_ml(m.get("title") or "") for m in members]
    volume_values = [v for v in volume_values if v is not None]
    capacity_ml = volume_values[0] if volume_values and len(set(volume_values)) == 1 else None

    payload = {
        "brand": choose_brand(members),
        "title": title,
        "normalized_title": normalize_text(title),
        "capacity_ml": capacity_ml,
        "color": choose_color(members),
        "gtin": choose_gtin(members),
        "active": True,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
    rows = sb("POST", "canonical_products", body=payload, prefer="return=representation")
    return rows[0]


def apply_group(best_score, indexes, edges, rows):
    members = [rows[i] for i in indexes]

    existing = [existing_match(m["product_id"]) for m in members]
    if any(existing):
        print("SKIP: Gruptaki ürünlerden en az biri daha önce canonical ürüne bağlanmış.")
        return False

    canonical = create_canonical(members)
    reasons = sorted({reason for _, reason, _, _ in edges}) or ["heuristic"]
    reason_text = ",".join(reasons)
    now = datetime.now(timezone.utc).isoformat()

    for member in members:
        sb(
            "POST",
            "product_matches",
            body={
                "canonical_product_id": canonical["id"],
                "product_id": member["product_id"],
                "match_score": round(best_score, 2),
                "match_reason": reason_text,
                "status": "approved",
                "updated_at": now,
            },
            prefer="return=minimal",
        )

    print(f"APPROVED: {canonical['title']} | {len(members)} mağaza ürünü | score={best_score:.1f}")
    for member in sorted(members, key=lambda x: (x["price"], x["merchant"])):
        print(f"  {member['merchant']:<14} {member['price']:>10.2f} {member['currency']} | {member['title']}")
    return True


def main():
    rows = load_rows()
    groups = build_groups(rows)

    print("=" * 88)
    print("CANONICAL MATCH WRITER")
    print("=" * 88)
    print(f"Aktif offer: {len(rows)}")
    print(f"Matcher grubu: {len(groups)}")
    print(f"Otomatik onay eşiği: {AUTO_APPROVE_MIN:.1f}")
    print("Sadece eşik üstündeki gruplar canonical_products/product_matches tablolarına yazılır.\n")

    applied = 0
    skipped_low = 0
    for best_score, indexes, edges in groups:
        if best_score < AUTO_APPROVE_MIN:
            skipped_low += 1
            continue
        if apply_group(best_score, indexes, edges, rows):
            applied += 1

    print("\n" + "=" * 88)
    print(f"Yeni canonical grup: {applied}")
    print(f"Eşik altı grup: {skipped_low}")
    print("=" * 88)


if __name__ == "__main__":
    main()
