"""
core/session.py
---------------
Shared requests.Session factory with:
  - certifi SSL fix (needed for macOS Homebrew Python)
  - Browser-like headers
  - Retry logic with backoff
"""

import certifi
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from urllib3.util.ssl_ import create_urllib3_context

UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": UA,
    "Accept-Language": "en-US,en;q=0.9",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Encoding": "gzip, deflate, br",
}


class _SSLAdapter(HTTPAdapter):
    """Injects certifi CA bundle — fixes SSL errors on macOS Homebrew Python."""
    def __init__(self, *args, **kwargs):
        self._retries = kwargs.pop("max_retries", None)
        super().__init__(*args, max_retries=self._retries or Retry(3, backoff_factor=0.5), **kwargs)

    def init_poolmanager(self, *args, **kwargs):
        ctx = create_urllib3_context()
        ctx.load_verify_locations(certifi.where())
        kwargs["ssl_context"] = ctx
        super().init_poolmanager(*args, **kwargs)


def make_session() -> requests.Session:
    """Return a Session with SSL fix, browser headers, and auto-retry."""
    retry  = Retry(total=3, backoff_factor=0.5, status_forcelist=[429, 500, 502, 503, 504])
    adapter = _SSLAdapter(max_retries=retry)
    session = requests.Session()
    session.headers.update(HEADERS)
    session.mount("https://", adapter)
    session.mount("http://",  adapter)
    session.verify = certifi.where()
    return session
