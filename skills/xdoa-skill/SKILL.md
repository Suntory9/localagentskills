---
name: xdoa-skill
version: 1.0.6
updateTime: "2026-06-22 18:23:25"
description: >-
  用于 XDOA CLI 安装配置、升级指引、能力路由和 OA 任务执行规划。当用户想安装或升级 xdoa、了解 xdoa 能做什么、判断应使用哪类 XDOA 工作流，或通过 xdoa 处理公司办公与 OA 任务时触发，例如文档查询、个人 OA 信息查询和审批流程处理。执行前应根据任务类型读取匹配的子参考文件：CLI 用法、文档工作流或审批流程工作流
---

# XDOA-skill

将此文件作为 `xdoa` 的主入口技能。

主技能应保持轻量，只负责：

- 确认 `xdoa` 已安装
- 当 `xdoa version` 提示有新版本时升级 `xdoa`
- 说明 `xdoa` 的主要能力范围
- 判断下一步应读取哪个子参考文件

不要把所有详细工作流都放在本文件中。只读取与当前任务匹配的子参考文件。

## 步骤 0：确认 `xdoa` 可用

先检查：

```bash
xdoa version
```

如果缺少 `xdoa`，先安装再继续。

macOS / Linux：

```bash
bash <(curl -fsSL https://oa-cdn.oss-cn-shanghai.aliyuncs.com/downloads/install.sh)
```

Windows PowerShell：

```powershell
irm https://oa-cdn.oss-cn-shanghai.aliyuncs.com/downloads/install.ps1 | iex
```

安装脚本不可用时使用备用方式：

```bash
npm login --scope=@xindong --auth-type=legacy --registry=https://npm.pkg.github.com
npm install -g @xindong/oa-cli
```

安装后验证：

```bash
xdoa version
```

## 步骤 1：发现新版本时升级

如果 `xdoa version` 提示存在新版本，默认不要继续使用旧版本。重新运行安装脚本完成升级：

macOS / Linux：

```bash
bash <(curl -fsSL https://oa-cdn.oss-cn-shanghai.aliyuncs.com/downloads/install.sh)
```

Windows PowerShell：

```powershell
irm https://oa-cdn.oss-cn-shanghai.aliyuncs.com/downloads/install.ps1 | iex
```

然后再次验证：

```bash
xdoa version
```

## 主要能力范围

`xdoa` 的主要能力分组包括：

- `auth`
  - 登录、状态查看、当前用户信息、退出登录
- `doc`
  - 搜索和阅读内部办公与 IT 文档
- `flow`
  - 搜索流程、查看表单、构造提交参数、提交审批、查看待办或提交状态
- `reserve`
  - 个人预订、会议室搜索、会议室预订操作
- `asset`
  - 个人资产列表和资产详情
- `space`
  - 工位查询、楼层地图、工位历史
- `okr`
  - OKR 相关 GET 查询

## 子参考文件路由

只读取匹配的子参考文件：

- 通用 CLI 用法、认证行为、命令风格和常见 OA 查询模式：
  - 读取 `references/cli-skill.md`
- 通过 `xdoa doc` 检索内部办公与 IT 文档：
  - 读取 `references/doc-skill.md`
- 审批流程搜索、表单查看、参数构造、提交和验证：
  - 读取 `references/flow-skill.md`

## 路由规则

- 如果用户询问如何安装、升级或验证 `xdoa`，默认停留在本文件，除非还需要详细命令用法
- 如果用户询问认证行为、常见命令用法、会议室、资产、工位、OKR 或个人 OA 状态，读取 `references/cli-skill.md`
- 如果用户询问办公制度、VPN、IT 支持、SSO、设备、权限、入职离职或其他内部文档，读取 `references/doc-skill.md`
- 如果用户要求查找、填写、测试提交、正式提交或验证审批流程，读取 `references/flow-skill.md`

## 回复风格

- 优先给出简洁、可执行的操作指引
- 当用户需要执行动作时，优先直接执行，而不是抽象解释
- 只加载当前任务所需的最小子参考文件
