import asyncio
import importlib.util
import inspect
import json
import os
import re
import unicodedata
import sys
from pathlib import Path
from urllib.parse import quote, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parent


def load_module(script: Path):
    module_name = f"category_collector_{script.stem}"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Collector yüklenemedi: {script}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def get_proxy_settings():
    server = os.getenv("PROXY_SERVER", "").strip()
    username = os.getenv("PROXY_USERNAME", "").strip()
    password = os.getenv("PROXY_PASSWORD", "").strip()

    if not server:
        return None

    if "://" not in server:
        server = "http://" + server

    return {
        "server": server,
        "username": username,
        "password": password,
    }


def proxy_url_with_auth(settings):
    server = settings["server"]
    username = settings.get("username") or ""
    password = settings.get("password") or ""

    if not username:
        return server

    parsed = urlsplit(server)
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port else ""
    auth = quote(username, safe="")
    if password:
        auth += ":" + quote(password, safe="")

    return urlunsplit((parsed.scheme, f"{auth}@{host}{port}", parsed.path, parsed.query, parsed.fragment))


def proxy_label(settings):
    parsed = urlsplit(settings["server"])
    host = parsed.hostname or "?"
    port = f":{parsed.port}" if parsed.port else ""
    return f"{parsed.scheme}://{host}{port}"


def enable_requests_proxy(settings):
    if not settings:
        return

    import requests

    original_session = requests.Session
    proxy_url = proxy_url_with_auth(settings)

    def proxied_session(*args, **kwargs):
        session = original_session(*args, **kwargs)
        # Yalnızca mağaza HTTP istekleri bu Session üzerinden geçer.
        # Supabase yazımları urllib ile yapıldığı için bu ayardan etkilenmez.
        session.proxies.update({"http": proxy_url, "https": proxy_url})
        session.trust_env = False
        return session

    requests.Session = proxied_session
    print(f"NETWORK  | requests proxy enabled | {proxy_label(settings)}")


def enable_playwright_proxy(module, settings):
    if not settings:
        return

    original_async_playwright = getattr(module, "async_playwright", None)
    if not callable(original_async_playwright):
        return

    playwright_proxy = {"server": settings["server"]}
    if settings.get("username"):
        playwright_proxy["username"] = settings["username"]
    if settings.get("password"):
        playwright_proxy["password"] = settings["password"]

    class BrowserTypeProxy:
        def __init__(self, browser_type):
            self._browser_type = browser_type

        async def launch(self, *args, **kwargs):
            kwargs.setdefault("proxy", playwright_proxy)
            return await self._browser_type.launch(*args, **kwargs)

        def __getattr__(self, name):
            return getattr(self._browser_type, name)

    class PlaywrightProxy:
        def __init__(self, playwright):
            self._playwright = playwright
            self.chromium = BrowserTypeProxy(playwright.chromium)
            self.firefox = BrowserTypeProxy(playwright.firefox)
            self.webkit = BrowserTypeProxy(playwright.webkit)

        def __getattr__(self, name):
            return getattr(self._playwright, name)

    class PlaywrightManagerProxy:
        def __init__(self, manager):
            self._manager = manager

        async def __aenter__(self):
            playwright = await self._manager.__aenter__()
            return PlaywrightProxy(playwright)

        async def __aexit__(self, exc_type, exc, tb):
            return await self._manager.__aexit__(exc_type, exc, tb)

    def proxied_async_playwright():
        return PlaywrightManagerProxy(original_async_playwright())

    module.async_playwright = proxied_async_playwright
    print(f"NETWORK  | Playwright proxy enabled | {proxy_label(settings)}")



def normalize_text(value):
    value = unicodedata.normalize("NFKD", str(value or "").casefold())
    value = value.replace("ı", "i")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def focused_category_relevant(query, raw_title):
    """Narrow title rules for the six categories audited in the Amazon log.

    Model names provide positive evidence, never an exemption for accessories.
    Return None for other categories so their existing behavior stays intact.
    """
    evidence = {
        "oyuncu kulakligi": (
            r"oyuncu kulakligi|gaming head(?:set|phones?)|headset",
            r"(?:oyun|oyuncu|gaming|esports?|espor) (?:\w+ ){0,5}kulakli(?:k|gi)",
            r"razer (?:blackshark|kraken|barracuda)|steelseries arctis|jbl quantum",
        ),
        "akilli bileklik": (
            r"akilli (?:takip )?bilekli(?:k|gi)|smart ?band|mi band|akilli bant",
            r"huawei band \d+|whoop (?:one|peak|life|[45] 0)|fitbit (?:air|charge|inspire|luxe)",
            r"fitness (?:band|bilekligi)|aktivite (?:bilekligi|izleyici)",
        ),
        "dikey supurge": (
            r"(?:dikey|dik|sarjli) (?:elektrik(?:li)? )?supurge(?:si)?",
            r"stick vacuum|cordless (?:stick )?vacuum",
        ),
        "sarjli matkap": (
            r"(?:sarjli|akulu|bataryali|cordless) (?:\w+ ){0,5}(?:matkap|drill)",
            r"sarjli matkap|akulu matkap|drill|vidalama",
            r"bosch (?:gsb|gsr) \d+v?(?: \w+){0,2} li",
        ),
        "arac kamerasi": (
            r"arac kamerasi|arac ici kamera|dash ?cam|oto kamera|araba kamerasi",
        ),
        "tablet": (r"tablet(?:i)?|ipad|galaxy tab|redmi pad",),

        "yazici": (
            r"yazici(?:si)?|printer|laserjet|deskjet",
            r"ecotank|pixma|designjet",
        ),
        "tiras makinesi": (
            r"tiras makinesi|tras makinesi",
            r"sac sakal (?:kesme |kesim )?makinesi|sakal duzeltici",
            r"erkek bakim seti|hibrit tiras|oneblade|tiras kiti",
        ),
        "elektrikli dis fircasi": (
            r"(?:elektrikli|sarjli|sarj edilebilir|sonic) (?:\w+ ){0,3}dis fircasi",
            r"oral-b (?:io|profesyonel temizlik)",
            r"philips sonicare (?!power flosser)",
        ),
        "hava temizleyici": (
            r"hava temizleyici(?:si)?|hava temizleme cihazi",
            r"air purifier|air performer|puricare",
        ),
        "mikrofon": (
            r"mikrofon(?:u)?|microphone|mic\b",
            r"yaka mikrofonu|yayinci mikrofonu|kondenser mikrofon|dinamik mikrofon",
        ),
        "elektrikli scooter": (
            r"elektrikli scooter|electric scooter",
        ),
        "hava nemlendirici": (
            r"hava nemlendirici(?:si)?|ortam nemlendirici|oda nemlendirici",
            r"humidifier|nemlendirme cihazi|buhar makinesi",
        ),
        "bebek arabasi": (
            r"bebek arabasi|travel sistem|travel system|pusetli bebek arabasi|puset",
        ),
        "bebek oto koltugu": (
            r"bebek oto koltugu|cocuk oto koltugu|oto koltugu|arac koltugu|car seat",
        ),
        "bebek telsizi": (
            r"bebek telsizi|bebek monitoru|bebek kamerasi|baby monitor|motorola vm\d+|philips avent scd\d+",
        ),
        "gogus pompasi": (
            r"gogus pompasi|sut pompasi|breast pump",
        ),
        "biberon sterilizatoru": (
            r"biberon sterilizatoru|buharli sterilizator|steam sterilizer|sterilizator",
        ),
        "biberon mama isitici": (
            r"biberon isitici|mama isitici|bottle warmer|philips avent scf35[58]",
        ),
        "epilator": (
            r"epilator|epilasyon cihazi|silk epil",
        ),
        "sac duzlestirici": (
            r"sac duzlestirici|hair straightener|corrale",
        ),
        "sac masasi": (
            r"sac masasi|bukle masasi|curling iron|hair curler",
        ),
        "sac kesme makinesi": (
            r"sac kesme makinesi|hair clipper|sac sakal kesme makinesi",
        ),
        "kitap": (
            r"kitap|roman|ciltli|ciltsiz",
        ),
        "guvenlik ip kamerasi": (
            r"guvenlik kamerasi|ip kamera|wifi kamera|wi fi kamera|akilli kamera|network camera",
        ),
    }
    if query not in evidence:
        return None

    def matches(pattern, text):
        return re.search(r"\b(?:" + pattern + r")\b", text)

    def positive(text):
        return any(matches(pattern, text) for pattern in evidence[query])

    title = normalize_text(raw_title)
    # Explicit product + accessory bundles are judged by their first component.
    # Memory sizes (8+128GB), resolutions (4K+2K) and model suffixes (Plus+)
    # must not be confused with bundle separators.
    bundle_title = re.sub(r"\bblack\s*\+\s*decker\b", "Black Decker", str(raw_title), flags=re.I)
    first = re.split(r"(?<!\d)\+(?!\d)|\s+\+\s+", bundle_title, maxsplit=1)[0]
    first = normalize_text(first)
    accessory_patterns = {
        "oyuncu kulakligi": r"yedek|ped(?:i|leri)?|ear ?pads?|cushions?|kilif(?:i)?|case|stand(?:i)?|tutucu(?:su)?|kablosu|cable|mikrofonu",
        "akilli bileklik": r"yedek|kayis(?:i)?|kordon(?:u)?|strap|wristband|kilif(?:i)?|case|ekran koruyucu(?:su)?|screen protector|sarj (?:cihazi|kablosu)|charger|charging cable",
        "dikey supurge": r"yedek|filtre(?:si|leri)?|filter|firca(?:si)?|baslik|batarya(?:si)?|battery|sarj cihazi|charger|mop|toz (?:haznesi|torbasi)",
        "sarjli matkap": r"yedek|(?:matkap|vidalama) uc(?:u|lari)|uc seti|bit set|drill bits?|batarya(?:si)?|battery|sarj cihazi|charger|mandren(?:i)?",
        "arac kamerasi": r"yedek|hafiza karti|memory card|montaj kiti|hardwire (?:kit|kiti)|kablo(?:su)?|cable|tutacak|tutacagi|bracket|sarj cihazi",
        "tablet": r"kilif(?:i)?|case|cover|ekran koruyucu(?:su)?|screen protector|kalem uc(?:u|lari)|stand(?:i)?|tutucu(?:su)?|yedek|sarj (?:aleti|cihazi|kablosu)|charger",

        "yazici": r"kartus|toner|murekkep(?:i)?|yazici kafasi|printhead|bakim kutusu|waste ink|yedek parca",

        "tiras makinesi": r"yedek bicak|yedek baslik|tiras basligi|kesici baslik|folyo|foil|tarak seti|sarj (?:aleti|cihazi|kablosu)|charger",

        "elektrikli dis fircasi": r"yedek baslik|firca basligi|replacement head|sarj (?:aleti|cihazi|kablosu)|charger",

        "hava temizleyici": r"yedek filtre|replacement filter|filtre seti|filtre kartusu|uyumlu filtre",
        "mikrofon": r"mikrofon standi|masa standi|boom arm|pop filtre(?:si)?|shock mount|mikrofon tutucu(?:su)?|mikrofon kablosu|mikrofon kilifi",
        "elektrikli scooter": r"tekerle(?:k)?|lastik|ic lastik|tubeless|jant|fren balat(?:a|asi)|sarj (?:aleti|cihazi)|charger|yedek parca",
        "hava nemlendirici": r"ucucu yag|esansiyel yag|koku yagi|buhurdanlik yagi|aroma yagi",
        "bebek arabasi": r"yagmur ortusu|puset ortusu|sineklik|bardaklik|tekerlek|adapter|adaptor|organizer|puseti icin|bebek arabasi icin|uyumlu",
        "bebek oto koltugu": r"kilif|koruyucu|minder|adapter|adaptor|isofix baza|isofix base|koltuk arkasi|oto koltugu icin|uyumlu",
        "bebek telsizi": r"tutucu|stand|montaj aparati|duvar aparati|kablo|sarj cihazi|adapter|adaptor|kilif|bebek monitoru icin|uyumlu",
        "gogus pompasi": r"yedek|flans|gogus kalkan|valf|hortum|saklama poseti|gogus pompasi icin|uyumlu",
        "biberon sterilizatoru": r"yedek|masa ustu raf|kurutma rafi|sterilizator icin|uyumlu",
        "biberon mama isitici": r"yedek|termos|saklama cantasi|isitici icin|uyumlu",
        "epilator": r"yedek baslik|epilator basligi|kilif|case|sarj cihazi|adapter|epilator icin|uyumlu",
        "sac duzlestirici": r"kilif|case|isiya dayanikli mat|heat mat|stand|yedek|duzlestirici icin|uyumlu",
        "sac masasi": r"kilif|case|isiya dayanikli mat|heat mat|stand|yedek|masa icin|uyumlu",
        "sac kesme makinesi": r"yedek bicak|yedek baslik|tarak seti|kilif|case|sarj cihazi|adapter|makine icin|uyumlu",
        "kitap": r"kitaplik|kitap destegi|kitap standi|kitap ayraci|e kitap okuyucu|defter|ajanda|kilif|case",
        "guvenlik ip kamerasi": r"montaj aparati|duvar aparati|bracket|hafiza karti|sd kart|kablo|sarj cihazi|adapter|adaptor|kamera icin|uyumlu|dummy kamera|sahte kamera",
    }

    # These phrases describe features of a complete device, not a spare part.
    # Require independent device evidence; numbers/model names on accessories
    # alone are insufficient.
    def accessory(text):
        checked = text
        if positive(text):
            if query == "dikey supurge":
                # Heads, HEPA filtration and a measured dust tank are listed
                # as features on complete vacuums. Require device evidence
                # before the feature plus performance/capacity specifications.
                performance = matches(r"\d+(?: \d+)? ?(?:w|kpa|v|dk|dakika|l)", text)
                if performance and not matches(r"uyumlu|icin|replacement|yedek|seti", text):
                    for feature in (r"(?:hepa|yikanabilir) filtre", r"(?:turbo|akilli(?: led)?|precisionpower|aqua plus) baslik", r"\d+ (?:ml|l) toz haznesi"):
                        for hit in reversed(list(re.finditer(r"\b(?:" + feature + r")\b", checked))):
                            if positive(checked[:hit.start()]):
                                checked = checked[:hit.start()] + checked[hit.end():]
            elif query == "akilli bileklik":
                checked = re.sub(r"\b(?:kayis|kordon) (?:dahil|hediyeli)\b", "", checked)
            elif query == "yazici":
                # "murekkep puskurtmeli" and "murekkep tankli" describe
                # complete printer technology, not standalone ink.
                checked = re.sub(
                    r"\bmurekkep (?:puskurtmeli|tankli)\b",
                    "",
                    checked,
                )
            elif query == "tiras makinesi":
                # OneBlade/model evidence alone can also occur on standalone
                # replacement blades. Only ignore an included spare blade/head
                # when the title explicitly describes a complete grooming device.
                if matches(
                    r"tiras makinesi|tras makinesi|sac sakal (?:kesme |kesim )?makinesi|"
                    r"sakal duzeltici|erkek bakim seti|hibrit tiras makinesi|tiras kiti",
                    text,
                ):
                    checked = re.sub(
                        r"\b(?:\d+ )?yedek (?:bicak|baslik)(?: (?:dahil|hediyeli))?\b",
                        "",
                        checked,
                    )
            elif query == "elektrikli dis fircasi":
                # Complete toothbrush listings commonly state brush heads and
                # the charger supplied in the box.
                checked = re.sub(
                    r"\b(?:\d+ )?(?:yedek )?(?:firca basligi|baslik)(?: (?:dahil|hediyeli))?\b",
                    "",
                    checked,
                )
                checked = re.sub(
                    r"\b(?:hizli manyetik )?sarj cihazi\b",
                    "",
                    checked,
                )
            elif query == "sarjli matkap":
                hit = matches(r"(?:celik|anahtarsiz) mandren", checked)
                if hit and positive(checked[:hit.start()]):
                    checked = checked[:hit.start()] + checked[hit.end():]
            elif query in {"bebek arabasi", "bebek oto koltugu", "bebek telsizi"}:
                checked = re.sub(
                    r"\b(?:isofix baza|adapter|adaptor|sarj cihazi|kablo)(?:su)? (?:dahil|ile birlikte|hediyeli)\b",
                    "",
                    checked,
                )
            elif query in {"epilator", "sac duzlestirici", "sac masasi", "sac kesme makinesi"}:
                checked = re.sub(
                    r"\b(?:sarj cihazi|adapter|adaptor|kilif|case) (?:dahil|ile birlikte|hediyeli)\b",
                    "",
                    checked,
                )
            elif query == "mikrofon":
                # Accessory listings can contain the word "mikrofon", e.g.
                # "pop filtre mikrofon aksesuari". Do not treat those as devices.
                accessory_context = matches(
                    r"mikrofon aksesuari|mikrofon icin|mikrofon uyumlu|"
                    r"microphone accessory|for microphone",
                    text,
                )

                # Strong device evidence means the title independently describes
                # an actual microphone, not merely an accessory for one.
                device_evidence = matches(
                    r"yaka mikrofonu|yayinci mikrofonu|oyuncu mikrofonu|"
                    r"kondenser mikrofon|studyo mikrofon(?:u)?|dinamik mikrofon|usb mikrofon|"
                    r"kablosuz mikrofon|karaoke mikrofonu|podcast mikrofonu|"
                    r"microphone",
                    text,
                )

                if device_evidence and not accessory_context:
                    checked = re.sub(
                        r"\b(?:dahili |entegre )?pop filtre(?:si)?\b",
                        "",
                        checked,
                    )
                    checked = re.sub(
                        r"\b(?:masa )?standi ve pop filtre(?:si)? hediyeli\b",
                        "",
                        checked,
                    )
                    checked = re.sub(
                        r"\b(?:masa )?stand(?:i)?(?: hediyeli)?\b",
                        "",
                        checked,
                    )
                    checked = re.sub(
                        r"\bshock mount\b",
                        "",
                        checked,
                    )
        return matches(accessory_patterns[query], checked)

    if query == "dikey supurge" and matches(r"robot", title):
        return False, "excluded:robot"

    if query == "hava temizleyici" and matches(
        r"nemlendirici|humidifier|difuzor|diffuser|aroma difuzoru",
        title,
    ):
        return False, "excluded:humidifier-diffuser"

    hit = accessory(title)
    if hit:
        explicit_bundle = first != title and positive(first) and not accessory(first)
        # Non-plus tablet bundles need both actual device specifications and
        # an explicit inclusion phrase. A model-compatible case is not a tablet.
        tablet_bundle = (
            query == "tablet"
            and positive(title)
            and matches(r"\d+ ?gb", title)
            and not matches(r"uyumlu|icin|compatible|for", title)
            and (matches(r"hediyeli", title) or matches(r"klavyeli tablet", title)
                 or matches(r"tablet pc", title))
        )
        if not (explicit_bundle or tablet_bundle):
            return False, "accessory-only:" + hit.group(0)
    # Book listings often contain only title, author and publisher. The exact
    # store search supplies category context, while the accessory check above
    # still blocks bookcases, stands, bookmarks and e-reader accessories.
    if query == "kitap":
        return True, None
    if not positive(title):
        return False, "category-term-missing"
    return True, None



def category_relevant(query, product):
    """Reject obvious search leakage before any product is persisted."""
    q = normalize_text(query)
    # Turkish dotless ı survives NFKD/casefold. Canonicalize it so rules can
    # safely use ASCII keys/tokens (maması -> mamasi, şarj -> sarj, etc.).
    q = q.replace("ı", "i")
    title = normalize_text(product.get("title")).replace("ı", "i")
    if not title:
        return False, "empty-title"

    focused = focused_category_relevant(q, product.get("title"))
    if focused is not None:
        return focused

    # Every active category query in categories.json is covered here. Keep the
    # rules title-based and conservative: reject clear accessories/other
    # categories, but do not require brand/model evidence at collector stage.
    rules = {
        "termos": (("termos", "thermos"), ()),
        "matara": (("matara", "suluk", "bottle"), ()),
        "termos bardak": (("termos", "termal", "thermal", "tumbler"), ()),
        "termos kupa": (("termos", "termal", "thermal", "tumbler"), ()),
        "cocuk matarasi": (("matara", "suluk", "bottle"), ()),
        "cocuk matara": (("matara", "suluk", "bottle"), ()),
        "bebek bezi": (("bebek bezi", "cocuk bezi"), ("islak mendil", "havuz bezi")),
        "islak mendil": (("islak mendil",), ("bebek bezi",)),
        "bebek islak mendil": (("islak mendil",), ("bebek bezi",)),
        "biberon": (("biberon", "feeding bottle"), ("biberon fircasi", "biberon temizleme")),
        "emzik": (("emzik", "pacifier"), ("emzik askisi", "emzik zinciri")),
        "mama sandalyesi": (("mama sandalyesi", "high chair"), ()),
        "bebek bakim urunleri": (("bebek",), ()),
        "bebek bakim seti": (("bebek",), ()),
        "fondoten": (("fondoten", "foundation"), ()),
        "maskara": (("maskara", "rimel", "mascara"), ()),
        "rimel": (("maskara", "rimel", "mascara"), ()),
        "ruj": (("ruj", "lipstick"), ()),
        "kapatici": (("kapatici", "concealer"), ()),
        "concealer": (("kapatici", "concealer"), ()),
        "allik": (("allik", "blush"), ()),
        "far paleti": (("far", "eyeshadow"), ()),
        "goz fari paleti": (("far", "eyeshadow"), ()),
        "parfum": (("parfum", "eau de parfum", "eau de toilette", "edp", "edt"), ("parfum sisesi", "parfum atomizer")),
        "cilt bakim": (("cilt", "yuz", "serum", "nemlendirici", "tonik", "cleanser"), ()),
        "cilt bakim seti": (("cilt", "yuz", "serum", "nemlendirici", "tonik", "cleanser"), ()),
        "sampuan": (("sampuan", "shampoo"), ()),
        "sac bakim": (("sac", "shampoo", "sampuan"), ()),
        "gunes kremi": (("gunes", "spf", "sun screen", "sunscreen"), ()),
        "gunes koruyucu": (("gunes", "spf", "sun screen", "sunscreen"), ()),
        "deodorant": (("deodorant", "antiperspirant"), ()),
        "saklama kabi": (("saklama", "storage container"), ()),
        "gida saklama kabi": (("saklama", "storage container"), ()),
        "tava": (("tava", "pan"), ()),
        "tencere": (("tencere", "pot"), ()),
        "tencere seti": (("tencere",), ()),
        "nevresim": (("nevresim", "duvet"), ()),
        "nevresim takimi": (("nevresim",), ()),
        "havlu": (("havlu", "towel"), ()),
        "banyo havlusu": (("havlu", "towel"), ()),
        "camasir deterjani": (("camasir", "laundry"), ("bulasik",)),
        "bulasik deterjani": (("bulasik",), ("camasir",)),
        "bulasik makinesi tableti": (("bulasik", "dishwasher"), ("camasir",)),
        "bulasik tableti": (("bulasik", "dishwasher"), ("camasir",)),
        "ev temizlik urunleri": (("temiz", "cleaner", "deterjan"), ()),
        "yuzey temizleyici": (("yuzey", "surface cleaner"), ()),
        "tuvalet kagidi": (("tuvalet kagidi", "toilet paper"), ("kagit havlu",)),
        "kagit havlu": (("kagit havlu", "paper towel"), ("tuvalet kagidi",)),
        "kahve": (("kahve", "coffee"), ("kahve makinesi", "kahve ogutucu", "french press", "filtre kagidi")),
        "filtre kahve": (("kahve", "coffee"), ("kahve makinesi", "filtre kagidi")),
        "cekirdek kahve": (("kahve", "coffee"), ("kahve makinesi",)),
        "kahve ekipmanlari": (("kahve", "coffee", "french press", "ogutucu"), ()),
        "french press": (("french press",), ()),
        "kahve ogutucu": (("ogutucu", "grinder"), ()),
        "mutfak gerecleri": (("mutfak", "kitchen"), ()),
        "mutfak seti": (("mutfak", "kitchen"), ()),
        "ram bellek": (("ram", "ddr4", "ddr5", "sodimm", "dimm", "bellek"), ("ram sogutucu",)),
        "oyun konsolu": (("playstation", "ps5", "xbox", "nintendo switch", "oyun konsolu"), ("kilif", "stand", "sarj istasyonu", "oyun kolu", "controller")),
        "yazici": (("yazici", "printer", "laserjet", "deskjet", "ecotank"), ("kartus", "toner", "murekkep", "kagit")),
        "microsd hafiza karti": (("microsd", "micro sd", "hafiza karti", "memory card"), ("kart okuyucu", "card reader", "adapter", "adaptor")),
        "usb bellek": (
            ("usb bellek", "flash bellek", "usb flash", "flash drive"),
            ("kart okuyucu", "card reader", "usb hub", "kablo")
        ),
        "bilimsel hesap makinesi": (
            ("hesap makinesi", "calculator", "fx-"),
            ("kilif", "case")
        ),
        "okul cantasi": (
            ("okul cantasi", "sirt cantasi", "backpack"),
            ("anahtarlik", "kalemlik", "yagmur kilifi")
        ),
        "webcam": (
            ("webcam", "web kamera"),
            ("tripod", "kapak", "cover", "kablo")
        ),
        "calisma masasi lambasi": (
            ("masa lambasi", "calisma lambasi", "desk lamp"),
            ("ampul", "yedek")
        ),
        "a4 fotokopi kagidi": (
            ("fotokopi kagidi", "a4 kagit", "copy paper"),
            ("fotograf kagidi", "etiket", "defter")
        ),
        "dijital kamera": (("kamera", "camera", "mirrorless", "dslr"), ("kamera cantasi", "camera bag", "batarya", "pil", "sarj cihazi", "lens kapagi", "tripod")),
        "oyuncu koltugu": (("oyuncu koltugu", "gaming chair"), ("koltuk kilifi", "tekerlek")),
        "ipl epilasyon cihazi": (("ipl", "lumea", "silk expert", "epilasyon"), ("baslik", "kilif")),
        "sac sekillendirici": (("sac sekillendirici", "airwrap", "multistyler", "styler"), ("baslik", "kilif", "cantasi")),
        "hava temizleyici": (("hava temizleyici", "air purifier"), ("filtre", "filter")),
        "buharli utu": (("utu", "iron", "steam iron"), ("utu masasi", "kirec", "temizleyici")),
        "akilli baskul": (("baskul", "tarti", "smart scale"), ()),
        "dis macunu": (("dis macunu", "toothpaste"), ("dis fircasi", "gargara")),
        "cep telefonu": (("telefon", "iphone", "galaxy", "redmi", "poco", "smartphone"), ("kilif", "ekran koruyucu", "sarj aleti")),
        "bluetooth kulaklik": (("kulaklik", "earbuds", "headphone"), ("kilif", "yedek ped")),
        "kulak ustu kulaklik": (("kulaklik", "headphone", "headset"), ("kulaklik stand", "yedek ped")),
        "bluetooth hoparlor": (("hoparlor", "speaker"), ("hoparlor kilifi",)),
        "akilli saat": (("akilli saat", "smartwatch", "watch"), ("saat kayisi", "ekran koruyucu")),
        "laptop": (("laptop", "notebook", "macbook", "dizustu"), ("laptop cantasi", "laptop stand", "kilif")),
        "monitor": (("monitor",), ("monitor kolu", "monitor standi")),
        "ssd": (("ssd", "solid state"), ("ssd kutusu", "ssd enclosure")),
        "klavye": (("klavye", "keyboard"), ("tus seti", "keycap")),
        "mouse": (("mouse", "fare"), ("mouse pad", "mousepad")),
        "oyun kolu": (("oyun kolu", "gamepad", "controller"), ("stand", "kilif")),
        "televizyon": (("televizyon", " television", " tv "), ("tv unitesi", "askı aparati", "aski aparati")),
        "powerbank": (("powerbank", "power bank", "tasinabilir sarj"), ("kilif",)),
        "sarj aleti": (("sarj", "charger", "adapter", "adaptor"), ("kablo", "cable")),
        "sarj adaptoru": (("sarj", "charger", "adapter", "adaptor"), ("kablo", "cable")),
        "modem": (("modem", "router"), ("anten",)),
        "router": (("router", "modem"), ("anten",)),
        "robot supurge": (("robot supurge", "robot vacuum"), ("yedek", "filtre", "firca", "mop bezi", "toz torbasi")),
        "kahve makinesi": (("kahve makinesi", "espresso makinesi", "turk kahve makinesi", "coffee machine"), ("kirec", "temizleyici", "tablet", "filtre kagidi", "kahve kagidi", "filtre yedek", "yedek filtre", "su filtresi", "aquaclean", "bakim seti", "temizlik seti", "kapsul stand", "kahve kapsulu", "kahve cekirdegi", "ogutulmus kahve", "kokteyl makinesi")),
        "airfryer": (("airfryer", "air fryer", "sicak hava fritoz"), ("pisirme kagidi", "silikon hazne", "aksesuar")),
        "blender": (("blender",), ("yedek", "bicak", "hazne")),
        "tost makinesi": (("tost makinesi", "sandvic makinesi", "grill"), ("yedek plaka",)),
        "kettle": (("kettle", "su isitici"), ("yedek",)),
        "sac kurutma makinesi": (("sac kurutma", "hair dryer"), ("difuzor", "baslik")),
        "tiras makinesi": (("tiras makinesi", "shaver", "trimmer"), ("yedek baslik", "yedek bicak")),
        "elektrikli dis fircasi": (("elektrikli dis fircasi", "electric toothbrush"), ("yedek baslik", "firca basi")),
        "oyuncak": (("oyuncak", "toy"), ()),
        "lego": (("lego",), ()),
        "yapi oyuncaklari": (("lego", "yapi oyuncak", "blok"), ()),
        "kedi mamasi": (("kedi mama", "cat food"), ("kopek mama", "kum", "odul")),
        "kopek mamasi": (("kopek mama", "dog food"), ("kedi mama", "odul")),
        "el aletleri": (("alet", "matkap", "tornavida", "testere", "anahtar"), ()),
        "elektrikli el aletleri": (("matkap", "testere", "taslama", "vidalama", "elektrikli"), ()),
        "otomobil aksesuarlari": (("arac", "oto", "otomobil", "car"), ()),
        "arac ici aksesuar": (("arac", "oto", "otomobil", "car"), ()),
        "fitness ekipmanlari": (("fitness", "dambıl", "dambil", "halter", "direnc", "egzersiz", "yoga"), ()),
        "spor ekipmanlari": (("spor", "fitness", "dambıl", "dambil", "halter", "egzersiz", "yoga"), ()),
        # categories.json v4 - new category rules
        "sac bakim seti": (("sac", "sampuan", "shampoo", "bakim"), ()),
        "rondo": (("rondo", "dograyici", "chopper"), ("yedek", "bicak", "hazne")),
        "mikser": (("mikser", "mixer"), ("yedek", "cirpici", "karistirici ucu")),
        "fritoz": (("fritoz", "airfryer", "air fryer", "sicak hava fritoz"), ("pisirme kagidi", "silikon hazne", "aksesuar")),

        "akilli cocuk saati": (
            ("akilli cocuk saati", "cocuk akilli saati", "gps cocuk saati", "kids smartwatch"),
            ("kayis", "kordon", "ekran koruyucu", "kilif", "sarj kablosu")
        ),
        "sanal gerceklik gozlugu": (
            ("sanal gerceklik", "vr gozluk", "vr headset", "virtual reality"),
            ("kilif", "case", "yuz pedi", "yedek ped", "kayis")
        ),
        "vr gozluk": (
            ("vr gozluk", "sanal gerceklik", "vr headset", "virtual reality"),
            ("kilif", "case", "yuz pedi", "yedek ped", "kayis")
        ),
        "soundbar": (
            ("soundbar", "sound bar"),
            ("duvar aparati", "bracket", "kumanda", "remote")
        ),
        "projeksiyon cihazi": (
            ("projeksiyon", "projektor", "projector"),
            ("perde", "aski aparati", "lamba", "ampul", "kumanda")
        ),
        "projektor": (
            ("projektor", "projeksiyon", "projector"),
            ("perde", "aski aparati", "lamba", "ampul", "kumanda")
        ),
        "media player": (
            ("media player", "tv box", "android box", "streaming box"),
            ("kumanda", "remote", "kilif", "adaptoru", "adapter")
        ),
        "android tv box": (
            ("android tv box", "tv box", "media player", "android box"),
            ("kumanda", "remote", "kilif", "adaptoru", "adapter")
        ),
        "mikrofon": (
            ("mikrofon", "microphone"),
            ("mikrofon standi", "pop filtre", "pop filter", "shock mount", "kablo")
        ),

        "elektrikli isitici": (
            ("elektrikli isitici", "fanli isitici", "konvektor", "heater"),
            ("yedek",)
        ),
        "fanli isitici": (
            ("fanli isitici", "elektrikli isitici", "fan heater"),
            ("yedek",)
        ),
        "cay makinesi": (
            ("cay makinesi", "cayci", "tea maker"),
            ("yedek", "demlik", "filtre")
        ),
        "hava nemlendirici": (
            ("hava nemlendirici", "nemlendirici", "humidifier"),
            ("yedek filtre", "replacement filter", "filtre kartusu")
        ),

        "sac boyasi": (
            ("sac boyasi", "hair color", "hair dye"),
            ()
        ),
        "sac serumu": (
            ("sac serumu", "hair serum"),
            ()
        ),
        "sac bakim yagi": (
            ("sac yagi", "sac bakim yagi", "hair oil"),
            ()
        ),

        "elektrikli bisiklet": (
            ("elektrikli bisiklet", "e-bike", "ebike"),
            ("yedek", "batarya", "sarj cihazi", "lastik")
        ),
        "elektrikli scooter": (
            ("elektrikli scooter", "e-scooter", "electric scooter"),
            ("yedek", "lastik", "batarya", "sarj cihazi")
        ),

        "protein tozu": (
            ("protein tozu", "whey protein", "whey"),
            ("shaker", "protein bar")
        ),
        "kreatin": (
            ("kreatin", "creatine"),
            ("shaker",)
        ),
        "protein bar": (
            ("protein bar", "proteinli bar"),
            ("protein tozu", "whey protein")
        ),
        "protein shaker": (
            ("shaker", "protein shaker"),
            ("protein tozu", "whey protein", "kreatin")
        ),
        "shaker": (
            ("shaker", "protein shaker"),
            ("protein tozu", "whey protein", "kreatin")
        ),

        "buzdolabi": (
            ("buzdolabi", "refrigerator", "fridge"),
            ("yedek", "raf", "cekmece", "filtre")
        ),
        "camasir makinesi": (
            ("camasir makinesi", "washing machine"),
            ("yedek", "hortum", "filtre", "kapak")
        ),
        "bulasik makinesi": (
            ("bulasik makinesi", "dishwasher"),
            ("tablet", "deterjan", "parlatici", "tuz", "yedek", "sepet")
        ),
        "kurutma makinesi": (
            ("kurutma makinesi", "kurutucu", "tumble dryer"),
            ("yedek", "filtre", "kurutma topu")
        ),
        "derin dondurucu": (
            ("derin dondurucu", "deep freezer", "freezer"),
            ("yedek", "sepet", "cekmece")
        ),
        "klima": (
            ("klima", "air conditioner"),
            ("klima kumandasi", "kumanda", "klima temizleyici", "montaj seti")
        ),
        "kombi": (
            ("kombi", "combi boiler"),
            ("yedek", "termostat", "baca", "pompa")
        ),
        "ankastre set": (
            ("ankastre set", "ankastre paket"),
            ("yedek",)
        ),
    }

    rule = rules.get(q)
    if not rule:
        # Fail closed for category queries: a newly-added query must get an
        # explicit rule before its search results are allowed into persistence.
        return False, "category-rule-missing"

    required, excluded = rule
    normalized_required = [
        normalize_text(token).replace("ı", "i") for token in required
    ]
    has_positive_evidence = bool(normalized_required) and any(
        token in title for token in normalized_required
    )

    accessory_only_phrases = {
        "bluetooth kulaklik": ("kulaklik kilifi",),
        "laptop": ("laptop cantasi", "notebook cantasi", "laptop standi", "notebook standi", "laptop kilifi", "notebook kilifi"),
        "usb bellek": ("usb bellek kutusu", "usb bellek kilifi"),
        "bilimsel hesap makinesi": ("hesap makinesi kilifi", "calculator case"),
        "webcam": ("webcam tripodu", "webcam tripod", "webcam kapagi", "webcam cover"),
        "calisma masasi lambasi": ("masa lambasi ampulu", "desk lamp bulb"),
        "a4 fotokopi kagidi": ("a4 fotograf kagidi", "a4 etiket"),
        # categories.json v4 accessory protection
        "buzdolabi": (
            "buzdolabi yedek raf",
            "buzdolabi yedek parca",
            "buzdolabi cekmecesi",
            "buzdolabi filtresi",
        ),
        "mikrofon": (
            "mikrofon standi",
            "mikrofon ayagi",
            "mikrofon kablosu",
            "mikrofon tutucu",
            "pop filtre",
            "pop filter",
            "shock mount",
        ),
        "soundbar": (
            "soundbar duvar aparati",
            "soundbar kumandasi",
            "soundbar remote",
        ),
        "projeksiyon cihazi": (
            "projeksiyon perdesi",
            "projeksiyon askisi",
            "projeksiyon aski aparati",
            "projeksiyon lambasi",
            "projeksiyon ampulu",
            "projeksiyon kumandasi",
        ),
        "projektor": (
            "projektor perdesi",
            "projektor aski aparati",
            "projektor lambasi",
            "projektor ampulu",
            "projektor kumandasi",
        ),
        "android tv box": (
            "android tv box kumandasi",
            "android tv box remote",
            "tv box kumandasi",
            "tv box remote",
        ),
        "media player": (
            "media player kumandasi",
            "media player remote",
            "tv box kumandasi",
            "tv box remote",
        ),
        "klima": (
            "klima kumandasi",
            "klima temizleyici",
            "klima montaj seti",
            "klima yedek parca",
        ),
    }
    for phrase in accessory_only_phrases.get(q, ()):
        if phrase in title:
            return False, f"accessory-only:{phrase}"

    for token in excluded:
        normalized_token = normalize_text(token).replace("ı", "i")
        if normalized_token in title and not has_positive_evidence:
            return False, f"excluded:{token}"

    # Some store searches leak completely unrelated categories (for example a
    # cocktail machine in a toaster search). Keep broad categories permissive
    # to avoid false negatives, but require positive evidence for categories
    # whose query terms are stable and descriptive.
    positive_required_queries = {
        "tost makinesi",
        "kahve makinesi",
        "robot supurge",
        "kettle",
        "airfryer",
        "blender",
        "sac kurutma makinesi",
        "tiras makinesi",
        "elektrikli dis fircasi",
        "monitor",
        "ssd",
        "klavye",
        "mouse",
        "televizyon",
        "ram bellek",
        "oyun konsolu",
        "yazici",
        "microsd hafiza karti",
        "usb bellek",
        "bilimsel hesap makinesi",
        "okul cantasi",
        "webcam",
        "calisma masasi lambasi",
        "a4 fotokopi kagidi",
        "dijital kamera",
        "oyuncu koltugu",
        "ipl epilasyon cihazi",
        "sac sekillendirici",
        "hava temizleyici",
        "buharli utu",
        "akilli baskul",
        "dis macunu",
        "sac bakim seti",
        "rondo",
        "mikser",
        "fritoz",
        "akilli cocuk saati",
        "sanal gerceklik gozlugu",
        "vr gozluk",
        "soundbar",
        "projeksiyon cihazi",
        "projektor",
        "media player",
        "android tv box",
        "mikrofon",
        "elektrikli isitici",
        "fanli isitici",
        "cay makinesi",
        "hava nemlendirici",
        "sac boyasi",
        "sac serumu",
        "sac bakim yagi",
        "elektrikli bisiklet",
        "elektrikli scooter",
        "protein tozu",
        "kreatin",
        "protein bar",
        "protein shaker",
        "shaker",
        "buzdolabi",
        "camasir makinesi",
        "bulasik makinesi",
        "kurutma makinesi",
        "derin dondurucu",
        "klima",
        "kombi",
        "ankastre set",
    }
    if q in positive_required_queries:
        if normalized_required and not has_positive_evidence:
            return False, "category-term-missing"

    # Ambiguous/broad categories remain exclusion-driven. This avoids the
    # previous false negatives for LEGO/Hot Wheels and powerbanks named only
    # as "Guc Bankasi".
    return True, None

def filter_category_products(query, products):
    kept = []
    rejected = 0
    for product in products:
        ok, reason = category_relevant(query, product)
        if ok:
            kept.append(product)
        else:
            rejected += 1
            print(f"CATEGORY FILTER | REJECT | {reason} | {str(product.get('title') or '')[:120]}")
    if rejected:
        print(f"CATEGORY FILTER | query={query!r} | kept={len(kept)} | rejected={rejected}")
    return kept

def collector_limit(module):
    raw = os.getenv("PRODUCT_LIMIT", str(getattr(module, "LIMIT", 20)))
    try:
        limit = int(raw)
    except (TypeError, ValueError):
        raise ValueError("PRODUCT_LIMIT pozitif tam sayi olmali") from None
    if limit <= 0:
        raise ValueError("PRODUCT_LIMIT pozitif tam sayi olmali")
    return limit


def run_sync_collector(module, query: str, filter_query: str | None = None) -> int:
    collect = getattr(module, "collect", None)
    save = getattr(module, "save_products_to_supabase", None)
    if not callable(collect) or not callable(save):
        raise RuntimeError("Collector collect/save_products_to_supabase arayüzünü desteklemiyor.")

    limit = collector_limit(module)
    products = collect(query=query, limit=limit)
    products = filter_category_products(filter_query or query, products)

    result = {
        "ok": bool(products),
        "source": module.__name__,
        "query": query,
        "count": len(products),
        "products": products,
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

    if not products:
        print(f"EMPTY | Bu mağazada sonuç bulunamadı: {query}")
        if getattr(module, "EMPTY_IS_FAILURE", False):
            print("COLLECTOR ERROR | Boş sonuç bu mağaza için başarısızlık sayılıyor.")
            return 4
        return 0

    save(products)
    return 0


def run_async_collector(module, query: str, filter_query: str | None = None) -> int:
    # Trendyol main() sorguyu DEFAULT_QUERY değişkeninden çalışma anında okuyor.
    module.DEFAULT_QUERY = query
    module.LIMIT = collector_limit(module)
    main = getattr(module, "main", None)
    if not callable(main):
        raise RuntimeError("Collector main() fonksiyonu bulunamadı.")

    try:
        result = main()
        if inspect.isawaitable(result):
            asyncio.run(result)
        return 0
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        # Arama sayfası açıldı ama ürün çıkmadıysa kategori taramasında boş sonuç kabul edilir.
        if code == 3:
            print(f"EMPTY | Bu mağazada sonuç bulunamadı: {query}")
            return 0
        raise


def main():
    if len(sys.argv) not in {3, 4}:
        print("Kullanım: python run_category_collector.py <collector.py> <query> [filter_query]")
        raise SystemExit(2)

    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = (ROOT / script).resolve()
    query = sys.argv[2].strip()
    filter_query = sys.argv[3].strip() if len(sys.argv) == 4 else query

    if not script.exists():
        print(f"Collector bulunamadı: {script}")
        raise SystemExit(2)
    if not query:
        print("Sorgu boş olamaz.")
        raise SystemExit(2)

    settings = get_proxy_settings()
    module = load_module(script)

    # requests tabanlı collector'larda yalnızca requests.Session üzerinden çıkan
    # mağaza isteklerine ortak proxy uygulanır. Supabase istekleri proxylenmez.
    if callable(getattr(module, "collect", None)):
        enable_requests_proxy(settings)
        raise SystemExit(run_sync_collector(module, query, filter_query))

    # Playwright tabanlı collector'larda browser launch seviyesinde aynı proxy uygulanır.
    # Inject the same pre-persistence category gate used by sync collectors.
    module.CATEGORY_FILTER = lambda _query, products: filter_category_products(filter_query, products)
    enable_playwright_proxy(module, settings)
    raise SystemExit(run_async_collector(module, query, filter_query))


if __name__ == "__main__":
    main()
