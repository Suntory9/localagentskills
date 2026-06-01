"""Shared domain logic for web novel downloaders.

Framework-agnostic utilities used by both Scrapy and Scrapling backends.
Response objects are duck-typed — they must support .css(), .urljoin(), .url, .text.
"""

from __future__ import annotations

import hashlib
import html
import json
import re
import sys
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable
from urllib.parse import parse_qs, quote_plus, unquote, urljoin, urlparse
from urllib.request import Request, urlopen

try:
    from ebooklib import epub as epublib
    HAS_EPUB = True
except ImportError:
    HAS_EPUB = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

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

# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# String / text utilities
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Resume support
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Chapter detection (framework-agnostic)
# ---------------------------------------------------------------------------


def looks_like_chapter(label: str, href: str) -> bool:
    """Regex-based detection of chapter-like links."""
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


def detect_by_link_structure(response, already_seen: set[str], logger=None):
    """Fallback: detect chapters by clustering URL path prefixes.

    Accepts a duck-typed response with .css('a'), .url, and .urljoin().
    """
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

    if logger:
        logger.info(
            "Structural detection found %d links under %s", len(found), best_prefix
        )
    return found


def extract_chapter_links(response, *, chapter_link_css=None, logger=None):
    """Extract chapter links from a TOC page.

    Accepts a duck-typed response with .css(), .urljoin(), .url.
    Uses regex heuristics and structural fallback when no CSS is given.
    """
    if chapter_link_css:
        urls = response.css(chapter_link_css).getall()
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
        if not looks_like_chapter(label, href):
            continue
        url = response.urljoin(href)
        if url in seen:
            continue
        seen.add(url)
        found.append((label, url))

    if len(found) < 3:
        found = detect_by_link_structure(response, seen, logger=logger)

    return found


# ---------------------------------------------------------------------------
# Content extraction (framework-agnostic)
# ---------------------------------------------------------------------------


def extract_title(response, *, title_css=None) -> str:
    """Extract chapter title using CSS selectors.

    Accepts a duck-typed response with .css().getall().
    """
    selectors = (
        [title_css]
        if title_css
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


def extract_content(response, *, content_css=None) -> str:
    """Extract chapter body text using CSS selectors.

    Accepts a duck-typed response with .css().getall().
    No longer attempts element drop() — noise is handled by strip_noise().
    """
    if content_css:
        return clean_text(response.css(content_css).getall())

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


# ---------------------------------------------------------------------------
# TOC pagination (framework-agnostic)
# ---------------------------------------------------------------------------


def find_toc_next_page(response, visited_urls: set[str], logger=None):
    """Find pagination links on a TOC page.

    Returns a list of (href, absolute_url) tuples for unvisited next-page links.
    The caller is responsible for enqueuing the requests.
    """
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
            if next_url not in visited_urls:
                if logger:
                    logger.info("Following TOC pagination: %s", next_url)
                return [(href, next_url)]
    return []


# ---------------------------------------------------------------------------
# Output formatters
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# Cross-source validation
# ---------------------------------------------------------------------------


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
