"""Print click totals by day, channel, merchant and deal."""
import argparse
import json
import os
from datetime import date, timedelta
from urllib.parse import urlencode
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
        f"{SUPABASE_URL}/rest/v1/rpc/get_click_report",
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
    rows = load_rows(args.days)
    total = sum(int(row.get("clicks") or 0) for row in rows)
    print(f"CLICK REPORT | days={args.days} | unique_human_clicks={total}")
    for row in rows:
        print(
            f"{int(row.get('clicks') or 0):>4} | "
            f"{row['channel']:<9} | {row['merchant']:<14} | {row['title']}"
        )


if __name__ == "__main__":
    main()
