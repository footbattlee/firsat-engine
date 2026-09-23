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
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", value).strip()


def category_relevant(query, product):
    """Reject obvious search leakage before any product is persisted."""
    q = normalize_text(query)
    # Turkish dotless ı survives NFKD/casefold. Canonicalize it so rules can
    # safely use ASCII keys/tokens (maması -> mamasi, şarj -> sarj, etc.).
    q = q.replace("ı", "i")
    title = normalize_text(product.get("title")).replace("ı", "i")
    if not title:
        return False, "empty-title"

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
        "dikey supurge": (("dikey supurge", "sarjli supurge", "stick vacuum"), ("yedek", "filtre", "firca", "batarya")),
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
    }

    rule = rules.get(q)
    if not rule:
        # Fail closed for category queries: a newly-added query must get an
        # explicit rule before its search results are allowed into persistence.
        return False, "category-rule-missing"

    required, excluded = rule
    for token in excluded:
        normalized_token = normalize_text(token).replace("ı", "i")
        if normalized_token in title:
            return False, f"excluded:{token}"

    # Search engines already rank by the requested category. A mandatory
    # positive keyword in every title creates false negatives (e.g. LEGO,
    # Hot Wheels, or 'Güç Bankası' without the literal word powerbank).
    # Keep positive terms as documentation/diagnostics and reject only known
    # leakage/accessory signals here. Matcher/validation remain downstream.
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

def run_sync_collector(module, query: str) -> int:
    collect = getattr(module, "collect", None)
    save = getattr(module, "save_products_to_supabase", None)
    if not callable(collect) or not callable(save):
        raise RuntimeError("Collector collect/save_products_to_supabase arayüzünü desteklemiyor.")

    limit = getattr(module, "LIMIT", 20)
    products = collect(query=query, limit=limit)
    products = filter_category_products(query, products)

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
        return 0

    save(products)
    return 0


def run_async_collector(module, query: str) -> int:
    # Trendyol main() sorguyu DEFAULT_QUERY değişkeninden çalışma anında okuyor.
    module.DEFAULT_QUERY = query
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
    if len(sys.argv) != 3:
        print("Kullanım: python run_category_collector.py <collector.py> <query>")
        raise SystemExit(2)

    script = Path(sys.argv[1])
    if not script.is_absolute():
        script = (ROOT / script).resolve()
    query = sys.argv[2].strip()

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
        raise SystemExit(run_sync_collector(module, query))

    # Playwright tabanlı collector'larda browser launch seviyesinde aynı proxy uygulanır.
    # Inject the same pre-persistence category gate used by sync collectors.
    module.CATEGORY_FILTER = filter_category_products
    enable_playwright_proxy(module, settings)
    raise SystemExit(run_async_collector(module, query))


if __name__ == "__main__":
    main()
