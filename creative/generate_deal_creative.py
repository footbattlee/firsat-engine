import argparse
import io
import json
import os
import re
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from PIL import Image, ImageDraw, ImageFont, ImageOps, ImageFile
from dotenv import load_dotenv

ImageFile.LOAD_TRUNCATED_IMAGES = True

# Load local secrets/config from the project root without committing them.
load_dotenv(Path(__file__).resolve().parents[1] / ".env")

SUPABASE_URL = os.getenv("SUPABASE_URL", "https://cmexmobjpeavlppmffqi.supabase.co").rstrip("/")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
OUT_DIR = Path(os.getenv("CREATIVE_OUTPUT_DIR", "creative_output"))
ASSET_DIR = Path(__file__).resolve().parent / "assets"
LOGO_PATH = Path(os.getenv("FIYATZADE_LOGO", str(ASSET_DIR / "fiyatzade_logo.jpg")))

FORMATS = {"instagram": (1080, 1350), "story": (1080, 1920), "site": (1200, 675)}

NAVY = (13, 53, 103)
NAVY_DARK = (7, 35, 76)
ORANGE = (255, 111, 12)
ORANGE_SOFT = (255, 235, 216)
INK = (20, 55, 96)
MUTED = (91, 112, 139)
BG = (248, 249, 247)
WHITE = (255, 255, 255)
LINE = (225, 231, 238)


def api_headers():
    if not SUPABASE_SERVICE_ROLE_KEY:
        raise RuntimeError("SUPABASE_SERVICE_ROLE_KEY tanimli degil")
    return {"apikey": SUPABASE_SERVICE_ROLE_KEY, "Authorization": f"Bearer {SUPABASE_SERVICE_ROLE_KEY}"}


def sb_get(table, params):
    url = f"{SUPABASE_URL}/rest/v1/{table}?" + urlencode(params, safe="(),.*:-+")
    with urlopen(Request(url, headers=api_headers()), timeout=45) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _one(table, params, label):
    rows = sb_get(table, params)
    if not rows:
        raise RuntimeError(f"{label} bulunamadi")
    return rows[0]


def load_candidates(limit=1, candidate_id=None):
    params = {
        "select": "id,canonical_product_id,cheapest_offer_id,cheapest_merchant_id,cheapest_price,competitor_price,gap_percent,verified,history_status",
        "order": "gap_percent.desc", "limit": str(limit),
    }
    if candidate_id:
        # Explicit IDs are useful for reruns/debugging even if the deal engine
        # changed the candidate status after a previous batch.
        params["id"] = f"eq.{candidate_id}"
        params["limit"] = "1"
    else:
        params["status"] = "eq.candidate"
    rows = sb_get("deal_candidates", params)
    if not rows:
        raise RuntimeError("Uygun deal_candidate bulunamadi")

    candidates = []
    for dc in rows:
        product = _one("canonical_products", {
            "select": "id,brand,title", "id": f"eq.{dc['canonical_product_id']}", "limit": "1"
        }, "canonical_product")
        offer = _one("offers", {
            "select": "id,image_url,product_url", "id": f"eq.{dc['cheapest_offer_id']}", "limit": "1"
        }, "cheapest_offer")
        merchant = _one("merchants", {
            "select": "id,name", "id": f"eq.{dc['cheapest_merchant_id']}", "limit": "1"
        }, "merchant")

        # Keep the deal candidate ID authoritative. product/offer rows also have
        # an "id" field and must not overwrite it, because Telegram callbacks and
        # publication FK records are keyed by deal_candidates.id.
        data = {
            **dc,
            "product_id": product["id"],
            "brand": product.get("brand"),
            "title": product.get("title"),
            "offer_id": offer["id"],
            "image_url": offer.get("image_url"),
            "product_url": offer.get("product_url"),
            "merchant": merchant["name"],
        }
        required = ("title", "image_url", "merchant", "cheapest_price", "competitor_price", "gap_percent")
        missing = [key for key in required if data.get(key) in (None, "")]
        if missing:
            raise RuntimeError(f"Creative verisi eksik ({dc['id']}): " + ", ".join(missing))
        candidates.append(data)
    return candidates


def load_candidate(candidate_id=None):
    return load_candidates(1, candidate_id)[0]


def _norm(value):
    text = str(value or "").casefold()
    return re.sub(r"[^a-z0-9çğıöşü]+", " ", text).strip()


def validate_candidate(data, gap_tolerance=0.35):
    """Validation Gate V1: product match, price math, image, merchant and product URL."""
    errors = []
    warnings = []

    title = _norm(data.get("title"))
    brand = _norm(data.get("brand"))
    if not title:
        errors.append("PRODUCT_TITLE_MISSING")
    elif brand and brand not in title:
        warnings.append(f"PRODUCT_MATCH_SUSPECT: brand={data.get('brand')}")

    try:
        cheapest = float(data.get("cheapest_price"))
        competitor = float(data.get("competitor_price"))
        stored_gap = float(data.get("gap_percent"))
        if cheapest <= 0 or competitor <= 0 or cheapest >= competitor:
            errors.append("PRICE_ORDER_INVALID")
        else:
            calculated_gap = ((competitor - cheapest) / competitor) * 100
            if abs(calculated_gap - stored_gap) > gap_tolerance:
                errors.append(
                    f"PRICE_GAP_MISMATCH: stored={stored_gap:.2f} calculated={calculated_gap:.2f}"
                )
    except (TypeError, ValueError):
        errors.append("PRICE_DATA_INVALID")

    merchant = str(data.get("merchant") or "").strip()
    if not merchant:
        errors.append("MERCHANT_MISSING")

    product_url = str(data.get("product_url") or "").strip()
    if not product_url.startswith(("http://", "https://")):
        errors.append("PRODUCT_URL_INVALID")

    image_url = str(data.get("image_url") or "").strip()
    if not image_url.startswith(("http://", "https://")):
        errors.append("IMAGE_URL_INVALID")
    else:
        try:
            image = download_image(image_url)
            image.verify()
        except Exception as exc:
            errors.append(f"IMAGE_UNAVAILABLE: {type(exc).__name__}")

    return {"ok": not errors, "errors": errors, "warnings": warnings}


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
    with urlopen(Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=45) as resp:
        return Image.open(io.BytesIO(resp.read())).convert("RGBA")


def money(value):
    s = f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    if s.endswith(",00"):
        s = s[:-3]
    return s + " TL"


def wrap_lines(draw, text, fnt, max_width, max_lines=3):
    words, lines, current = str(text).split(), [], ""
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


def light_canvas(size):
    canvas = Image.new("RGB", size, BG)
    draw = ImageDraw.Draw(canvas)
    w, h = size
    draw.ellipse((int(w*.42), int(h*.11), int(w*1.03), int(h*.80)), fill=ORANGE_SOFT)
    return canvas, draw


def draw_brand(draw, x, y, scale=1.0):
    # Faithful compact fallback for the supplied square Fiyatzade mark.
    s = scale
    side = int(70*s)
    draw.rounded_rectangle((x, y, x+side, y+side), int(10*s), fill=NAVY_DARK)
    # White tilted price tag.
    tag = [(x+int(18*s),y+int(25*s)),(x+int(42*s),y+int(18*s)),
           (x+int(52*s),y+int(47*s)),(x+int(27*s),y+int(54*s))]
    draw.polygon(tag, fill=WHITE)
    # Orange falling-price arrow inside the tag.
    draw.line((x+int(32*s),y+int(30*s),x+int(38*s),y+int(43*s)),fill=ORANGE,width=max(3,int(5*s)))
    draw.polygon([(x+int(33*s),y+int(42*s)),(x+int(45*s),y+int(39*s)),(x+int(40*s),y+int(50*s))],fill=ORANGE)


def paste_logo_asset(canvas, x, y, max_size):
    candidates = [LOGO_PATH, ASSET_DIR / "fiyatzade_logo.jpg", ASSET_DIR / "fiyatzade_logo.jpeg", ASSET_DIR / "fiyatzade_logo.png"]
    logo_path = next((p for p in candidates if p.exists()), None)
    if logo_path is None:
        return False
    logo = Image.open(logo_path).convert("RGB")
    # User-approved square logo: keep its artwork intact and present it as a compact brand mark.
    logo = ImageOps.fit(logo, (max_size[1], max_size[1]), method=Image.Resampling.LANCZOS)
    mask = Image.new("L", logo.size, 255)
    canvas.paste(logo, (x, y), mask)
    return True


def draw_header(canvas, draw, x, y, logo_size, disclosure_x, disclosure_y, disclosure_size):
    if not paste_logo_asset(canvas, x, y, logo_size):
        draw_brand(draw, x, y, logo_size[1]/70)

    # Keep the supplied square mark intact; render the Fiyatzade wordmark beside it.
    logo_h = logo_size[1]
    word_size = max(18, int(logo_h * 0.43))
    word_x = x + logo_h + max(12, int(logo_h * 0.16))
    word_y = y + max(4, int(logo_h * 0.24))
    draw.text((word_x, word_y), "FİYATZADE", font=font(word_size, True), fill=NAVY_DARK)

    draw.text((disclosure_x, disclosure_y), "#işbirliği  #reklam", font=font(disclosure_size), fill=MUTED)


def merchant_badge(draw, box, merchant):
    x1, y1, x2, y2 = box
    draw.rounded_rectangle(box, 22, fill=WHITE, outline=LINE, width=2)
    name = str(merchant or "").strip()
    key = name.lower().replace("ı", "i")
    if "hepsiburada" in key:
        icon = (x1+22, y1+15, x1+78, y2-15)
        draw.rounded_rectangle(icon, 12, fill=ORANGE)
        draw.text((x1+31, y1+23), "hb", font=font(25, True), fill=WHITE)
        draw.text((x1+96, y1+25), "Hepsiburada", font=font(26, True), fill=NAVY_DARK)
    else:
        draw.text((x1+26, y1+25), name, font=font(26, True), fill=NAVY_DARK)


def product_panel(canvas, draw, product, box):
    x1,y1,x2,y2 = box
    draw.rounded_rectangle(box, 34, fill=WHITE, outline=LINE, width=2)
    w,h=x2-x1,y2-y1
    fitted=ImageOps.contain(product,(int(w*.97),int(h*.97)))
    canvas.paste(fitted,(x1+(w-fitted.width)//2,y1+(h-fitted.height)//2),fitted)


def old_price(draw, x, y, value, size):
    f=font(size,True); label=money(value)
    draw.text((x,y),label,font=f,fill=INK)
    b=draw.textbbox((x,y),label,font=f); cy=(b[1]+b[3])//2
    draw.line((b[0]-3,cy,b[2]+3,cy-4),fill=ORANGE,width=max(4,size//9))


def discount_badge(draw, box, gap, big, small):
    draw.rounded_rectangle(box, 28, fill=ORANGE)
    x1,y1,_,_=box
    draw.text((x1+28,y1+20),f"%{float(gap):.2f}".replace(".",","),font=font(big,True),fill=WHITE)
    draw.text((x1+30,y1+22+big), "DAHA UCUZ",font=font(small,True),fill=WHITE)


def price_card(draw, box, data, scale=1.0):
    x1,y1,x2,y2=box
    draw.rounded_rectangle(box,28,fill=WHITE,outline=LINE,width=2)
    draw.text((x1+30,y1+28),"RAKİP FİYAT",font=font(int(18*scale),True),fill=MUTED)
    old_price(draw,x1+30,y1+55,data["competitor_price"],int(30*scale))
    draw.text((x1+30,y1+112),"FIRSAT FİYATI",font=font(int(18*scale),True),fill=MUTED)
    price_text = money(data["cheapest_price"])
    price_size = int(45*scale)
    max_price_width = (x2-x1) - 60
    while price_size > 24:
        price_font = font(price_size, True)
        if draw.textbbox((0, 0), price_text, font=price_font)[2] <= max_price_width:
            break
        price_size -= 2
    draw.text((x1+30,y1+142),price_text,font=font(price_size,True),fill=NAVY_DARK)


def draw_footer(draw, y, width, size=17):
    draw.line((55,y,width-55,y),fill=LINE,width=2)
    labels=["Güvenli alışveriş","Gerçek ürün görseli","Fırsatları takip et"]
    xs=[70,width//2-105,width-310]
    for x,label in zip(xs,labels):
        draw.ellipse((x,y+22,x+28,y+50),outline=NAVY,width=3)
        draw.text((x+42,y+23),label,font=font(size,True),fill=INK)


def render_instagram(data, product):
    canvas,draw=light_canvas(FORMATS["instagram"])
    draw_header(canvas,draw,55,42,(88,88),805,62,17)
    draw.text((58,155),(data.get("brand") or "FIRSAT").upper(),font=font(28,True),fill=ORANGE)
    tf=font(43,True)
    for i,line in enumerate(wrap_lines(draw,data["title"],tf,920,3)):
        draw.text((58,195+i*50),line,font=tf,fill=NAVY_DARK)

    # V2.2: product is the hero; pricing is a large supporting block.
    product_panel(canvas,draw,product,(355,335,1025,1015))
    discount_badge(draw,(715,285,1020,430),data["gap_percent"],50,21)

    price_card(draw,(55,485,340,800),data,1.18)
    merchant_badge(draw,(55,820,340,915),data["merchant"])

    draw.rounded_rectangle((430,1040,1018,1135),46,fill=ORANGE)
    draw.text((545,1062),"FIRSATI YAKALA  →",font=font(31,True),fill=WHITE)
    draw.text((430,1155),"Fiyatlar değişebilir. Satın alma mağazada tamamlanır.",font=font(17),fill=MUTED)
    draw_footer(draw,1235,1080,15)
    return canvas


def render_story(data, product):
    canvas,draw=light_canvas(FORMATS["story"])
    draw_header(canvas,draw,60,55,(92,92),800,75,17)
    draw.text((60,180),(data.get("brand") or "FIRSAT").upper(),font=font(31,True),fill=ORANGE)
    tf=font(48,True)
    for i,line in enumerate(wrap_lines(draw,data["title"],tf,930,3)):
        draw.text((60,225+i*56),line,font=tf,fill=NAVY_DARK)

    product_panel(canvas,draw,product,(100,405,980,1195))
    discount_badge(draw,(655,360,985,515),data["gap_percent"],52,23)

    # Balanced lower row: equal visual weight for price and merchant/CTA.
    price_card(draw,(70,1240,570,1515),data,1.08)
    merchant_badge(draw,(600,1240,1010,1350),data["merchant"])
    draw.rounded_rectangle((600,1380,1010,1495),48,fill=ORANGE)
    draw.text((638,1408),"FIRSATI YAKALA →",font=font(27,True),fill=WHITE)

    draw.text((70,1555),"Fiyatlar değişebilir. Satın alma mağazada tamamlanır.",font=font(19),fill=MUTED)
    draw_footer(draw,1710,1080,15)
    return canvas


def render_site(data, product):
    canvas,draw=light_canvas(FORMATS["site"])
    draw_header(canvas,draw,42,25,(70,70),1030,42,15)
    draw.text((45,105),(data.get("brand") or "FIRSAT").upper(),font=font(20,True),fill=ORANGE)
    tf=font(27,True)
    for i,line in enumerate(wrap_lines(draw,data["title"],tf,360,3)):
        draw.text((45,136+i*33),line,font=tf,fill=NAVY_DARK)

    # Site follows the same hierarchy as Story but in three responsive columns.
    price_card(draw,(45,285,385,525),data,.92)
    product_panel(canvas,draw,product,(410,125,835,585))
    discount_badge(draw,(790,105,1148,240),data["gap_percent"],43,19)

    merchant_badge(draw,(865,275,1150,360),data["merchant"])
    draw.rounded_rectangle((865,385,1150,465),36,fill=ORANGE)
    draw.text((900,406),"FIRSATI YAKALA →",font=font(19,True),fill=WHITE)
    draw.text((865,495),"Fiyatlar değişebilir.",font=font(14),fill=MUTED)
    draw.text((865,517),"Satın alma mağazada tamamlanır.",font=font(14),fill=MUTED)
    return canvas


RENDERERS={"instagram":render_instagram,"story":render_story,"site":render_site}


def output_path_for(data, format_name):
    width, height = FORMATS[format_name]
    return OUT_DIR / f"deal_{data['id']}_{format_name}_{width}x{height}.png"


def render_candidate_bundle(data):
    outputs = {}
    errors = {}
    for format_name in FORMATS:
        output = output_path_for(data, format_name)
        try:
            render(data, output, format_name)
            outputs[format_name] = output
        except Exception as exc:
            errors[format_name] = str(exc)
    if errors:
        details = " | ".join(f"{name}: {message}" for name, message in errors.items())
        raise RuntimeError(details)
    return outputs


def render(data, output_path, format_name="instagram"):
    if format_name not in RENDERERS:
        raise ValueError(f"Bilinmeyen format: {format_name}")
    product=download_image(data["image_url"])
    canvas=RENDERERS[format_name](data,product)
    output_path=Path(output_path); output_path.parent.mkdir(parents=True,exist_ok=True)
    # Pillow's optimize path can intermittently raise WinError/Errno 22 on
    # Windows for otherwise valid PNGs. Save through an in-memory buffer and
    # atomically replace the destination instead.
    buffer = io.BytesIO()
    canvas.save(buffer, "PNG")
    temp_path = output_path.with_suffix(output_path.suffix + ".tmp")
    with open(temp_path, "wb") as handle:
        handle.write(buffer.getvalue())
    os.replace(temp_path, output_path)
    return output_path


def main():
    parser=argparse.ArgumentParser(description="Fiyatzade Light Commerce Creative Generator V2")
    parser.add_argument("--candidate-id"); parser.add_argument("--output")
    parser.add_argument("--format",choices=FORMATS.keys(),default="instagram")
    parser.add_argument("--all-formats",action="store_true")
    parser.add_argument("--limit",type=int,default=1,help="En yuksek indirimli N gercek candidate'i isle")
    args=parser.parse_args()
    if args.limit < 1:
        parser.error("--limit 1 veya daha buyuk olmali")
    if args.candidate_id and args.limit != 1:
        parser.error("--candidate-id ile --limit birlikte kullanilamaz")
    if args.output and args.limit != 1:
        parser.error("--output toplu uretimde kullanilamaz")

    candidates = load_candidates(args.limit, args.candidate_id)
    ok = 0
    failed = 0
    for index, data in enumerate(candidates, 1):
        try:
            validation = validate_candidate(data)
            if not validation["ok"]:
                failed += 1
                print(f"VALIDATION FAILED | {index}/{len(candidates)} | {data['id']} | " + " | ".join(validation["errors"]))
                continue
            if validation["warnings"]:
                print(f"VALIDATION WARNING | {index}/{len(candidates)} | {data['id']} | " + " | ".join(validation["warnings"]))
            else:
                print(f"VALIDATION OK | {index}/{len(candidates)} | {data['id']}")

            if args.all_formats:
                outputs = render_candidate_bundle(data)
                for format_name, output in outputs.items():
                    print(f"CREATIVE OK | {index}/{len(candidates)} | {format_name} | {output}")
            else:
                output = Path(args.output) if args.output else output_path_for(data, args.format)
                render(data, output, args.format)
                print(f"CREATIVE OK | {index}/{len(candidates)} | {args.format} | {output}")
            print(f"CANDIDATE | {data['id']} | {data['title']} | {money(data['cheapest_price'])} | %{float(data['gap_percent']):.2f} | {data['merchant']}")
            ok += 1
        except Exception as exc:
            failed += 1
            print(f"CREATIVE FAIL | {index}/{len(candidates)} | {data['id']} | {exc}")

    print(f"BATCH DONE | candidates={len(candidates)} | ok={ok} | failed={failed}")
    if failed:
        raise SystemExit(1)


if __name__=="__main__":
    main()
