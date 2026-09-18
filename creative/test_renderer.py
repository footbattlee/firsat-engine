from pathlib import Path

from PIL import Image

from creative.generate_deal_creative import FORMATS, render


SAMPLE = {
    "id": "stanley-smoke-test",
    "title": "Stanley The Transit Fliptop Mug 0.47L Krem Termos",
    "brand": "STANLEY",
    "cheapest_price": "1959.00",
    "competitor_price": "3599.00",
    "gap_percent": "45.57",
    "merchant": "Hepsiburada",
    "verified": False,
    # Smoke-test URL is only a network/render fixture. Live creatives always use offers.image_url.
    "image_url": "https://productimages.hepsiburada.net/s/777/375/110001089901345.jpg/format:webp",
}


def verify_png(path, expected_size):
    assert path.exists(), f"PNG olusturulamadi: {path}"
    assert path.stat().st_size > 10_000, f"PNG beklenenden kucuk: {path}"
    with Image.open(path) as image:
        assert image.format == "PNG", f"Beklenen PNG, gelen: {image.format}"
        assert image.size == expected_size, f"Yanlis boyut: {image.size}, beklenen: {expected_size}"
        image.verify()
    assert path.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n", "Gecersiz PNG signature"


def main():
    outputs = {
        "instagram": Path("creative_output") / "stanley_smoke_test.png",
        "story": Path("creative_output") / "stanley_smoke_test_story.png",
        "site": Path("creative_output") / "stanley_smoke_test_site.png",
    }

    for format_name, output in outputs.items():
        if output.exists():
            output.unlink()
        render(SAMPLE, output, format_name)
        verify_png(output, FORMATS[format_name])
        print(
            f"SMOKE TEST OK | {format_name} | {output.resolve()} | "
            f"{output.stat().st_size} bytes | PNG {FORMATS[format_name][0]}x{FORMATS[format_name][1]} VERIFIED"
        )


if __name__ == "__main__":
    main()
