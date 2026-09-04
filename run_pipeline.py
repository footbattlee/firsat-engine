import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CATEGORIES_FILE = ROOT / "categories.json"
CATEGORY_RUNNER = ROOT / "run_category_collector.py"

COLLECTORS = [
    ("Trendyol", ROOT / "collectors" / "trendyol.py"),
    ("Hepsiburada", ROOT / "collectors" / "hepsiburada_requests.py"),
    ("n11", ROOT / "collectors" / "n11.py"),
    ("MediaMarkt", ROOT / "collectors" / "mediamarkt.py"),
    ("Vatan", ROOT / "collectors" / "vatan.py"),
]

POST_STEPS = [
    ("MATCH", "Product Matcher", ROOT / "matching" / "product_matcher.py"),
    ("MATCH", "Apply Matches", ROOT / "matching" / "apply_matches.py"),
    ("DEAL", "Deal Engine", ROOT / "deals" / "deal_engine.py"),
]


def load_active_subcategories():
    if not CATEGORIES_FILE.exists():
        raise RuntimeError(f"Kategori dosyası bulunamadı: {CATEGORIES_FILE}")

    data = json.loads(CATEGORIES_FILE.read_text(encoding="utf-8"))
    rows = []

    for category in data.get("categories", []):
        if not category.get("active", True):
            continue

        for subcategory in category.get("subcategories", []):
            if not subcategory.get("active", True):
                continue

            queries = [str(q).strip() for q in subcategory.get("queries", []) if str(q).strip()]
            if not queries:
                continue

            rows.append(
                {
                    "category": category.get("name", ""),
                    "category_slug": category.get("slug", ""),
                    "subcategory": subcategory.get("name", ""),
                    "subcategory_slug": subcategory.get("slug", ""),
                    # MVP: Her alt kategori tek kez taranır. İlk sorgu ana sorgudur.
                    # categories.json içindeki diğer sorgular ileride fallback/genişletme için saklanır.
                    "query": queries[0],
                    "aliases": queries[1:],
                }
            )

    only_slug = os.getenv("CATEGORY_SLUG", "").strip()
    if only_slug:
        rows = [r for r in rows if r["subcategory_slug"] == only_slug]

    category_limit_raw = os.getenv("CATEGORY_LIMIT", "").strip()
    if category_limit_raw:
        try:
            category_limit = max(1, int(category_limit_raw))
            rows = rows[:category_limit]
        except ValueError:
            raise RuntimeError("CATEGORY_LIMIT tam sayı olmalı.")

    return rows


def run_process(stage: str, name: str, command, *, category=None) -> dict:
    started = time.time()
    print("\n" + "=" * 96)
    print(f"{stage:<8} | START | {name}")
    if category:
        print(
            f"CATEGORY | {category['category']} > {category['subcategory']} "
            f"| query={category['query']!r}"
        )
    print("=" * 96)

    try:
        proc = subprocess.run(
            command,
            cwd=str(ROOT),
            env=os.environ.copy(),
            check=False,
        )
        seconds = time.time() - started
        ok = proc.returncode == 0
        print(
            f"{stage:<8} | END   | {name} | "
            f"{'OK' if ok else 'FAIL'} | {seconds:.1f}s | code={proc.returncode}"
        )
        return {
            "stage": stage,
            "name": name,
            "ok": ok,
            "seconds": seconds,
            "code": proc.returncode,
            "category": category,
        }
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        seconds = time.time() - started
        print(f"ERROR    | {name}: {exc}")
        return {
            "stage": stage,
            "name": name,
            "ok": False,
            "seconds": seconds,
            "code": -2,
            "category": category,
        }


def run_collector(name: str, script: Path, category: dict) -> dict:
    if not script.exists():
        return {
            "stage": "COLLECT",
            "name": name,
            "ok": False,
            "seconds": 0.0,
            "code": -1,
            "category": category,
        }

    command = [
        sys.executable,
        str(CATEGORY_RUNNER),
        str(script.relative_to(ROOT)),
        category["query"],
    ]
    return run_process("COLLECT", name, command, category=category)


def run_post_step(stage: str, name: str, script: Path) -> dict:
    if not script.exists():
        return {
            "stage": stage,
            "name": name,
            "ok": False,
            "seconds": 0.0,
            "code": -1,
            "category": None,
        }
    return run_process(stage, name, [sys.executable, str(script)])


def print_summary(results, total_seconds, category_count, stopped=False):
    print("\n" + "=" * 96)
    print("FIRSAT ENGINE - MULTI CATEGORY PIPELINE SUMMARY")
    print("=" * 96)

    collect_results = [r for r in results if r["stage"] == "COLLECT"]
    post_results = [r for r in results if r["stage"] != "COLLECT"]

    collect_ok = sum(1 for r in collect_results if r["ok"])
    print(
        f"Alt kategori: {category_count} | Mağaza: {len(COLLECTORS)} | "
        f"Collector başarılı: {collect_ok}/{len(collect_results)}"
    )

    failed = [r for r in collect_results if not r["ok"]]
    if failed:
        print("\nBaşarısız collector adımları:")
        for r in failed:
            c = r.get("category") or {}
            print(
                f"FAIL | {c.get('category')} > {c.get('subcategory')} | "
                f"{r['name']} | code={r['code']}"
            )

    if post_results:
        print("\nAnaliz adımları:")
        for r in post_results:
            print(
                f"{'OK  ' if r['ok'] else 'FAIL'} | {r['stage']:<7} | "
                f"{r['name']:<20} | {r['seconds']:>7.1f}s | code={r['code']}"
            )

    print("-" * 96)
    ok_count = sum(1 for r in results if r["ok"])
    print(f"Başarılı adım: {ok_count}/{len(results)} | Toplam süre: {total_seconds:.1f}s")
    if stopped:
        print("Pipeline kritik analiz hatası nedeniyle durduruldu.")
    else:
        if failed:
            print("PIPELINE TAMAMLANDI (bazı collector adımları başarısız oldu).")
        else:
            print("PIPELINE TAMAMLANDI.")
    print("=" * 96)


def main():
    if not os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip():
        print("HATA: SUPABASE_SERVICE_ROLE_KEY tanımlı değil.")
        print("Pipeline Supabase okuma/yazma adımlarını güvenilir biçimde çalıştıramaz.")
        raise SystemExit(2)

    if not CATEGORY_RUNNER.exists():
        print(f"HATA: {CATEGORY_RUNNER.name} bulunamadı.")
        raise SystemExit(2)

    try:
        categories = load_active_subcategories()
    except Exception as exc:
        print(f"HATA: categories.json okunamadı: {exc}")
        raise SystemExit(2)

    if not categories:
        print("HATA: Çalıştırılacak aktif alt kategori bulunamadı.")
        raise SystemExit(2)

    print("=" * 96)
    print("FIRSAT ENGINE - MULTI CATEGORY PIPELINE")
    print("=" * 96)
    print(f"Aktif alt kategori: {len(categories)}")
    print(f"Mağaza: {len(COLLECTORS)}")
    print(f"Toplam collector çalışması: {len(categories) * len(COLLECTORS)}")
    print("Akış: Tüm kategoriler/mağazalar -> Product Matcher -> Apply Matches -> Deal Engine")
    print("Her alt kategori için categories.json içindeki ilk sorgu ana sorgu olarak kullanılır.")
    print("Collector hataları loglanır; diğer mağaza/kategoriler çalışmaya devam eder.")
    print("Sadece Matcher / Apply Matches / Deal Engine gibi kritik analiz adımları hata verirse pipeline durur.")

    started = time.time()
    results = []

    for index, category in enumerate(categories, 1):
        print("\n" + "#" * 96)
        print(
            f"ALT KATEGORİ {index}/{len(categories)} | "
            f"{category['category']} > {category['subcategory']} | "
            f"{category['query']}"
        )
        print("#" * 96)

        for collector_name, collector_script in COLLECTORS:
            result = run_collector(collector_name, collector_script, category)
            results.append(result)

            if not result["ok"]:
                print(
                    f"UYARI    | {collector_name} başarısız oldu; "
                    "pipeline sonraki collector ile devam ediyor."
                )

    # Eşleştirme ve fırsat hesapları tüm ulaşılabilen mağaza/kategori verileri toplandıktan sonra bir kez çalışır.
    for stage, name, script in POST_STEPS:
        result = run_post_step(stage, name, script)
        results.append(result)

        if not result["ok"]:
            total = time.time() - started
            print_summary(results, total, len(categories), stopped=True)
            raise SystemExit(2)

    total = time.time() - started
    print_summary(results, total, len(categories), stopped=False)


if __name__ == "__main__":
    main()
