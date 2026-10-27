"""
core/asset_handler.py
---------------------
Downloads publicly visible images, CSS, and JavaScript referenced
in HTML or CSS, and returns a mapping { original_url -> local_rel_path }.

Assets are shared across all pages of a site clone (images/ for images, site root for CSS/JS).
"""

import re
import hashlib
import posixpath
from pathlib import Path
from urllib.parse import urljoin, urlparse, unquote

from core.session import make_session
from utils.logger import setup_logger

log = setup_logger("assets")

# Images use images/; CSS, JavaScript, and fonts stay at the site root.
_IMAGE_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico", ".avif", ".bmp",
}
_ROOT_ASSET_EXTENSIONS = {
    ".css", ".js", ".woff", ".woff2", ".ttf", ".otf", ".eot",
}

_MAX_BYTES = 10 * 1024 * 1024   # 10 MB per asset cap


class AssetHandler:
    """
    Downloads and tracks all public assets for a site clone.
    A single instance should be reused across all pages of the same site
    so assets are only downloaded once.

    Parameters
    ----------
    assets_dir  : Path to output/<site>/
    timeout     : per-request timeout (seconds)
    base_url    : site origin, used to resolve relative URLs
    """

    def __init__(self, assets_dir: Path, timeout: int = 15, base_url: str = ""):
        self.assets_dir = assets_dir
        self.timeout    = timeout
        self.base_url   = base_url
        self._session   = make_session()
        # Global maps shared across all pages
        self.asset_map:  dict[str, str] = {}   # original_url → local_rel_path
        self._downloaded: set[str]      = set()

    # ── public ──────────────────────────────────────────────────────────────

    def process_html(self, html: str, page_url: str) -> list[str]:
        """
        Scan HTML for asset URLs and queue them for download.
        Returns the list of discovered absolute asset URLs.
        """
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, "html.parser")
        urls = set()

        # <img src> / <img srcset>
        for tag in soup.find_all("img"):
            if tag.get("src"):
                urls.add(urljoin(page_url, tag["src"]))
            for part in (tag.get("srcset") or "").split(","):
                parts = part.strip().split()
                if parts:
                    urls.add(urljoin(page_url, parts[0]))

        # <link>: stylesheets, icons, preload
        for tag in soup.find_all("link"):
            href = tag.get("href", "")
            rel  = " ".join(tag.get("rel", []))
            if href and any(r in rel for r in ("stylesheet", "icon", "preload", "font")):
                urls.add(urljoin(page_url, href))

        # <script src>
        for tag in soup.find_all("script", src=True):
            urls.add(urljoin(page_url, tag["src"]))

        # <source src> / <source srcset>
        for tag in soup.find_all("source"):
            if tag.get("src"):
                urls.add(urljoin(page_url, tag["src"]))
            for part in (tag.get("srcset") or "").split(","):
                parts = part.strip().split()
                if parts:
                    urls.add(urljoin(page_url, parts[0]))

        # Inline style url()
        for tag in soup.find_all(style=True):
            for m in re.finditer(r'url\(["\']?([^)"\']+)["\']?\)', tag["style"]):
                raw = m.group(1)
                if not raw.startswith("data:"):
                    urls.add(urljoin(page_url, raw))

        valid = [u for u in urls if u.startswith(("http://", "https://"))]
        for u in valid:
            self.download(u)
        return valid

    def download(self, url: str) -> str | None:
        """
        Download a single asset (once).
        Returns local path relative to the site output root, or None on failure.
        """
        if url in self._downloaded:
            return self.asset_map.get(url)
        self._downloaded.add(url)

        parsed  = urlparse(url)
        ext     = Path(unquote(parsed.path)).suffix.lower()
        if ext not in _IMAGE_EXTENSIONS | _ROOT_ASSET_EXTENSIONS:
            log.debug(f"  Skipping unsupported asset type: {url}")
            return None
        folder = (
            self.assets_dir / "images"
            if ext in _IMAGE_EXTENSIONS else self.assets_dir
        )
        folder.mkdir(parents=True, exist_ok=True)

        filename = self._safe_name(url, ext)
        dest     = folder / filename

        if dest.exists():
            rel = self._rel(dest)
            self.asset_map[url] = rel
            return rel

        try:
            resp    = self._session.get(url, timeout=self.timeout, stream=True)
            resp.raise_for_status()
            content = b""
            for chunk in resp.iter_content(8192):
                content += chunk
                if len(content) > _MAX_BYTES:
                    log.warning(f"  Skipping oversized: {url}")
                    return None
            dest.write_bytes(content)
            rel = self._rel(dest)
            self.asset_map[url] = rel
            log.debug(f"  ✓ {rel}  ({len(content):,} B)")
            return rel
        except Exception as e:
            log.warning(f"  ✗ {url}: {e}")
            return None

    def rewrite_css_urls(
        self, css_text: str, css_base_url: str, output_dir: str = "."
    ) -> str:
        """Download assets inside CSS url() and rewrite to local paths."""
        def _rep(m):
            raw = m.group(1).strip("'\"")
            if raw.startswith("data:"):
                return m.group(0)
            local = self.download(urljoin(css_base_url, raw))
            if not local:
                return m.group(0)
            relative = posixpath.relpath(local, output_dir)
            return f"url('{relative}')"
        return re.sub(r'url\(\s*([^)]+)\s*\)', _rep, css_text)

    # ── helpers ─────────────────────────────────────────────────────────────

    def _safe_name(self, url: str, ext: str) -> str:
        base = Path(unquote(urlparse(url).path)).name
        base = re.sub(r'[?#].*', '', base)
        base = re.sub(r'[^\w.\-]', '_', base)[:80]
        if not base or base == ext:
            base = hashlib.md5(url.encode()).hexdigest()[:12] + ext
        elif not base.lower().endswith(ext):
            base += ext
        return f"{hashlib.md5(url.encode()).hexdigest()[:8]}_{base}"

    def _rel(self, abs_path: Path) -> str:
        """Path relative to the generated site root."""
        return str(abs_path.relative_to(self.assets_dir)).replace("\\", "/")
