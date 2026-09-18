import argparse
import io
import json
import os
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

NAVY = (8, 24, 58)
NAVY_2 = (18, 31, 82)
ORANGE = (249, 115, 22)
WHITE = (248, 250, 252)
MUTED = (183, 194, 218)
CARD = (16, 34, 75)
SOFT_WHITE = (255, 255, 255)


def api_headers():
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanimli degil")
    return {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}


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
    if not url:
        raise RuntimeError("offers.image_url bos")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=45) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGBA")


def money(value):
    n = float(value)
    s = f"{n:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",00"):
        s = s[:-3]
    return s + " TL"


def gradient_canvas(size):
    w, h = size
    canvas = Image.new("RGB", size, NAVY)
    draw = ImageDraw.Draw(canvas)
    for y in range(h):
        t = y / max(h - 1, 1)
        color = tuple(int(NAVY[i] * (1 - t) + NAVY_2[i] * t) for i in range(3))
        draw.line((0, y, w, y), fill=color)
    return canvas, draw


def wrap_lines(draw, text, fnt, max_width, max_lines=3):
    words = str(text).split()
    lines, current = [], ""
    for word in words:
        trial = (current + " " + word).strip()
        if draw.textbbox((0, 0), trial, font=fnt)[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word
    if current:
        lines.append(current)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        while lines[-1] and draw.textbbox((0, 0), lines[-1] + "...", font=fnt)[2] > max_width:
            lines[-1] = lines[-1][:-1].rstrip()
        lines[-1] += "..."
    return lines


def draw_logo(draw, x, y, scale=1.0):
    # Asset-free V2 mark: orange price-tag frame + explicit downward arrow.
    s = scale
    box = (x, y, x + int(58*s), y + int(58*s))
    draw.rounded_rectangle(box, radius=int(14*s), outline=ORANGE, width=max(3, int(4*s)))
    cx = x + int(29*s)
    draw.line((cx, y + int(13*s), cx, y + int(37*s)), fill=ORANGE, width=max(3, int(5*s)))
    draw.polygon([
        (cx - int(10*s), y + int(31*s)),
        (cx + int(10*s), y + int(31*s)),
        (cx, y + int(44*s)),
    ], fill=ORANGE)
    draw.text((x + int(76*s), y + int(5*s)), "FİYATZADE", font=font(max(18, int(36*s)), True), fill=WHITE)


def draw_product_card(canvas, product, box):
    x1, y1, x2, y2 = box
    w, h = x2-x1, y2-y1
    panel = Image.new("RGBA", (w, h), SOFT_WHITE + (255,))
    fitted = ImageOps.contain(product, (int(w*0.88), int(h*0.88)))
    panel.alpha_composite(fitted, ((w-fitted.width)//2, (h-fitted.height)//2))
    canvas.paste(panel.convert("RGB"), (x1, y1))


def draw_old_price(draw, x, y, value, size):
    fnt = font(size, True)
    label = money(value)
    draw.text((x, y), label, font=fnt, fill=WHITE)
    b = draw.textbbox((x, y), label, font=fnt)
    cy = (b[1] + b[3]) // 2
    draw.line((b[0], cy, b[2], cy), fill=ORANGE, width=max(4, size//9))


def draw_disclosure(draw, x, y, size=18):
    draw.text((x, y), "#işbirliği  #reklam", font=font(size), fill=MUTED)


def render_instagram(data, product):
    canvas, draw = gradient_canvas(FORMATS["instagram"])
    draw_logo(draw, 62, 48, 1.0)
    draw_disclosure(draw, 790, 65, 18)

    draw.text((64, 150), (data.get("brand") or "FIRSAT").upper(), font=font(30, True), fill=ORANGE)
    title_f = font(45, True)
    for i, line in enumerate(wrap_lines(draw, data["title"], title_f, 940, 3)):
        draw.text((64, 195 + i*52), line, font=title_f, fill=WHITE)

    draw_product_card(canvas, product, (55, 375, 575, 1015))
    draw.rounded_rectangle((610, 375, 1025, 1015), 30, fill=CARD)

    draw.text((646, 425), "RAKİP FİYAT", font=font(23, True), fill=MUTED)
    draw_old_price(draw, 646, 462, data["competitor_price"], 38)
    draw.text((646, 555), "FIRSAT FİYATI", font=font(23, True), fill=MUTED)
    draw.text((646, 595), money(data["cheapest_price"]), font=font(49, True), fill=WHITE)

    gap = float(data["gap_percent"])
    draw.rounded_rectangle((640, 710, 995, 835), 26, fill=ORANGE)
    draw.text((672, 726), f"%{gap:.2f}".replace(".", ","), font=font(48, True), fill=WHITE)
    draw.text((672, 783), "DAHA UCUZ", font=font(22, True), fill=WHITE)
    draw.text((646, 895), str(data["merchant"]), font=font(31, True), fill=WHITE)

    draw.text((64, 1070), "FIRSATI YAKALA", font=font(36, True), fill=ORANGE)
    draw.text((64, 1120), "Fiyatlar değişebilir. Satın alma mağazada tamamlanır.", font=font(22), fill=MUTED)
    if not data.get("verified"):
        draw.text((64, 1170), "Geçmiş fiyat doğrulaması bekleniyor", font=font(19), fill=MUTED)
    return canvas


def render_story(data, product):
    canvas, draw = gradient_canvas(FORMATS["story"])
    draw_logo(draw, 64, 58, 1.05)
    draw_disclosure(draw, 790, 76, 18)

    draw.text((64, 175), (data.get("brand") or "FIRSAT").upper(), font=font(32, True), fill=ORANGE)
    title_f = font(48, True)
    for i, line in enumerate(wrap_lines(draw, data["title"], title_f, 950, 3)):
        draw.text((64, 225 + i*56), line, font=title_f, fill=WHITE)

    draw_product_card(canvas, product, (75, 430, 1005, 1130))
    draw.rounded_rectangle((75, 1170, 1005, 1580), 34, fill=CARD)

    draw.text((120, 1220), "RAKİP FİYAT", font=font(24, True), fill=MUTED)
    draw_old_price(draw, 120, 1260, data["competitor_price"], 38)
    draw.text((120, 1350), "FIRSAT FİYATI", font=font(24, True), fill=MUTED)
    draw.text((120, 1390), money(data["cheapest_price"]), font=font(54, True), fill=WHITE)

    gap = float(data["gap_percent"])
    draw.rounded_rectangle((625, 1230, 950, 1435), 28, fill=ORANGE)
    draw.text((660, 1260), f"%{gap:.2f}".replace(".", ","), font=font(50, True), fill=WHITE)
    draw.text((660, 1325), "DAHA UCUZ", font=font(24, True), fill=WHITE)
    draw.text((625, 1490), str(data["merchant"]), font=font(30, True), fill=WHITE)

    draw.text((75, 1640), "FIRSATI YAKALA", font=font(40, True), fill=ORANGE)
    draw.text((75, 1695), "Fiyatlar değişebilir. Satın alma mağazada tamamlanır.", font=font(22), fill=MUTED)
    if not data.get("verified"):
        draw.text((75, 1745), "Geçmiş fiyat doğrulaması bekleniyor", font=font(19), fill=MUTED)
    return canvas


def render_site(data, product):
    canvas, draw = gradient_canvas(FORMATS["site"])
    draw_logo(draw, 48, 30, 0.82)
    draw_disclosure(draw, 990, 47, 16)

    draw.text((48, 112), (data.get("brand") or "FIRSAT").upper(), font=font(23, True), fill=ORANGE)
    title_f = font(31, True)
    for i, line in enumerate(wrap_lines(draw, data["title"], title_f, 1080, 2)):
        draw.text((48, 145 + i*37), line, font=title_f, fill=WHITE)

    draw_product_card(canvas, product, (48, 230, 510, 610))
    draw.rounded_rectangle((545, 230, 1152, 610), 28, fill=CARD)

    draw.text((585, 270), "RAKİP FİYAT", font=font(19, True), fill=MUTED)
    draw_old_price(draw, 585, 302, data["competitor_price"], 31)
    draw.text((585, 370), "FIRSAT FİYATI", font=font(19, True), fill=MUTED)
    draw.text((585, 403), money(data["cheapest_price"]), font=font(43, True), fill=WHITE)

    gap = float(data["gap_percent"])
    draw.rounded_rectangle((900, 275, 1115, 410), 24, fill=ORANGE)
    draw.text((928, 292), f"%{gap:.2f}".replace(".", ","), font=font(37, True), fill=WHITE)
    draw.text((928, 340), "DAHA UCUZ", font=font(18, True), fill=WHITE)

    draw.text((585, 490), str(data["merchant"]), font=font(27, True), fill=WHITE)
    draw.text((585, 540), "FIRSATI YAKALA", font=font(27, True), fill=ORANGE)
    draw.text((585, 575), "Fiyatlar değişebilir. Satın alma mağazada tamamlanır.", font=font(16), fill=MUTED)
    return canvas


RENDERERS = {
    "instagram": render_instagram,
    "story": render_story,
    "site": render_site,
}


def render(data, output_path, format_name="instagram"):
    if format_name not in RENDERERS:
        raise ValueError(f"Bilinmeyen format: {format_name}")
    product = download_image(data["image_url"])
    canvas = RENDERERS[format_name](data, product)
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    canvas.save(output_path, "PNG", optimize=True)
    return output_path


def main():
    parser = argparse.ArgumentParser(description="Fiyatzade Creative Generator V2")
    parser.add_argument("--candidate-id")
    parser.add_argument("--output")
    parser.add_argument("--format", choices=FORMATS.keys(), default="instagram")
    parser.add_argument("--all-formats", action="store_true")
    args = parser.parse_args()

    data = load_candidate(args.candidate_id)
    selected = list(FORMATS) if args.all_formats else [args.format]
    outputs = []
    for format_name in selected:
        width, height = FORMATS[format_name]
        output = (
            Path(args.output)
            if args.output and len(selected) == 1
            else OUT_DIR / f"deal_{data['id']}_{format_name}_{width}x{height}.png"
        )
        render(data, output, format_name)
        outputs.append(output)
        print(f"CREATIVE OK | {format_name} | {output}")

    print(f"{data['title']} | {money(data['cheapest_price'])} | %{float(data['gap_percent']):.2f} | {data['merchant']}")


if __name__ == "__main__":
    main()
