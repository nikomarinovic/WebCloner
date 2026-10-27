#!/usr/bin/env python3
"""
main.py — WebCloner
===================
Clone the publicly visible appearance of a website into
a local static snapshot for educational purposes.
"""

import argparse
import os
import sys
import re
from urllib.parse import urlparse

from core.cloner import SiteCloner
from utils.logger import setup_logger

log = setup_logger("main")

# --------------------------------------------------
# Metadata
# --------------------------------------------------
APP_NAME = "WebCloner"
VERSION = "v1.0.0"
AUTHOR = "Niko Marinović"
GITHUB = "https://github.com/nikomarinovic"

# --------------------------------------------------
# ANSI Colors
# --------------------------------------------------
RED = "\033[91m"
GRAY = "\033[90m"
RESET = "\033[0m"

# --------------------------------------------------
# Banner
# --------------------------------------------------
BANNER = r"""
▄▄▌ ▐ ▄▌▄▄▄ .▄▄▄▄·  ▄▄· ▄▄▌         ▐ ▄ ▄▄▄ .▄▄▄  
██· █▌▐█▀▄.▀·▐█ ▀█▪▐█ ▌▪██•  ▪     •█▌▐█▀▄.▀·▀▄ █·
██▪▐█▐▐▌▐▀▀▪▄▐█▀▀█▄██ ▄▄██▪   ▄█▀▄ ▐█▐▐▌▐▀▀▪▄▐▀▀▄ 
▐█▌██▐█▌▐█▄▄▌██▄▪▐█▐███▌▐█▌▐▌▐█▌.▐▌██▐█▌▐█▄▄▌▐█•█▌
 ▀▀▀▀ ▀▪ ▀▀▀ ·▀▀▀▀ ·▀▀▀ .▀▀▀  ▀█▄▀▪▀▀ █▪ ▀▀▀ .▀  ▀
       
                                                                                                                          
"""

# --------------------------------------------------
# Banner Printer
# --------------------------------------------------
def print_banner():
    print(RED + BANNER + RESET)

    print(GRAY + f" Tool    : {APP_NAME}" + RESET)
    print(GRAY + f" Version : {VERSION}" + RESET)
    print(GRAY + f" Author  : {AUTHOR}" + RESET)
    print(GRAY + f" GitHub  : {GITHUB}" + RESET)

    print(GRAY + """
 DISCLAIMER
 ----------
 This software is created strictly for educational purposes.
 Visual website replication is intended only for learning UI/UX concepts.

 Real cloning, scraping protected content, or unauthorized data extraction
 may be illegal. The author does not take responsibility for misuse.
""" + RESET)


def normalize_url(value: str) -> str:
    """Accept a hostname or full HTTP(S) URL and return a validated URL."""
    value = value.strip()
    if not value:
        raise ValueError("Please enter a website URL.")
    if "://" not in value:
        value = f"https://{value}"

    parsed = urlparse(value)
    try:
        hostname = parsed.hostname
        parsed.port
    except ValueError as exc:
        raise ValueError("The URL contains an invalid host or port.") from exc

    if parsed.scheme not in ("http", "https") or not parsed.netloc or not hostname:
        raise ValueError("Enter a valid http:// or https:// website URL.")
    if any(char.isspace() for char in value):
        raise ValueError("The URL cannot contain spaces.")
    return value


def _prompt_choice(prompt: str, choices: dict[str, str], input_fn=input) -> str:
    options = "/".join(choices)
    while True:
        answer = input_fn(f"{prompt} ({options}): ").strip()
        if answer in choices:
            return answer
        print(f"Please choose one of: {options}.")


def configure_interactively(args, input_fn=input):
    """Ask beginner-friendly questions and apply the choices to parsed args."""
    print("\nLet's set up your website clone.\n")

    while True:
        try:
            entered_url = input_fn("Website URL (for example, example.com/about): ")
            args.url = normalize_url(entered_url)
            break
        except ValueError as exc:
            print(exc)

    scope = _prompt_choice(
        "\nWhat would you like to clone?\n"
        "  1) This page only\n"
        "  2) The whole site\n"
        "  3) A limited number of pages",
        {"1": "one page", "2": "whole site", "3": "limited pages"},
        input_fn,
    )
    if scope == "1":
        args.max_pages = 1
    elif scope == "2":
        args.max_pages = 0
    else:
        while True:
            value = input_fn("Maximum number of pages (positive number): ").strip()
            try:
                args.max_pages = int(value)
                if args.max_pages > 0:
                    break
            except ValueError:
                pass
            print("Enter a whole number greater than 0.")

    dynamic = _prompt_choice(
        "\nDoes the site need JavaScript rendering? (Most sites do not)",
        {"y": "yes", "n": "no"},
        input_fn,
    )
    args.dynamic = dynamic == "y"

    output = input_fn("\nOutput folder [./output]: ").strip()
    args.output = output or "./output"
    return args


# --------------------------------------------------
# Argument Parser
# --------------------------------------------------
def build_parser():
    parser = argparse.ArgumentParser(
        prog="webcloner",
        description="Clone the visual appearance of a website into a static bundle.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "url",
        nargs="?",
        help="Starting URL (must start with http:// or https://)"
    )

    parser.add_argument("--version", action="store_true",
                        help="Show program version")

    parser.add_argument("--about", action="store_true",
                        help="Show program information")

    parser.add_argument("--output", "-o",
                        default="./output",
                        metavar="DIR",
                        help="Parent directory for the generated site folder")

    parser.add_argument("--max-pages", "-m",
                        type=_nonnegative_int,
                        default=0,
                        metavar="N",
                        help="Max pages to crawl (0 = unlimited)")

    parser.add_argument("--delay",
                        type=float,
                        default=0.5,
                        metavar="SEC",
                        help="Delay between requests")

    parser.add_argument("--dynamic", "-d",
                        action="store_true",
                        help="Use Playwright for JS-rendered sites")

    parser.add_argument("--timeout", "-t",
                        type=int,
                        default=15,
                        metavar="SEC",
                        help="Request timeout")

    parser.add_argument("--inline",
                        action="store_true",
                        help="Inline CSS into HTML")

    return parser


def _nonnegative_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("must be a whole number") from exc
    if number < 0:
        raise argparse.ArgumentTypeError("must be 0 (unlimited) or greater")
    return number


# --------------------------------------------------
# Main Logic
# --------------------------------------------------
def main():
    parser = build_parser()
    args = parser.parse_args()

    # ---- Version flag ----
    if args.version:
        print(f"{APP_NAME} {VERSION}")
        sys.exit(0)

    # ---- About flag ----
    if args.about:
        print_banner()
        sys.exit(0)

    # ---- No URL: start the guided terminal flow ----
    if not args.url and sys.stdin.isatty():
        try:
            args = configure_interactively(args)
        except KeyboardInterrupt:
            print("\nCancelled.")
            return 130
        except EOFError:
            print("\nCancelled.")
            return 0
    elif not args.url:
        print_banner()
        parser.print_help()
        return 0

    try:
        args.url = normalize_url(args.url)
    except ValueError as exc:
        log.error(str(exc))
        return 2

    # ---- Startup banner ----
    print_banner()

    # ---- Configuration summary ----
    log.info(f"URL        : {args.url}")
    log.info(f"Output     : {os.path.abspath(args.output)}")
    log.info(f"Max pages  : {args.max_pages or 'unlimited'}")
    log.info(f"Delay      : {args.delay}s")
    log.info(f"Renderer   : {'Playwright (JS)' if args.dynamic else 'requests'}")
    log.info(f"CSS mode   : {'inline' if args.inline else 'styles.css'}")
    print()

    # ---- Run Cloner ----
    cloner = SiteCloner(
        url=args.url,
        output_root=args.output,
        max_pages=args.max_pages,
        delay=args.delay,
        use_playwright=args.dynamic,
        timeout=args.timeout,
        inline_css=args.inline,
    )

    ok = cloner.run()

    if ok:
        domain = re.sub(r"^www\.", "", urlparse(args.url).netloc)
        site_dir = os.path.join(os.path.abspath(args.output), domain)
        local_page = cloner.url_to_local.get(args.url, "index.html")
        index_file = os.path.join(site_dir, local_page)

        print()
        log.info("✅ Done!")
        log.info(f"📁 Site folder : {site_dir}")
        log.info(f"🌐 Open        : {index_file}")
    else:
        log.error("❌ Failed — no pages were saved. Check the URL and messages above.")
        return 1
    return 0


# --------------------------------------------------
# Entry Point
# --------------------------------------------------
if __name__ == "__main__":
    sys.exit(main())