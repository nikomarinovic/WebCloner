"""
core/crawler.py
---------------
Crawls an entire website by following internal links breadth-first.

Rules:
  - Only follows links on the same domain (no external sites)
  - Respects an optional max_pages cap
  - Skips binary files, feeds, sitemaps, mailto/tel links
  - Returns an ordered list of (url, html, final_url) tuples
"""

import re
import time
from collections import deque
from urllib.parse import urljoin, urlparse, urldefrag

from bs4 import BeautifulSoup
from core.session import make_session, UA
from utils.logger import setup_logger

log = setup_logger("crawler")

# URL patterns to skip — not useful pages to clone
_SKIP_EXT = re.compile(
    r'\.(pdf|zip|gz|tar|rar|7z|exe|dmg|pkg|mp4|mp3|avi|mov|wmv|'
    r'jpg|jpeg|png|gif|webp|svg|ico|avif|bmp|woff|woff2|ttf|otf|eot|'
    r'css|js|xml|json|rss|atom)(\?.*)?$',
    re.I
)
_SKIP_SCHEME = re.compile(r'^(mailto|tel|javascript|#)', re.I)


class Crawler:
    """
    Breadth-first internal link crawler.

    Parameters
    ----------
    start_url     : the URL to begin crawling from
    max_pages     : stop after this many pages (0 = unlimited)
    delay         : seconds to wait between requests (be polite)
    use_playwright: use headless browser for JS-heavy sites
    timeout       : per-request timeout in seconds
    """

    def __init__(
        self,
        start_url: str,
        max_pages: int = 0,
        delay: float = 0.5,
        use_playwright: bool = False,
        timeout: int = 15,
    ):
        self.start_url      = start_url
        self.max_pages      = max_pages
        self.delay          = delay
        self.use_playwright = use_playwright
        self.timeout        = timeout

        parsed           = urlparse(start_url)
        self.domain      = parsed.netloc          # e.g. "www.example.com"
        self.scheme      = parsed.scheme
        self.base_origin = f"{parsed.scheme}://{parsed.netloc}"

        self._session    = make_session()

        # Choose fetcher
        if use_playwright:
            from core.fetcher import DynamicFetcher
            self._fetcher = DynamicFetcher(timeout=timeout)
        else:
            from core.fetcher import StaticFetcher
            self._fetcher = StaticFetcher(timeout=timeout)

    # ── public ──────────────────────────────────────────────────────────────

    def crawl(self):
        """
        Generator — yields (page_url, html, final_url) for every crawled page.
        Caller decides what to do with each page.
        """
        queue   = deque([self.start_url])
        visited = set()
        count   = 0

        while queue:
            url = queue.popleft()

            # Normalise (strip fragment)
            url, _ = urldefrag(url)
            if url in visited:
                continue
            visited.add(url)

            # Respect max_pages cap
            if self.max_pages and count >= self.max_pages:
                log.info(f"  Reached max_pages={self.max_pages}, stopping crawl.")
                break

            # Fetch the page
            log.info(f"[{count+1}] Crawling: {url}")
            html, final_url = self._fetcher.fetch(url)

            if not html:
                log.warning(f"  Skipped (fetch failed): {url}")
                continue

            count += 1
            yield url, html, final_url

            # Parse outgoing links and enqueue internal ones
            new_links = self._extract_links(html, final_url)
            added = 0
            for link in new_links:
                norm, _ = urldefrag(link)
                if norm not in visited and norm not in queue:
                    queue.append(norm)
                    added += 1
            if added:
                log.info(f"  Found {added} new internal links (queue={len(queue)})")

            # Polite delay between requests
            if self.delay > 0:
                time.sleep(self.delay)

        log.info(f"Crawl complete — {count} pages visited.")

    # ── internals ───────────────────────────────────────────────────────────

    def _extract_links(self, html: str, base_url: str) -> list[str]:
        """Extract all internal links from a page's HTML."""
        soup  = BeautifulSoup(html, "html.parser")
        links = []

        for tag in soup.find_all("a", href=True):
            raw = tag["href"].strip()

            # Skip non-navigable schemes
            if _SKIP_SCHEME.match(raw):
                continue

            # Resolve to absolute URL
            abs_url = urljoin(base_url, raw)
            parsed  = urlparse(abs_url)

            # Only follow same-domain http(s) links
            if parsed.scheme not in ("http", "https"):
                continue
            if parsed.netloc != self.domain:
                continue

            # Skip binary/asset extensions
            if _SKIP_EXT.search(parsed.path):
                continue

            links.append(abs_url)

        return links
