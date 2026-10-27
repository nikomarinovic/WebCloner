"""
core/cloner.py
--------------
SiteCloner — orchestrates a full multi-page site clone.

Output structure per site:
    output/
    └── example.com/
        ├── index.html
        ├── about.html
        ├── styles.css
        ├── app.js
        └── images/

Pipeline per page
-----------------
1. Crawl all internal pages (breadth-first)
2. For each page: extract CSS, download assets, rewrite HTML
3. Write every page as a flat HTML file
4. Write HTML, CSS, and JavaScript into the site folder, images into images/
"""

import re
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin, urldefrag

from core.crawler       import Crawler
from core.asset_handler import AssetHandler
from core.css_extractor import CSSExtractor
from core.page_builder  import PageBuilder
from utils.logger       import setup_logger

log = setup_logger("cloner")


def _url_to_path(url: str, site_origin: str) -> str:
    """
    Convert a page URL to a flat HTML file path inside the site folder.

    https://www.example.com/             → index.html
    https://www.example.com/about/       → about.html
    https://www.example.com/blog/post-1  → blog_post-1.html
    """
    parsed = urlparse(url)
    path   = parsed.path.rstrip("/") or "/"

    if path == "/":
        return "index.html"

    parts = [p for p in path.split("/") if p]
    parts = [re.sub(r'[^\w.\-]', '_', p) for p in parts]
    parts[-1] = Path(parts[-1]).stem
    name = "_".join(part for part in parts if part) or "page"
    return f"{name}.html"


class SiteCloner:
    """
    Clones an entire public website.

    Parameters
    ----------
    url           : starting URL
    output_root   : parent directory (a site subfolder is created)
    max_pages     : 0 = unlimited
    delay         : seconds between requests
    use_playwright: headless browser for JS SPAs
    timeout       : per-request HTTP timeout
    inline_css    : embed all CSS in each HTML file
    """

    def __init__(
        self,
        url: str,
        output_root: str = "./output",
        max_pages: int = 0,
        delay: float = 0.5,
        use_playwright: bool = False,
        timeout: int = 15,
        inline_css: bool = False,
    ):
        self.start_url     = url
        self.output_root   = Path(output_root)
        self.max_pages     = max_pages
        self.delay         = delay
        self.use_playwright = use_playwright
        self.timeout       = timeout
        self.inline_css    = inline_css

        parsed             = urlparse(url)
        self.domain        = parsed.netloc                    # www.example.com
        self.site_origin   = f"{parsed.scheme}://{parsed.netloc}"

        # Per-site output folder:  output/example.com/
        site_folder        = re.sub(r'^www\.', '', self.domain)  # strip www.
        self.site_dir      = self.output_root / site_folder
        self.css_dir       = self.site_dir

        # Create dirs
        self.site_dir.mkdir(parents=True, exist_ok=True)
        (self.site_dir / "images").mkdir(exist_ok=True)

        # Shared helpers (reused across all pages)
        self.assets   = AssetHandler(self.site_dir, timeout=timeout, base_url=self.site_origin)
        self.css_ext  = CSSExtractor(self.css_dir, timeout=timeout)

        # url → relative local path (e.g. "about.html")
        self.url_to_local: dict[str, str] = {}

        self._stats = {"pages": 0, "assets": 0, "errors": 0}

    # ── public ──────────────────────────────────────────────────────────────

    def run(self) -> bool:
        t0 = time.time()
        log.info(f"Site folder : {self.site_dir}")
        log.info(f"Max pages   : {self.max_pages or 'unlimited'}")
        log.info(f"Delay       : {self.delay}s between requests")
        print()

        # ── Pass 1: Crawl all pages, collect HTML ─────────────────────────
        log.info("── Pass 1  Crawling pages...")
        crawler = Crawler(
            start_url=self.start_url,
            max_pages=self.max_pages,
            delay=self.delay,
            use_playwright=self.use_playwright,
            timeout=self.timeout,
        )

        pages = []   # list of (original_url, html, final_url)
        for orig_url, html, final_url in crawler.crawl():
            local_path = _url_to_path(final_url, self.site_origin)
            used_paths = {path.casefold() for path in self.url_to_local.values()}
            if local_path.casefold() in used_paths:
                path = Path(local_path)
                suffix = len(pages) + 1
                while local_path.casefold() in used_paths:
                    local_path = f"{path.stem}_{suffix}{path.suffix}"
                    suffix += 1
            self.url_to_local[orig_url]  = local_path
            self.url_to_local[final_url] = local_path
            pages.append((orig_url, html, final_url, local_path))

        log.info(f"  Crawled {len(pages)} pages")
        print()
        if not pages:
            log.error("No pages were fetched; check the URL, connection, or renderer setup.")
            return False

        # ── Pass 2: Extract CSS + download assets for all pages ───────────
        log.info("── Pass 2  Extracting CSS & downloading assets...")
        page_css: dict[str, tuple[dict, str]] = {}   # local_path → (sheet_map, combined)

        for orig_url, html, final_url, local_path in pages:
            log.info(f"  Processing: {final_url}")

            # CSS
            sheet_map, combined = self.css_ext.extract_from_html(html, final_url)
            if combined and self.assets:
                combined = self.assets.rewrite_css_urls(
                    combined, final_url, output_dir="."
                )
            page_css[local_path] = (sheet_map, combined)

            # Assets
            self.assets.process_html(html, final_url)

        self._stats["assets"] = len(self.assets.asset_map)
        log.info(f"  Assets collected: {self._stats['assets']}")
        print()

        # ── Pass 3: Rewrite HTML and write files ──────────────────────────
        log.info("── Pass 3  Writing output files...")
        all_css_chunks = []

        for orig_url, html, final_url, local_path in pages:
            sheet_map, combined = page_css[local_path]
            all_css_chunks.append(combined)

            builder = PageBuilder(
                html=html,
                page_url=final_url,
                site_origin=self.site_origin,
                asset_map=self.assets.asset_map,
                stylesheet_map=sheet_map,
                url_to_local=self.url_to_local,
                local_path=local_path,
                inline_css=self.inline_css,
                combined_css=combined,
            )
            final_html = builder.build()

            # Keep every HTML page alongside CSS and JavaScript files.
            dest = self.site_dir / local_path

            # Inject link to combined styles.css (unless inlining)
            if not self.inline_css and "styles.css" not in final_html:
                final_html = final_html.replace(
                    "</head>",
                    '<link rel="stylesheet" href="styles.css">\n</head>',
                    1
                )

            dest.write_text(final_html, encoding="utf-8")
            log.info(f"  ✓ {local_path}")
            self._stats["pages"] += 1

        # ── Write combined stylesheet ────────────────────────────────────
        all_css = "\n\n".join(set(all_css_chunks))  # deduplicate identical chunks
        (self.site_dir / "styles.css").write_text(all_css, encoding="utf-8")
        log.info(f"  ✓ styles.css  ({len(all_css):,} chars)")

        elapsed = time.time() - t0
        log.info(f"\n  Pages  : {self._stats['pages']}")
        log.info(f"  Assets : {self._stats['assets']}")
        log.info(f"  Time   : {elapsed:.1f}s")
        return True

    # ── helpers ─────────────────────────────────────────────────────────────
