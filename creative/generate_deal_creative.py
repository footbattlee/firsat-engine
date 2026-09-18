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


def load_candidate(candidate_id=None):
    params = {
        "select": "id,canonical_product_id,cheapest_offer_id,cheapest_merchant_id,cheapest_price,competitor_price,gap_percent,verified,history_status",
        "status": "eq.candidate", "order": "gap_percent.desc", "limit": "1",
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
    draw.text((x1+30,y1+142),money(data["cheapest_price"]),font=font(int(45*scale),True),fill=NAVY_DARK)


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

    price_card(draw,(55,510,330,785),data,1.05)
    merchant_badge(draw,(55,805,330,900),data["merchant"])

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
    draw_header(canvas,draw,42,28,(70,70),1030,45,15)
    draw.text((45,108),(data.get("brand") or "FIRSAT").upper(),font=font(21,True),fill=ORANGE)
    tf=font(29,True)
    for i,line in enumerate(wrap_lines(draw,data["title"],tf,520,3)):
        draw.text((45,140+i*35),line,font=tf,fill=NAVY_DARK)

    product_panel(canvas,draw,product,(455,120,875,590))
    discount_badge(draw,(835,110,1148,245),data["gap_percent"],43,19)

    price_card(draw,(45,300,410,535),data,.88)
    merchant_badge(draw,(895,285,1150,365),data["merchant"])
    draw.rounded_rectangle((895,390,1150,465),34,fill=ORANGE)
    draw.text((923,409),"FIRSATI YAKALA →",font=font(18,True),fill=WHITE)
    draw.text((895,495),"Fiyatlar değişebilir.",font=font(14),fill=MUTED)
    draw.text((895,517),"Satın alma mağazada tamamlanır.",font=font(14),fill=MUTED)
    return canvas


RENDERERS={"instagram":render_instagram,"story":render_story,"site":render_site}


def render(data, output_path, format_name="instagram"):
    if format_name not in RENDERERS:
        raise ValueError(f"Bilinmeyen format: {format_name}")
    product=download_image(data["image_url"])
    canvas=RENDERERS[format_name](data,product)
    output_path=Path(output_path); output_path.parent.mkdir(parents=True,exist_ok=True)
    canvas.save(output_path,"PNG",optimize=True)
    return output_path


def main():
    parser=argparse.ArgumentParser(description="Fiyatzade Light Commerce Creative Generator V2")
    parser.add_argument("--candidate-id"); parser.add_argument("--output")
    parser.add_argument("--format",choices=FORMATS.keys(),default="instagram")
    parser.add_argument("--all-formats",action="store_true")
    args=parser.parse_args()
    data=load_candidate(args.candidate_id)
    selected=list(FORMATS) if args.all_formats else [args.format]
    for format_name in selected:
        width,height=FORMATS[format_name]
        output=Path(args.output) if args.output and len(selected)==1 else OUT_DIR/f"deal_{data['id']}_{format_name}_{width}x{height}.png"
        render(data,output,format_name)
        print(f"CREATIVE OK | {format_name} | {output}")
    print(f"{data['title']} | {money(data['cheapest_price'])} | %{float(data['gap_percent']):.2f} | {data['merchant']}")


if __name__=="__main__":
    main()
