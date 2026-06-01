# Personal Skills

我的 Agent Skills 集合，兼容 **Claude Code** 和 **Codex** 平台。

## 目录结构

```
skills/
  <skill-name>/
    SKILL.md          # 技能定义（必须）
    scripts/           # 可执行脚本（可选）
    references/        # 参考文档（可选）
    agents/            # Codex 专用配置（可选）
```

## 技能列表

| 技能 | 描述 |
|------|------|
| [web-novel-downloader](skills/web-novel-downloader/) | 网文下载器：搜索下载公开网络小说（TXT/EPUB），**优先整本直链下载**（ixdzs/Z-Library），找不到才逐章爬取。双后端（Scrapy 轻量 + Scrapling 反爬 + Cloudflare 绕过），支持多源交叉验证 |

## 格式规范

所有技能遵循 [Agent Skills 规范](https://agentskills.io/specification)。

## 安装

**跨平台**（macOS / Linux / Windows），需要 Python 3.10+：

```bash
# 克隆仓库
git clone <this-repo-url> ~/personal-skills
cd ~/personal-skills

# 一键安装所有技能到 Claude Code + Codex
python3 install.py

# 或选择性安装
python3 install.py --target claude                  # 只装到 Claude Code
python3 install.py --skill web-novel-downloader     # 只装指定技能
python3 install.py --pip                            # 同时装 Python 依赖

# 查看可用技能
python3 install.py --list

# 卸载
python3 install.py --uninstall
```

> **Windows 用户注意**：安装脚本优先使用符号链接。如果权限不足（需管理员或开发者模式），会自动回退到目录复制。建议在 Windows 设置中开启「开发者模式」以获得最佳体验。

## 更新技能

符号链接安装后，更新仓库即自动更新技能（无需重装）：

```bash
cd ~/personal-skills && git pull
# 如果 requirements.txt 有变动：
python3 install.py --pip
```

## 最近更新

**web-novel-downloader v2** (2026-06)：
- **优先整本下载**：新增 ixdzs（ZIP 直链）、Z-Library（EPUB）等整本书站下载模式，比逐章爬取快 100x+
- **Scrapling 后端**：TLS 指纹伪装 + headless browser + Cloudflare Turnstile 绕过
- **智能 digest**：跨源下载时自动写校验摘要、自动打印对比报告
- **兼容层**：Scrapy/Scrapling 元素 API 差异抽象（`_get_href`/`_get_text_list`）
- **分两阶段提取**：窄选择器优先（高置信度），宽选择器兜底

## 兼容性说明

- `SKILL.md`、`scripts/`、`references/`、`requirements.txt` — 两个平台共用
- `agents/openai.yaml` — 仅 Codex 使用（Claude Code 会忽略此目录）
- 所有路径使用相对路径，安装到任意位置均可使用
