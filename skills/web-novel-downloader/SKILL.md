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

## Site-Specific Patterns

实战中验证过的站点下载模式，直接套用即可。

### ixdzs (爱下电子书)

整本 ZIP 下载，最简单可靠，**优先尝试**：

```bash
# Step 1: 搜索拿 book ID
curl -sL "https://ixdzs8.com/bsearch?q=书名" \
  -H "User-Agent: Mozilla/5.0 ... Chrome/125.0.0.0 Safari/537.36" \
  | grep -oP 'data-url="/read/\d+/"'

# Step 2: 直链下载 (book ID 替换到 URL)
curl -L -o "书名.zip" "https://down7.ixdzs8.com/{book_id}.zip"

# Step 3: 解压 + 转码 (文件通常是 GB18030 编码)
python3 -c "
from charset_normalizer import from_bytes
with open('书名.zip', 'rb') as f:
    raw = f.read()
# 提取 ZIP 中的 txt, 检测编码, 转 UTF-8
"
```

**注意**: ixdzs 文件编碼是 GB18030（不是 UTF-8），直接读会乱码。必须用 `charset-normalizer` 检测后转码。

### Z-Library

完全 JS 渲染 + Cloudflare 保护，**必须用 Scrapling stealth + CDP 下载处理**：

```python
# Step 1: Scrapling stealth bypass CF, 搜索拿书籍链接
# 搜索结果页: https://zh.z-library.sk/s/书名
# 书籍详情: /book/{hash}/书名.html
# 下载链接: /dl/{hash}

# Step 2: 下载需要配置 CDP download behavior
from scrapling.fetchers import StealthyFetcher
import asyncio, os

async def do_download(page):
    download_path = '/tmp/zlibrary'
    os.makedirs(download_path, exist_ok=True)
    
    # 监听 download 事件
    dl_future = asyncio.get_event_loop().create_future()
    async def on_download(download):
        path = os.path.join(download_path, download.suggested_filename)
        await download.save_as(path)
        dl_future.set_result(path)
    page.on('download', on_download)
    
    # 访问下载链接触发下载
    try:
        await page.goto('https://zh.z-library.sk/dl/{hash}', 
                       referer='https://zh.z-library.sk/book/{hash}/',
                       timeout=30000)
    except Exception as e:
        if 'Download is starting' in str(e):
            pass  # 预期行为
    
    return await asyncio.wait_for(dl_future, timeout=60)

await StealthyFetcher.async_fetch(
    'https://zh.z-library.sk/book/{hash}/书名.html',
    headless=True, solve_cloudflare=True,
    network_idle=True, page_action=do_download,
)
```

**注意**: Z-Library 的 `StealthySession.fetch()` 返回 `body=0`（内容全 JS 渲染）。必须用 `page_action` 获取渲染后的 DOM 或用 CDP 拦截下载。

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
| ixdzs ZIP 乱码 | 文件是 GB18030 编码，需用 `charset-normalizer` 检测后转 UTF-8 |
| Z-Library body 为空 | Z-Library 完全 JS 渲染，`fetch()` 返回空 body。用 `page_action` 获取 DOM 或 CDP 拦截下载 |
| Z-Library "Download is starting" error | 这是预期行为——下载被浏览器触发。用 CDP `Browser.setDownloadBehavior` + `page.on('download')` 捕获文件 |
