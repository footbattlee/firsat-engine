import requests

TARGETS = {
    "Trendyol": "https://www.trendyol.com/",
    "Hepsiburada": "https://www.hepsiburada.com/",
    "n11": "https://www.n11.com/",
    "MediaMarkt": "https://www.mediamarkt.com.tr/",
    "Vatan": "https://www.vatanbilgisayar.com/",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/152.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "tr-TR,tr;q=0.9,en;q=0.8",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}


def probe(name: str, url: str) -> None:
    try:
        response = requests.get(url, headers=HEADERS, timeout=20, allow_redirects=True)
        print(f"{name:<14} -> HTTP {response.status_code} | final={response.url} | bytes={len(response.content)}", flush=True)
    except requests.RequestException as exc:
        print(f"{name:<14} -> ERROR | {exc}", flush=True)


def main() -> None:
    print("=== RENDER NETWORK PROBE ===", flush=True)
    for name, url in TARGETS.items():
        probe(name, url)
    print("=== PROBE FINISHED ===", flush=True)


if __name__ == "__main__":
    main()
