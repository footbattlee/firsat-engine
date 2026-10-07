"""Print browser navigation signals and unverified link requests separately."""
import argparse
import json
import os
from urllib.request import Request, urlopen

from dotenv import load_dotenv

load_dotenv()
SUPABASE_URL = os.getenv("SUPABASE_URL", "").rstrip("/")
SERVICE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()


def load_rows(days):
    if not SUPABASE_URL or not SERVICE_KEY:
        raise RuntimeError("SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY eksik")
    payload = json.dumps({
        "p_days": max(1, min(int(days), 90)),
        "p_complete_days": False,
    }).encode()
    req = Request(
        f"{SUPABASE_URL}/rest/v1/rpc/get_click_report_v2",
        data=payload,
        method="POST",
        headers={
            "apikey": SERVICE_KEY,
            "Authorization": f"Bearer {SERVICE_KEY}",
            "Content-Type": "application/json",
        },
    )
    with urlopen(req, timeout=30) as response:
        return json.loads(response.read().decode() or "[]")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--days", type=int, default=7)
    args = parser.parse_args()
    report = load_rows(args.days)
    rows = report["rows"]
    total = sum(int(row.get("clicks") or 0) for row in rows)
    unknown = sum(int(row.get("unverified_clicks") or 0) for row in rows)
    print(f"LINK REPORT | browser_navigation_signals={total} | unverified_requests={unknown}")
    print(f"Period: {report['period_start']} <= time < {report['period_end']}")
    print("Product/channel/day totals, not people or official Amazon Associates clicks.")
    for row in rows:
        print(
            f"{int(row.get('clicks') or 0):>4} navigation | "
            f"{int(row.get('unverified_clicks') or 0):>4} unverified | "
            f"{row['channel']:<9} | {row['merchant']:<14} | {row['title']}"
        )


if __name__ == "__main__":
    main()
