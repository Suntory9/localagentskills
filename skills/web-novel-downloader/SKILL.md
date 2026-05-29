---
name: web-novel-downloader
description: Use this skill when the user gives a web novel name (or a chapter-list URL) and wants to download the full text. Searches the web for sources, picks the best one, and downloads all chapters into TXT (preferred) or EPUB files via Scrapy. Supports multi-source cross-validation.
compatibility: Designed for Claude Code and Codex (or similar products). Requires Python 3.10+ and pip.
---

# Web Novel Downloader

## Overview

Download web novel chapters from any publicly reachable source. Output is **TXT** (preferred) or **EPUB**. After downloading from multiple sources, cross-validate to ensure content completeness and integrity.

## Source Selection Strategy

**优先找整本打包下载**（TXT/EPUB 直接下载），比逐章爬取更快更完整。搜索时加关键词如 `"{书名}" TXT下载`、`"{书名}" EPUB下载`、`"{title}" ebook download`，优先选择提供整本文件下载的电子书站（如 Z-Library、ixdzs 等），这类站点域名可能变化，以搜索结果为准。

如果找到直接下载链接，用 `curl` 或 `wget` 下载即可，不需要跑 spider。只有在找不到打包下载时，才用 spider 逐章抓取。

## Installation

First, install Python dependencies:

```bash
python3 -m pip install -r requirements.txt
```

All paths below assume commands are run from the **skill directory** (the directory containing this SKILL.md). The agent should `cd` to the skill directory before running commands.

## Workflow

### Step 1 — Find sources (aim for 2+)

Goal: find **at least 2 different sources** so we can cross-validate later.

**Priority order:**
1. Check **recommended sites** above (WebFetch the search page).
2. Use **WebSearch** to find more sources:
   - Chinese: `"{书名}" 全文免费阅读`, `"{书名}" TXT下载`
   - English: `"{title}" novel read online free`, `"{title}" epub download`
3. Fallback — script built-in search:
   ```bash
   python3 scripts/novel_scrapy.py \
     --title "Novel Title" --dry-run-search --output-dir downloads
   ```

### Step 2 — Download from source A

If you got a direct TXT/EPUB file (e.g. from Z-Library or ixdzs):
```bash
curl -L -o "downloads/<slug>/<title>.txt" "<download-url>"
```

If the source is a chapter-list page, use the spider:
```bash
python3 scripts/novel_scrapy.py \
  --title "Novel Title" \
  --url "https://source-a.com/novel/toc" \
  --source-name "source-a" \
  --output-dir downloads
```

For first-time testing, add `--max-chapters 5` to verify quality.

### Step 3 — Download from source B

Repeat Step 2 with a different source, using a different `--source-name`:
```bash
python3 scripts/novel_scrapy.py \
  --title "Novel Title" \
  --url "https://source-b.com/novel/toc" \
  --source-name "source-b" \
  --output-dir downloads
```

### Step 4 — Cross-validate

Each spider run writes a `digest_<source>.json` with chapter count, total chars, and content hashes. Compare them:

```bash
python3 scripts/novel_scrapy.py \
  --title "Novel Title" --compare --output-dir downloads
```

This prints a validation report showing:
- Whether chapter counts match across sources
- Whether first/last chapter content is consistent (hash comparison)
- Whether total character counts are close

**What to look for:**
- `[OK]` — sources agree, content is likely correct
- `[WARNING] Chapter counts differ` — one source may be incomplete, prefer the one with more chapters
- `[WARNING] Content differs` — text may have been altered; skim-compare a few chapters manually

### Step 5 — Report

Tell the user:
- Which sources were used
- Cross-validation results (OK / warnings)
- Number of chapters in the final file
- Exact output file paths

## Script Options

| Option | Default | Description |
|--------|---------|-------------|
| `--title` | required | Novel title or search phrase |
| `--url` | — | Table-of-contents URL (skips search) |
| `--output-dir` | `downloads` | Base output directory |
| `--format` | `txt` | Output format: `txt`, `epub`, or `both` |
| `--source-name` | auto (domain) | Label for this source (used in digest filename) |
| `--max-chapters N` | `0` (unlimited) | Cap chapter downloads |
| `--chapter-link-css` | auto-detect | CSS selector for chapter hrefs |
| `--content-css` | auto-detect | CSS selector for chapter body |
| `--title-css` | auto-detect | CSS selector for chapter title |
| `--proxy URL` | — | HTTP/SOCKS proxy |
| `--compare` | false | Compare all digests and print validation report |
| `--dry-run-search` | false | Search only, don't crawl |

## Key Behaviors

- **TXT-first output**: Always writes TXT. EPUB is optional (`--format epub` or `--format both`).
- **Source digests**: Every download writes a `digest_<source>.json` for cross-validation.
- **Pagination**: Automatically follows "下一页" / "Next" on chapter-list pages.
- **Encoding fix**: Auto-detects GBK/GB2312 (requires `charset-normalizer`).
- **Noise removal**: Strips watermark / ad text from chapter content.
- **Structural detection**: Falls back to link-pattern heuristics when standard chapter patterns aren't found.

## Troubleshooting

| Problem | Fix |
|---------|-----|
| Empty / boilerplate content | Site may use JS rendering — try a different source |
| Garbled text | Install `charset-normalizer`: `pip install charset-normalizer` |
| Rate limited / 403 | Use `--proxy` or find a different source |
| Only first page of chapters | Find a "全部章节" link and use that as `--url` |
| EPUB not generated | Install `ebooklib`: `pip install ebooklib` |
