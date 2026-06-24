---
name: ai-spend-audit
description: 分析最近 N 天(默认 7 天,支持任意天)的全部 AI 耗量与花费,横跨 Claude Code、Codex、XDT Maker、OpenClaw 等本地 session,可通过 providers.json 扩展更多写本地 token 日志的工具(Pi / OpenCode 等)。把 token 用量按公开 API 价格折算成美元做统一标尺,给出按来源/模型/任务/项目的花费占比,定位浪费:跑飞的死循环 session、低缓存复用率、用高级模型做小任务的降级候选、烧钱的定时任务。触发词:AI 耗量/用量分析、审计 AI 耗量/用量、耗量审计、审计一下我的用量、花了多少钱、cost/spend 分析、token 消耗、哪里浪费、性价比、降本、看看我的 AI 账单。
---

# AI Spend Audit

把散落在本机各处的 AI session 拉到一起,折算成钱,告诉用户:钱花在哪、占比多少、哪里有浪费、哪里能省。

只要用户说类似「分析下我最近的 AI 耗量 / 看看钱花哪了 / 哪里浪费了 / 哪些能用便宜模型 / 我的 AI 账单」,就用本 skill。

## 数据来源(自动发现 + 去重)

内置(随脚本始终运行,数据存在才生效):
1. **Claude Code CLI** — `$CLAUDE_CONFIG_DIR/projects`、`~/.config/claude/projects`、`~/.claude/projects` 下的 `*.jsonl`(逐条 message 的 token)
2. **Codex** — `$CODEX_HOME`、`~/.codex`、(若有)XDT 自管的 `<xdt>/codex-home` 的 `sessions/**` + `archived_sessions/`(rollout token_count,按 session id 去重)
3. **XDT Maker**(可选,有其 sqlite 才启用)— `~/Library/Application Support/xdt-maker/*.db`(真实计费 ledger + 最全元数据 + 定时任务)

配置驱动(`providers.json`,没装就静默跳过):
4. **OpenClaw** — `~/.openclaw`:每个 agent 的嵌套 `codex-home`(标准 Codex 格式,权威)+ 原生 `sessions/*.jsonl`(只补非 Codex 后端,避免与 codex-home 重复)。
5. **Pi / OpenCode-Go** 及任意自定义工具(见下「扩展」)。

XDT Maker 通过 SDK 跑的 Claude session 也会落到 `~/.claude/projects`,脚本按 `sdk_session_id` 归并,**不会重复计算**。OpenClaw 的数据通常在**另一台机器**上——把脚本拷过去在那台机器跑(`analyze.py` 纯标准库)。细节见 `references/data-sources.md`。

## 通用性:扩展更多本地 token 工具(`providers.json`,无需改代码)

这是个**通用** skill,但**只做一件事、做扎实:能从本地可靠拿到「逐条 token」的工具,才折算成本。** 这是范围红线——别为了"支持得多"去接那些拿不到 token 的工具(见下方「明确不支持」)。格式知识用 [steipete/CodexBar](https://github.com/steipete/CodexBar) 交叉验证过。

已支持:
- 内置三源:Claude Code、Codex、XDT Maker。
- `Pi`(`format: pi_jsonl`)— `~/.pi/agent/sessions/**/*.jsonl`;Pi 代理上游,openai-codex→gpt-5.x 计价、anthropic→claude 计价。默认 enabled(没装就静默跳过)。
- `OpenCode-Go`(`format: opencode_sqlite`)— 本地 `opencode.db` 里存的是**预算好的美元**(无 token 明细),直接记账。
- 任意其它写 token JSONL 的工具:在 `providers.json` 加一条 `generic_jsonl`,**不用改代码**:

```json
{ "name": "MyTool", "format": "generic_jsonl", "billing": "metered", "enabled": true,
  "roots": [{"env": "MYTOOL_HOME", "path": "~/.mytool/sessions", "glob": "**/*.jsonl"}],
  "fields": {"type_key":"type","type_value":"assistant","model":"message.model",
             "ts":["timestamp","message.timestamp"],
             "input":["message.usage.input_tokens","message.usage.input"],
             "output":["message.usage.output_tokens"],
             "cache_read":["message.usage.cache_read_input_tokens"],
             "cached_in_input": false} }
```
  - `fields` 每项是**点路径**或**别名列表**(命中第一个非空)。`ts` 省略则按文件 mtime 估窗口;`type_key/type_value` 过滤行;`cached_in_input:true` 用于"input 已含缓存"的厂商,避免缓存重复计费;`billing` 覆盖整工具的计费口径。`roots` 不存在 → 静默跳过。验证好后 `format_verified` 标 `true`。

- 已内置价表的厂商:Anthropic(opus/sonnet/haiku)、OpenAI(gpt-5.x,含 priority/272k 档)、Google Gemini、xAI Grok、DeepSeek。**未知模型**触发 `UNKNOWN MODEL PRICING` 警告 → 按价格规则联网核实官方价后写进 `pricing.json`。
- **覆盖范围板块**:报告末尾有一张「覆盖范围(本机探测的工具)」表,逐个列出每个 provider 的状态——`有数据` / `已装·窗口内无数据` / `未安装` / `未启用`。让用户一眼看到 skill **查了哪些工具**,而不只是查到了什么(给别人用时尤其重要)。`providers.json` 的 `_roadmap_local_token_tools` 里记了下一批可加的本地 token 工具(Continue.dev / Aider / Cline / Roo / Zed,路径待核实)。

### 明确不支持(范围红线 —— 别再尝试接)
有些工具**不写可靠的本地逐条 token**,只有"额度% / 美元余额"这类鉴权接口(cookie / app token,且会过期)。**它们一律不纳入**——产出的是百分比/美元而非 token、鉴权脆、维护成本高。已评估并**故意排除**:**Gemini CLI、Amp、Grok、DeepSeek、Cursor、Copilot、Windsurf**。
- 典型是 **Cursor**:本地 `state.vscdb` 只有 **chat 模式**的 token(**agent 模式 = 0**),服务端**根本不给 token**、只给月度美元/百分比(连 CodexBar 都标 `supportsTokenCost:false`)。拿不全、不可靠 → 不做。
- **规则**:判断一个工具能不能支持,**先真去翻它的本地数据**(`find` / 开 sqlite),确认有「逐条 token」再接;只有额度/美元的,不接。`providers.json` 的 `_not_supported` 注记里有完整名单和原因。

## 怎么跑

引擎是 `scripts/analyze.py`(纯 Python 标准库 + sqlite3,只读)。**先跑脚本,再读它的输出来组织回答**——不要自己去读那些巨大的 jsonl / 602MB sqlite,会爆 context。

```bash
# 最近 7 天(默认),终端打印 markdown
python3 ~/.claude/skills/ai-spend-audit/scripts/analyze.py --days 7

# 最近 1 天
python3 ~/.claude/skills/ai-spend-audit/scripts/analyze.py --days 1

# 存档 markdown 报告到 skill 自己的 reports/(稳定、已 gitignore)
python3 ~/.claude/skills/ai-spend-audit/scripts/analyze.py --days 7 \
    --out ~/.claude/skills/ai-spend-audit/reports --quiet

# 需要结构化数据做追问时,用 --json 走 stdout(不落盘),自己 parse:
python3 ~/.claude/skills/ai-spend-audit/scripts/analyze.py --days 7 --json --quiet
```

常用参数:`--days N`、`--end YYYY-MM-DD`(默认现在)、`--top N`(榜单条数)、`--pricing PATH`(改价表)、`--providers PATH`、`--out DIR`、`--json`、`--quiet`。**全程只读、不联网**(纯本地 token 分析)。

存档约定:**`--out` 只写一个 `.md` 报告文件**(不再产 `.json`)。要逐 session 明细时单独用 `--json`(打到 stdout、不落盘);只有 `--out` 和 `--json` 同时给才会额外写一个 `.json` 文件。

默认行为:**跑一次(带 `--out` 存档到 skill 的 `reports/` 目录,别用 `/tmp`——它会被清且不稳定),把脚本输出读进来,再用中文给用户一份有判断、有建议的总结**。`--out` 时脚本会向 stderr 打印 `.md` 的 `file://` 绝对路径,直接拿来用。

**给文件路径时(关键 UX):** 用**一条 `.md` 的 `file://` markdown 链接**,例如 `[报告](file:///abs/path/spend-7d-YYYYMMDD.md)`。**绝不要**用 `dir/spend.{md,json}` 这种 shell 简写,也不要只贴裸路径——XD Maker 不会把简写/裸路径变成可点链接,用户就打不开。

`reports/` 已 gitignore,但报告含 session 标题、路径、ID 等敏感信息;不要公开贴完整产物。

## 计费模式规则(订阅 vs 按量,决定怎么解读美元)

**先判断每个渠道是「包月订阅」还是「按量 API」,口径完全不同**(配置在 `pricing.json` 的 `billing`,按模型族:`claude` / `codex`;analyzer 用 `billing_of()` 落到每个 session)。

- **按量 API(metered,如 Claude/XDT)**:美元 = **真金白银**。volume 和 waste 都要管;省下的 token 就是省下的钱。XDT 的 `daily_spend` 就是这条渠道实际花掉的现金。
- **包月订阅(subscription,如 Codex = ChatGPT Pro / unlimited)**:边际成本 ≈ **$0**。美元只是 **API-等价 what-if**,不是账单。**在这条渠道多用是合理的** —— 不要因为"美元大"就建议少用。只需找**可节约的浪费 token**:死循环 / 跑飞的自动化 / 遗留 cron / 重复重建缓存 / 用高配模型干 trivial 活(浪费的是配额和时间,不是钱)。

判定来源(写规则,别猜):Codex 看 rollout 的 `rate_limits.plan_type` / XDT `account_usage_snapshots`(pro + unlimited → 订阅);Claude 看是否 `ANTHROPIC_API_KEY` / `CLAUDE_CODE_PROVIDER_MANAGED_BY_HOST`(→ 按量)还是纯 `oauthAccount`(→ 订阅)。**拿不准就问用户**,别替用户假设。`pricing.json` 的 `billing` 给的是一组通用默认(Claude/XDT=按量、Codex=包月),用户账号不同就改它。

报告里:总览会并列「真金白银(按量)」与「what-if(包月)」两个数;浪费清单每条标 `[按量·真金]` / `[包月·$0边际]`;建议必须按这个分:**按量渠道优先省钱,包月渠道只清浪费**。

## 必须向用户讲清的「价格口径」(关键,别让用户误解)

报告里的美元是 **token 用量 × 公开 API 标价** 折算的**统一标尺**,不是真实账单。用户若是订阅制,实际现金远低于此。脚本会同时给出 XDT Maker 自己的 `daily_spend`(真实现金,折扣价口径),两者通常差一个数量级(标尺 ≫ 真实现金),**这是订阅折扣,不是 bug**。

- 想知道「**资源到底消耗在哪、哪里浪费、占比**」→ 看 token 折算标尺(它如实反映消耗;订阅 ledger 因 cache 极便宜会把重度消耗藏起来)。
- 想知道「**真实烧了多少现金**」→ 看 XDT ledger。

回答里第一段就要点明这个口径,避免用户被大数字吓到或误读。

## 怎么把脚本输出变成「有判断的报告」

脚本只给结构化信号(表格 + flag 候选)。你要在上面加判断和可执行建议:

1. **总览**:窗口内统一标尺总额 + 真实现金 ledger + 各来源占比。一句话定性(钱主要在哪个来源/模型/任务)。
2. **占比(三个正交维度,别混)**:报告给「按来源(宿主 App)」「按模型」「按 来源×模型 交叉」「按项目(工作目录)」。三个维度互不相等,**最容易混的是「宿主 App」和「项目」**:
   - **宿主 App** = session 实际在哪个工具里跑的(以 Codex rollout 的 `originator` / Claude transcript 的 entrypoint 为准)。**XDT Maker 是聚合器,会把你在 Codex Desktop 里跑的 session 收录进它的库 —— 但那些宿主是 Codex,不是 XDT**;只有 XDT 真正编排的(orca worker/lead,`orca_role` 非空)才算 XDT 宿主。别因为"在 XDT 库里"或"项目叫 xdt-maker"就判成 XDT 宿主。
   - **项目** = session 在改哪个 codebase(cwd,如 `my-app` / `api-server` / `docs`)。一个在 Codex Desktop 里改 `my-app` 仓库的 session:宿主=Codex,项目=my-app。
   - **务必区分 token 占比 vs 美元占比**:便宜模型(gpt-5.x)常常 token 大头但美元小头,贵模型(opus)反之——只看美元会把高量廉价的 Codex 藏起来,总览已并列两种占比。
3. **浪费定位**(把脚本的 flag 翻译成行动):
   - `runaway`(标记 `花费偏高`):花费明显偏高的 session(> 中位数 6 倍且 ≥ $5)。可能是死循环 / 跑飞的自动化 / 复用同一 session 导致 context 越滚越大,也可能是合理的重活。逐个看 turns、时长、title 判断是否合理。
   - `low_cache`(缓存复用率低,不是严格 hit rate):多轮 session 中大量 input 未复用缓存、被反复重发。建议:稳定 prompt 前缀、复用 session、别频繁清上下文、把易变内容后置。
   - `downgrade`(标记 `大材小用`):opus / gpt-5.x 且 high/xhigh effort 干了点小事(输出小、turn 少)。建议:这类任务作为「降级候选(需人工确认)」,再决定是否换 Haiku/Sonnet 或调低 effort。给出「这批共 $X、N 个 session 是降级候选」。
   - **定时任务**:看「Scheduled / recurring jobs」表。高频 + opus + 复用 session 往往是头号黑洞(典型:每 2 小时一次的巡检)。建议:降频、换便宜模型、每次开新 session 避免 context 累积、或缩小巡检范围。
   - **思考深度(effort)与快速模式**:看「思考深度与快速模式」板块。
     - **effort**:xhigh/high = reasoning token 多、更慢。Codex 常默认顶格 xhigh —— 包月($0)钱上无影响,但日常/简单任务降到 high/medium 省配额和时间;Claude 的 xhigh 是按量真金(reasoning 越深 output 越多越贵),按需才用。
     - **快速模式(fast / priority)**:价格杠杆且很贵 —— **Opus fast = 2×($30/$150);Codex priority = 2.5×($12.5/$75/缓存$1.25,已与 CodexBar 交叉验证)**。识别方式:Claude 按 `usage.speed=='fast'`;Codex **逐 turn** 从 `~/.codex/logs_2.sqlite`(websocket 请求的 `service_tier`)判定,日志没覆盖的 turn 回退 `~/.codex/config.toml` 的 service_tier。另有 272k input 阈值档(非 priority 且 >272k → $10/$45/$1)。按量渠道开 fast = 真金白银翻倍;包月渠道开 priority 多烧配额。建议:只在确实需要低延迟时开,日常关掉。
4. **建议**:给 3–5 条**具体、可执行、按预计省钱排序**的优化项(改哪个 schedule 的 cron/model、哪类任务降级、怎么提 cache 命中),尽量量化「预计省多少」。

## 价格来源规则(Non-negotiable)

价格**绝不能用你(模型)记忆里的数** —— 记忆会过时/出错(已踩过坑:opus 记成 $15/$75 实为 $5/$25;gpt-5.5 记成 $1.25/$10 实为 $5/$30,两个错叠加把结论整个搞反)。单价只允许来自两处:

1. **已记录在本地 `pricing.json`**(price-of-record)——直接用。模型按前缀匹配(opus/sonnet/haiku/gpt-5.x/codex)。
2. **未知 / 新模型** —— `analyze.py` 的 warnings 会喊 `UNKNOWN MODEL PRICING: X`。这时**必须先查到官方价再下结论**,权威来源优先级:
   - **Claude 系**:若本机有 XDT Maker 源码,可参考它自带的 cc-code 模型价格表(XDT 算 `daily_spend` 用的表,源自 platform.claude.com/pricing)。**注意它是手工维护的代码表、不是实时 API**,可能没收录最新版(会落到 `$5/$25` 默认 tier),仍以官方定价页为准。
   - **XDT 表没覆盖的 / 兜底**:用 `WebSearch` 搜官方定价页(Anthropic `platform.claude.com`、OpenAI `openai.com/api/pricing`),多源交叉。**Codex / gpt-5.x:XDT 完全不给它计价,只能联网搜。**

**每次因为某个未知模型去联网搜时,顺手把 `pricing.json` 里所有模型价格一并复核刷新一遍**,并更新文件里的 `pricing_version`、`last_reviewed` 和 `_notes`(记下 source + 日期)。

**流程**:跑 `analyze.py` → 若 warnings 有 `UNKNOWN MODEL PRICING`,或 `last_reviewed` 已久 → 先按上面把价格查实写进 `pricing.json` 再重跑 → **不要拿兜底价直接给用户下结论**。

补充:fast mode 是 Opus 的 2× 档($30/$150),已按 `claude-opus-4-fast` 建模(命中 `usage.speed=='fast'` 时启用)。注意 pre-4.5 的 Opus 4/4.1 原价 $15/$75,而本表把所有 `opus` 归到当前 $5/$25 tier —— 若出现老 Opus 会低估,需要时再细分。

## Non-negotiables

- **只读**:绝不写 / 改任何 session 库或 jsonl。脚本以 `mode=ro` 打开 DB。
- **先跑脚本**,基于其输出回答;不要把原始 jsonl / sqlite 读进 context。
- **不编造**:数字一律来自脚本输出。脚本没覆盖到的(如某来源缺数据)如实说,别脑补。
- **必讲价格口径**:token 折算标尺 vs 真实现金 ledger 的区别,以及为何差一个数量级。
- **保护隐私**:报告产物含 session 标题、项目路径、session ID,只发必要摘要,不要公开贴完整 JSON/Markdown。
- 报告用中文,结构清晰(总览 → 占比 → 浪费 → 建议),给路径不要只说「跑完了」。
