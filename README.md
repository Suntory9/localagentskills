# LocalAgentSkills

统一管理本地 Agent Skills 的仓库。当前仓库集中保存 Claude Code / Codex 可复用的 skills，默认按项目安装。

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
install.py                  # CLI 主实现
```

## 安装方式：安装到项目

### 安装 CLI 依赖

推荐先安装 Python 依赖以获得最佳交互体验：

```bash
python3 -m pip install -r requirements.txt
```

依赖包括：

- `rich`：美化表格和 summary 输出
- `InquirerPy`：现代化多选交互界面

缺少依赖时 CLI 会自动回退到基础模式，仍可正常使用。

### 首次安装 CLI

如果当前 shell 还不能直接运行 `localagentskills`，先在本仓库根目录执行一次注册命令：

| 平台 | 命令 |
|---|---|
| macOS / Linux | `./install-cli.sh` |
| Windows PowerShell | `powershell -ExecutionPolicy Bypass -File .\install-cli.ps1` |

注册后重新打开终端，确认命令可用：

```bash
localagentskills list
```

### 项目安装

统一使用 `localagentskills` 把本仓库中的 skill 选择性链接到当前项目：

```bash
# 在当前项目中交互选择并安装 skill 到 .agents/skills
localagentskills install

# 查看可用 skills
localagentskills list

# 查看当前项目安装状态
localagentskills status

# 卸载当前项目中的 skill
localagentskills uninstall
```

`localagentskills install` 会打开多选界面：已安装 InquirerPy 时使用现代化多选，否则回退到手写空格多选。已安装到当前项目的 skill 会显示 `(installed)` 并默认勾选。安装完成后会输出 summary，清晰列出 Added、Already installed、Skipped 等结果。

常用命令：

```bash
localagentskills install web-novel-downloader        # 安装指定 skill 到当前项目
localagentskills install --all                       # 安装全部 skill 到当前项目
localagentskills install --project /path/to/project  # 安装到指定项目
localagentskills list                                # 查看可用 skill（Rich 表格）
localagentskills list --json                         # 查看可用 skill（JSON 输出）
localagentskills uninstall                           # 交互选择卸载当前项目的 skill
localagentskills uninstall jira-submit-to-git        # 卸载当前项目中的指定 skill
localagentskills uninstall --all                     # 卸载当前项目中的全部已安装 skill
localagentskills status                              # 查看当前项目安装状态
localagentskills status --project /path/to/project   # 查看指定项目安装状态
localagentskills status --json                       # JSON 格式输出当前项目状态
```

新增参数：

```bash
--json        # JSON 输出（支持 list / status / install / uninstall）
--no-color    # 禁用彩色输出
--all         # uninstall 中使用，卸载全部已安装 skill
```

安装后目标项目结构大致为：

```text
<project>/
  .agents/skills/<skill-name>  ->  本仓库 skills/<skill-name>
  .claude/skills               ->  ../.agents/skills
```

安装流程会：

- 使用现代化多选界面（InquirerPy）或回退空格多选，已安装的 skill 会显示标识并默认选中。
- 安装结束后输出结构化 summary，列出 Added、Already installed、Skipped、Replaced 等。
- 给 Git 项目自动把 `.agents` 和 `.claude` 加入 `.gitignore`。
- 默认使用软链接，因此更新本仓库后，目标项目会使用最新本地版本。

## 全局安装（可选）

全局安装会把 skill 安装到 `~/.claude/skills` 和 `~/.codex/skills`，适合需要跨所有项目可用的场景：

```bash
localagentskills install --global                    # 交互选择并全局安装 skill
localagentskills install --global tdd                # 全局安装指定 skill
localagentskills install --global --all              # 全局安装全部 skill
localagentskills install --global --target claude    # 只装到 Claude Code
localagentskills install --global --target codex     # 只装到 Codex
localagentskills install --global --pip              # 同时安装 requirements.txt 依赖
localagentskills uninstall --global                  # 交互选择并卸载全局 skill
localagentskills uninstall --global tdd              # 卸载指定全局 skill
localagentskills uninstall --global --all            # 卸载全部全局 skill
localagentskills status --global                     # 查看全局安装状态
```

注意：`localagentskills` 安装的是 skill 文档和随 skill 提供的脚本，不会自动安装外部工具本体。
例如 `agent-reach` 仍需要本机存在 `agent-reach` CLI；Windows 下可先用
`Get-Command agent-reach` 或 `agent-reach --version` 验证，缺失时按该 skill 的官方安装指南修复。

## Skill 列表

<!-- SKILLS_TABLE_START -->
| Skill | 描述 | 来源 | 更新策略 |
|---|---|---|---|
| [agent-reach](skills/agent-reach/) | MUST USE when user wants to 调研/research/搜索/search/查/找/look up anything on the internet — e.g. 全… | [GitHub](https://github.com/Panniantong/Agent-Reach) | 脚本同步 |
| [ai-spend-audit](skills/ai-spend-audit/) | 分析最近 N 天(默认 7 天,支持任意天)的全部 AI 耗量与花费,横跨 Claude Code、Codex、XDT Maker、OpenClaw 等本地 session,可通过 prov… | 自制 | 本地维护 |
| [codex-review](skills/codex-review/) | Codex code review closeout: local dirty changes, PR branch vs main, parallel tests. | 自制 | 本地维护 |
| [diagnosing-bugs](skills/diagnosing-bugs/) | Diagnosis loop for hard bugs and performance regressions. Use when the user says "diagnose"/"de… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [find-skills](skills/find-skills/) | Helps users discover and install agent skills when they ask questions like "how do I do X", "fi… | [网上](https://skills.sh/) | 手动 diff 同步 |
| [git-cherry-pick](skills/git-cherry-pick/) | Ports a batch of commits from a source git branch onto the current branch using cherry-pick, in… | 自制 | 本地维护 |
| [grill-me](skills/grill-me/) | A relentless interview to sharpen a plan or design. | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [grill-with-docs](skills/grill-with-docs/) | A relentless interview to sharpen a plan or design, which also creates docs (ADR's and glossary… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [grilling](skills/grilling/) | Interview the user relentlessly about a plan or design. Use when the user wants to stress-test… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [handoff](skills/handoff/) | Compact the current conversation into a handoff document for another agent to pick up. | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [improve-codebase-architecture](skills/improve-codebase-architecture/) | Scan a codebase for deepening opportunities, present them as a visual HTML report, then grill t… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [jira-submit-to-git](skills/jira-submit-to-git/) | Submit Jira-related local changes from one of the configured XD repositories directly to the re… | 内部 | 本地维护 |
| [jira-unity-to-tw](skills/jira-unity-to-tw/) | Move Jira-related Unity commits onto the TW branch in this project, with commit lookup, depende… | 内部 | 本地维护 |
| [last30days](skills/last30days/) | Research what people actually say about any topic in the last 30 days. Pulls posts and engageme… | [GitHub](https://github.com/mvanhorn/last30days-skill) | 脚本同步 |
| [pdf](skills/pdf/) | Use when tasks involve reading, creating, or reviewing PDF files where rendering and layout mat… | 第三方 | 手动 diff 同步 |
| [prototype](skills/prototype/) | Build a throwaway prototype to flesh out a design — a runnable terminal app for state/business-… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [tdd](skills/tdd/) | Test-driven development. Use when the user wants to build features or fix bugs test-first, ment… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [tech-doc-style-chinese](skills/tech-doc-style-chinese/) | 在撰写、改写或审阅中文技术文档、文档首页、产品文案、界面文案、Markdown 文档或接口说明时使用。采用克制、准确、可扫读的中文技术写作风格：避免第二人称和宣传腔，统一使用直角引号，在可见… | [GitHub](https://github.com/Fenng/tech-doc-style-chinese.git) | 脚本同步 |
| [to-issues](skills/to-issues/) | Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker usi… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [to-prd](skills/to-prd/) | Turn the current conversation into a PRD and publish it to the project issue tracker — no inter… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [triage](skills/triage/) | Move issues and external PRs through a state machine of triage roles — categorise, verify, gril… | [GitHub](https://github.com/mattpocock/skills) | 脚本同步 |
| [ttdbl2-unity-prefab-view-builder](skills/ttdbl2-unity-prefab-view-builder/) | Build or adapt Unity uGUI prefabs and matching Lua Views for the ttdbl2_unity client. Use when… | 内部 | 本地维护 |
| [unity-mcp-skill](skills/unity-mcp-skill/) | Orchestrate Unity Editor via MCP (Model Context Protocol) tools and resources. Use when working… | 第三方 | 手动 diff 同步 |
| [web-novel-downloader](skills/web-novel-downloader/) | Use this skill when the user gives a web novel name (or a chapter-list URL) and wants to downlo… | 自制 | 本地维护 |
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

当前仍需补充原始来源的第三方条目：`pdf`、`unity-mcp-skill`。补齐后把它们从 `third-party` 改为更准确的 `github` / `web`，并填入 `source`。

## 新增 skill 流程

1. 在 `skills/<skill-name>/` 下添加 `SKILL.md`。
2. 如果需要脚本或参考资料，放入该 skill 目录下的 `scripts/`、`references/` 或 `agents/`。
3. 在 `skills-manifest.json` 中登记来源、更新策略和备注。
4. 运行：

   ```bash
   localagentskills update --no-pull --no-sync
   ```

   这会自动补全 manifest 中缺失的条目、更新 schema、重新生成 README skill 表格并审计。

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
   localagentskills update --no-pull --no-sync
   ```

   这会补全 manifest、更新 schema、重新生成 README 表格并审计。注意：**不要直接用上游内容覆盖本地 skill**，除非确认该 skill 没有本地适配。

## 维护命令

`localagentskills update` 一站式完成仓库维护，依次执行：

1. `git pull origin main`
2. 扫描 `skills/`，将新增 skill 补入 `skills-manifest.json`，清理已删除条目
3. 按 manifest 中的 GitHub 来源拉取最新内容，覆盖对应 `skills/<skill-name>/`
4. 更新 `skills-manifest.schema.json`
5. 重新生成 README skill 表格
6. 运行审计检查（manifest 覆盖、frontmatter、README 一致性）

```bash
localagentskills update              # 完整更新
localagentskills update tdd          # 只同步指定 skill
localagentskills update --no-pull    # 跳过 git pull
localagentskills update --no-sync    # 跳过在线同步（新增 skill 后常用）
localagentskills update --no-readme  # 跳过 README 和审计
```

注意：有 GitHub `source` 的 skill 会被网上最新版本覆盖；本地自制、内部或未登记来源的 skill 不会被在线内容覆盖。

底层脚本可直接调用，适合 CI 或调试场景：

```bash
python3 scripts/generate-readme.py   # 仅重新生成 README 表格
python3 scripts/audit-skills.py      # 仅检查 manifest、frontmatter 和 README
```

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
