from pathlib import Path

from PIL import Image

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
    output = Path("creative_output") / "stanley_smoke_test.png"
    if output.exists():
        output.unlink()

    render(SAMPLE, output)
    assert output.exists(), "PNG olusturulamadi"
    assert output.stat().st_size > 10_000, "PNG beklenenden kucuk"

    with Image.open(output) as image:
        assert image.format == "PNG", f"Beklenen PNG, gelen: {image.format}"
        assert image.size == (1080, 1350), f"Yanlis boyut: {image.size}"
        image.verify()

    signature = output.read_bytes()[:8]
    assert signature == b"\x89PNG\r\n\x1a\n", f"Gecersiz PNG signature: {signature!r}"
    print(f"SMOKE TEST OK | {output.resolve()} | {output.stat().st_size} bytes | PNG 1080x1350 VERIFIED")


if __name__ == "__main__":
    main()
