"""
core/css_extractor.py
---------------------
Fetches all external stylesheets linked from a page,
resolves @import chains, and caches them locally.
Returns:
    stylesheet_map : { original_href -> "assets/css/xxx.css" }
    combined_css   : all CSS text joined (used for --inline mode)
"""

import re
import hashlib
from pathlib import Path
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from core.session import make_session
from utils.logger import setup_logger

log = setup_logger("css")

_MAX_DEPTH = 3


class CSSExtractor:
    """
    Shared across pages of the same site — already-fetched sheets are
    served from the in-memory cache without re-downloading.
    """

    def __init__(self, css_dir: Path, timeout: int = 15):
        self.css_dir  = css_dir
        self.timeout  = timeout
        self._session = make_session()
        self._fetched: dict[str, tuple[str, str]] = {}  # url → (text, local_path)
        css_dir.mkdir(parents=True, exist_ok=True)

    # ── public ──────────────────────────────────────────────────────────────

    def extract_from_html(self, html: str, page_url: str) -> tuple[dict[str, str], str]:
        """
        Process one page's HTML.
        Returns (stylesheet_map, combined_css_text).
        """
        soup    = BeautifulSoup(html, "html.parser")
        css_map = {}
        chunks  = []

        # External <link rel="stylesheet">
        for tag in soup.find_all("link", rel=lambda r: r and "stylesheet" in r):
            href = (tag.get("href") or "").strip()
            if not href or href.startswith("data:"):
                continue
            abs_url = urljoin(page_url, href)
            text, local = self._fetch(abs_url, depth=0)
            if text is not None:
                chunks.append(f"/* === {abs_url} === */\n{text}")
                css_map[href]    = local
                css_map[abs_url] = local

        # Inline <style> blocks
        for tag in soup.find_all("style"):
            t = tag.get_text()
            if t.strip():
                chunks.append(t)

        return css_map, "\n\n".join(chunks)

    # ── internals ───────────────────────────────────────────────────────────

    def _fetch(self, url: str, depth: int) -> tuple[str | None, str]:
        if depth > _MAX_DEPTH:
            return None, ""
        if url in self._fetched:
            return self._fetched[url]

        log.debug(f"  CSS ← {url}")
        try:
            resp = self._session.get(url, timeout=self.timeout)
            resp.raise_for_status()
            resp.encoding = "utf-8"
            text = resp.text
        except Exception as e:
            log.warning(f"  CSS fetch failed {url}: {e}")
            self._fetched[url] = (None, "")
            return None, ""

        text  = self._resolve_imports(text, url, depth + 1)
        local = self._write(url, text)
        self._fetched[url] = (text, local)
        return text, local

    def _resolve_imports(self, css: str, base: str, depth: int) -> str:
        def _rep(m):
            raw = (m.group(1) or m.group(2) or "").strip().strip("'\"")
            if not raw or raw.startswith("data:"):
                return ""
            text, _ = self._fetch(urljoin(base, raw), depth)
            return f"/* @import {raw} */\n{text}" if text else ""
        return re.sub(
            r'@import\s+(?:url\(\s*([^)]+)\s*\)|["\']([^"\']+)["\'])\s*;?',
            _rep, css
        )

    def _write(self, url: str, text: str) -> str:
        name = urlparse(url).path.split("/")[-1] or "style"
        name = re.sub(r'[^\w.\-]', '_', name)
        if not name.endswith(".css"):
            name += ".css"
        h    = hashlib.md5(url.encode()).hexdigest()[:6]
        dest = self.css_dir / f"{h}_{name}"
        dest.write_text(text, encoding="utf-8")
        return f"assets/css/{h}_{name}"
