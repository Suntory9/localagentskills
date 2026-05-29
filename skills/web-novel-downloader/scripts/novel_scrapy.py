#!/usr/bin/env python3
"""Search for a web novel source and download chapters with Scrapy."""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

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

try:
    from ebooklib import epub as epublib
    HAS_EPUB = True
except ImportError:
    HAS_EPUB = False


SEARCH_ENGINES = [
    ("DuckDuckGo", "https://duckduckgo.com/html/?q={query}"),
    ("Bing", "https://www.bing.com/search?q={query}&count=20"),
]

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)

NOISE_PATTERNS = [
    re.compile(p, re.I)
    for p in [
        r"本章未完.*?[翻点]",
        r"请记住.*?网址",
        r"最新章节.*?阅读",
        r"手机版阅读网址",
        r"一秒记住.*?免费",
        r"天才一秒记住",
        r"笔趣阁.*?最快更新",
        r"最新网址：\S+",
        r"推荐.*?小说",
        r"(?:https?://|www\.)\S+",
    ]
]

SKIP_DOMAINS = frozenset([
    "google.", "bing.", "duckduckgo.", "youtube.", "facebook.",
    "baidu.", "zhihu.com", "weibo.com", "douban.com",
    "amazon.", "jd.com", "taobao.com", "tmall.com",
])


@dataclass
class Chapter:
    index: int
    title: str
    url: str
    text: str


@dataclass
class SourceDigest:
    """Per-source summary used for cross-validation."""
    source_url: str
    source_name: str
    chapter_count: int
    total_chars: int
    first_chapter_hash: str
    last_chapter_hash: str
    sample_titles: list[str] = field(default_factory=list)


def slugify(value: str) -> str:
    slug = re.sub(r"[^0-9A-Za-z一-鿿._-]+", "-", value.strip())
    slug = re.sub(r"-{2,}", "-", slug).strip("-")
    return slug or "novel"


def clean_text(parts: Iterable[str]) -> str:
    lines: list[str] = []
    for part in parts:
        text = html.unescape(part).replace("\xa0", " ")
        text = re.sub(r"[ \t\r\f\v]+", " ", text).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def strip_noise(text: str) -> str:
    for pattern in NOISE_PATTERNS:
        text = pattern.sub("", text)
    return text.strip()


def content_hash(text: str) -> str:
    normalized = re.sub(r"\s+", "", text)[:2000]
    return hashlib.md5(normalized.encode("utf-8")).hexdigest()[:12]


def unwrap_redirect_url(raw_url: str) -> str:
    parsed = urlparse(raw_url)
    if "duckduckgo.com" in parsed.netloc and parsed.path.startswith("/l/"):
        target = parse_qs(parsed.query).get("uddg", [""])[0]
        if target:
            return unquote(target)
    if "bing.com" in parsed.netloc and parsed.path == "/ck/a":
        target = parse_qs(parsed.query).get("u", [""])[0]
        if target:
            return unquote(target)
    return raw_url


def _is_skip_domain(domain: str) -> bool:
    return any(skip in domain for skip in SKIP_DOMAINS)


def search_candidates(title: str, limit: int = 10) -> list[dict[str, str]]:
    cn_queries = [
        f"{title} 全文免费阅读",
        f"{title} 小说 全本 在线阅读",
    ]
    en_queries = [
        f"{title} novel read online free chapters",
    ]
    has_cjk = bool(re.search(r"[一-鿿]", title))
    queries = cn_queries if has_cjk else en_queries

    candidates: list[dict[str, str]] = []
    seen_domains: set[str] = set()

    for query_text in queries:
        for engine_name, engine_url in SEARCH_ENGINES:
            if len(candidates) >= limit:
                break
            try:
                encoded_query = quote_plus(query_text)
                url = engine_url.format(query=encoded_query)
                request = Request(url, headers={
                    "User-Agent": USER_AGENT,
                    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                })
                with urlopen(request, timeout=20) as response:
                    page = response.read().decode("utf-8", errors="replace")

                link_patterns = [
                    re.compile(
                        r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
                        re.I | re.S,
                    ),
                    re.compile(
                        r'<a[^>]+href="(?P<href>https?://[^"]+)"[^>]*>(?P<title>[^<]{4,80})</a>',
                        re.I | re.S,
                    ),
                ]
                for pattern in link_patterns:
                    for match in pattern.finditer(page):
                        raw = html.unescape(match.group("href"))
                        result_url = unwrap_redirect_url(raw)
                        result_title = clean_text(
                            [re.sub(r"<[^>]+>", "", match.group("title"))]
                        )
                        domain = urlparse(result_url).netloc.lower()
                        if not result_url.startswith(("http://", "https://")):
                            continue
                        if domain in seen_domains or _is_skip_domain(domain):
                            continue
                        seen_domains.add(domain)
                        candidates.append({
                            "title": result_title,
                            "url": result_url,
                            "domain": domain,
                            "engine": engine_name,
                        })
                        if len(candidates) >= limit:
                            break
                    if len(candidates) >= limit:
                        break
            except Exception as exc:
                print(f"[search] {engine_name} failed: {exc}", file=sys.stderr)
                continue

    return candidates


def load_existing_chapters(txt_path: Path) -> set[str]:
    """Read chapter titles from existing TXT to support resume."""
    titles: set[str] = set()
    if not txt_path.exists():
        return titles
    with txt_path.open("r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line.startswith("======"):
                continue
            if line and len(line) < 120 and re.search(
                r"第.+[章节回]|Chapter|序章|楔子|番外|尾声", line, re.I
            ):
                titles.add(line)
    return titles


def write_txt(novel_title: str, chapters: list[Chapter], output_path: Path):
    with output_path.open("w", encoding="utf-8") as f:
        f.write(f"{novel_title.strip()}\n\n")
        for ch in chapters:
            f.write(f"{ch.title}\n\n{ch.text}\n\n{'=' * 40}\n\n")
    print(f"[output] TXT: {output_path} ({len(chapters)} chapters)", file=sys.stderr)


def write_epub(novel_title: str, chapters: list[Chapter], output_path: Path):
    if not HAS_EPUB:
        print("[output] EPUB skipped: install ebooklib (`pip install ebooklib`)", file=sys.stderr)
        return
    book = epublib.EpubBook()
    book.set_identifier(f"web-novel-{slugify(novel_title)}")
    book.set_title(novel_title)
    book.set_language("zh")

    spine = ["nav"]
    toc = []
    for ch in chapters:
        filename = f"ch_{ch.index:04d}.xhtml"
        paragraphs = "\n".join(
            f"<p>{html.escape(line)}</p>" for line in ch.text.split("\n") if line.strip()
        )
        epub_ch = epublib.EpubHtml(
            title=ch.title, file_name=filename, lang="zh"
        )
        epub_ch.content = (
            f"<html><head><title>{html.escape(ch.title)}</title></head>"
            f"<body><h2>{html.escape(ch.title)}</h2>{paragraphs}</body></html>"
        )
        book.add_item(epub_ch)
        spine.append(epub_ch)
        toc.append(epub_ch)

    book.toc = toc
    book.spine = spine
    book.add_item(epublib.EpubNcx())
    book.add_item(epublib.EpubNav())
    epublib.write_epub(str(output_path), book)
    print(f"[output] EPUB: {output_path} ({len(chapters)} chapters)", file=sys.stderr)


def build_source_digest(
    source_url: str, source_name: str, chapters: list[Chapter]
) -> dict:
    if not chapters:
        return {
            "source_url": source_url,
            "source_name": source_name,
            "chapter_count": 0,
            "total_chars": 0,
            "first_chapter_hash": "",
            "last_chapter_hash": "",
            "sample_titles": [],
        }
    sorted_chs = sorted(chapters, key=lambda c: c.index)
    return {
        "source_url": source_url,
        "source_name": source_name,
        "chapter_count": len(sorted_chs),
        "total_chars": sum(len(c.text) for c in sorted_chs),
        "avg_chapter_chars": sum(len(c.text) for c in sorted_chs) // max(len(sorted_chs), 1),
        "first_chapter_hash": content_hash(sorted_chs[0].text),
        "last_chapter_hash": content_hash(sorted_chs[-1].text),
        "sample_titles": [c.title for c in sorted_chs[:3]] + (
            [sorted_chs[-1].title] if len(sorted_chs) > 3 else []
        ),
    }


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
        self.chapters: list[Chapter] = []
        self.seen_chapter_urls: set[str] = set()
        self.chapter_count = 0
        self.toc_pages_visited: set[str] = set()

    def parse(self, response):
        response = self._fix_encoding(response)
        self.toc_pages_visited.add(response.url)

        links = self.extract_chapter_links(response)
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

        yield from self._follow_toc_pagination(response)

    def _follow_toc_pagination(self, response):
        pagination_patterns = [
            "a:contains('下一页')::attr(href)",
            "a:contains('下页')::attr(href)",
            "a:contains('Next')::attr(href)",
            "a.next::attr(href)",
            "a.pager_next::attr(href)",
            "li.next > a::attr(href)",
            ".pagination a:last-child::attr(href)",
        ]
        for selector in pagination_patterns:
            try:
                next_urls = response.css(selector).getall()
            except Exception:
                continue
            for href in next_urls:
                next_url = response.urljoin(href)
                if next_url not in self.toc_pages_visited:
                    self.logger.info("Following TOC pagination: %s", next_url)
                    yield response.follow(href, callback=self.parse, priority=2)
                    return

    def _fix_encoding(self, response):
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

    def extract_chapter_links(self, response) -> list[tuple[str, str]]:
        if self.chapter_link_css:
            urls = response.css(self.chapter_link_css).getall()
            return [
                (f"Chapter {idx}", response.urljoin(url))
                for idx, url in enumerate(urls, start=1)
            ]

        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        for anchor in response.css("a"):
            href = anchor.attrib.get("href")
            label = clean_text(anchor.css("::text").getall())
            if not href or not label:
                continue
            if not self._looks_like_chapter(label, href):
                continue
            url = response.urljoin(href)
            if url in seen:
                continue
            seen.add(url)
            found.append((label, url))

        if len(found) < 3:
            found = self._detect_by_link_structure(response, seen)

        return found

    @staticmethod
    def _looks_like_chapter(label: str, href: str) -> bool:
        text = f"{label} {href}".lower()
        patterns = [
            r"第\s*[0-9一二三四五六七八九十百千万零两]+\s*[章节回卷集]",
            r"(?:序[章言幕]|楔子|前[言传]|番外|尾声|后记|终章|完结)",
            r"\bchapter\s*\d+",
            r"\bchapter\s+[ivxlcdm]+\b",
            r"\bch(?:ap(?:ter)?)?[-_./]?\d+",
            r"/\d{4,}\.s?html?",
            r"(?:^|\s)\d{1,4}[.、]\s*\S",
        ]
        return any(re.search(pattern, text, re.I) for pattern in patterns)

    def _detect_by_link_structure(
        self, response, already_seen: set[str]
    ) -> list[tuple[str, str]]:
        from collections import Counter

        path_prefix_count: Counter[str] = Counter()
        anchors_data: list[tuple[str, str, str]] = []
        base_path = urlparse(response.url).path.rstrip("/")

        for anchor in response.css("a"):
            href = anchor.attrib.get("href", "")
            label = clean_text(anchor.css("::text").getall())
            if not href or not label or len(label) < 2 or len(label) > 120:
                continue
            url = response.urljoin(href)
            parsed = urlparse(url)
            if parsed.netloc != urlparse(response.url).netloc:
                continue
            path = parsed.path
            prefix = "/".join(path.split("/")[:-1])
            if prefix and prefix != base_path:
                path_prefix_count[prefix] += 1
                anchors_data.append((label, url, prefix))

        if not path_prefix_count:
            return []

        best_prefix, best_count = path_prefix_count.most_common(1)[0]
        if best_count < 5:
            return []

        found: list[tuple[str, str]] = []
        for label, url, prefix in anchors_data:
            if prefix == best_prefix and url not in already_seen:
                found.append((label, url))

        self.logger.info(
            "Structural detection found %d links under %s", len(found), best_prefix
        )
        return found

    def parse_chapter(self, response, index: int, fallback_title: str):
        response = self._fix_encoding(response)
        title = self.extract_title(response) or fallback_title or f"Chapter {index}"
        text = self.extract_content(response)
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

    def extract_title(self, response) -> str:
        selectors = (
            [self.title_css]
            if self.title_css
            else ["h1::text", "h2::text", ".bookname h1::text", ".chapter-title::text"]
        )
        for selector in selectors:
            if not selector:
                continue
            for raw_title in response.css(selector).getall():
                title = clean_text([raw_title])
                if title and len(title) < 200:
                    return title
        return ""

    def extract_content(self, response) -> str:
        if self.content_css:
            return clean_text(response.css(self.content_css).getall())

        for tag in ("script", "style", "nav", "footer", "header", "aside", ".ad", "#ad"):
            try:
                response.css(tag).drop()
            except Exception:
                pass

        candidate_selectors = [
            "#content ::text",
            "#chapter-content ::text",
            "#chaptercontent ::text",
            "#BookText ::text",
            "#booktext ::text",
            ".chapter-content ::text",
            ".chapterContent ::text",
            ".content_read ::text",
            ".read-content ::text",
            ".entry-content ::text",
            ".post-content ::text",
            ".novelcontent ::text",
            ".txt_cont ::text",
            "article ::text",
            "main ::text",
        ]
        best = ""
        for selector in candidate_selectors:
            text = clean_text(response.css(selector).getall())
            if len(text) > len(best):
                best = text
        return best

    def closed(self, reason):
        self.output_dir.mkdir(parents=True, exist_ok=True)
        chapters = sorted(self.chapters, key=lambda c: c.index)

        # --- Write TXT ---
        txt_path = self.output_dir / f"{slugify(self.novel_title)}.txt"
        write_txt(self.novel_title, chapters, txt_path)

        # --- Optionally write EPUB ---
        if self.output_format in ("epub", "both"):
            epub_path = self.output_dir / f"{slugify(self.novel_title)}.epub"
            write_epub(self.novel_title, chapters, epub_path)

        # --- Write source digest for cross-validation ---
        digest = build_source_digest(
            self.start_urls[0], self.source_name, chapters
        )
        digest_path = self.output_dir / f"digest_{slugify(self.source_name)}.json"
        digest_path.write_text(
            json.dumps(digest, indent=2, ensure_ascii=False), encoding="utf-8"
        )

        self.logger.info("Done: %d chapters from %s", len(chapters), self.source_name)
        self.logger.info("TXT: %s", txt_path)
        self.logger.info("Digest: %s", digest_path)


def compare_digests(digest_dir: Path) -> str:
    """Load all digest_*.json in a directory and produce a comparison report."""
    digest_files = sorted(digest_dir.glob("digest_*.json"))
    if len(digest_files) < 2:
        return ""

    digests = []
    for f in digest_files:
        try:
            digests.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception:
            continue

    if len(digests) < 2:
        return ""

    lines = ["", "=" * 60, "CROSS-SOURCE VALIDATION REPORT", "=" * 60]
    for d in digests:
        lines.append(
            f"\n  Source: {d['source_name']}\n"
            f"  URL:    {d['source_url']}\n"
            f"  Chapters: {d['chapter_count']}\n"
            f"  Total chars: {d['total_chars']:,}\n"
            f"  Avg chars/chapter: {d.get('avg_chapter_chars', 'N/A')}\n"
            f"  First chapter hash: {d['first_chapter_hash']}\n"
            f"  Last chapter hash:  {d['last_chapter_hash']}\n"
            f"  Sample titles: {d['sample_titles']}"
        )

    ch_counts = [d["chapter_count"] for d in digests]
    if max(ch_counts) > 0 and min(ch_counts) / max(ch_counts) < 0.8:
        lines.append("\n[WARNING] Chapter counts differ significantly — some sources may be incomplete.")
    else:
        lines.append("\n[OK] Chapter counts are consistent across sources.")

    first_hashes = set(d["first_chapter_hash"] for d in digests if d["first_chapter_hash"])
    if len(first_hashes) > 1:
        lines.append("[WARNING] First chapter content differs — text may have been altered by a source.")
    elif first_hashes:
        lines.append("[OK] First chapter content matches across sources.")

    last_hashes = set(d["last_chapter_hash"] for d in digests if d["last_chapter_hash"])
    if len(last_hashes) > 1:
        lines.append("[WARNING] Last chapter content differs — check for truncation or extra content.")
    elif last_hashes:
        lines.append("[OK] Last chapter content matches across sources.")

    char_counts = [d["total_chars"] for d in digests if d["total_chars"] > 0]
    if char_counts and max(char_counts) > 0:
        ratio = min(char_counts) / max(char_counts)
        if ratio < 0.9:
            lines.append(f"[WARNING] Total character counts vary ({ratio:.0%} ratio) — possible missing content.")
        else:
            lines.append(f"[OK] Total character counts are close ({ratio:.0%} ratio).")

    lines.append("=" * 60)
    return "\n".join(lines)


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
    )
    process.start()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
