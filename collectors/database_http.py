"""Keep one database HTTPS connection per collector process; never retry writes."""
import io
from urllib.error import HTTPError
from urllib.parse import urlsplit
from requests.sessions import Session


def install(module):
    original = getattr(module, "urlopen", None)
    base = getattr(module, "SUPABASE_URL", "")
    if not callable(original) or not base:
        return
    session = Session()  # Bypass the store-proxy Session factory.
    session.trust_env = False
    database_host = urlsplit(base).netloc

    def pooled(request, timeout=30, **kwargs):
        address = getattr(request, "full_url", str(request))
        parsed = urlsplit(address)
        if parsed.scheme != "https" or parsed.netloc != database_host or kwargs:
            return original(request, timeout=timeout, **kwargs)
        response = session.request(
            request.get_method(), address, headers=dict(request.header_items()),
            data=request.data, timeout=timeout, allow_redirects=False,
        )
        # Buffer only API JSON, so callers retain urllib's context/read contract.
        stream = io.BytesIO(response.content)
        if not 200 <= response.status_code < 300:
            raise HTTPError(address, response.status_code, "database-http-failed",
                            response.headers, stream)
        return stream

    module.urlopen = pooled
    module._database_session = session
