"""
core/fetcher.py
---------------
StaticFetcher  — requests-based, fast, good for server-rendered HTML
DynamicFetcher — Playwright headless Chromium, good for JS SPAs

Both return (html_string, final_url_after_redirects).
"""

import time
import certifi
from core.session import make_session, UA
from utils.logger import setup_logger

log = setup_logger("fetcher")


class StaticFetcher:
    """Fetches raw HTML via requests (no JS execution)."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = make_session()

    def fetch(self, url: str):
        log.info(f"  GET {url}")
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            resp.raise_for_status()
            resp.encoding = resp.apparent_encoding or "utf-8"
            log.info(f"  HTTP {resp.status_code}  ({len(resp.text):,} chars)")
            return resp.text, resp.url
        except Exception as e:
            log.error(f"  Fetch failed: {e}")
            return None, url


class DynamicFetcher:
    """
    Fetches fully JS-rendered HTML via Playwright headless Chromium.
    Requires:  pip install playwright && playwright install chromium
    """

    def __init__(self, timeout: int = 15):
        self.timeout = timeout * 1_000  # Playwright uses ms

    def fetch(self, url: str):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            log.error("Playwright missing. Run: pip install playwright && playwright install chromium")
            return None, url

        log.info(f"  Playwright → {url}")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            ctx     = browser.new_context(user_agent=UA, viewport={"width": 1440, "height": 900})
            page    = ctx.new_page()
            try:
                page.goto(url, timeout=self.timeout, wait_until="networkidle")
                time.sleep(1.5)
                html = page.content()
                log.info(f"  Rendered {len(html):,} chars")
                return html, page.url
            except Exception as e:
                log.error(f"  Playwright error: {e}")
                return None, url
            finally:
                browser.close()
