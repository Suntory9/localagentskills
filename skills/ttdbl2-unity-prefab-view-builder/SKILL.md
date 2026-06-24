---
name: ttdbl2-unity-prefab-view-builder
description: Build or adapt Unity uGUI prefabs and matching Lua Views for the ttdbl2_unity client. Use when creating UI from mockups, Zeplin links, screenshots, reference prefabs, or requirements, and the result must fit this project's Prefabs/Plane, Views, UIDefine, Component/Partial, and UIManager runtime conventions. Drives UnityMCP for both prefab creation (Mode A) and reference-prefab content replacement (Mode B).
---

# TTDBL2 Unity Prefab View Builder

Use this skill for `/Users/songdc/ttdbl2_unity` UI work that creates, modifies, or evaluates a prefab together with its Lua View. The goal is not visual similarity alone — the result must be cheap to wire into the project's runtime (UIManager, UIDefine, Component/Partial, AssetBundle naming).

The workflow is two-stage: produce an explicit UI schema, then build/adapt the prefab in Unity through UnityMCP. For openable views, default to Mode B — instantiate a same-feature reference prefab and replace only the content subtree — so the generated UI inherits the project's root, mask/body shell, animation, button, font, and layout conventions.

## Hard Precondition: UnityMCP

Before any prefab-generation work:

1. Confirm UnityMCP tools are available.
2. Confirm the Unity Editor is reachable.
3. **Stop and tell the user** if UnityMCP is unavailable or not connected. Do not silently fall back to manual editor instructions unless the user explicitly asks for a non-UnityMCP fallback.

Schema-only analysis (no prefab writes) can proceed without UnityMCP, but say so explicitly.

## First Read

Load only what is needed for the current task:

- **Schema stage** (mockup → JSON, before any Unity write): `references/schema-fields.md` for the per-node fields, node types, and project-specific schema extensions.
- **UnityMCP execution** (when about to create or modify in Unity): `references/unitymcp-execution.md` for Mode A vs Mode B procedure and the standard tool sequence.
- **Prefab structure, reusable nodes, screen anchors, text/font, component patterns**: `references/prefab-patterns.md`.
- **Lua View files, `Component`, `Partial`, `Memo`, `Event`, lifecycle**: `references/view-patterns.md`.
- **Confluence/client-framework rules and where docs conflict with code**: `references/ui-framework-docs-summary.md`.
- **Before final delivery or before changing files**: `references/validation-checklist.md`.

If the user names a specific feature folder, scan that folder first and treat same-folder code/prefabs as more authoritative than older reference examples.

## Workflow

1. **Classify the target UI** before building:
   - `FullView`/`Function`: full-screen function page.
   - `PopView`: top-layer dialog, usually with a mask node (`BG` or `Background`), a `Content` body, and a close/return control.
   - `CanvasView`: top-layer special view that does not match the standard popup shell.
   - `EmbeddedView`: partial content hosted by a parent view.
   - `ItemWidget`: reusable item/cell/widget.
   - **Name does not dictate type.** Names like `PopView_Level` / `PopView_Star` can appear on prefabs that are actually loaded as `Partial.Widget` sub-content (bare `RectTransform` root, no `Canvas`). Always confirm with `ViewType` in Lua + `Canvas` presence in the prefab before classifying.

2. **Resolve runtime identity:**
   - Prefab path: `Assets/Prefabs/Plane/<Feature>/<Name>.prefab`.
   - Lua path: `Assets/Scripts/LuaScript/Views/<Feature>/<Name>.lua`.
   - `UIDefine` value for openable views: `<Feature>/<Name>`.
   - Runtime asset path: `plane/<Feature>/<Name>`.
   - For a newly generated view-type prefab (`FullView`, `PopView`, `CanvasView`), set the prefab importer's `assetBundleName` to the matching runtime asset path. Follow same-folder casing conventions from nearby openable prefab `.meta` files. Not required for `ItemWidget` or `EmbeddedView` unless an existing same-feature reference proves it loads as a standalone bundle.

3. **Produce the schema** (see `references/schema-fields.md` for fields):
   - For openable views, split into `shellSchema` (copied from the selected reference prefab) and `contentSchema` (generated from the mockup).
   - Include the project-specific extension fields: `viewType`, `planeType`, `referencePrefab`, `rootComponents`, `shellNodes`, `fontPolicy`, `reusePrefabs`, `assetBundleName`, `bindingPaths`, `uncertainties`.
   - If no good reference prefab is named, search the same feature folder and choose the closest openable view, popup, embedded view, or item widget before creating a shell from scratch. If no suitable reference exists, state that explicitly.

4. **Reuse before rebuilding:**
   - For openable `PlaneType.Top` or `PlaneType.Function` views, default to a same-feature reference prefab via Mode B (see `references/unitymcp-execution.md`). Creating `Root`/`BG`/`Content` from scratch is allowed only when no suitable reference exists.
   - Prefer existing feature widgets and common widgets over rebuilding.
   - Prefer the common return prefab (e.g. `Assets/Prefabs/Plane/General/DownLeft.prefab`) for return/close controls when the feature uses it.
   - For repeated cells, prefer `Partial` with `Widget` (external prefab) or `WidgetPath` (current-prefab template).

5. **Generate or modify the prefab** through UnityMCP:
   - Detailed Mode A / Mode B procedure: `references/unitymcp-execution.md`.
   - Detailed component stack rules (root UI stack for openable views, `BG`-style mask requirements, `Content`-style body requirements, font policy, slicing, anchors): `references/prefab-patterns.md`.
   - Key invariants worth surfacing here:
     - Openable Top/Function view root must include `CanvasRenderer`, `Canvas`, `CanvasGroup`, `GraphicRaycaster`.
     - Embedded views and item widgets must not have an independent `Canvas`.
     - Mask node (commonly named `BG`, sometimes `Background` or `Mask`), when present, needs `CanvasRenderer` + `Image` + `Button` with `Button.transition = None`.
     - `Content`-style body nodes, when present, need `RectTransform` + `CanvasGroup` + `Animator` (reuse same-feature popup controller such as `UIM_Popup_Center`). Add `CanvasRenderer` + `Image` **only** when `Content` itself draws the body background; if the design moves body art into `Content/Background/*` children (Variant B), `Image` on `Content` is intentionally absent.
     - Legacy `Text` nodes must use the project font `Assets/TextMesh Pro/Font/HYZhengYuan/HYZhengYuan-85S.ttf` (guid `9f9a67f476836d646af8f26f3f63f3b8`), not Unity's built-in default.
     - When the reference prefab includes a common return/close control visible in the mockup, instantiate the same nested prefab — do not draw a placeholder.
     - Tip-style popups may skip a `DownLeft` control entirely and rely on the mask `Button` for closure. Allowed when the mockup shows no explicit close affordance and the nearest same-feature reference does the same.

6. **Generate or update the Lua View** to match the prefab (see `references/view-patterns.md`):
   - New-style Views use `ViewType`, `Component`, `Partial`, `Memo`, `Event`, `PostMemo`, `PostEvent`, `PostPartial` as appropriate.
   - Do not mix old `_ViewBase:New` style into new-style `Views/*` files unless the target file already uses that style.
   - Every `Component.Path`, `Partial.Root`, and `WidgetPath` is a runtime contract with the prefab hierarchy.

7. **Validate** structure and binding paths against `references/validation-checklist.md` before reporting done.

## Project Defaults

- Design resolution: `1125x2436`. The Unity scene canvas reference resolution is also `1125x2436`.
- Prefer project-local style over generic Unity UI defaults.
- Treat project code and existing prefabs as source of truth when they conflict with Confluence docs.
- Do not edit `Library/`, `Temp/`, `UserSettings/`, generated caches, signing/channel config, or unrelated resources.

## Output Expectations

When planning or analyzing, return:

- Target UI classification.
- Existing reference prefabs/views used.
- Proposed prefab shell (`shellSchema`).
- Proposed Lua binding and partial strategy.
- Uncertainties that affect runtime or visual fidelity.

When implementing, report:

- Prefab path and Lua path changed.
- `UIDefine` or other registration changed, if any.
- AssetBundle name set for new view-type prefabs, or why it is intentionally empty.
- Reference prefab used for the shell, or why no suitable reference existed.
- Reused prefabs/widgets.
- Validation performed.
- Anything still requiring Unity Editor, device, or integration verification (including Mode B fallbacks where old `Content` children were disabled instead of deleted).
