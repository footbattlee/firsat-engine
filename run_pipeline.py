import json
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
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
    ("Amazon", ROOT / "collectors" / "amazon.py"),
]

POST_STEPS = [
    # apply_matches imports and runs the same matcher before persisting matches,
    # so running product_matcher.py separately here duplicated the expensive
    # full matching pass on every pipeline execution.
    ("MATCH", "Apply Matches", ROOT / "matching" / "apply_matches.py"),
    ("DEAL", "Deal Engine", ROOT / "deals" / "deal_engine.py"),
]

APPROVAL_SCRIPT = ROOT / "run_telegram_approval.py"


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
                    "stores": list(dict.fromkeys((subcategory.get("stores") or category.get("stores") or [name for name, _ in COLLECTORS]) + (["Amazon"] if os.getenv("AMAZON_ENABLED", "1").strip().lower() not in {"0", "false", "no"} else []))),
                    "strict_match": subcategory.get("strict_match"),
                }
            )

    only_slug = os.getenv("CATEGORY_SLUG", "").strip()
    only_slugs_raw = os.getenv("CATEGORY_SLUGS", "").strip()

    if only_slug and only_slugs_raw:
        raise RuntimeError("CATEGORY_SLUG ve CATEGORY_SLUGS aynı anda kullanılamaz.")

    if only_slug:
        rows = [r for r in rows if r["subcategory_slug"] == only_slug]

    if only_slugs_raw:
        requested_slugs = [slug.strip() for slug in only_slugs_raw.split(",") if slug.strip()]
        requested_set = set(requested_slugs)
        available_set = {r["subcategory_slug"] for r in rows}
        unknown_slugs = [slug for slug in requested_slugs if slug not in available_set]
        if unknown_slugs:
            raise RuntimeError(
                "CATEGORY_SLUGS içinde bilinmeyen alt kategori var: "
                + ", ".join(unknown_slugs)
            )
        rows = [r for r in rows if r["subcategory_slug"] in requested_set]

    category_limit_raw = os.getenv("CATEGORY_LIMIT", "").strip()
    if category_limit_raw:
        try:
            category_limit = max(1, int(category_limit_raw))
            rows = rows[:category_limit]
        except ValueError:
            raise RuntimeError("CATEGORY_LIMIT tam sayı olmalı.")

    store_filter_raw = os.getenv("STORE_FILTER", "").strip()
    if store_filter_raw:
        requested_stores = [store.strip() for store in store_filter_raw.split(",") if store.strip()]
        known_stores = {name for name, _ in COLLECTORS}
        unknown_stores = [store for store in requested_stores if store not in known_stores]
        if unknown_stores:
            raise RuntimeError(
                "STORE_FILTER içinde bilinmeyen mağaza var: "
                + ", ".join(unknown_stores)
            )

        requested_store_set = set(requested_stores)
        for row in rows:
            row["stores"] = [
                store for store in row["stores"] if store in requested_store_set
            ]

        rows = [row for row in rows if row["stores"]]

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
    selected_stores = sorted({store for category in categories for store in category["stores"]})
    print(f"Mağaza: {len(selected_stores)} | {', '.join(selected_stores)}")
    total_collector_runs = sum(len(category["stores"]) for category in categories)
    print(f"Toplam collector çalışması: {total_collector_runs}")
    print("Akış: Tüm kategoriler/mağazalar -> Product Matcher -> Apply Matches -> Deal Engine")
    print("Her alt kategori için categories.json içindeki ilk sorgu ana sorgu olarak kullanılır.")
    print("Collector hataları loglanır; diğer mağaza/kategoriler çalışmaya devam eder.")
    print("Sadece Matcher / Apply Matches / Deal Engine gibi kritik analiz adımları hata verirse pipeline durur.")

    started = time.time()
    results = []

    # Scope post-processing to offers refreshed by this pipeline run. This keeps
    # filtered benchmarks from matching/evaluating stale categories already in Supabase.
    os.environ["PIPELINE_STARTED_AT"] = __import__("datetime").datetime.now(
        __import__("datetime").timezone.utc
    ).isoformat()

    collector_jobs = []
    for category in categories:
        enabled_stores = set(category["stores"])
        for collector_name, collector_script in COLLECTORS:
            if collector_name in enabled_stores:
                collector_jobs.append((collector_name, collector_script, category))

    # Collector processes are independent. Run a small, configurable pool
    # instead of serializing hundreds of network-bound searches. Keep the
    # default conservative to reduce 403/503 pressure on store sites.
    try:
        collector_workers = max(1, int(os.getenv("COLLECTOR_WORKERS", "3")))
    except ValueError:
        raise RuntimeError("COLLECTOR_WORKERS tam sayı olmalı.")

    print(f"Collector paralellik: {collector_workers} worker")

    with ThreadPoolExecutor(max_workers=collector_workers) as executor:
        future_jobs = {
            executor.submit(run_collector, name, script, category): (name, category)
            for name, script, category in collector_jobs
        }
        try:
            for future in as_completed(future_jobs):
                collector_name, category = future_jobs[future]
                try:
                    result = future.result()
                except Exception as exc:
                    result = {
                        "stage": "COLLECT",
                        "name": collector_name,
                        "ok": False,
                        "seconds": 0.0,
                        "code": -2,
                        "category": category,
                    }
                    print(f"ERROR    | {collector_name}: {exc}")
                results.append(result)
                if not result["ok"]:
                    print(
                        f"UYARI    | {collector_name} başarısız oldu; "
                        "pipeline diğer collector'larla devam ediyor."
                    )
        except KeyboardInterrupt:
            for future in future_jobs:
                future.cancel()
            raise

    # Eşleştirme ve fırsat hesapları tüm ulaşılabilen mağaza/kategori verileri toplandıktan sonra bir kez çalışır.
    for stage, name, script in POST_STEPS:
        result = run_post_step(stage, name, script)
        results.append(result)

        if not result["ok"]:
            total = time.time() - started
            print_summary(results, total, len(categories), stopped=True)
            raise SystemExit(2)

    # Deal Engine başarılı olduktan sonra yeni candidate fırsatları admin
    # Telegram grubuna otomatik ve idempotent olarak gönder.
    approval_result = run_process(
        "APPROVAL",
        "Telegram Admin Dispatch",
        [sys.executable, str(APPROVAL_SCRIPT), "--dispatch-pending", "--limit", "100"],
    )
    results.append(approval_result)
    if not approval_result["ok"]:
        print("UYARI    | Telegram admin dispatch başarısız oldu; fırsat verileri korunuyor.")

    total = time.time() - started
    print_summary(results, total, len(categories), stopped=False)


if __name__ == "__main__":
    main()
