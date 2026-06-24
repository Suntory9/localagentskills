# Prefab Patterns

This reference captures observed UI prefab conventions in `/Users/songdc/ttdbl2_unity`. The first complete sample set was `Assets/Prefabs/Plane/Mount`, scanned at 43 prefabs.

## Classification

Do not use one shell for every UI. Classify first:

- `FullView`: full-screen feature page. Root usually stretches to full screen and may include `Background`, `Content`, and common navigation.
- `PopView`: top-layer dialog. Root usually has `Canvas`, `CanvasGroup`, and `GraphicRaycaster`; common children are a mask (`BG` or `Background`), a `Content` body, and a return/close prefab instance.
- `CanvasView`: special top-layer view with `Canvas` but no standard popup shell.
- `EmbeddedView`: content loaded by a parent `Partial`; should not have its own `Canvas`.
- `ItemWidget`: reusable cell/card/widget; fixed size; should not have its own `Canvas`.

**Name does not dictate type.** Pet's `PetPopView_Level` and `PetPopView_Star` carry "PopView" in the name but are actually embedded/sub-view content loaded via `Partial.Widget`, with bare `RectTransform` roots and no `Canvas`. Always confirm with `ViewType` in Lua + `Canvas` presence in the prefab before classifying.

## Mount Sample Statistics

Full scan of `Assets/Prefabs/Plane/Mount`:

- Total prefabs: 43
- `Pop/Top View`: 27
- `Item/Widget`: 11
- `Canvas View`: 2
- `Embedded/Partial`: 2
- `Full/Function View`: 1

Component and structure counts:

- 30 with `Canvas`
- 35 with `CanvasGroup`
- 40 with `Animator`
- 29 with `BG`
- 30 with `Content`
- 27 with `DownLeft`
- 17 with scroll structures
- 42 with Button
- 42 with Text
- 12 with TMP
- 43 with Image

## Common Shells

Full or function view:

```text
ViewRoot
  Background
  Content
  DownLeft or feature-specific navigation
```

Popup/top view:

```text
ViewRoot
  BG
  Content
    title/text/images/buttons/red points/scroll content
  DownLeft
```

Embedded view:

```text
EmbeddedRoot
  feature nodes
  optional Prefabs template holder
```

Item widget:

```text
ItemRoot
  icon/frame/text/state/badge nodes
```

## Project Rules

- Root of a full view usually stretches: `anchorMin=(0,0)`, `anchorMax=(1,1)`, `sizeDelta=(0,0)`.
- Root of an openable `PlaneType.Top` or `PlaneType.Function` view must carry the project-standard root component stack: `CanvasRenderer`, `Canvas`, `CanvasGroup`, and `GraphicRaycaster`. Some older/generated prefabs may be missing this, but new output should not copy that defect.
- Do not add `CanvasScaler` inside feature prefabs; the outer UI scene canvas handles scaling.
- Only root and true full-background images should stretch by default.
- Use top anchors for top bars/titles; use bottom anchors for bottom actions/navigation.
- Use fixed sizes and clear pivots for panels, icons, buttons, text, and item cells.
- `BG` and `Content` are recommended shell node names, not mandatory names for every openable view. Same-feature prefabs may use alternatives such as `Background` (Pet's StarDescView), `Mask`, or `Center`; follow the reference naming when appropriate.
- Use a mask node (`BG` / `Background` / `Mask`) for full-screen popup masks. Required component stack when this node exists: `CanvasRenderer`, `Image`, and `Button`. The `Image` is commonly sliced, raycast target enabled, and may use a black/background sprite. The `Button` transition should be `None`; it may have an empty `OnClick` list until Lua binds it.
- Use a `Content`-style node for the dialog body or main content host. Required component stack: `RectTransform`, `CanvasGroup`, and `Animator`. The `Animator` should reuse the same-feature popup controller when available; `UIM_Popup_Center` is a common popup-center controller.
- `Content` Image is **conditional** — two variants coexist:
  - **Variant A (Content draws body art):** `Content` adds `CanvasRenderer` + `Image`, with `Image.sprite` being the dialog body background. The `Image` component must remain even if the sprite changes. Examples: Mount's MountInfoView, Pet's PetPopView, PetStoneSlotView, StarDescView.
  - **Variant B (body art in children):** `Content` has only `RectTransform + CanvasGroup + Animator`; body art lives in `Content/Background/Image` (and optional `Image2`) children. Do not force `Image` onto `Content` when copying Variant B shells. Examples: Pet's PetInfoView, PetChangeView.
- Align mask/body shell nodes against same-feature reference prefabs. Mask nodes normally stretch full-screen. Popup body nodes such as `Content` or `Center` should reuse the reference anchor, pivot, size, component stack, and approximate vertical placement rather than using a visually guessed rectangle.
- Use a `CanvasGroup` on groups that are animated or frequently shown/hidden.
- Preserve `Image Type=Sliced` for panel/button backgrounds that are meant to scale.
- Scroll content commonly uses `ScrollPlane` and an inner `Layout` node.
- Red notification dots are commonly named `RedPoint` or `redPoint`.
- Button nodes often use `btn_*`; project buttons commonly include `Button + Image + Animator`.
- Text component type varies by feature and even within the same feature folder — do not assume one default. Mount and BP samples skew legacy `UnityEngine.UI.Text`; Pet's `PetInfo` and `PetView` use TMPro heavily for stat / name / level labels alongside legacy `Text` for other strings. **Always check the nearest reference node** before deciding.
- For legacy `Text`, use the project font from existing references or explicitly assign `Assets/TextMesh Pro/Font/HYZhengYuan/HYZhengYuan-85S.ttf` (`guid: 9f9a67f476836d646af8f26f3f63f3b8`). Do not leave generated text on Unity's built-in font guid `0000000000000000e000000000000000`.

## Tip-Style Popup Variant

Some popups (e.g. Pet's `StarDescView`) skip a `DownLeft` close control entirely and rely on the mask `Button` for closure. The shell looks like:

```text
ViewRoot  (CanvasRenderer + Canvas + CanvasGroup + GraphicRaycaster)
  Background  (CanvasRenderer + Image + Button)   <- mask doubles as the only close target
  Content     (full body with layout, possibly Variant A or B)
  Prefabs     (optional inactive template host for WidgetPath clones)
```

Allowed when the mockup shows no explicit close affordance and the nearest same-feature reference does the same. Do not force a `DownLeft` onto these views.

## Internal Template Host Pattern

Complex views with many heterogeneous repeated cells use an internal `Prefabs/` GameObject as a template host (Pet's StarDescView, PetPopView_Star, ASkillDescView, PetResetView, PetResetLevelView):

```text
ViewRoot
  ...
  Prefabs        (RectTransform, activeSelf=false)
    Item
    StartItem
    CatItem
    AddSkillDesc
    ...
```

Lua references each template with `Partial = { Key = {WidgetPath = "Prefabs/Item", Root = "..."} }`. The `Prefabs/` host is normally inactive — it exists only as the source for `WidgetPath` clones. Use this pattern when the cell variants are view-internal (not worth promoting to a shared feature widget). Use `Partial.Widget` instead when the cell is shared across multiple parent views.

## Reuse Priorities

- For openable project views, use a same-feature reference prefab as the shell source before generating new content. Preserve the reference root, mask/body nodes, animation, button behavior, font policy, and shell anchors; replace only the intended content host.
- Reuse common navigation/return prefabs rather than recreating their internals.
- Reuse same-feature widgets for repeated cells and complex cards.
- Reuse `CommonWidgets/CommonTabs` for tabs when matching existing View patterns.
- For repeated display items, prefer a reusable `ItemWidget` plus `Partial`.

## Common Failure Modes

- Generating an embedded view or item with its own `Canvas`.
- Drawing a visual clone of a common return button instead of instancing the project prefab.
- Missing `CanvasGroup` or `Animator` on a popup `Content`.
- Missing `Button` on the mask node (`BG` / `Background` / `Mask`), so click-outside-close behavior cannot be wired.
- Forcing `CanvasRenderer + Image` onto `Content` when the design uses Variant B (body art in `Content/Background/*` children).
- Missing the root UI stack on an openable Top/Function view: `CanvasRenderer`, `Canvas`, `CanvasGroup`, `GraphicRaycaster`.
- Building a new openable view from a visually correct empty shell while skipping the nearest same-feature reference prefab. This can produce BPAutoTaskRewardView-like output: `ViewType = PlaneType.Top` in Lua but prefab root lacks the UI stack, `BG` lacks `Button`, `Content` lacks `Animator`, or generated legacy `Text` keeps Unity's default font.
- A mask-style node missing `Button`, or using a visible button transition instead of `None`.
- A `Content`-style body node missing `CanvasGroup` or `Animator`. (Note: `Image` on `Content` is conditional — see Variant A/B above. Omitting it is correct for Variant B.)
- Leaving legacy `Text` nodes on Unity's built-in/default font instead of `HYZhengYuan-85S.ttf` or the same-feature reference font.
- Treating a name like `PopView_Level` as a top-level openable view when the prefab root has no `Canvas` and the Lua has no `ViewType` — it's actually a sub-widget loaded via `Partial.Widget`.
- Guessing `Content` size/position instead of copying the shell from a similar prefab.
- Using TMP everywhere when the feature uses legacy `Text`.
- Missing `Image Type=Sliced`, causing panels or buttons to stretch poorly.
- Using absolute design coordinates for edge controls that should use top/bottom anchors.
- Renaming nodes without updating `Component.Path`, `Partial.Root`, or `WidgetPath`.
- Wrong sibling order for mask, content, text, red points, and buttons.

## Mount Sample Classification

- `FullView`: `AutoBreakCheckView`
- `PopView`: `MountAddSkillDetailView`, `MountAddSkillInfoView`, `MountAddSkillView`, `MountChangeOutfitView`, `MountChipSelectView`, `MountCollectView`, `MountEquipAutoBreakView`, `MountEquipEntryInfoView`, `MountEquipInfoBagView`, `MountEquipInfoView`, `MountEquipMatView`, `MountEquipPopView`, `MountEquipUpSettingView`, `MountEquipView`, `MountEquipsView`, `MountFeedbackView`, `MountInfoView`, `MountOpenSkillDetailView`, `MountPopView`, `MountSealConfirmView`, `MountSealDetailView`, `MountSealRefreshView`, `MountSealView`, `MountSealsView`, `MountSettingView`, `MountSkillSwitchView`, `MountView`
- `CanvasView`: `MountEquipBreakView`, `MountLicenseUpView`
- `EmbeddedView`: `MountView_Main`, `MountView_Space`
- `ItemWidget`: `MountEquip`, `MountEquipAttrItem`, `MountEquipPopView_Up`, `MountEquipPopView_Wash`, `MountEquipPos`, `MountInfo`, `MountItem`, `MountPopView_Equip`, `MountPopView_Level`, `MountPopView_Star`, `MountSkillSwitchSuccessView`
