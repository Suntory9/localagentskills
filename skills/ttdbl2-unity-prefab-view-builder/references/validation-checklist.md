# Validation Checklist

Use this before reporting a prefab/View task as done.

## Scope

- Confirm the target feature folder and target view name.
- Confirm whether this is `FullView`, `PopView`, `CanvasView`, `EmbeddedView`, or `ItemWidget`.
- Confirm whether the user asked for analysis only or implementation.
- Avoid modifying unrelated assets, generated caches, signing/channel config, audio resources, or unrelated prefabs.

## Prefab Checks

- Prefab file name matches the view/widget name.
- Openable view path matches `Assets/Prefabs/Plane/<Feature>/<Name>.prefab`.
- Openable `PlaneType.Top` and `PlaneType.Function` root has `CanvasRenderer`, `Canvas`, `CanvasGroup`, and `GraphicRaycaster`.
- Full roots and full backgrounds stretch as intended.
- Embedded views and item widgets do not have an independent `Canvas`.
- Shell node names such as `BG` and `Content` follow same-feature references; those names are recommended, not mandatory. Mask nodes may also be named `Background` (Pet's StarDescView) or `Mask`. Body nodes may also be named `Center`.
- If a mask node (`BG` / `Background` / `Mask`) exists, it has `CanvasRenderer`, `Image`, and `Button`; `Button.transition` is `None`.
- If a `Content`-style body node exists, it has `RectTransform`, `CanvasGroup`, and `Animator`. `CanvasRenderer` + `Image` are present **only when** `Content` itself draws the body background (Variant A); absent when body art is moved to `Content/Background/*` children (Variant B — confirmed in Pet's PetInfoView and PetChangeView). Do not flag Variant B as missing `Image`.
- Mask node alignment matches same-feature popup/function references, usually full stretch with `anchorMin=(0,0)`, `anchorMax=(1,1)`, `sizeDelta=(0,0)`.
- Body node alignment, size, pivot, and component stack are copied from the nearest normal reference prefab unless the design explicitly requires a different shell.
- Reused common prefabs are instanced rather than visually recreated.
- Buttons that need runtime callbacks have `Button` components.
- Popup `BG` can be wired as a mask/click-close target when desired.
- Dialog bodies and animated groups have `CanvasGroup` or `Animator` when matching local patterns.
- Scroll areas have the expected `ScrollPlane`/viewport/content/layout nodes.
- Repeated item templates exist under expected `Prefabs/...` paths when `WidgetPath` is used.
- Image slicing and layout components are preserved when copying panels/buttons/items.
- Text component type matches local convention; do not blindly convert legacy Text to TMP or TMP to legacy Text.
- Legacy `Text` font is not Unity built-in/default; use `HYZhengYuan-85S.ttf` (`guid: 9f9a67f476836d646af8f26f3f63f3b8`) or a same-feature reference font.

## Lua View Checks

- Lua file path matches `Assets/Scripts/LuaScript/Views/<Feature>/<Name>.lua`.
- Openable views have appropriate `ViewType` (`PlaneType.Top` or `PlaneType.Function`).
- Item widgets and embedded partials may intentionally omit `ViewType`. **Do not infer "View" / "PopView" suffix in the name implies openable** — Pet has `PetPopView_Level`, `PetPopView_Star`, `PetStoneSlot` that omit `ViewType` despite the suffix. Confirm with both `ViewType` in Lua and `Canvas` presence in the prefab.
- `Component.Path` entries exist in the prefab hierarchy.
- `Partial.Root` entries exist in the prefab hierarchy.
- `WidgetPath` template paths exist inside the current prefab.
- `Widget` targets have matching prefab and Lua files.
- Close callbacks use `CloseUI()` or `UIManager:Close(...)`, not direct object hiding.
- Button/toggle/slider callbacks do not rely on additive listener stacking.
- Local state and cached instance ids are cleared in `OnExit`.
- `Event`/`PostEvent`, `Memo`/`PostMemo`, and `Partial`/`PostPartial` pairs are internally consistent.

## Runtime Identity Checks

- `UIDefine` is present for views opened directly by gameplay code.
- `UIDefine` value matches `<Feature>/<Name>`.
- `UIManager:Open(...)` call sites use the expected value.
- Runtime asset path will resolve as `plane/<Feature>/<Name>`.
- Prefab asset object name matches the last path segment expected by loading code.
- For newly generated `FullView`, `PopView`, or `CanvasView` prefabs, the prefab `.meta` / importer `assetBundleName` is set to the matching runtime asset path, following same-folder casing conventions. Normal `ItemWidget` and `EmbeddedView` prefabs may leave it empty unless they are loaded directly as standalone bundles.

## Verification

- If Unity MCP is available, inspect the prefab hierarchy through Unity and check the console after changes.
- For generated prefabs, compare root components, mask/body shell nodes such as `BG`, `Background`, `Content`, or `Center`, and font references against at least one same-feature normal prefab before finalizing.
- If visual accuracy matters, capture a Game/Scene view screenshot after instantiating or opening the view.
- If Unity Editor is not run, explicitly report that Editor/device verification was not performed.
- For screen background changes, consider whether `UIKit.ScreenConstraint(rect, coverTran)` is needed.
- For frontend/backend-linked UI, list service/config fields that still need integration verification.
