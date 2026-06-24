---
name: git-cherry-pick
description: >-
  Ports a batch of commits from a source git branch onto the current branch
  using cherry-pick, including ticket-ID resolution, ordering,
  submodule and large generated-code conflict handling, commits whose message lists
  multiple ticket IDs, revert pairs, empty picks,
  and post-flight diff checks vs source. Use when the user asks to cherry-pick
  from another branch, batch cherry-pick by ticket IDs (e.g. JIRA-style) from a
  file, port commits from a source branch onto release/maintenance branches, or work in
  monorepos with git submodules and large generated sources from IDL/contracts.
---

# git-cherry-pick（批量 cherry-pick 工作流）

本技能描述在多分支、子模块、巨型生成代码（由 **IDL/契约** 驱动、在各语言中的生成物）场景下，**安全、可重复**地完成一批提交的 cherry-pick，并避免常见遗漏（如同一单多提交、**一条提交含多个工单号**、Revert 误匹配、空提交、子模块指针）。

## 适用前提

- 已配置远程；下文命令以 **`origin/<源分支>`** 为例。若实际远程名为 `upstream` 等而非 `origin`，将命令中的远程别名 **`origin`** 一律换成实际名称（如 `upstream/<源分支>`、对应该远程的 `git fetch`）；**不要**对文件路径、分支名等字符串做无差别的全局替换。执行前 **`git fetch`** 更新源分支。
- 工作区有未提交改动时：对**将要被 cherry 触碰的路径**先 **`git stash push`**（默认 stash 不含未跟踪文件；子模块慎用 `stash pop` 覆盖刚对齐的 `gitlink`）。
- 用户给出：**源分支名**（须明确，无仓库级默认；下文均以 `<源分支>` 指代）、**提交列表**（见下）。

## 输入格式

支持两类输入（可并存，最终都解析为 **全哈希列表**）：

1. **工单号 / 标签**：一行一个，如 `PROJ-41995`（用 `git log` 的 `--grep` 解析；见下文陷阱）。
2. **完整或短 commit hash**：直接使用。

- **多行工单号与同一提交**：列表里**不同行**的单号解析后可能得到**相同** hash（常见于**一条提交说明里含多个工单号**）。以 §2 去重后的唯一 hash 为准，只 cherry-pick 一次；细节见 §1「单提交包含多个工单号」与 §6 总结模板。

可来自：用户粘贴；仓库内任意路径的列表文件（例如 `docs/*.md`、工单 `.txt`）；或在客户端里 **`@` 附加工作区中的列表文件**，以**文件正文**为输入（如 Cursor 通过 @ 选文件将内容纳入上下文；若无此能力，则粘贴全文或提供路径由代理读取）。

## 工作流（按顺序执行）

- **混合输入**：已是 **commit hash**（完整或短）的行**不要**走 §1 的 `--grep`，原样纳入待 pick 列表；仅 **工单号 / 标签**行才用 §1 解析。两类结果**合并**后再进入 §2。若某行**无法区分**是工单还是短 hash，以**用户说明**为准或先 `git rev-parse --verify` 试探再决定。

### 1. 解析工单 → commit

对每一行工单号，**先**列出源分支上**全部**匹配的提交（**勿**用 `git log … -1 --grep` 作为唯一手段）：

```bash
git log origin/<源分支> --format=%H --grep="<工单号>"
```

（默认从新到旧输出，**一行一个完整 hash**；条数可能大于 1。`--grep` 按 Git 文档中的**正则**解析，默认**区分大小写**；需要忽略大小写时加 `-i`（以 `git help log` 为准）。单号若含 `.[]*?\+` 等正则元字符，须转义或改用当前版本 `git help log` 提供的**固定字符串**类选项，避免误匹配。）

- **是否 `--first-parent`**：若团队只在合并历史的「主线」上认工单，解析时是否对 `git log` 加 `--first-parent` 以**收窄**命中范围，须**与团队约定**；本技能**不默认**加。

- **无输出**：记「源分支无此 grep 命中」，**勿静默跳过**，须告知用户。
- **仅一行**：该 hash 即本行工单的解析结果（若 subject 仍可疑，可用 `git show -s --oneline <hash>` 复核）。
- **多行**：同一工单在分支上**多次出现**时，`-1` 只会留下其中一条（通常是最新），**其余会被漏掉**——必须结合下列「陷阱与处理」决定保留**哪些** hash（可能需**全部** pick）。

**陷阱与处理（多行或语义需甄别时）：**

- **`--grep` 会匹配 Revert 行**：例如 `PROJ-41214` 可能先命中 `Revert "PROJ-41214…"`。已用无 `-1` 的 `git log` 得到**全部** `%H` 后，配合
  `git log origin/<源分支> --oneline --grep="<工单号>"`
  看 subject，按语义选择：
  - 需要功能 + 回滚：保留 **原始功能提交** 与 **Revert 提交** 两个 hash（用户若要求「revert 也要 pick」，两个都纳入列表）。
  - 仅要最终源分支状态：按源分支上**时间顺序** pick（先功能后 Revert，或反之取决于该分支历史）。
- **同一工单多个非 Revert 提交**：源分支上常拆成「主体」+「小修复」多个 commit；上面 `git log --format=%H` 会输出**多行**，须 **人工确认是否需将全部 hash 都纳入 pick 列表**，避免只 pick 到「修复」而漏「主体」。
- **单提交包含多个工单号**：一条 commit 的 **subject 或正文**里可能出现**多个**工单号（合单、正文多行各带单号、`Co-authored-by` 旁注等）。对用户列表里的**每一个**号分别 `grep` 时，可能都得到**同一 `%H`**——属正常情况。§2 去重后 **只 cherry-pick 该提交一次**；**禁止**因「列表里有两个号却只落了一个新 commit」而重复 pick 同一 hash。收尾总结须写明：**哪些工单号对应同一源 hash**（例如 `PROJ-41951`、`PROJ-41950` → 同一 `%H`），避免被误判为漏合。

### 2. 去重与排序

- 多个工单解析到 **同一 hash** 时只 pick 一次（含 **单提交多工单号**：不同行工单号指向同一提交，仍计 **一个** hash）。
- **按提交时间升序** cherry-pick（先祖先、后子孙），减少上下文冲突：

```bash
# 对每个唯一 hash 取提交时间戳（秒）后 sort -n 得到升序 pick 顺序
git log -1 --format=%ct <hash>
```

（`<hash>` 建议用 §1 输出的**完整** hash，避免短 hash 歧义；若两提交时间戳相同，排序并列时先后可再按拓扑或 subject 约定。**注意**：按**时间戳升序**在多数线性历史上等价于按祖先先后 pick；若本批中存在**彼此无祖先关系**的并列提交（少见），仅靠时间排序仍可能冲突，须结合 `git log --graph` 或与用户约定顺序。）

### 3. 执行 cherry-pick

```bash
git cherry-pick <hash1> <hash2> ...
# 或冲突时逐个：cherry-pick 单个 hash → 解决 → git cherry-pick --continue
# 放弃整段进行中的序列、回到序列开始前：git cherry-pick --abort（见下）
```

- **`--no-edit`**：保持原提交说明（团队有要求时除外）。
- **`-x`**（可选）：若团队要求在新提交说明中可追溯源提交，可使用 **`git cherry-pick -x`**，在说明中追加 `(cherry picked from commit …)`；是否与 `--no-edit` 同用、是否签名策略冲突，以项目规范为准。
- **`--abort`**：当前处于 cherry-pick **进行中**（含冲突未解决）且需**放弃本次 cherry-pick 操作**时执行；仓库会回到**启动本次 `git cherry-pick …` 命令之前**的状态。**区分**：同一条命令里写了**多个** hash、第一个已成功、第二个起冲突后 `abort`，通常**连已成功的也会一并撤销**（整次命令视为一次操作）；若采用**逐个** `git cherry-pick`（每颗单独一条命令），则 `abort` **只撤销当前这一条**，此前已成功落库的提交**保留**。属破坏性操作，**须用户明确确认**（与「安全」一致）。
- **无 merge commit 的约定**：若团队主线为线性/压合习惯、历史中**不出现 merge commit**，则 cherry-pick 列表均为普通提交，**无需** merge 节点专项处理；本技能**不展开** `-m` 等多父场景。若偶发遇到多父提交，与用户核对是否引用错误或另有流程。

### 4. 冲突处理策略（按路径类型）

| 冲突类型 | 建议 |
|----------|------|
| **子模块目录** | 读取**当前正在 pick 的提交**中的 gitlink：`git ls-tree <pick的commit> <子模块路径>`，在子模块内 `git fetch` 后 **`git checkout <该hash>`**，回到上层 **`git add <子模块路径>`**。 |
| **巨型生成代码**（体积大、通常可由脚本从 schema/契约全量重生的检入文件） | 在 cherry-pick 冲突状态下，常可先 **`git checkout --theirs -- <文件>`** 再 `git add`（*theirs* 为**被 cherry 进来的提交**版本）。若与当前分支其它生成输入不同步，后续按项目约定 **重新跑生成脚本**。 |
| **手写业务代码** | **禁止无脑全选 theirs**：对比 HEAD 与 incoming，保留当前分支已存在的 API/行为（例如函数签名已变、分支独有字段或配置键），把对方**意图**合入。 |
| **空 cherry-pick** | `git cherry-pick --skip`（并记录：可能表示补丁已在分支上）。不要 `--allow-empty` 除非用户明确要求留空提交。 |

### 5. 结束后校验（与源分支「是否漏代码」）

- **汇总本批 cherry-pick 涉及的全部文件路径**（对每一个已 pick 的 commit 用 `git show --pretty=format: --name-only <hash>` 或 `git diff-tree --no-commit-id --name-only -r <hash>` 列出变更文件，去重后得到清单），再与源分支做 **定向 diff**（而非整仓库 `git diff`）：
  `git diff HEAD origin/<源分支> -- <路径清单>`
  不得以主观「挑几条看看」代替完整路径清单。比较的是**已提交**的 `HEAD` 与远程跟踪分支 tip；**工作区未提交改动**不在此 diff 内，结论勿与工作区脏状态混淆。
- 对 **同一工单多提交**、**单提交多工单号** 两类场景，用源分支日志再对账：相关 hash 是否都已处理；同一 hash 是否 **未重复** pick。
- 可选：`git cherry -v HEAD origin/<源分支>`（参数顺序为 **`git cherry <upstream> <head>`**，此处 upstream=当前 **HEAD**，head=**源分支**）。输出里 **`+`** 表示该提交相对 HEAD **尚无等价 patch**（常见解读：可能仍漏合）；**`-`** 表示在 HEAD 上**已有等价 patch**（常见解读：可能已 cherry-pick/rebase 过）。仅作辅助：**冲突解决、手工合并会改变 patch-id**，`+`/`-` 与「是否真的漏代码」不完全等价，须结合**本节前段**定向 diff 结论判断。

### 6. 最终输出总结（必填）

工作流收尾时**必须**向用户给出一段结构化总结（可直接用下面模板；无内容的节写「无」）。

```markdown
## Cherry-pick 总结

### 上下文
- **当前分支**：…
- **源分支**：…（远程如 `origin/<源分支>`）
- **输入**：列表文件路径、粘贴的摘要，或通过 `@` 附加进对话的文件（写明其一即可）

### 已 cherry-pick 落库的提交
- 按时间或操作顺序列出：**新 commit hash**（短 hash 即可）+ **原 subject**（含工单号）
- 若同一工单对应多个源端 hash，注明「源 hash → 新 hash」便于对账
- 若 **多个工单号对应同一源提交**（单提交多号），集中写一行：**工单号 A、B、… → 同一源 hash → 新 hash（若有）**，避免阅读者以为只迁了其中一单

### 未执行或已跳过的项
- **空 pick / `--skip`**：列出源 commit 与原因（已与当前树一致、用户要求跳过等）
- **源分支无 grep 命中**的工单号：逐条列出

### 冲突与特殊处理（若有）
- **子模块**（路径 + 当前指向的 commit / detached 说明）
- **生成类文件**：是否采用 `--theirs`、是否已重跑项目约定生成命令等
- **业务代码手工合并**：文件路径 + 保留分支侧行为的一句话（如保留某参数、某分支独有字段）

### 与源分支的定向 diff 结论
- **路径清单来源**：本批涉及文件已汇总（简述数量或范围）
- **命令**：`git diff HEAD origin/<源分支> -- <路径清单>` 的**结论**：是否仍有 diff；若有，说明是预期分支差异（如发布分支独有功能）还是疑似漏合

### 验证
- 已执行：项目构建/测试命令（**写清命令与结果**：通过 / 失败摘要）
- 未执行：说明原因

### 风险与后续建议
- **stash**：是否存在未 pop 的 stash、是否含子模块需谨慎 pop
- **推送**：是否需推子模块、主仓库 push 前检查项
- **`cherry-pick --abort`**：本次流程中是否执行过；若执行过，写明**原因**、是**单次多 hash 命令**还是**逐条 pick**（后者 abort 后此前已成功的提交仍可能在分支上），以及当前是否已脱离「cherry-pick 进行中」状态；若无则写「无」
- **回滚**：若需撤销本批，建议 `git reset --hard` 到何 commit 或 `git revert` 范围（仅建议，不自动执行）

### 相对「整分支对齐源分支」的说明（若用户关心）
- 本批仅迁移列出的工单/提交；与源分支全量差异不属于本次范围（一句话即可）
```

**要点**：总结要**可审计**——他人仅凭文字能复现「做了什么、没做什么、还剩什么风险」，而不是只有「完成了」三个字。

## 示例：工单列表文件

文件内容示例（一行一个）：

```text
PROJ-41995
PROJ-41992
PROJ-41214
```

对 `PROJ-41214` 必须先 `git log origin/<源分支> --oneline --grep="PROJ-41214"` 看到功能提交与 Revert 两行，再按用户要求是否两者都 pick。

## 示例：「一单多提交」

源分支上可能出现：

- Commit A：功能主体（模型、协议、核心业务改动等）。
- Commit B：紧随其后的单行或小范围修复。

仅 grep 取 `-1` 容易只得到 B 或只 pick 到「看似空」的补丁。**必须**列出 A、B（及更多）hash 并依次 pick（或与用户确认只要其中一部分）。

## 示例：单提交多工单号

源分支上**一次**提交的说明里可含**多个**工单号（如正文多行、每行一个单号，或 subject 与正文各带单号）。若用户列表里同时写了 `PROJ-41951` 与 `PROJ-41950`，分别对两号执行本节开头的 `git log … --format=%H --grep="<单号>"`，可能**各自仅一行输出**且两行 **hash 相同**。按 §2 去重后 **只 cherry-pick 一次**；总结中写明两号（或多号）**共享**该源提交及 pick 后的新 hash，避免被理解成「少 pick 了一单」。

## 与「整分支对齐源分支」的区别

本技能是 **按列表 cherry-pick 一批提交**，不负责把当前分支变成源分支的完整副本。当前分支与 **`<源分支>`** 全量相差大量提交是常态；回答「有没有遗漏」时要区分：

- **本批工单/提交**是否都已落库（含多提交、Revert）；
- 用户是否还要求 **整条分支与源分支逐提交一致**：属于另行约定的大范围同步（如 rebase 等），**不是**本技能默认目标。在**无 merge commit** 的团队习惯下，此处**不讨论**带 merge 节点的合入策略。

## 安全

- 不在日志中输出 token、密码。
- 破坏性操作（`reset --hard`、`push -f`、`git cherry-pick --abort` 等）前需用户明确确认；本技能默认不执行。
