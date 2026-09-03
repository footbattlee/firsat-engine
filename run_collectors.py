import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent

COLLECTORS = [
    ("Trendyol", ROOT / "collectors" / "trendyol.py"),
    ("Hepsiburada", ROOT / "collectors" / "hepsiburada_requests.py"),
    ("n11", ROOT / "collectors" / "n11.py"),
    ("MediaMarkt", ROOT / "collectors" / "mediamarkt.py"),
    ("Vatan", ROOT / "collectors" / "vatan.py"),
]


def run_collector(name: str, script: Path) -> dict:
    started = time.time()
    print("\n" + "=" * 72)
    print(f"START | {name}")
    print(f"FILE  | {script.relative_to(ROOT)}")
    print("=" * 72)

    if not script.exists():
        print(f"ERROR | Dosya bulunamadı: {script}")
        return {"name": name, "ok": False, "seconds": 0.0, "code": -1}

    try:
        proc = subprocess.run(
            [sys.executable, str(script)],
            cwd=str(ROOT),
            env=os.environ.copy(),
            check=False,
        )
        seconds = time.time() - started
        ok = proc.returncode == 0
        print(f"END   | {name} | {'OK' if ok else 'FAIL'} | {seconds:.1f}s | code={proc.returncode}")
        return {"name": name, "ok": ok, "seconds": seconds, "code": proc.returncode}
    except KeyboardInterrupt:
        raise
    except Exception as exc:
        seconds = time.time() - started
        print(f"ERROR | {name}: {exc}")
        return {"name": name, "ok": False, "seconds": seconds, "code": -2}


def main():
    if not os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip():
        print("UYARI: SUPABASE_SERVICE_ROLE_KEY tanımlı değil.")
        print("Collector'lar veri çekebilir ancak Supabase yazma adımı atlanabilir/başarısız olabilir.\n")

    started = time.time()
    results = []

    for name, script in COLLECTORS:
        results.append(run_collector(name, script))

    total = time.time() - started
    ok_count = sum(1 for r in results if r["ok"])

    print("\n" + "=" * 72)
    print("COLLECTOR SUMMARY")
    print("=" * 72)
    for r in results:
        print(f"{'OK  ' if r['ok'] else 'FAIL'} | {r['name']:<12} | {r['seconds']:>6.1f}s | code={r['code']}")
    print("-" * 72)
    print(f"Başarılı: {ok_count}/{len(results)} | Toplam süre: {total:.1f}s")

    if ok_count != len(results):
        raise SystemExit(2)


if __name__ == "__main__":
    main()
