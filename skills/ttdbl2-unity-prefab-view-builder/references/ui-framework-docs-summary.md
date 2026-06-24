# UI Framework Docs Summary

This summarizes the Confluence directory under:

`https://xindong.atlassian.net/wiki/spaces/RE/pages/243667756`

Read project code and existing prefabs first when docs conflict with code.

## Pages Read

Accessible with body content:

- `UI模块`
- `资源管理模块`
- `UI应用层框架`
- `UI开发流程`
- `UI框架`
- `界面信息共享`
- `界面适配不同屏幕接口和方法`

Special cases:

- Parent page `客户端框架文档` returned empty body and works mainly as a directory.
- `插件开发指南` returned empty body.
- `UI应用层框架进阶指南` was draft and returned 404 through the tool.

## Key Takeaways

### UI module

The UI documentation groups:

- UI scheduling/management.
- Shared/common UI to avoid duplicate development.
- UI application-layer framework.

### Resource management

The resource module encourages loading resources by project-relative asset path through a loader abstraction and releasing the loader with the module lifecycle. For UI generation, prefer framework-managed UI loading where possible rather than manual AssetBundle assumptions.

### UI application-layer framework

Important concepts:

- View scripts are scope-isolated; outside code should not access internal members directly.
- UI should focus on data handling and display, not unrelated systems.
- Reusable UI components should be composed as nested UI Views.
- `Memo` and `PostMemo` are the preferred data/display split.
- `Partial` and `CallPartial(instanceId, path, ...)` provide safe local communication between hosted components.
- A feature can place prefabs under `Prefabs/Plane/<Feature>/...` and scripts under `LuaScript/Views/<Feature>/...`.
- The framework favors composition over inheritance.

### UI development flow

New-style structure:

- `ViewType = PlaneType.Top` replaces the old `_ViewBase:New("Name", PlaneType.Top)` declaration.
- `Memo`, `Component`, and `Partial` are extension configurations.
- `Component` shape is `Key = { Path = "...", Component = "...", Callback = ... }`.
- `Partial` can use `WidgetPath` for current-prefab child templates or `Widget` for external UI Views.
- Main lifecycle functions are `InitPanel`, `OnEnter`, and `OnExit`.
- `PostMemo` and `PostPartial` are hook points.

### Old UI framework page

This older page describes:

- Plane types such as HUD, Func, Top, Tip, Loading.
- Old prefab creation from a template.
- Old component naming convention `customName_componentName`.
- Old Lua auto-generation into `Assets/Scripts/LuaScript/Plane/<Name>.lua`.
- Old `_ViewBase` lifecycle and `EventManager`.

Use this page for old-style `Plane` files only. For `Views/*` files, prefer current code and the new-style framework pages.

### Screen adaptation

`UIKit.ScreenConstraint(rect, coverTran)` scales a background RectTransform proportionally until it covers the target area. If `coverTran` is omitted, the screen is the cover target.

Use this for large full-screen background art that must cover variable aspect ratios. It is not a replacement for correct anchors on buttons, text, panels, and item cells.

## Code Authority

For actual runtime behavior, prefer these project files:

- `Assets/Scripts/LuaScript/Global/UIManager.lua`
- `Assets/Scripts/LuaScript/Global/_ViewBase.lua`
- `Assets/Scripts/LuaScript/Tools/UIView/Core/UIDriver.lua`
- `Assets/Scripts/LuaScript/Tools/UIView/Core/UIController.lua`
- `Assets/Scripts/LuaScript/Tools/UIView/Extension/UIExtensionComponent.lua`
- `Assets/Scripts/LuaScript/Tools/UIView/Extension/UIExtensionPartial.lua`
- `Assets/Scripts/LuaScript/Tools/UIView/Extension/UIExtensionEvent.lua`
- `Assets/Scripts/LuaScript/Tools/UIView/Extension/UIExtensionMemo.lua`
- Same-feature prefab and Lua View files.

## Practical Build Rule

When creating a new project prefab from a mockup, follow the two-stage discipline (schema first, then build) using project-specific shells:

1. Produce an explicit schema that names visible nodes and runtime shell nodes (see `references/schema-fields.md`).
2. Pick a same-feature reference prefab for the shell.
3. Preserve or recreate required root components, `BG`, `Content`/`Center`, common navigation, font references, and reusable widgets.
4. Only then place the mockup-specific visible content (see `references/unitymcp-execution.md` for Mode A vs Mode B).
