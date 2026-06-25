# LocalAgentSkills

统一管理本地 Agent Skills 的仓库。当前仓库集中保存 Claude Code / Codex 可复用的 skills，并提供两种安装方式：

- **推荐**：按项目安装到 `<project>/.agents/skills`，再让 `<project>/.claude/skills` 指向同一份目录。
- **备用**：全局安装到 `~/.claude/skills` / `~/.codex/skills`。

## 这个仓库解决什么问题

- 集中保存所有本地 skill，避免分散在不同项目或用户目录里。
- 支持按项目选择性启用 skill，减少每个项目的上下文污染。
- 同一份 skill 可以被 Claude Code、Codex 或项目级 agent 配置复用。
- 为 GitHub / 网上来源 / 自制 / 内部定制 skill 记录来源，方便未来同步更新。
- 用软链接安装，仓库更新后目标项目可自动使用最新本地版本。

## 目录结构

```text
skills/
  <skill-name>/
    SKILL.md          # skill 定义，必须存在
    scripts/           # 可执行脚本，可选
    references/        # 参考文档，可选
    agents/            # Codex 专用配置，可选

scripts/
  generate-readme.py   # 根据 SKILL.md 和 skills-manifest.json 生成 README skill 表格
  audit-skills.py      # 检查 manifest 覆盖、frontmatter 和 README 生成状态

skills-manifest.json        # skill 来源、同步策略和维护备注
skills-manifest.schema.json # manifest 字段约束说明
localagentskills            # macOS / Linux CLI 入口
localagentskills.ps1        # Windows PowerShell CLI 入口
localagentskills.cmd        # Windows cmd CLI 入口
install-cli.sh              # macOS / Linux: 注册 localagentskills 到 ~/.local/bin
install-cli.ps1             # Windows: 注册 localagentskills 到用户 PATH
skill-install.sh            # 兼容入口：安装到指定项目
install.py                  # CLI 主实现；也兼容旧的 python install.py 用法
```

## 推荐安装方式：安装到某个项目

推荐使用 `localagentskills` 把本仓库中的 skill 选择性链接到当前项目：

```bash
# macOS / Linux: 注册 localagentskills 到 ~/.local/bin
./install-cli.sh

# Windows: 注册 localagentskills 到当前用户 PATH
powershell -ExecutionPolicy Bypass -File .\install-cli.ps1

# 在当前项目中交互选择并安装 skill 到 .agents/skills
localagentskills install
```

`localagentskills install` 会打开空格多选界面：`↑/↓` 或 `j/k` 移动，空格勾选，`Enter` 确认，`Esc` 退出。已经安装到当前项目的 skill 会显示 `(installed)` 并默认勾选。

常用命令：

```bash
localagentskills install web-novel-downloader        # 安装指定 skill 到当前项目
localagentskills install --all                       # 安装全部 skill 到当前项目
localagentskills install --project /path/to/project  # 安装到指定项目
localagentskills list                                # 查看可用 skill
localagentskills uninstall                           # 卸载当前项目中的全部 skill
localagentskills uninstall jira-submit-to-git        # 卸载当前项目中的指定 skill
```

安装后目标项目结构大致为：

```text
<project>/
  .agents/skills/<skill-name>  ->  本仓库 skills/<skill-name>
  .claude/skills               ->  ../.agents/skills
```

安装流程会：

- 支持空格多选，已安装的 skill 会显示标识并默认选中。
- 给 Git 项目自动把 `.agents` 和 `.claude` 加入 `.gitignore`。
- 默认使用软链接，因此更新本仓库后，目标项目会使用最新本地版本。

兼容入口 `skill-install.sh` 仍可使用：

```bash
./skill-install.sh /path/to/project
```

## 备用安装方式：全局安装到用户目录

全局安装会把 skill 安装到：

```text
~/.claude/skills
~/.codex/skills
```

常用命令：

```bash
localagentskills install --global                    # 全局安装全部 skill
localagentskills install --global --target claude    # 只装到 Claude Code
localagentskills install --global --target codex     # 只装到 Codex
localagentskills install --global --pip              # 同时安装 requirements.txt 依赖
localagentskills uninstall --global                  # 卸载全局安装的 skill
```

旧入口 `python3 install.py --list`、`python3 install.py --uninstall` 暂时保留，用于兼容已有脚本。

## Skill 列表

<!-- SKILLS_TABLE_START -->
| Skill | 描述 | 来源 | 更新策略 |
|---|---|---|---|
| [agent-reach](skills/agent-reach/) | MUST USE when user wants to 调研/research/搜索/search/查/找/look up anything on the internet — e.g. 全… | [GitHub](https://github.com/Panniantong/Agent-Reach) | 脚本同步 |
| [ai-spend-audit](skills/ai-spend-audit/) | 分析最近 N 天(默认 7 天,支持任意天)的全部 AI 耗量与花费,横跨 Claude Code、Codex、XDT Maker、OpenClaw 等本地 session,可通过 prov… | 自制 | 本地维护 |
| [caveman](skills/caveman/) | Ultra-compressed communication mode. Cuts token usage ~75% by dropping filler, articles, and pl… | 自制 | 本地维护 |
| [codex-review](skills/codex-review/) | Codex code review closeout: local dirty changes, PR branch vs main, parallel tests. | 自制 | 本地维护 |
| [diagnose](skills/diagnose/) | Disciplined diagnosis loop for hard bugs and performance regressions. Reproduce → minimise → hy… | 自制 | 本地维护 |
| [find-skills](skills/find-skills/) | Helps users discover and install agent skills when they ask questions like "how do I do X", "fi… | [网上](https://skills.sh/) | 手动 diff 同步 |
| [git-cherry-pick](skills/git-cherry-pick/) | Ports a batch of commits from a source git branch onto the current branch using cherry-pick, in… | 自制 | 本地维护 |
| [grill-me](skills/grill-me/) | A relentless interview to sharpen a plan or design. | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [grill-with-docs](skills/grill-with-docs/) | A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [handoff](skills/handoff/) | Compact the current conversation into a handoff document for another agent to pick up. | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [hatch-pet](skills/hatch-pet/) | Create, repair, validate, preview, and package Codex-compatible animated pets and pet spriteshe… | 第三方 | 手动 diff 同步 |
| [improve-codebase-architecture](skills/improve-codebase-architecture/) | Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill t… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [jira-fullstack-orchestrator](skills/jira-fullstack-orchestrator/) | Use this skill when a Jira-driven feature needs coordinated planning and execution across multi… | 内部 | 本地维护 |
| [jira-proto-to-main](skills/jira-proto-to-main/) | Given a Jira issue such as TTDBL-42165, locate the corresponding proto commits in /Users/songdc… | 内部 | 本地维护 |
| [jira-submit-to-git](skills/jira-submit-to-git/) | Submit Jira-related local changes from one of the configured XD repositories directly to the re… | 内部 | 本地维护 |
| [jira-unity-to-main](skills/jira-unity-to-main/) | Read a Jira issue, extract its summary, review and validate existing local Unity changes, then… | 内部 | 本地维护 |
| [jira-unity-to-tw](skills/jira-unity-to-tw/) | Move Jira-related Unity commits onto the TW branch in this project, with commit lookup, depende… | 内部 | 本地维护 |
| [last30days](skills/last30days/) | Research what people actually say about any topic in the last 30 days. Pulls posts and engageme… | [GitHub](https://github.com/mvanhorn/last30days-skill) | 脚本同步 |
| [pdf](skills/pdf/) | Use when tasks involve reading, creating, or reviewing PDF files where rendering and layout mat… | 第三方 | 手动 diff 同步 |
| [prototype](skills/prototype/) | Build a throwaway prototype to flesh out a design — a runnable terminal app for state/business-… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [setup-matt-pocock-skills](skills/setup-matt-pocock-skills/) | Configure this repo for the engineering skills — set up its issue tracker, triage label vocabul… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [tdd](skills/tdd/) | Test-driven development. Use when the user wants to build features or fix bugs test-first, ment… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [tech-doc-style-chinese](skills/tech-doc-style-chinese/) | 在撰写、改写或审阅中文技术文档、文档首页、产品文案、界面文案、Markdown 文档或接口说明时使用。采用克制、准确、可扫读的中文技术写作风格：避免第二人称和宣传腔，统一使用直角引号，在可见… | [GitHub](https://github.com/Fenng/tech-doc-style-chinese.git) | 脚本同步 |
| [to-issues](skills/to-issues/) | Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker usi… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [to-prd](skills/to-prd/) | Turn the current conversation into a PRD and publish it to the project issue tracker — no inter… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [triage](skills/triage/) | Move issues and external PRs through a state machine of triage roles — categorise, verify, gril… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [ttdbl2-unity-prefab-view-builder](skills/ttdbl2-unity-prefab-view-builder/) | Build or adapt Unity uGUI prefabs and matching Lua Views for the ttdbl2_unity client. Use when… | 内部 | 本地维护 |
| [unity-mcp-skill](skills/unity-mcp-skill/) | Orchestrate Unity Editor via MCP (Model Context Protocol) tools and resources. Use when working… | 第三方 | 手动 diff 同步 |
| [web-novel-downloader](skills/web-novel-downloader/) | Use this skill when the user gives a web novel name (or a chapter-list URL) and wants to downlo… | 自制 | 本地维护 |
| [xdoa-skill](skills/xdoa-skill/) | 用于 XDOA CLI 安装配置、升级指引、能力路由和 OA 任务执行规划。当用户想安装或升级 xdoa、了解 xdoa 能做什么、判断应使用哪类 XDOA 工作流，或通过 xdoa 处理公… | 内部 | 本地维护 |
| [zoom-out](skills/zoom-out/) | Tell the agent to zoom out and give broader context or a higher-level perspective. Use when you… | 自制 | 本地维护 |
<!-- SKILLS_TABLE_END -->

## 来源与同步策略

每个 skill 的来源记录在 [`skills-manifest.json`](skills-manifest.json)。建议使用以下分类：

| 类型 | 含义 |
|---|---|
| `custom` | 自制或主要由本地维护的 skill |
| `github` | 来自 GitHub 仓库的 skill |
| `web` | 来自网页、skills 目录站点或非 GitHub 来源 |
| `third-party` | 第三方来源，但原始 URL 尚未完全确认 |
| `internal` | 内部项目或内部系统相关 skill |

同步策略建议：

| 策略 | 含义 |
|---|---|
| `local` | 本地维护，不从上游自动同步 |
| `manual-diff` | 有上游来源，但同步前必须先 diff，再人工合并 |
| `script` | 可用脚本同步 |
| `git-subtree` | 使用 git subtree 跟踪上游 |

当前建议先使用 **vendored copy + manifest + manual diff**：第三方 skill 复制到本仓库中，记录上游 URL 和本地改动说明；需要更新时先拉取上游到临时目录，diff 后再合并，避免覆盖本地适配。

当前仍需补充原始来源的第三方条目：`hatch-pet`、`pdf`、`unity-mcp-skill`。补齐后把它们从 `third-party` 改为更准确的 `github` / `web`，并填入 `source`。

## 新增 skill 流程

1. 在 `skills/<skill-name>/` 下添加 `SKILL.md`。
2. 如果需要脚本或参考资料，放入该 skill 目录下的 `scripts/`、`references/` 或 `agents/`。
3. 在 `skills-manifest.json` 中登记来源、更新策略和备注。
4. 运行 README 生成脚本：

   ```bash
   python3 scripts/generate-readme.py
   ```

5. 检查 README 中的 Skill 列表是否正确。

## 更新第三方 skill

建议流程：

1. 从 `skills-manifest.json` 找到 `source`。
2. 将上游内容拉到临时目录。
3. 与本仓库中的 `skills/<skill-name>/` 做 diff。
4. 手动合并需要的变更。
5. 更新 manifest 中的备注，例如上游 commit、同步日期或本地改动说明。
6. 运行：

   ```bash
   python3 scripts/generate-readme.py
   ```

不要直接用上游内容覆盖本地 skill，除非确认该 skill 没有本地适配。

## 维护命令

常用检查命令：

```bash
# 重新生成 README 中的 Skill 表格
python3 scripts/generate-readme.py

# 检查 manifest 覆盖、SKILL.md frontmatter、README 表格是否最新
python3 scripts/audit-skills.py

# 检查 JSON 格式
python3 -m json.tool skills-manifest.json >/dev/null
```

`localagentskills update` 用于维护本仓库本身：

```bash
localagentskills update
```

它会依次执行：

- 拉取当前仓库的 `origin/main`。
- 扫描 `skills/`，把本地新增 skill 自动补进 `skills-manifest.json`。
- 根据 `skills-manifest.json` 直接从 GitHub 拉取最新 skill 内容，并覆盖对应的本地 `skills/<skill-name>/`。
- 重新生成 README 中的 Skill 表格。
- 运行 `scripts/audit-skills.py` 检查 manifest、frontmatter 和 README 状态。

常用选项：

```bash
localagentskills update tdd          # 只同步指定 skill
localagentskills update --no-pull    # 跳过当前仓库 git pull
localagentskills update --no-sync    # 只补 manifest、生成 README 和审计
localagentskills update --no-readme  # 只拉取仓库和在线 skill
```

注意：有 GitHub `source` 的 skill 会被网上最新版本覆盖；本地自制、内部或未登记来源的 skill 不会被在线内容覆盖。

`audit-skills.py` 会检查：

- `skills/` 下每个有效 skill 都已登记到 `skills-manifest.json`。
- manifest 中没有指向不存在 skill 的多余条目。
- 每个 `SKILL.md` 都有 `name` 和 `description` frontmatter。
- README 生成区块与当前 skill/manifest 状态一致。

## 维护约定

- `SKILL.md` 是识别 skill 的必要文件；没有 `SKILL.md` 的目录不会出现在 README 表格中。
- 第三方来源必须尽量记录 `source`、license 和本地改动说明。
- README 的 Skill 表格由脚本生成，不要手动编辑标记区块内的内容。
- 对内部项目相关 skill，避免把敏感链接、token 或账号信息写入公开文档。
- `.DS_Store`、下载产物、虚拟环境等本地文件不应提交。

## 兼容性说明

- `SKILL.md`、`scripts/`、`references/`、`requirements.txt` 通常可被 Claude Code 和 Codex 共用。
- `agents/openai.yaml` 仅 Codex 使用，Claude Code 会忽略该目录。
- 推荐使用相对路径和 skill 内部路径，避免绑定到某台机器的绝对路径。
