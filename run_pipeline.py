import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

PIPELINE = [
    ("COLLECT", "Trendyol", ROOT / "collectors" / "trendyol.py"),
    ("COLLECT", "Hepsiburada", ROOT / "collectors" / "hepsiburada_requests.py"),
    ("COLLECT", "n11", ROOT / "collectors" / "n11.py"),
    ("COLLECT", "MediaMarkt", ROOT / "collectors" / "mediamarkt.py"),
    ("COLLECT", "Vatan", ROOT / "collectors" / "vatan.py"),
    ("MATCH", "Product Matcher", ROOT / "matching" / "product_matcher.py"),
    ("MATCH", "Apply Matches", ROOT / "matching" / "apply_matches.py"),
    ("DEAL", "Deal Engine", ROOT / "deals" / "deal_engine.py"),
]


def run_step(stage: str, name: str, script: Path) -> dict:
    started = time.time()
    print("\n" + "=" * 88)
    print(f"{stage:<7} | START | {name}")
    print(f"FILE    | {script.relative_to(ROOT)}")
    print("=" * 88)

    if not script.exists():
        print(f"ERROR   | Dosya bulunamadı: {script}")
        return {
            "stage": stage,
            "name": name,
            "ok": False,
            "seconds": 0.0,
            "code": -1,
        }

    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            env=os.environ.copy(),
            check=False,
        )
        seconds = time.time() - started
        ok = proc.returncode == 0
        print(
            f"{stage:<7} | END   | {name} | "
            f"{'OK' if ok else 'FAIL'} | {seconds:.1f}s | code={proc.returncode}"
        )
        return {
            "stage": stage,
            "name": name,
            "ok": ok,
            "seconds": seconds,
            "code": proc.returncode,
        }
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        seconds = time.time() - started
        print(f"ERROR   | {name}: {exc}")
        return {
            "stage": stage,
            "name": name,
            "ok": False,
            "seconds": seconds,
            "code": -2,
        }


def print_summary(results, total_seconds, stopped=False):
    print("\n" + "=" * 88)
    print("FIRSAT ENGINE - PIPELINE SUMMARY")
    print("=" * 88)

    for r in results:
        print(
            f"{'OK  ' if r['ok'] else 'FAIL'} | "
            f"{r['stage']:<7} | {r['name']:<20} | "
            f"{r['seconds']:>7.1f}s | code={r['code']}"
        )

    print("-" * 88)
    ok_count = sum(1 for r in results if r["ok"])
    print(f"Başarılı adım: {ok_count}/{len(results)} | Toplam süre: {total_seconds:.1f}s")
    if stopped:
        print("Pipeline hata nedeniyle durduruldu; sonraki adımlar çalıştırılmadı.")
    elif len(results) == len(PIPELINE):
        print("PIPELINE TAMAMLANDI.")
    print("=" * 88)


def main():
    if not os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip():
        print("HATA: SUPABASE_SERVICE_ROLE_KEY tanımlı değil.")
        print("Pipeline Supabase okuma/yazma adımlarını güvenilir biçimde çalıştıramaz.")
        raise SystemExit(2)

    print("=" * 88)
    print("FIRSAT ENGINE - FULL PIPELINE")
    print("=" * 88)
    print("Akış: Collectors -> Product Matcher -> Apply Matches -> Deal Engine")
    print("Bir adım hata verirse, tutarsız veriyle devam etmemek için pipeline durur.")

    started = time.time()
    results = []

    for stage, name, script in PIPELINE:
        result = run_step(stage, name, script)
        results.append(result)

        if not result["ok"]:
            total = time.time() - started
            print_summary(results, total, stopped=True)
            raise SystemExit(2)

    total = time.time() - started
    print_summary(results, total, stopped=False)


if __name__ == "__main__":
    main()
