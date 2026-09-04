import asyncio
import importlib.util
import inspect
import json
import os
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


def run_sync_collector(module, query: str) -> int:
    collect = getattr(module, "collect", None)
    save = getattr(module, "save_products_to_supabase", None)
    if not callable(collect) or not callable(save):
        raise RuntimeError("Collector collect/save_products_to_supabase arayüzünü desteklemiyor.")

    limit = getattr(module, "LIMIT", 20)
    products = collect(query=query, limit=limit)

    result = {
        "ok": bool(products),
        "source": getattr(module, "DEFAULT_QUERY", module.__name__),
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
    enable_playwright_proxy(module, settings)
    raise SystemExit(run_async_collector(module, query))


if __name__ == "__main__":
    main()
