"""
core/cloner.py
--------------
SiteCloner — orchestrates a full multi-page site clone.

Output structure per site:
    output/
    └── example.com/
        ├── index.html
        ├── about/
        │   └── index.html
        ├── contact/
        │   └── index.html
        ├── styles.css         ← combined CSS from entire site
        ├── assets/
        │   ├── images/
        │   ├── fonts/
        │   ├── css/           ← individual cached sheets
        │   └── js/
        └── _cloner_report.txt

Pipeline per page
-----------------
1. Crawl all internal pages (breadth-first)
2. For each page: extract CSS, download assets, rewrite HTML
3. Write every page to a mirrored folder hierarchy
4. Write combined styles.css and a report
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
    Convert a page URL to a relative file path inside the site folder.

    https://www.example.com/             → index.html
    https://www.example.com/about/       → about/index.html
    https://www.example.com/blog/post-1  → blog/post-1/index.html
    """
    parsed = urlparse(url)
    path   = parsed.path.rstrip("/") or "/"

    if path == "/":
        return "index.html"

    # Strip leading slash, use as directory, put index.html inside
    parts = [p for p in path.split("/") if p]
    # Sanitise each path segment
    parts = [re.sub(r'[^\w.\-]', '_', p) for p in parts]

    # If the last segment looks like a file (has an extension), use as-is
    if "." in parts[-1]:
        return "/".join(parts)
    else:
        return "/".join(parts) + "/index.html"


class SiteCloner:
    """
    Clones an entire public website.

    Parameters
    ----------
    url           : starting URL
    output_root   : base output directory (a subfolder per site is created)
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
        self.assets_dir    = self.site_dir / "assets"
        self.css_dir       = self.assets_dir / "css"

        # Create dirs
        for sub in ("images", "fonts", "css", "js", "misc"):
            (self.assets_dir / sub).mkdir(parents=True, exist_ok=True)

        # Shared helpers (reused across all pages)
        self.assets   = AssetHandler(self.assets_dir, timeout=timeout, base_url=self.site_origin)
        self.css_ext  = CSSExtractor(self.css_dir, timeout=timeout)

        # url → relative local path (e.g. "about/index.html")
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
            # Deduplicate: two URLs might resolve to the same local path
            if local_path in {v for v in self.url_to_local.values()}:
                # Give it a unique suffix
                local_path = local_path.replace("/index.html", f"_{len(pages)}/index.html")
            self.url_to_local[orig_url]  = local_path
            self.url_to_local[final_url] = local_path
            pages.append((orig_url, html, final_url, local_path))

        log.info(f"  Crawled {len(pages)} pages")
        print()

        # ── Pass 2: Extract CSS + download assets for all pages ───────────
        log.info("── Pass 2  Extracting CSS & downloading assets...")
        page_css: dict[str, tuple[dict, str]] = {}   # local_path → (sheet_map, combined)

        for orig_url, html, final_url, local_path in pages:
            log.info(f"  Processing: {final_url}")

            # CSS
            sheet_map, combined = self.css_ext.extract_from_html(html, final_url)
            if combined and self.assets:
                combined = self.assets.rewrite_css_urls(combined, final_url)
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
                inline_css=self.inline_css,
                combined_css=combined,
            )
            final_html = builder.build()

            # Write to mirrored path
            dest = self.site_dir / local_path
            dest.parent.mkdir(parents=True, exist_ok=True)

            # Inject link to combined styles.css (unless inlining)
            if not self.inline_css and "styles.css" not in final_html:
                # Calculate relative path to styles.css from this file's location
                depth   = len(Path(local_path).parts) - 1
                rel_css = ("../" * depth) + "styles.css"
                final_html = final_html.replace(
                    "</head>",
                    f'<link rel="stylesheet" href="{rel_css}">\n</head>',
                    1
                )

            dest.write_text(final_html, encoding="utf-8")
            log.info(f"  ✓ {local_path}")
            self._stats["pages"] += 1

        # ── Write combined styles.css ─────────────────────────────────────
        all_css = "\n\n".join(set(all_css_chunks))  # deduplicate identical chunks
        (self.site_dir / "styles.css").write_text(all_css, encoding="utf-8")
        log.info(f"  ✓ styles.css  ({len(all_css):,} chars)")

        # ── Write report ──────────────────────────────────────────────────
        self._write_report(pages, time.time() - t0)

        elapsed = time.time() - t0
        log.info(f"\n  Pages  : {self._stats['pages']}")
        log.info(f"  Assets : {self._stats['assets']}")
        log.info(f"  Time   : {elapsed:.1f}s")
        return True

    # ── helpers ─────────────────────────────────────────────────────────────

    def _write_report(self, pages, elapsed: float):
        lines = [
            "WebCloner — Site Clone Report",
            "=" * 50,
            f"Source      : {self.start_url}",
            f"Cloned at   : {time.strftime('%Y-%m-%d %H:%M:%S')}",
            f"Pages       : {len(pages)}",
            f"Assets      : {len(self.assets.asset_map)}",
            f"Time        : {elapsed:.1f}s",
            "",
            "Pages cloned:",
            "-" * 50,
        ]
        for orig_url, _, final_url, local_path in pages:
            lines.append(f"  {local_path:50s}  ← {final_url}")

        lines += [
            "",
            "DISCLAIMER",
            "-" * 50,
            "This is a static visual snapshot of publicly accessible",
            "content. No backend, authentication, or API functionality",
            "is present. Do not publish or redistribute this clone.",
            "Respect the original site's Terms of Service.",
        ]
        report = self.site_dir / "_cloner_report.txt"
        report.write_text("\n".join(lines), encoding="utf-8")
        log.info(f"  ✓ _cloner_report.txt")
