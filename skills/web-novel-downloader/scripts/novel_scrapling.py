#!/usr/bin/env python3
"""Download web novel chapters using Scrapling (stealth/anti-bot capable).

Use this backend when the target site has Cloudflare protection, JS rendering,
or aggressive anti-bot measures that Scrapy's basic downloader can't handle.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from urllib.parse import urlparse

# --- Shared domain logic ---
sys.path.insert(0, str(Path(__file__).resolve().parent))
from common import (  # noqa: E402
    Chapter, slugify, strip_noise,
    search_candidates, load_existing_chapters,
    write_txt, write_epub, build_source_digest, compare_digests,
    looks_like_chapter, extract_chapter_links, detect_by_link_structure,
    extract_title, extract_content, find_toc_next_page,
)

# --- Scrapling-specific imports ---
try:
    from scrapling.spiders import Spider, Request
    from scrapling.fetchers import FetcherSession
    HAS_SCRAPLING = True
except ImportError:
    HAS_SCRAPLING = False
    Spider = object  # type: ignore
    Request = object  # type: ignore
    FetcherSession = object  # type: ignore

# Optional stealth import
try:
    from scrapling.fetchers import AsyncStealthySession
    HAS_STEALTH = True
except ImportError:
    HAS_STEALTH = False
    AsyncStealthySession = None  # type: ignore


# ---------------------------------------------------------------------------
# Scrapling Spider
# ---------------------------------------------------------------------------


class NovelScraplingSpider(Spider):
    """Scrapling-based spider with optional stealth/anti-bot capabilities."""

    name = "generic_novel_scrapling"

    # --- Spider settings (Scrapling uses class attributes) ---
    concurrent_requests = 4
    download_delay = 0.5
    robots_txt_obey = False
    max_blocked_retries = 5
    logging_level = logging.INFO

    def __init__(
        self,
        start_url: str = "",
        output_dir: str = "",
        novel_title: str = "",
        max_chapters: int = 0,
        chapter_link_css: str | None = None,
        content_css: str | None = None,
        title_css: str | None = None,
        output_format: str = "txt",
        source_name: str = "",
        stealth: bool = False,
        impersonate: str = "chrome",
        headless: bool = True,
        network_idle: bool = False,
        solve_cloudflare: bool = False,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        # Set the initial URL
        if start_url:
            self.start_urls = [start_url]

        self._output_dir = Path(output_dir) if output_dir else Path("downloads")
        self._novel_title = novel_title
        self._max_chapters = max_chapters
        self._chapter_link_css = chapter_link_css
        self._content_css = content_css
        self._title_css = title_css
        self._output_format = output_format
        self._source_name = source_name or (urlparse(start_url).netloc if start_url else "unknown")
        self._stealth = stealth
        self._impersonate = impersonate
        self._headless = headless
        self._network_idle = network_idle
        self._solve_cloudflare = solve_cloudflare

        # Internal state
        self.chapters: list[Chapter] = []
        self._seen_chapter_urls: set[str] = set()
        self._chapter_count = 0
        self._toc_pages_visited: set[str] = set()
        self._session_id = "stealth" if stealth else "default"

    # ------------------------------------------------------------------
    # Session configuration
    # ------------------------------------------------------------------

    def configure_sessions(self, manager):
        """Configure fetcher sessions. Uses stealth browser when --stealth is set."""
        if self._stealth:
            if not HAS_STEALTH:
                raise SystemExit(
                    "Stealth mode requires 'scrapling[fetchers]'.\n"
                    "Install with: pip install 'scrapling[fetchers]'\n"
                    "Then run: scrapling install"
                )
            manager.add(
                "stealth",
                AsyncStealthySession(
                    headless=self._headless,
                    solve_cloudflare=self._solve_cloudflare,
                    network_idle=self._network_idle,
                ),
            )
        else:
            manager.add(
                "default",
                FetcherSession(impersonate=self._impersonate),
            )

    # ------------------------------------------------------------------
    # Spider lifecycle
    # ------------------------------------------------------------------

    async def on_start(self, resuming: bool = False):
        if resuming:
            self.logger.info("Resuming from checkpoint...")
        else:
            self.logger.info(
                "Starting download from %s (stealth=%s)",
                self.start_urls[0] if self.start_urls else "?",
                self._stealth,
            )

    async def on_close(self):
        """Write output files and digest on spider completion."""
        self._output_dir.mkdir(parents=True, exist_ok=True)
        chapters = sorted(self.chapters, key=lambda c: c.index)

        # TXT output (always)
        txt_path = self._output_dir / f"{slugify(self._novel_title)}.txt"
        write_txt(self._novel_title, chapters, txt_path)

        # EPUB output (optional)
        if self._output_format in ("epub", "both"):
            epub_path = self._output_dir / f"{slugify(self._novel_title)}.epub"
            write_epub(self._novel_title, chapters, epub_path)

        # Source digest for cross-validation (compatible with Scrapy backend)
        digest = build_source_digest(
            self.start_urls[0] if self.start_urls else "",
            self._source_name,
            chapters,
        )
        digest_path = self._output_dir / f"digest_{slugify(self._source_name)}.json"
        digest_path.write_text(
            json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        self.logger.info("Done: %d chapters from %s", len(chapters), self._source_name)
        self.logger.info("TXT: %s", txt_path)
        self.logger.info("Digest: %s", digest_path)

    # ------------------------------------------------------------------
    # Parse callbacks (async generators — required by Scrapling)
    # ------------------------------------------------------------------

    async def parse(self, response):
        """Parse a TOC page, extract chapter links, and follow pagination."""
        self._toc_pages_visited.add(response.url)

        links = extract_chapter_links(
            response,
            chapter_link_css=self._chapter_link_css,
            logger=self.logger,
        )
        if not links:
            self.logger.info(
                "No chapter links on %s; exporting page as single text item",
                response.url,
            )
            await self._process_chapter(response, index=1, fallback_title=self._novel_title)
            return

        for index, (label, url) in enumerate(links, start=1):
            if self._max_chapters > 0 and self._chapter_count >= self._max_chapters:
                break
            if url in self._seen_chapter_urls:
                continue
            self._seen_chapter_urls.add(url)
            self._chapter_count += 1
            yield Request(
                url,
                sid=self._session_id,
                callback=self._chapter_cb,
                meta={"index": index, "fallback_title": label},
                priority=1,
            )

        # Follow TOC pagination
        for _href, next_url in find_toc_next_page(
            response, self._toc_pages_visited, logger=self.logger
        ):
            yield Request(
                next_url,
                sid=self._session_id,
                callback=self.parse,
                priority=2,
            )

    async def _chapter_cb(self, response):
        """Async generator callback for chapter pages.

        Wraps _process_chapter to satisfy Scrapling's requirement that
        callbacks are async generators.
        """
        index = response.meta.get("index", 0)
        fallback_title = response.meta.get("fallback_title", "")
        await self._process_chapter(response, index=index, fallback_title=fallback_title)
        yield  # required: makes this an async generator

    async def _process_chapter(
        self, response, index: int = 0, fallback_title: str = ""
    ):
        """Extract title and content from a chapter page."""
        title = (
            extract_title(response, title_css=self._title_css)
            or fallback_title
            or f"Chapter {index}"
        )
        text = extract_content(response, content_css=self._content_css)
        if not text or len(text) < 50:
            self.logger.warning(
                "Short/empty chapter at %s (%d chars)",
                response.url,
                len(text) if text else 0,
            )
            return
        text = strip_noise(text)
        self.chapters.append(
            Chapter(index=index, title=title, url=response.url, text=text)
        )
        total = len(self.chapters)
        if total % 20 == 0 or total <= 5:
            print(f"[progress] Downloaded {total} chapters", file=sys.stderr)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Novel title or search phrase.")
    parser.add_argument("--url", help="Known table-of-contents URL.")
    parser.add_argument(
        "--output-dir", default="downloads", help="Base output directory."
    )
    parser.add_argument(
        "--max-chapters", type=int, default=0,
        help="Max chapters to download (0 = unlimited).",
    )
    parser.add_argument(
        "--chapter-link-css", help="CSS selector for chapter href values."
    )
    parser.add_argument("--content-css", help="CSS selector for chapter body text.")
    parser.add_argument("--title-css", help="CSS selector for chapter title text.")
    parser.add_argument(
        "--format", dest="output_format", default="txt",
        choices=["txt", "epub", "both"],
        help="Output format: txt (default), epub, or both.",
    )
    parser.add_argument(
        "--source-name", default="",
        help="Label for this source (used in digest filenames).",
    )
    parser.add_argument(
        "--dry-run-search", action="store_true",
        help="Only search and write candidates.",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Compare all digest_*.json in output dir and print validation report.",
    )

    # --- Scrapling-specific flags ---
    stealth_group = parser.add_argument_group("Scrapling backend options")
    stealth_group.add_argument(
        "--stealth", action="store_true",
        help="Use headless browser (AsyncStealthySession) for Cloudflare bypass.",
    )
    stealth_group.add_argument(
        "--no-headless", dest="headless", action="store_false",
        help="Show browser window (debugging, only meaningful with --stealth).",
    )
    stealth_group.add_argument(
        "--impersonate", default="chrome",
        help="TLS fingerprint target: chrome, firefox, safari, edge (default: chrome).",
    )
    stealth_group.add_argument(
        "--network-idle", action="store_true", default=False,
        help="Wait for network idle before parsing (JS-heavy pages).",
    )
    stealth_group.add_argument(
        "--solve-cloudflare", action="store_true", default=False,
        help="Actively solve Cloudflare challenges (requires --stealth).",
    )
    stealth_group.add_argument(
        "--checkpoint-dir", default=None,
        help="Enable pause/resume with checkpoint directory.",
    )
    return parser.parse_args()


def main() -> int:
    if not HAS_SCRAPLING:
        _skill_dir = Path(__file__).resolve().parent.parent
        raise SystemExit(
            "Scrapling is required. Install it with:\n"
            f"  python3 -m pip install -r {_skill_dir / 'requirements.txt'}\n"
            "Or: pip install 'scrapling[fetchers]'"
        )

    args = parse_args()
    novel_dir = Path(args.output_dir) / slugify(args.title)
    novel_dir.mkdir(parents=True, exist_ok=True)

    # --- Compare mode (cross-backend compatible) ---
    if args.compare:
        report = compare_digests(novel_dir)
        if report:
            print(report)
        else:
            print(
                "Need at least 2 source digests to compare. "
                "Download from multiple sources first."
            )
        return 0

    # --- Resolve start URL ---
    start_url = args.url
    if not start_url:
        print(f"[search] Searching for: {args.title}", file=sys.stderr)
        candidates = search_candidates(args.title)
        candidates_path = novel_dir / "search_candidates.json"
        candidates_path.write_text(
            json.dumps(candidates, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        if not candidates:
            print(f"No candidates found. Wrote {candidates_path}", file=sys.stderr)
            return 2
        print(f"Wrote {len(candidates)} candidates to {candidates_path}")
        for idx, c in enumerate(candidates, start=1):
            print(f"  {idx}. [{c.get('engine', '')}] {c['title']} - {c['url']}")
        if args.dry_run_search:
            return 0
        start_url = candidates[0]["url"]
        print(f"Using: {start_url}")

    # --- Run spider ---
    if args.stealth and not HAS_STEALTH:
        print(
            "[warning] Stealth mode requested but AsyncStealthySession not available.",
            file=sys.stderr,
        )
        print(
            "Install with: pip install 'scrapling[fetchers]' && scrapling install",
            file=sys.stderr,
        )

    spider = NovelScraplingSpider(
        start_url=start_url,
        output_dir=str(novel_dir),
        novel_title=args.title,
        max_chapters=args.max_chapters,
        chapter_link_css=args.chapter_link_css,
        content_css=args.content_css,
        title_css=args.title_css,
        output_format=args.output_format,
        source_name=args.source_name or urlparse(start_url).netloc,
        stealth=args.stealth,
        impersonate=args.impersonate,
        headless=args.headless,
        network_idle=args.network_idle,
        solve_cloudflare=args.solve_cloudflare,
        crawldir=args.checkpoint_dir,
    )

    result = spider.start()
    return 0 if not result.paused else 1


if __name__ == "__main__":
    raise SystemExit(main())
