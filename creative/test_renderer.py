from pathlib import Path

from creative.generate_deal_creative import render


SAMPLE = {
    "id": "stanley-smoke-test",
    "title": "Stanley Classic 1.9 Litre Vakumlu Termos",
    "brand": "STANLEY",
    "cheapest_price": "1959.00",
    "competitor_price": "3599.00",
    "gap_percent": "45.57",
    "merchant": "Hepsiburada",
    "verified": False,
    "image_url": "https://productimages.hepsiburada.net/s/777/375/110001089901345.jpg/format:webp",
}


def main():
    output = Path("creative_output/stanley_smoke_test.png")
    render(SAMPLE, output)
    assert output.exists() and output.stat().st_size > 10_000
    print(f"SMOKE TEST OK | {output} | {output.stat().st_size} bytes")


if __name__ == "__main__":
    main()
