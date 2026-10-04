import argparse
from pathlib import Path
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
    pair_score,
    prepare_rows,
    sb_get,
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


def plan_group(best_score, indexes, edges, rows, existing_rows):
    """Pure planner shared by dry-run and writer; refuses weak group bridges."""
    members = [rows[i] for i in indexes]
    member_ids = {m["product_id"] for m in members}
    edge_pairs = {tuple(sorted((i, j))) for _, _, i, j in edges}
    required = {tuple(sorted((i, j))) for n, i in enumerate(indexes) for j in indexes[n + 1:]}
    if len(members) < 2 or edge_pairs != required or any(s < AUTO_APPROVE_MIN for s, _, _, _ in edges):
        return {"action": "review", "reason": "weak-or-incomplete-group"}
    if len(member_ids) != len(members):
        return {"action": "review", "reason": "multiple-variants-one-product"}
    by_product = {}
    for match in existing_rows:
        by_product.setdefault(match["product_id"], []).append(match)
    existing = [m for pid in member_ids for m in by_product.get(pid, [])]
    if any(m.get("status") != "approved" for m in existing):
        return {"action": "review", "reason": "existing-nonapproved-match"}
    cids = {m["canonical_product_id"] for m in existing}
    if len(cids) > 1:
        return {"action": "review", "reason": "canonical-conflict"}
    new_members = [m for m in members if m["product_id"] not in by_product]
    if not new_members:
        return {"action": "skip", "reason": "already-linked"}
    canonical_id = next(iter(cids), None)
    if canonical_id:
        anchors = [m for m in existing_rows if m["canonical_product_id"] == canonical_id]
        if any(m.get("status") != "approved" for m in anchors):
            return {"action": "review", "reason": "canonical-has-nonapproved-members"}
        rows_by_product = {}
        for row in rows:
            rows_by_product.setdefault(row["product_id"], []).append(row)
        if any(m["product_id"] not in rows_by_product for m in anchors):
            return {"action": "review", "reason": "canonical-member-outside-snapshot"}
        for member in new_members:
            for anchor in anchors:
                for reference in rows_by_product[anchor["product_id"]]:
                    # Same-store aliases still need identity compatibility.
                    reference = {**reference, "merchant_id": "__canonical_reference__"}
                    if pair_score(member, reference)[0] < AUTO_APPROVE_MIN:
                        return {"action": "review", "reason": "canonical-member-incompatible"}
    return {
        "action": "attach" if canonical_id else "create",
        "canonical_id": canonical_id,
        "members": members,
        "new_members": new_members,
        "score": min(s for s, _, _, _ in edges),
        "reason": ",".join(sorted({reason for _, reason, _, _ in edges})),
    }


def execute_plan(plan):
    canonical = {"id": plan["canonical_id"]} if plan["canonical_id"] else create_canonical(plan["members"])
    now = datetime.now(timezone.utc).isoformat()
    written = []
    for member in plan["new_members"]:
        payload = {
            "canonical_product_id": canonical["id"],
            "product_id": member["product_id"],
            "match_score": round(plan["score"], 2),
            "match_reason": plan["reason"],
            "status": "approved",
            "updated_at": now,
        }
        sb("POST", "product_matches", body=payload, prefer="return=minimal")
        written.append(payload)
    return written


def apply_group(best_score, indexes, edges, rows, existing_rows=None):
    if existing_rows is None:
        existing_rows = sb_get("product_matches", {"select": "product_id,canonical_product_id,status", "order": "id"})
    plan = plan_group(best_score, indexes, edges, rows, existing_rows)
    if plan["action"] not in {"create", "attach"}:
        print(f"{plan['action'].upper()}: {plan['reason']}")
        return False
    written = execute_plan(plan)
    existing_rows.extend(written)
    print(f"{plan['action'].upper()}: {len(written)} product | score={plan['score']:.1f}")
    return True


def main():
    parser = argparse.ArgumentParser(description="Canonical match writer with read-only/offline planning")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--input", type=Path, help="Offline JSON containing rows and matches; requires --dry-run")
    parser.add_argument("--report", type=Path)
    args = parser.parse_args()
    if args.input and not args.dry_run:
        parser.error("--input requires --dry-run")
    if args.input:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        rows, existing = prepare_rows(data["rows"]), list(data["matches"])
    else:
        rows = load_rows()
        existing = sb_get("product_matches", {"select": "product_id,canonical_product_id,status", "order": "id"})
    # Build at the actual approval threshold. Weak edges must neither inflate a
    # group via its best score nor consume members of otherwise valid groups.
    groups = build_groups(rows, min_score=AUTO_APPROVE_MIN)
    summary = {"mode": "dry-run" if args.dry_run else "write", "rows": len(rows),
               "approval_threshold": AUTO_APPROVE_MIN, "groups": len(groups),
               "new_canonicals": 0, "attached_groups": 0, "new_product_matches": 0,
               "decisions": []}
    for number, (score, indexes, edges) in enumerate(groups):
        plan = plan_group(score, indexes, edges, rows, existing)
        summary["decisions"].append({"action": plan["action"], "reason": plan["reason"],
                                     "product_ids": [rows[i]["product_id"] for i in indexes]})
        if plan["action"] not in {"create", "attach"}:
            continue
        if args.dry_run:
            cid = plan["canonical_id"] or f"dry-run:{number}"
            written = [{"product_id": m["product_id"], "canonical_product_id": cid, "status": "approved"}
                       for m in plan["new_members"]]
        else:
            written = execute_plan(plan)
        existing.extend(written)
        summary["new_canonicals"] += plan["action"] == "create"
        summary["attached_groups"] += plan["action"] == "attach"
        summary["new_product_matches"] += len(written)
    if args.report:
        args.report.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({k: v for k, v in summary.items() if k != "decisions"}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
