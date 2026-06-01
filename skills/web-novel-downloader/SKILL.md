---
name: web-novel-downloader
description: Use this skill when the user gives a web novel name (or a chapter-list URL) and wants to download the full text. Searches the web for sources, picks the best one, and downloads all chapters into TXT (preferred) or EPUB files via Scrapy (default) or Scrapling (anti-bot). Supports multi-source cross-validation.
compatibility: Designed for Claude Code and Codex (or similar products). Requires Python 3.10+ and pip.
---

# Web Novel Downloader

## Overview

Download web novel chapters from any publicly reachable source. Output is **TXT** (preferred) or **EPUB**. After downloading from multiple sources, cross-validate to ensure content completeness and integrity.

## Source Selection Strategy

**优先找整本打包下载**（TXT/EPUB/ZIP 直接下载），比逐章爬取更快更完整。

### 优先级 1：电子书站整本下载

搜索时加关键词 `"{书名}" TXT下载`、`"{书名}" EPUB下载`、`"{title}" ebook download`。

**优先尝试这些站点**（域名可能变化，以搜索为准）：

| 站点 | 下载方式 | 示例 |
|------|---------|------|
| **ixdzs** (爱下电子书) | 搜索 → 拿到 book ID → `down7.ixdzs8.com/{id}.zip` | 搜索 `ixdzs8.com/bsearch?q=书名` |
| **Z-Library** | 搜索 → 下载页 → 选格式 | 搜索 `zh.z-library.sk/s/书名` |
| **知轩藏书** | 搜索 → 下载页 → TXT | 搜索 `zxcs.me` 或搜索引擎 |

如果找到直接下载链接，用 `curl` 或 `wget` 下载即可，不需要跑 spider。

### 优先级 2：逐章爬取（仅当找不到整本时）

只有在所有电子书站都找不到打包下载时，才用 spider 逐章抓取。

## Backend Selection

Two download backends are available:

| Backend | Script | When to use |
|---------|--------|-------------|
| **Scrapy** (default) | `novel_scrapy.py` | Standard sites without bot protection. Battle-tested, lightweight. |
| **Scrapling** | `novel_scrapling.py` | Sites with Cloudflare, JS rendering, or aggressive anti-bot measures. |

Both backends produce **identical output formats** (TXT, EPUB) and source digests, so you can freely mix them — e.g. download source A with Scrapy and source B with Scrapling, then cross-validate with `--compare`.

### Scrapling Additional Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--stealth` | false | Use headless browser (`AsyncStealthySession`) for Cloudflare bypass |
| `--no-headless` | false | Show browser window (debugging, only with `--stealth`) |
| `--impersonate` | `chrome` | TLS fingerprint target: `chrome`, `firefox`, `safari`, `edge` |
| `--network-idle` | false | Wait for network to settle before parsing (JS-heavy TOC pages) |
| `--solve-cloudflare` | false | Actively solve Cloudflare challenges (only with `--stealth`) |
| `--checkpoint-dir` | — | Enable pause/resume with checkpoint directory |

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
1. **电子书站整本下载**（最重要！）— 直接搜 ixdzs、Z-Library：
   ```bash
   # ixdzs — 搜索并拿到 book ID，直接下载 ZIP
   curl -sL "https://ixdzs8.com/bsearch?q=书名" | grep -oP '/read/\d+'
   # 然后: curl -L -o "书名.zip" "https://down7.ixdzs8.com/{id}.zip"
   ```
2. Use **WebSearch** to find more sources:
   - Chinese: `"{书名}" TXT下载`, `"{书名}" 全文免费阅读`
   - English: `"{title}" novel read online free`, `"{title}" epub download`
3. Fallback — script built-in search:
   ```bash
   python3 scripts/novel_scrapy.py \
     --title "Novel Title" --dry-run-search --output-dir downloads
   ```

### Step 2 — Download

**如果找到整本下载链接（优先！）**：
```bash
# ixdzs ZIP 直链
curl -L -o "downloads/<slug>/<title>.zip" "https://down7.ixdzs8.com/{book_id}.zip"
# 或用 wget
wget -O "downloads/<slug>/<title>.epub" "https://example.com/book.epub"
```

**如果只有章节列表页**，使用 spider。

If the source has bot protection (Cloudflare, JS rendering), use the Scrapling backend:

```bash
python3 scripts/novel_scrapling.py \
  --title "Novel Title" \
  --url "https://protected-site.com/novel/toc" \
  --source-name "source-a" \
  --output-dir downloads
```

If the site uses aggressive Cloudflare protection, add `--stealth`:

```bash
python3 scripts/novel_scrapling.py \
  --title "Novel Title" \
  --url "https://protected-site.com/novel/toc" \
  --source-name "source-a" \
  --output-dir downloads \
  --stealth
```

Otherwise, use the default Scrapy backend:

```bash
python3 scripts/novel_scrapy.py \
  --title "Novel Title" \
  --url "https://source-a.com/novel/toc" \
  --source-name "source-a" \
  --output-dir downloads
```

For first-time testing, add `--max-chapters 5` to verify quality.

### Step 3 — Download from source B

Repeat Step 2 with a different source, using a different `--source-name` (use `novel_scrapling.py` if source B has bot protection):

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
| Cloudflare / JS challenge / 403 | Switch to Scrapling backend with `--stealth --solve-cloudflare` |
| JS-rendered page (empty content) | Use Scrapling with `--network-idle` |
| Empty / boilerplate content | Site may use JS rendering — try a different source |
| Garbled text | Install `charset-normalizer`: `pip install charset-normalizer` |
| Rate limited / 403 | For Scrapy: use `--proxy` or find a different source. For Scrapling: use `--stealth` |
| Only first page of chapters | Find a "全部章节" link and use that as `--url` |
| EPUB not generated | Install `ebooklib`: `pip install ebooklib` |
| Scrapling not installed | `pip install 'scrapling[fetchers]'` then `scrapling install` |
