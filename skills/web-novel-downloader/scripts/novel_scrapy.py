#!/usr/bin/env python3
"""Search for a web novel source and download chapters with Scrapy."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent))

# --- Shared domain logic ---
from common import (  # noqa: E402
    Chapter, slugify, clean_text, strip_noise,
    search_candidates, load_existing_chapters,
    write_txt, write_epub, build_source_digest, compare_digests,
    looks_like_chapter, extract_chapter_links, detect_by_link_structure,
    extract_title, extract_content, find_toc_next_page,
    USER_AGENT,
)

# --- Scrapy-specific imports ---
try:
    import scrapy
    from scrapy.crawler import CrawlerProcess
except ImportError as exc:
    _skill_dir = Path(__file__).resolve().parent.parent
    raise SystemExit(
        "Scrapy is required. Install it with:\n"
        f"  python3 -m pip install -r {_skill_dir / 'requirements.txt'}"
    ) from exc

try:
    from charset_normalizer import from_bytes as detect_encoding
except ImportError:
    detect_encoding = None


# ---------------------------------------------------------------------------
# Scrapy Spider
# ---------------------------------------------------------------------------


class NovelSpider(scrapy.Spider):
    name = "generic_novel"

    custom_settings = {
        "ROBOTSTXT_OBEY": False,
        "DOWNLOAD_DELAY": 0.5,
        "CONCURRENT_REQUESTS_PER_DOMAIN": 4,
        "CONCURRENT_REQUESTS": 8,
        "AUTOTHROTTLE_ENABLED": True,
        "AUTOTHROTTLE_START_DELAY": 0.5,
        "AUTOTHROTTLE_MAX_DELAY": 5.0,
        "RETRY_TIMES": 5,
        "RETRY_HTTP_CODES": [500, 502, 503, 504, 408, 429],
        "LOG_LEVEL": "INFO",
        "USER_AGENT": USER_AGENT,
        "DEFAULT_REQUEST_HEADERS": {
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        },
        "DOWNLOAD_TIMEOUT": 30,
    }

    def __init__(
        self,
        start_url: str,
        output_dir: str,
        novel_title: str,
        max_chapters: int = 0,
        chapter_link_css: str | None = None,
        content_css: str | None = None,
        title_css: str | None = None,
        output_format: str = "txt",
        source_name: str = "",
        write_digest: bool = False,
        *args,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.start_urls = [start_url]
        self.output_dir = Path(output_dir)
        self.novel_title = novel_title
        self.max_chapters = max_chapters
        self.chapter_link_css = chapter_link_css
        self.content_css = content_css
        self.title_css = title_css
        self.output_format = output_format
        self.source_name = source_name or urlparse(start_url).netloc
        self._write_digest = write_digest
        self.chapters: list[Chapter] = []
        self.seen_chapter_urls: set[str] = set()
        self.chapter_count = 0
        self.toc_pages_visited: set[str] = set()

    def parse(self, response):
        response = self._fix_encoding(response)
        self.toc_pages_visited.add(response.url)

        links = extract_chapter_links(
            response,
            chapter_link_css=self.chapter_link_css,
            logger=self.logger,
        )
        if not links:
            self.logger.info(
                "No chapter links on %s; exporting page as single text item",
                response.url,
            )
            self.parse_chapter(response, index=1, fallback_title=self.novel_title)
            return

        for index, (label, url) in enumerate(links, start=1):
            if self.max_chapters > 0 and self.chapter_count >= self.max_chapters:
                break
            if url in self.seen_chapter_urls:
                continue
            self.seen_chapter_urls.add(url)
            self.chapter_count += 1
            yield response.follow(
                url,
                callback=self.parse_chapter,
                cb_kwargs={"index": index, "fallback_title": label},
                priority=1,
            )

        # TOC pagination
        for href, _next_url in find_toc_next_page(
            response, self.toc_pages_visited, logger=self.logger
        ):
            yield response.follow(href, callback=self.parse, priority=2)

    def _fix_encoding(self, response):
        """Detect and fix misdeclared encodings (GBK/GB2312 disguised as UTF-8).

        Scrapy trusts the server-declared encoding, but many Chinese novel sites
        declare UTF-8 while serving GBK content. Scrapling handles this
        automatically, but Scrapy needs manual correction.
        """
        if detect_encoding is None:
            return response
        body = response.body
        declared = response.encoding
        if declared and declared.lower() in ("utf-8", "utf8"):
            try:
                body.decode("utf-8")
                return response
            except UnicodeDecodeError:
                pass
        result = detect_encoding(body)
        best = result.best()
        if best and best.encoding and best.encoding.lower() not in ("utf-8", "utf8", "ascii"):
            self.logger.info("Re-decoding from %s (was %s)", best.encoding, declared)
            return response.replace(body=body, encoding=best.encoding)
        return response

    def parse_chapter(self, response, index: int, fallback_title: str):
        response = self._fix_encoding(response)
        title = extract_title(response, title_css=self.title_css) or fallback_title or f"Chapter {index}"
        text = extract_content(response, content_css=self.content_css)
        if not text or len(text) < 50:
            self.logger.warning(
                "Short/empty chapter at %s (%d chars)",
                response.url, len(text) if text else 0,
            )
            return
        text = strip_noise(text)
        self.chapters.append(
            Chapter(index=index, title=title, url=response.url, text=text)
        )
        total = len(self.chapters)
        if total % 20 == 0 or total <= 5:
            print(f"[progress] Downloaded {total} chapters", file=sys.stderr)

    def closed(self, reason):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        chapters = sorted(self.chapters, key=lambda c: c.index)

        txt_path = self.output_dir / f"{slugify(self.novel_title)}.txt"
        write_txt(self.novel_title, chapters, txt_path)

        if self.output_format in ("epub", "both"):
            epub_path = self.output_dir / f"{slugify(self.novel_title)}.epub"
            write_epub(self.novel_title, chapters, epub_path)

        # Auto-digest: write when explicitly requested OR when other digests already exist
        existing_digests = list(self.output_dir.glob("digest_*.json"))
        should_write_digest = self._write_digest or len(existing_digests) > 0
        if should_write_digest and chapters:
            digest = build_source_digest(
                self.start_urls[0], self.source_name, chapters
            )
            digest_path = self.output_dir / f"digest_{slugify(self.source_name)}.json"
            digest_path.write_text(
                json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8"
            )
            self.logger.info("Digest: %s", digest_path)

        # Auto-compare: print report if 2+ digests now exist
        all_digests = list(self.output_dir.glob("digest_*.json"))
        if len(all_digests) >= 2:
            report = compare_digests(self.output_dir)
            if report:
                print(report, file=sys.stderr)

        self.logger.info("Done: %d chapters from %s", len(chapters), self.source_name)
        self.logger.info("TXT: %s", txt_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--title", required=True, help="Novel title or search phrase.")
    parser.add_argument("--url", help="Known table-of-contents URL.")
    parser.add_argument("--output-dir", default="downloads", help="Base output directory.")
    parser.add_argument(
        "--max-chapters", type=int, default=0,
        help="Max chapters to download (0 = unlimited).",
    )
    parser.add_argument("--chapter-link-css", help="CSS selector for chapter href values.")
    parser.add_argument("--content-css", help="CSS selector for chapter body text.")
    parser.add_argument("--title-css", help="CSS selector for chapter title text.")
    parser.add_argument(
        "--format", dest="output_format", default="txt",
        choices=["txt", "epub", "both"],
        help="Output format: txt (default), epub, or both.",
    )
    parser.add_argument("--source-name", default="", help="Label for this source (used in digest filenames).")
    parser.add_argument("--dry-run-search", action="store_true", help="Only search & write candidates.")
    parser.add_argument("--proxy", help="HTTP/SOCKS proxy URL (e.g. http://127.0.0.1:7890).")
    parser.add_argument(
        "--digest", action="store_true",
        help="Write digest_*.json for cross-validation (off by default).",
    )
    parser.add_argument(
        "--compare", action="store_true",
        help="Compare all digest_*.json in output dir and print validation report.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    novel_dir = Path(args.output_dir) / slugify(args.title)
    novel_dir.mkdir(parents=True, exist_ok=True)

    # --- Compare mode ---
    if args.compare:
        report = compare_digests(novel_dir)
        if report:
            print(report)
        else:
            print("Need at least 2 source digests to compare. Download from multiple sources first.")
        return 0

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

    settings: dict = {}
    if args.proxy:
        settings["HTTPPROXY_ENABLED"] = True
        settings["HTTP_PROXY"] = args.proxy
        settings["HTTPS_PROXY"] = args.proxy

    process = CrawlerProcess(settings=settings)
    process.crawl(
        NovelSpider,
        start_url=start_url,
        output_dir=str(novel_dir),
        novel_title=args.title,
        max_chapters=args.max_chapters,
        chapter_link_css=args.chapter_link_css,
        content_css=args.content_css,
        title_css=args.title_css,
        output_format=args.output_format,
        source_name=args.source_name or urlparse(start_url).netloc,
        write_digest=args.digest,
    )
    process.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
