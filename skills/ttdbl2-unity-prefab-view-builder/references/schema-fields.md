# Schema Fields

Stage 1 of any prefab/View build is to produce an explicit UI schema before touching Unity. The schema makes visual assumptions inspectable and lets a reviewer catch problems before they become committed prefab nodes.

## Always Include

- Short design understanding summary (1-3 sentences).
- `uncertainties`: anything not visually reliable from the mockup — color values that are hard to read, sprite identity guesses, repeated-cell counts, hidden states, scroll boundaries.
- JSON node tree (see fields below).

Keep guesses out of the main node tree. If a node only "probably" exists, put it in `uncertainties`, do not invent it as a real node.

## Per-Node Fields

Minimum fields for every node in the tree:

- `name` — stable, implementation-friendly identifier. Prefer `btn_Confirm` over `点击确认按钮`. CJK is fine for visible text content, not for node ids.
- `type` — see node-type list below.
- `parent` — parent node name, or `null` for root.
- `anchorMin` — `[x, y]` 0..1.
- `anchorMax` — `[x, y]` 0..1.
- `pivot` — `[x, y]` 0..1.
- `sizeDelta` — `[w, h]` in pixels at the project's 1125x2436 design resolution.
- `anchoredPosition` — `[x, y]` in pixels.
- `spriteKey` — sprite identifier/path/guid, or `null` if pure layout.
- `text` — display text or `null`.
- `fontSize` — integer or `null`.
- `color` — hex `#RRGGBB[AA]` or `null`.
- `alignment` — `Left|Center|Right|TopLeft|...` or `null`.
- `interactable` — `true|false|null`.
- `children` — array of child nodes (recurse), `[]` if leaf.

## Node Types

Use these unless the project clearly needs more. Reach for new types only after confirming no existing project component fills the role.

- `Root` — top of the prefab. Carries the openable-view root component stack when applicable.
- `Empty` — pure layout/group container, no graphic.
- `Image` — sprite or solid color graphic.
- `TextTMP` — TMP text. **Only use when same-feature reference proves TMP is in use** — most legacy features in this project use plain `Text`.
- `Text` — legacy `UnityEngine.UI.Text`. Default for this project's older feature folders.
- `Button` — interactive button. Must be split into background + text (or icon) children, not a single fused node.
- `VerticalLayout` / `HorizontalLayout` — auto-layout container.
- `ScrollPlane` — project scroll container; usually contains an inner `Layout` node.

## Project-Specific Schema Extensions

In addition to the visible node tree, every schema for an openable view in this project must declare:

- `viewType` — `FullView` | `PopView` | `CanvasView` | `EmbeddedView` | `ItemWidget`.
- `planeType` — `PlaneType.Top` | `PlaneType.Function` | empty for non-openable widgets.
- `referencePrefab` — nearest existing prefab used for shell/components. Required for openable views unless explicitly "no suitable reference exists" is stated.
- `rootComponents` — required components for the root (typically `CanvasRenderer, Canvas, CanvasGroup, GraphicRaycaster` for openable Top/Function views).
- `shellNodes` — recommended mask/body shell nodes and their required component stacks when those nodes are used.
- `fontPolicy` — project font (`HYZhengYuan-85S.ttf`, guid `9f9a67f476836d646af8f26f3f63f3b8`) or "reuse reference node font".
- `reusePrefabs` — common or same-feature prefabs to instantiate (e.g. `Assets/Prefabs/Plane/General/DownLeft.prefab` for return controls).
- `assetBundleName` — required runtime bundle name for new `FullView`/`PopView`/`CanvasView` prefabs (normally `plane/<Feature>/<Name>`); empty/omitted for normal `ItemWidget` and `EmbeddedView`.
- `bindingPaths` — intended Lua `Component.Path`, `Partial.Root`, and `WidgetPath` entries.

For openable views, split the schema into:

- `shellSchema` — copied from the selected same-feature reference prefab: root components, mask/body shell nodes, anchors, pivots, component stacks, animation controller, button transition, font policy.
- `contentSchema` — generated from the mockup or requirement, placed under the chosen `Content` subtree or content host.

## Repeated Cells

If a repeated cell is obvious in the mockup:

- Note in the schema that it is a repeated pattern.
- Still provide one concrete node tree for a single build path (so reviewers can verify field-level decisions).
- Mark count as `uncertain` unless the mockup clearly shows total items.
- Plan to use `Partial` with `Widget` (external item prefab) or `WidgetPath` (template child of current prefab) at Lua-binding time, not raw duplicated nodes.

## Naming Stability

- Prefer stable names over visual labels: `btn_Close` not `右上角的×按钮`.
- Use feature-folder existing naming first; new names should look like neighbors.
- Once a node is named in the schema, that name becomes the runtime contract with Lua `Component.Path` / `Partial.Root` / `WidgetPath`. Renaming later requires updating both sides.

## Sanity Check Before Stage 2

Before handing the schema to UnityMCP build, confirm:

- Every openable view has `referencePrefab` filled in (or an explicit "no suitable reference" justification).
- `shellSchema` mirrors the reference, not a guess.
- `uncertainties` is not empty for any non-trivial mockup — if it is, you have probably invented certainty that doesn't exist.
- Every node that needs a runtime binding appears in `bindingPaths`.
