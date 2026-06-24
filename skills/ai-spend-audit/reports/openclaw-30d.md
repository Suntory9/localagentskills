# AI 耗量审计 — 最近 30 天 (2026-05-06 → 2026-06-05)

_生成于 2026-06-05 03:03。**花费 = token 用量 × 公开 API 标价**(pricing.json 2026-06-04.2)。**计费混合**:Claude/XDT 按量 API → 美元=真金白银;Codex 等包月订阅 → 美元=what-if(边际≈$0,不是现金)。价格可能过时,跑前建议联网复核。_

## 总览

- **折算花费(按 API 标价等价):$653.50**,最近 30 天 (2026-05-06 → 2026-06-05),共 1557 个 session
  - OpenClaw:$653.50 (100%),1557 个 session,791.0M tokens
- **真金白银(按量 API,主要是 Claude):≈$0.00** · 包月渠道(Codex 等)API-等价 what-if $653.50(订阅,边际≈$0,不是现金)
- 按模型族 · 美元: Codex/gpt-5.x[包月·$0边际] $653.50(100%)
- 按模型族 · token: Codex/gpt-5.x 791.0M(100%)

## 按来源(宿主 App)

| 来源 | 折算$ | 占比 | session数 | tokens | 缓存复用率 |
|---|--:|--:|--:|--:|--:|
| OpenClaw | $653.50 | 100% | 1557 | 791.0M | 87% |

## 按模型

| 模型 | 折算$ | 占比 | session数 | tokens | 缓存复用率 |
|---|--:|--:|--:|--:|--:|
| gpt-5.5 | $524.24 | 80% | 1014 | 430.2M | 87% |
| gpt-5.4 | $129.10 | 20% | 540 | 360.6M | 87% |
| gpt-5.4-mini | $0.17 | 0% | 3 | 233k | 54% |

## 按 来源 × 模型族(宿主 App × 模型,两维一起看)

| 来源 × 模型 | 折算$ | 占比 | session数 | tokens | 缓存复用率 |
|---|--:|--:|--:|--:|--:|
| OpenClaw · Codex/gpt-5.x | $653.50 | 100% | 1557 | 791.0M | 87% |

## 按使用类型

| 类型 | 折算$ | 占比 | session数 | tokens | 缓存复用率 |
|---|--:|--:|--:|--:|--:|
| Codex | $652.47 | 100% | 1548 | 788.5M | 87% |
| openclaw | $1.04 | 0% | 9 | 2.5M | 80% |

## 按项目(工作目录)

| 项目 | 折算$ | 占比 | session数 | tokens | 缓存复用率 |
|---|--:|--:|--:|--:|--:|
| workspace | $367.30 | 56% | 615 | 344.7M | 90% |
| workspace-food-group | $193.99 | 30% | 655 | 383.0M | 86% |
| workspace-wife | $40.18 | 6% | 63 | 29.0M | 85% |
| workspace-caoz | $33.18 | 5% | 192 | 19.4M | 70% |
| workspace-coding | $14.24 | 2% | 14 | 10.2M | 83% |
| workspace-work | $2.10 | 0% | 5 | 1.3M | 78% |
| workspace-folotoy | $1.47 | 0% | 4 | 932k | 46% |
| main | $0.77 | 0% | 3 | 2.3M | 83% |
| folotoy | $0.27 | 0% | 6 | 173k | 30% |

_无代码项目的对话默认合并;单个 ≥$2.00 的按标题单列。_

## 最贵的 15 个 session

_「项目」来自 session 的实际工作目录(cwd),是"干了啥"的可靠信号;「标题」是会话第一句话/外部元数据,resume 续用的老会话可能过时(标题归 A、实际在做 B),两者不一致时以项目为准。_

| 折算$ | 来源 | 模型 | 类型 | turns | tokens | 缓存复用 | 标记 | 项目 | 标题 |
|--:|---|---|---|--:|--:|--:|---|---|---|
| $17.44 | OpenClaw | gpt-5.5 | Codex | 143 | 18.8M | 93% | 花费偏高 | workspace | [media attached: /Users/cindy/.ope |
| $12.45 | OpenClaw | gpt-5.5 | Codex | 99 | 15.5M | 95% | 花费偏高 | workspace | workspace · 05-24 20:23 |
| $12.11 | OpenClaw | gpt-5.5 | Codex | 100 | 15.3M | 96% | 花费偏高 | workspace | workspace · 05-25 13:58 |
| $9.90 | OpenClaw | gpt-5.5 | Codex | 88 | 11.8M | 95% | 花费偏高 | workspace | workspace · 05-25 12:50 |
| $9.67 | OpenClaw | gpt-5.5 | Codex | 90 | 10.3M | 92% | 花费偏高 | workspace | 你前面卡死了嘛 |
| $7.97 | OpenClaw | gpt-5.5 | Codex | 77 | 10.2M | 96% | 花费偏高 | workspace | 你再去网上搜一下有没有什么不同的、值得参考和保存的图片或视频。 |
| $7.73 | OpenClaw | gpt-5.5 | Codex | 74 | 10.0M | 96% | 花费偏高 | workspace | workspace · 05-25 11:39 |
| $7.39 | OpenClaw | gpt-5.5 | Codex | 48 | 5.6M | 83% | 花费偏高 | workspace-food-group | workspace-food-group · 05-21 13:21 |
| $7.33 | OpenClaw | gpt-5.5 | Codex | 55 | 9.5M | 96% | 花费偏高 | workspace | workspace · 05-25 12:25 |
| $6.94 | OpenClaw | gpt-5.5 | Codex | 62 | 8.1M | 94% | 花费偏高 | workspace | 重新整理一下本地目录，从 github xindong 下把 das |
| $6.45 | OpenClaw | gpt-5.5 | Codex | 92 | 6.0M | 88% | 花费偏高 | workspace-coding | 请判断这次更新是否值得在频道播报。 规则： - ping 事件只用于 |
| $5.91 | OpenClaw | gpt-5.5 | Codex | 53 | 4.1M | 82% | 花费偏高 | workspace-wife | 你看一下我邮箱里有一封Xueyao.Zhang@drewnapier |
| $5.90 | OpenClaw | gpt-5.5 | Codex | 43 | 5.5M | 89% | 花费偏高 | workspace | 你前面是遇到了什么问题，为什么没有回复？ |
| $5.58 | OpenClaw | gpt-5.5 | Codex | 60 | 4.6M | 86% | 花费偏高 | workspace-food-group | [Queued messages while agent was b |
| $5.13 | OpenClaw | gpt-5.5 | Codex | 42 | 5.3M | 93% | 花费偏高 | workspace | 给我查日志，总结一下，我们最近一周的Token都用在了哪些地方 |

## 思考深度(effort)与快速模式

| 模型族 · effort | 折算$ | 占比 | session数 | tokens | 缓存复用率 |
|---|--:|--:|--:|--:|--:|
| Codex/gpt-5.x · effort=high | $646.10 | 99% | 1525 | 784.8M | 87% |
| Codex/gpt-5.x · effort=medium | $5.02 | 1% | 21 | 2.9M | 78% |
| Codex/gpt-5.x · effort=low | $1.35 | 0% | 2 | 741k | 40% |
| Codex/gpt-5.x · effort=默认 | $1.04 | 0% | 9 | 2.5M | 80% |

- **快速模式:未使用 ✓** —— 没在烧 fast 溢价。(提醒:Opus fast = 2×($30/$150);Codex priority ≈ 2.5×($12.5/$75),按需才开。)

## 浪费与优化信号

_(session 花费中位数:$0.22;只单列值得人工看的——按量真金 ≥$3.00 或 包月 ≥$15.00,其余只给汇总。)_
_口径:**按量(Claude/XDT)= 真金,优先省**;**包月(Codex 等)边际 $0**,只清死循环 / 遗留 cron / 重复重缓存(省的是配额与时间,不是钱)。_

- **大材小用(高级模型干小活):** 685 个、合计 $84.80。 基本都是包月($0 边际),省的是配额/时间,不是钱;不必逐个处理。
  - 主要来自:`workspace` 323 次 / $34.81、`workspace-food-group` 173 次 / $25.28、`workspace-caoz` 161 次 / $20.76
- **花费偏高(>中位数 6 倍):** 16 个 —— 按量真金 $0.00 / 包月 what-if $132.98。真金的逐个看是否值;包月的只排死循环 / 跑飞自动化。

### 花费偏高 session(值得单看)

- [包月·$0边际] $17.44 —— OpenClaw/Codex `gpt-5.5` 143 turns,412 分钟 —— [media attached: /Users/cindy/.openclaw/media/inbo

## 覆盖范围(本机探测的工具)

_本 skill 检查了下列写本地 token 日志的工具。「已装·窗口内无数据」= 工具在但这段时间没用;「未安装」= 本机未发现其数据。这样你能看到**查了哪些**,而不只是查到了什么。_

| 工具 | 状态 | 计费 | 说明 |
|---|---|---|---|
| OpenClaw | 有数据 |  | $653.50 · 1557 session · 791.0M tok |
| Claude Code | 已装·窗口内无数据 | 按量·真金 | 本地有该工具,但所选时间窗内无用量 |
| Codex | 已装·窗口内无数据 | 包月·$0边际 | 本地有该工具,但所选时间窗内无用量 |
| OpenCode | 未安装 | 按量·真金 | 本机未发现其数据(roots 不存在) |
| Pi | 未安装 | 包月·$0边际 | 本机未发现其数据(roots 不存在) |
| XDT Maker | 未安装 | 按量·真金 | 本机未发现其数据(roots 不存在) |

## 警告

- XDT Maker DB not found.
- Codex 服务档逐 turn 判定(logs_2.sqlite):2 priority / 0 standard turn;未记录的 turn 回退 config(service_tier=standard)。priority 按 2.5× 计价。
- 已用 --source 过滤:只保留来源含 'openclaw' 的 session(共 1557 个)。
