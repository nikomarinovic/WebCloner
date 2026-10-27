<h1 align="center">
  <img src="public/logo.png" alt="WebCloner Logo" width="96" />
  <br />
  WebCloner
</h1>

<p align="center">
  Clone entire public websites into fully browsable offline static copies — including all pages, assets, and navigation.
</p>

---

## What is WebCloner?

**WebCloner is a full‑site replication tool designed for educational analysis and offline browsing:**

- Crawls **all internal pages** automatically  
- Downloads HTML, CSS, images, and JavaScript
- Rebuilds complete website structure locally  
- Rewrites navigation for fully offline browsing  
- Supports dynamic JavaScript websites (React / Vue / Angular)

**`A complete static mirror of any publicly accessible website.`**

---

## How It Works

Getting started with WebCloner is fast:

1. **Crawl Website** — Discovers and queues all internal pages  
2. **Fetch Content** — Downloads HTML using requests or Playwright  
3. **Extract Resources** — Collects CSS, images, and scripts
4. **Rewrite Links** — Converts all navigation to local paths  
5. **Generate Snapshot** — Builds a browsable offline website

> [!TIP]
> Use `--max-pages` when testing large websites to avoid long crawls.

---

## Installation

### macOS / Linux

```bash
git clone https://github.com/nikomarinovic/WebCloner.git
cd WebCloner
```

```bash
python3 -m pip install -r requirements.txt
```

# Optional (for dynamic JS websites)

```bash
pip install playwright
playwright install chromium
```

### Windows (PowerShell)

```bash
git clone https://github.com/nikomarinovic/WebCloner.git
cd WebCloner
```

```bash
python -m pip install -r requirements.txt
```

# Optional (for dynamic JS websites)

```bash
pip install playwright
playwright install chromium
```

---

## Usage

### Easiest: guided terminal mode

Start WebCloner without a URL and follow the prompts:

```bash
python3 main.py
```

Enter a website URL (a page URL is okay), then choose to clone that page only,
the whole site, or a limited number of pages. Most users can answer `n` to
JavaScript rendering. The generated site is saved under `./output` by default.

### Clone entire site

```bash
python main.py https://example.com
```

### Limit crawl size

```bash
python main.py https://example.com --max-pages 20
```

### JavaScript-rendered websites

```bash
python main.py https://example.com --dynamic
```

### Custom output folder

```bash
python main.py https://example.com --output ./clone
```

**Output example:**

```text
output/
└── example.com/
    ├── index.html                # Homepage
    ├── about.html                # /about/
    ├── blog_post-1.html          # /blog/post-1/
    ├── styles.css
    ├── downloaded CSS, JavaScript, and font files
    └── images/                   # Downloaded images
```

Clones are static snapshots. Cookies, sign-in, forms, and other features that
depend on the original site's server are not carried over or expected to work.

---

## Features
-	Full Site Crawling — Automatically discovers all internal pages
-	Structured Output — Each website stored in its own organised folder
-	Offline Navigation — Links rewritten for local browsing
-	Asset Deduplication — Images downloaded only once
-	Dynamic Rendering — Playwright support for modern JS apps

---

## Screenshots

<p align="center">
  <img src="public/screenshot-1.png" alt="WebCloner Screenshot 1" width="800" />
</p>

---

## Data & Privacy

WebCloner downloads only publicly accessible content and does not bypass authentication, paywalls, or private systems.

> [!NOTE]
> Forms are disabled, authentication endpoints removed, and tracking scripts stripped automatically.

> [!CAUTION]
> This project is provided strictly for educational purposes.
> Real website cloning or misuse may violate laws or website terms.
> The author does not take responsibility for improper use.

---

<h3 align="center">
WebCloner does not accept feature implementations via pull requests. Feature requests and bug reports are welcome via GitHub Issues.
</h3>

---

<p align="center">
  © 2026 Niko Marinović. All rights reserved.
</p>
