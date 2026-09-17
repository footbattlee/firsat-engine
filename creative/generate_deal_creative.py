import argparse
import io
import json
import os
import textwrap
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
OUT_DIR = Path(os.getenv("CREATIVE_OUTPUT_DIR", "creative_output"))
FORMATS = {
    "instagram": (1080, 1350),
    "story": (1080, 1920),
    "site": (1200, 675),
}
W, H = FORMATS["instagram"]

NAVY = (8, 24, 58)
NAVY_2 = (18, 31, 82)
ORANGE = (249, 115, 22)
WHITE = (248, 250, 252)
MUTED = (183, 194, 218)
CARD = (16, 34, 75)


def api_headers():
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanimli degil")
    return {
        "apikey": SUPABASE_SERVICE_ROLE_KEY,
        "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}",
    }


def sb_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urlencode(params, safe="(),.*:-+")
    with urlopen(Request(url, headers=api_headers()), timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_candidate(candidate_id=None):
    params = {
        "select": "id,canonical_product_id,cheapest_offer_id,cheapest_merchant_id,cheapest_price,competitor_price,gap_percent,verified,history_status",
        "status": "eq.candidate",
        "order": "gap_percent.desc",
        "limit": "1",
    }
    if candidate_id:
        params["id"] = f"eq.{candidate_id}"
    rows = sb_get("deal_candidates", params)
    if not rows:
        raise RuntimeError("Uygun deal_candidate bulunamadi")
    dc = rows[0]

    product = sb_get("canonical_products", {"select": "id,brand,title", "id": f"eq.{dc['canonical_product_id']}", "limit": "1"})[0]
    offer = sb_get("offers", {"select": "id,image_url,product_url", "id": f"eq.{dc['cheapest_offer_id']}", "limit": "1"})[0]
    merchant = sb_get("merchants", {"select": "id,name", "id": f"eq.{dc['cheapest_merchant_id']}", "limit": "1"})[0]
    return {**dc, **product, **offer, "merchant": merchant["name"]}


def font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ]
    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def download_image(url):
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=45) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGBA")


def money(value):
    n = float(value)
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",00"):
        s = s[:-3]
    return s + " TL"


def fit_title(draw, title, max_width=920, max_lines=3):
    f = font(50, True)
    words = title.split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=f)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    lines = lines[:max_lines]
    if len(lines) == max_lines and " ".join(lines) != title:
        lines[-1] = textwrap.shorten(lines[-1], width=max(10, len(lines[-1]) - 3), placeholder="...")
    return lines, f


def render(data, output_path):
    canvas = Image.new("RGB", (W, H), NAVY)
    draw = ImageDraw.Draw(canvas)
    # deterministic vertical gradient
    for y in range(H):
        t = y / H
        color = tuple(int(NAVY[i] * (1 - t) + NAVY_2[i] * t) for i in range(3))
        draw.line((0, y, W, y), fill=color)

    draw.rounded_rectangle((55, 45, 1025, 125), 30, fill=CARD)
    draw.text((85, 66), "FIYATZADE", font=font(38, True), fill=WHITE)
    draw.text((330, 76), "Fiyatı biz takip ederiz.", font=font(25), fill=MUTED)

    brand = (data.get("brand") or "FIRSAT").upper()
    draw.text((70, 165), brand, font=font(32, True), fill=ORANGE)
    lines, title_font = fit_title(draw, data["title"])
    y = 210
    for line in lines:
        draw.text((70, y), line, font=title_font, fill=WHITE)
        y += 58

    product = download_image(data["image_url"])
    product = ImageOps.contain(product, (470, 560))
    product_bg = Image.new("RGBA", (510, 600), (255, 255, 255, 255))
    px = (510 - product.width) // 2
    py = (600 - product.height) // 2
    product_bg.alpha_composite(product, (px, py))
    canvas.paste(product_bg.convert("RGB"), (55, 405))

    draw.rounded_rectangle((595, 405, 1025, 1005), 32, fill=CARD)
    draw.text((635, 450), "RAKİP FİYAT", font=font(27, True), fill=MUTED)
    old = money(data["competitor_price"])
    draw.text((635, 495), old, font=font(43, True), fill=WHITE)
    old_box = draw.textbbox((635, 495), old, font=font(43, True))
    draw.line((old_box[0], (old_box[1]+old_box[3])//2, old_box[2], (old_box[1]+old_box[3])//2), fill=ORANGE, width=6)

    draw.text((635, 590), "FIRSAT FİYATI", font=font(27, True), fill=MUTED)
    draw.text((635, 635), money(data["cheapest_price"]), font=font(55, True), fill=WHITE)

    gap = float(data["gap_percent"])
    draw.rounded_rectangle((625, 740, 995, 865), 28, fill=ORANGE)
    draw.text((665, 758), f"%{gap:.2f}".replace(".", ","), font=font(55, True), fill=WHITE)
    draw.text((665, 818), "DAHA UCUZ", font=font(25, True), fill=WHITE)

    draw.text((635, 915), data["merchant"], font=font(34, True), fill=WHITE)
    draw.text((70, 1060), "FIRSATI YAKALA", font=font(38, True), fill=ORANGE)
    draw.text((70, 1110), "Fiyatlar değişebilir. Satın alma mağazada tamamlanır.", font=font(24), fill=MUTED)

    if not data.get("verified"):
        draw.rounded_rectangle((70, 1175, 520, 1235), 20, outline=(104, 123, 166), width=2)
        draw.text((92, 1190), "Geçmiş fiyat doğrulaması bekleniyor", font=font(20), fill=MUTED)

    draw.text((70, 1280), "fiyatzade", font=font(27, True), fill=WHITE)
    draw.text((790, 1285), "#işbirliği  #reklam", font=font(20), fill=MUTED)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG", optimize=True)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Fiyatzade deal creative generator")
    parser.add_argument("--candidate-id")
    parser.add_argument("--output")
    parser.add_argument("--format", choices=FORMATS.keys(), default="instagram")
    args = parser.parse_args()

    data = load_candidate(args.candidate_id)
    width, height = FORMATS[args.format]
    output = Path(args.output) if args.output else OUT_DIR / f"deal_{data['id']}_{args.format}_{width}x{height}.png"
    render(data, output)
    print(f"CREATIVE OK | {output}")
    print(f"{data['title']} | {money(data['cheapest_price'])} | %{float(data['gap_percent']):.2f} | {data['merchant']}")


if __name__ == "__main__":
    main()
