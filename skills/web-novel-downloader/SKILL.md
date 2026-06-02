---
name: web-novel-downloader
description: Use this skill when the user gives a web novel name (or a chapter-list URL) and wants to download the full text. Searches the web for sources, picks the best one, and downloads all chapters into TXT (preferred) or EPUB files via Scrapy (default) or Scrapling (anti-bot). Supports multi-source cross-validation.
compatibility: Designed for Claude Code and Codex (or similar products). Requires Python 3.10+ and pip.
---

# Web Novel Downloader

## Overview

Download web novel chapters from any publicly reachable source. Output is **TXT** (preferred) or **EPUB**.

## Token Efficiency (Read This First)

不同下载方式消耗的 token 差距极大。**每次下载前先问自己：这本书能用 ixdzs 整本下吗？**

| 下载方式 | Token/本 | 耗时 | 适用场景 |
|----------|----------|------|----------|
| **ixdzs 整本 ZIP** | ~5K | ~30秒 | 首选，绝大多数中文网文 |
| **Spider 逐章（顺利）** | ~15K | ~10-20分钟 | ixdzs 没有时 |
| **Spider 逐章（多次失败）** | ~35K+ | ~30分钟+ | 换了多个站才找到能用的 |

**核心原则：**
1. **永远先试 ixdzs** — 搜索 + 下载 + 转码一条龙，~5K token 搞定
2. **Spider 先测 5 章** — `--max-chapters 5` 确认站点可用再全量跑，避免在不可用站点上浪费 token
3. **失败站点不恋战** — 连续 2 个站点 403/空内容，改用 WebSearch 重新找源，不要盲目换站
4. **搜索设上限** — 同一本书搜 3 轮无结果就标记为不可获取，向用户说明原因

## Source Selection Strategy

**优先找整本打包下载**（TXT/EPUB/ZIP 直接下载），比逐章爬取更快更完整且省 token。

### 优先级 1：ixdzs 整本下载（最优方案）

ixdzs 是最可靠的整本下载来源。**每本书都应该先试 ixdzs**：

```bash
# Step 1: 搜索拿 book ID（多本书可并行 curl）
curl -sL --max-time 15 "https://ixdzs8.com/bsearch?q=书名" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36" \
  | grep -oP 'data-url="/read/\d+/"'

# Step 2: 验证 ID 对应的书名（确认是目标书而不是同名书）
curl -sL --max-time 15 "https://ixdzs8.com/read/{book_id}/" \
  -H "User-Agent: Mozilla/5.0" \
  | grep -oP '<title>[^<]+</title>'

# Step 3: 直链下载 ZIP
curl -L --max-time 120 -o "书名.zip" "https://down7.ixdzs8.com/{book_id}.zip" \
  -H "User-Agent: Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"

# Step 4: 解压 + 编码转换（文件是 GB18030，不是 UTF-8）
python3 << 'EOF'
import zipfile
from charset_normalizer import from_bytes

zip_path = "书名.zip"
with zipfile.ZipFile(zip_path, 'r') as zf:
    for name in zf.namelist():
        raw = zf.read(name)
        result = from_bytes(raw).best()
        if result:
            out_name = "书名.txt"
            with open(out_name, 'w', encoding='utf-8') as f:
                f.write(str(result))
            print(f"Done: {out_name}, {len(str(result))} chars, encoding: {result.encoding}")
EOF

# Step 5: 验证内容（确认作者和内容正确）
head -3 "书名.txt"

# Step 6: 清理中间文件
rm -f "书名.zip"
```

**ixdzs 注意事项：**
- 文件编码是 **GB18030**（不是 UTF-8），必须用 `charset-normalizer` 转码
- ixdzs 显示的"作者"有时是**上传者**而非实际作者（如"子夜月隐"显示为多本书的"作者"）——以书名匹配为准，最终以 head 验证内容确认
- 如果 ixdzs8.com 不可访问，换备用域名 `ixdzs.tw` 或 `ixdzs.hk`
- 多本书时，**并行执行** Step 1-2-3（不同的书之间没有依赖）

### 优先级 2：其他电子书站

| 站点 | 下载方式 | 示例 |
|------|---------|------|
| **Z-Library** | 搜索 → 下载页 → 选格式 | 搜索 `zh.z-library.sk/s/书名` |
| **知轩藏书** | 搜索 → 下载页 → TXT | 搜索 `zxcs.me` 或搜索引擎 |

### 优先级 3：逐章爬取（仅当整本下载不可用时）

只有在所有电子书站都找不到打包下载时，才用 spider 逐章抓取。

## Backend Selection

Two download backends are available:

| Backend | Script | When to use |
|---------|--------|-------------|
| **Scrapy** (default) | `novel_scrapy.py` | Standard sites without bot protection. Battle-tested, lightweight. |
| **Scrapling** | `novel_scrapling.py` | Sites with Cloudflare, JS rendering, or aggressive anti-bot measures. |

Both backends produce **identical output formats** (TXT, EPUB) and source digests.

### Scrapling Additional Flags

| Flag | Default | Description |
|------|---------|-------------|
| `--stealth` | false | Use headless browser for Cloudflare bypass |
| `--no-headless` | false | Show browser window (debugging, only with `--stealth`) |
| `--impersonate` | `chrome` | TLS fingerprint target: `chrome`, `firefox`, `safari`, `edge` |
| `--network-idle` | false | Wait for network to settle before parsing (JS-heavy TOC pages) |
| `--solve-cloudflare` | false | Actively solve Cloudflare challenges (only with `--stealth`) |
| `--checkpoint-dir` | — | Enable pause/resume with checkpoint directory |

## Installation

```bash
python3 -m pip install -r requirements.txt
```

All paths below assume commands are run from the **skill directory** (the directory containing this SKILL.md).

## Workflow

### Step 1 — Find sources (aim for 2+)

Goal: find **at least 2 different sources** so we can cross-validate later.

**Priority order:**
1. **ixdzs 整本下载**（最重要！最省 token！）— 直接 curl 搜索拿 ID
2. Use **WebSearch** to find more sources:
   - Chinese: `"{书名}" TXT下载`, `"{书名}" 全文免费阅读`
   - English: `"{title}" novel read online free`, `"{title}" epub download`
3. Fallback — script built-in search:
   ```bash
   python3 scripts/novel_scrapy.py \
     --title "Novel Title" --dry-run-search --output-dir downloads
   ```

### Step 2 — Download

**如果 ixdzs 有 → 整本 ZIP 下载（最优！见上方 ixdzs 完整流程）。**

**如果只有章节列表页 → spider 逐章下载。**

**Spider 使用规则（防 token 浪费）：**

1. **必须先测 5 章** — 永远先加 `--max-chapters 5` 验证站点可用性
2. **测试不同站点用不同 `--source-name`** — 避免后一次运行覆盖前一次的输出文件
3. **连续 2 个站点失败 → WebSearch 重新找源** — 不要盲目试第 3 个

```bash
# 测试阶段：不同 source-name 避免互相覆盖
python3 scripts/novel_scrapy.py \
  --title "Novel Title" \
  --url "https://site-a.com/novel/toc" \
  --source-name "site-a" \
  --output-dir downloads \
  --max-chapters 5

# 测试成功 → 去掉 --max-chapters 全量下载
python3 scripts/novel_scrapy.py \
  --title "Novel Title" \
  --url "https://site-a.com/novel/toc" \
  --source-name "site-a" \
  --output-dir downloads \
  --digest
```

**Auto-fallback**: If Scrapy returns 0 chapters or all chapters are < 50 chars → site likely has bot protection. Switch to Scrapling with `--stealth` and retry the **same URL** (不要换站，先换后端).

If the site uses aggressive Cloudflare protection, add `--stealth`:

```bash
python3 scripts/novel_scrapling.py \
  --title "Novel Title" \
  --url "https://protected-site.com/novel/toc" \
  --source-name "source-a" \
  --output-dir downloads \
  --stealth
```

### Step 3 — Download from source B (optional, for cross-validation)

Repeat Step 2 with a different source, using a different `--source-name`:

```bash
python3 scripts/novel_scrapy.py \
  --title "Novel Title" \
  --url "https://source-b.com/novel/toc" \
  --source-name "source-b" \
  --output-dir downloads
```

### Step 4 — Cross-validate

```bash
python3 scripts/novel_scrapy.py \
  --title "Novel Title" --compare --output-dir downloads
```

**What to look for:**
- `[OK]` — sources agree, content is likely correct
- `[WARNING] Chapter counts differ` — one source may be incomplete, prefer the one with more chapters
- `[WARNING] Content differs` — text may have been altered; skim-compare a few chapters manually

### Step 5 — Cleanup

```bash
# 删除中间 ZIP 文件（已成功提取 txt 的）
rm -f downloads/*/书名_ixdzs.zip

# 删除 GB18030 原始文件（已转 UTF-8 的）
rm -f downloads/*/"*（正式版）.txt"
```

### Step 6 — Report

Tell the user:
- Which sources were used (ixdzs vs spider, domain names)
- Cross-validation results (OK / warnings)
- Number of chapters and total chars in the final file
- Exact output file paths

## Batch Download Mode

When downloading multiple books (e.g., from a top-N list), use **subagents for maximum parallelism**. Each book's full pipeline (search → download → extract) is independent of others.

### Subagent Strategy（推荐，3+ 本书时使用）

```
Dispatcher (主 agent)
  ├── Agent 1: "下载《书名A》" — ixdzs 全流程
  ├── Agent 2: "下载《书名B》" — ixdzs 全流程
  ├── Agent 3: "下载《书名C》" — ixdzs 全流程
  ├── Agent 4: "下载《书名D》" — 先试 ixdzs，没有则 spider
  └── Agent 5: "下载《书名E》" — 先试 ixdzs，没有则 spider
          ↓ 全部完成后
  Dispatcher: 汇总报告（成功/失败/需要 spider 的）
```

**并发限制**：
- ixdzs agent：可 5-8 个并行（curl 请求轻量，互不干扰）
- spider agent：最多 2-3 个并行（spider 本身有并发请求，叠加过多会触发限流）

**Dispatcher 执行流程**：

```bash
# Phase 1: 所有书先启动 ixdzs agent（并行）
# 每本书一个 agent，内部执行搜索→验证→下载→解压→转码→确认
for book in "书名1" "书名2" "书名3"; do
  Agent "下载《$book》：先搜 ixdzs，找到后下载 ZIP 解压转 UTF-8" &
done
# 等待全部完成

# Phase 2: 只对 ixdzs 没找到的书启动 spider agent（并行，限 2-3 个）
for book in failed_books; do
  Agent "下载《$book》：ixdzs 没有，用 spider 逐章下载" &
done

# Phase 3: 汇总报告
```

### 无 Subagent 时的备选方案（2 本以内）

1. **Phase 1 — ixdzs sweep（并行 curl）**: 搜索所有书名，提取 ID
2. **Phase 2 — Verify IDs（并行 curl）**: 验证每个 ID 的书名页 title
3. **Phase 3 — Download ZIPs（并行 curl）**: 下载所有确认的 ZIP
4. **Phase 4 — Extract & Convert（串行）**: 逐个解压转码验证
5. **Phase 5 — Spider fallback（只对 ixdzs 没有的）**: 逐一下载
6. **Phase 6 — Report**: 汇总成功/失败

## Handling Unfindable Books

有些书可能根本找不到。**搜索 3 轮无结果就停止**，不要无限搜索：

1. **第一轮** — ixdzs 直搜（curl）
2. **第二轮** — WebSearch `"书名" TXT下载`
3. **第三轮** — 核实作者/书名是否正确（查豆瓣、百度百科）

3 轮后仍无结果 → **标记为不可获取**，向用户说明：
- 搜索了哪些渠道
- 为什么认为找不到（作者信息有误？书名太冷门？出版而非网文？）
- 建议用户核实列表中该条目的准确性

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
| `--digest` | false | Write digest JSON for cross-validation |
| `--compare` | false | Compare all digest_*.json and print validation report |
| `--dry-run-search` | false | Search only, don't crawl |

## Key Behaviors

- **TXT-first output**: Always writes TXT. EPUB is optional (`--format epub` or `--format both`).
- **Auto-digest**: When other `digest_*.json` files already exist in the output dir, new downloads automatically write their own digest. Use `--digest` to force on first download.
- **Pagination**: Automatically follows "下一页" / "Next" on chapter-list pages.
- **Encoding fix**: Auto-detects GBK/GB2312 (requires `charset-normalizer`).
- **Noise removal**: Strips watermark / ad text from chapter content.
- **Structural detection**: Falls back to link-pattern heuristics when standard chapter patterns aren't found.

## Site-Specific Patterns

### ixdzs (爱下电子书)

整本 ZIP 下载，**最省 token 的方案，永远优先尝试**。

完整流程见上文 **优先级 1：ixdzs 整本下载** 章节（含解压+转码+验证+清理的完整脚本）。

**关键注意事项：**
- 文件编码是 **GB18030**，必须用 `charset-normalizer` 转 UTF-8
- ixdzs 显示的"作者"可能是**上传者**而非原作者，以书名匹配为准
- 如果 ixdzs8.com 不可访问（500/超时），换备用域名 `ixdzs.tw` 或 `ixdzs.hk`
- 搜索结果可能有同名书，**必须用 Step 2 的 title 验证确认**

### Z-Library

完全 JS 渲染 + Cloudflare 保护，需要 Scrapling stealth 模式。

**关键点：**
- 搜索页 `/s/{书名}`、详情页 `/book/{hash}/`、下载链接 `/dl/{hash}`
- `StealthySession.fetch()` 返回 `body=0`（全 JS 渲染），必须用 `page_action` 获取渲染后 DOM
- 下载由浏览器触发（非 HTTP 直链），需通过 CDP `page.on('download')` 事件拦截文件保存

**用法：** Scrapling `--stealth --solve-cloudflare --network-idle`，配合 `page_action` 处理下载事件。

## Troubleshooting

| Problem | Fix |
|---------|-----|
| **Output file overwritten** (multiple spiders write same file) | Use different `--source-name` for each spider test. Even with `--max-chapters 5`, different sources must have different names. |
| **Spider test output overwritten by next spider** | Test different sources with **different `--source-name`** values. The default output filename includes the source name — same name = same file = overwrite. |
| Cloudflare / JS challenge / 403 | Switch to Scrapling backend with `--stealth --solve-cloudflare` |
| JS-rendered page (empty content) | Use Scrapling with `--network-idle` |
| Empty / boilerplate content | Site may use JS rendering — try a different source |
| 2+ spider sites fail in a row | **Stop and WebSearch** for new sources, don't blindly try more sites |
| Garbled text | Install `charset-normalizer`: `pip install charset-normalizer` |
| Rate limited / 403 | For Scrapy: use `--proxy` or find a different source. For Scrapling: use `--stealth` |
| Only first page of chapters | Find a "全部章节" link and use that as `--url` |
| EPUB not generated | Install `ebooklib`: `pip install ebooklib` |
| Scrapling not installed | `pip install 'scrapling[fetchers]'` then `scrapling install` |
| ixdzs ZIP 乱码 | 文件是 GB18030 编码，需用 `charset-normalizer` 检测后转 UTF-8 |
| ixdzs 作者显示不对 | ixdzs 作者字段可能是上传者。以书名匹配 + head 验证内容为准 |
| Z-Library body 为空 | Z-Library 完全 JS 渲染，`fetch()` 返回空 body。用 `page_action` 获取 DOM 或 CDP 拦截下载 |
| Book completely unfindable | 搜 3 轮无结果 → 标记为不可获取，向用户说明原因。不要无限搜索。 |
