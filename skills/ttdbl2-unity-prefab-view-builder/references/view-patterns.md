# View Patterns

This reference captures Lua View conventions in `/Users/songdc/ttdbl2_unity`. The first complete sample set was `Assets/Scripts/LuaScript/Views/Mount`, scanned at 43 Lua files.

## Runtime Model

The project has old-style `Plane` files and new-style `Views + UIDriver` files.

For new-style Views:

- `UIManager:Open(planeName, ...)` eventually loads `Views/<planeName>.lua` when no old-style global plane table exists.
- `UIDriver` reads `ViewType` from the module and delegates lifecycle to the framework.
- The prefab asset path normally resolves as `plane/<planeName>`.
- The prefab asset name is normally the last path segment of `planeName`.

## New-Style View Shape

```lua
ViewType = PlaneType.Top

local state
local childInstId

Component = {
    CloseButton = {Path = "DownLeft/CloseButton", Component = "Button", Callback = CloseUI},
    MaskButton = {Path = "BG", Component = "Button", Callback = CloseUI},
    TitleText = {Path = "Content/Title", Component = "Text"},
    _Text1 = {Path = "DownLeft/CloseButton/Text", Component = "Text", Lang = "Common_GoBack"},
}

Partial = {
    Item = {Widget = "Feature/Item", Root = "Content/ScrollPlane/Layout"},
}

function OnEnter(...)
    -- initialize state, components, partials
end

function OnExit()
    -- clear locals and cached instance ids
end
```

Do not add `require` or `return` unless the target file style already requires it. Do not use `self.__xxx` conventions for this framework.

For any Lua file with `ViewType = PlaneType.Top` or `ViewType = PlaneType.Function`, the matching prefab is an openable view. Its root prefab object must include the project UI root stack: `CanvasRenderer`, `Canvas`, `CanvasGroup`, and `GraphicRaycaster`.

## Component Binding

`Component` is the main binding contract:

```lua
Component = {
    Key = {Path = "Relative/Path", Component = "Button", Callback = SomeFunc, Lang = "TextKey", Init = InitFunc},
}
```

Common field naming:

- `XxxObj`: GameObject only, usually for show/hide.
- `XxxText`: text component.
- `XxxImage`: image component.
- `XxxRect`: `RectTransform`.
- `XxxButton`: button component.
- `XxxToggle`: toggle component.
- `XxxTra`: transform.
- `_Text1`, `_Text2`: static localized text binding.
- `XxxRes = function() ... end`: grouped or repeated bindings, often numeric child paths.

Rules:

- `Path` is relative to the view root.
- `Path = ""` means the view/widget root.
- `Component = "Text"` is handled by project framework and may try TMP first before type lookup. When the bound node is TMP, prefer the explicit form `Component = "TMPro.TMP_Text"` (Pet's ASkillDescView, PetView do this on TMP nodes). Either way, match same-feature convention.
- Component callbacks for Button/GameObject bind click behavior. Toggle/Slider/InputField/Scrollbar bind value-change behavior.
- Framework callback binding removes old listeners; combine multiple behaviors in one callback instead of relying on stacking.

## Partial Binding

Use `Partial` for repeated items, hosted child views, or template children:

```lua
Partial = {
    Child = {Widget = "Feature/ChildView", Root = "Content"},
    Item = {WidgetPath = "Prefabs/Item", Root = "Content/Layout"},
}
```

- `Widget` loads another prefab + Lua View.
- `WidgetPath` clones a template node inside the current prefab.
- `Root` must exist in the prefab.
- `PostPartial[Partial.Key]` is required when a `WidgetPath` template needs parsed components.
- Use `AcquirePartial`, `AcquirePartialWithParent`, `ReleasePartial`, and `ReleasePartials` for lifecycle.

## Memo And Events

- `Memo` stores view-local display state.
- `PostMemo[Memo.Key]` responds to display-state changes.
- `Event = { LocalKey = ViewEvent.SomeEvent }` registers logic events while the view is displayed.
- `PostEvent[Event.LocalKey] = function(...) ... end` handles events.
- Clear local state and cached partial instance ids in `OnExit`.

## Sample Statistics

Cross-validated against `Assets/Scripts/LuaScript/Views/Mount` (43 files) and `Assets/Scripts/LuaScript/Views/Pet` (39 files):

- Both feature folders are 100% new-style — zero `_ViewBase:New` calls, zero `require(...)`.
- `UIDefine` entry count matches `ViewType.Top + ViewType.Function` count exactly in each folder (Mount: 31 = 30+1; Pet: 32 = 31+1). Item widgets and embedded partials intentionally have no `UIDefine` entry.
- About half of files use `Partial` (Pet: 22/39 = 56%); widget reuse is dense — same-feature widgets like `Pet/PetInfo`, `Pet/PetScroll`, `Pet/PetSkill` are each instantiated by 5+ different parent views.

Common `Partial.Widget` targets observed:

- Same-feature widgets: `Mount/MountItem`, `Mount/MountEquip`, `Mount/MountInfo`, `Mount/MountEquipPos`, `Pet/PetInfo`, `Pet/PetScroll`, `Pet/PetSkill`, `Pet/PetStoneSlot`, `Pet/PetTSkill`, etc.
- Cross-feature common: `CommonWidgets/CommonTabs`.
- Cross-feature item info: `Item/ItemInfoView_Source`.

Common `Partial.WidgetPath` targets follow a `Prefabs/<Template>` convention pointing into an inactive `Prefabs/` host node inside the current prefab: `Prefabs/Item`, `Prefabs/PropItem`, `Prefabs/StoneItem`, `Prefabs/Stage`, `Prefabs/Effect`, `Prefabs/Star`, `Prefabs/CatItem`, etc. See the "Internal Template Host Pattern" section of `prefab-patterns.md`.

Common `Component.Path` roots:

- `Content`
- `DownLeft`
- `BG` / `Background`
- `Prefabs` (template host)
- numeric roots such as `1`, `2`
- feature-specific roots (`Atts`, `Slots`, `StoneLevelTotal`, `Equip`, `ScrollPlane` in Pet; `Normal`, `Result`, `Consume`, `Attrs` in Mount)
- widget-local roots such as `Equiped`, `Lock`, `Level`, `tex_*`

## Registration

Openable views normally need a `UIDefine` entry, for example:

```lua
SomeView = "Feature/SomeView"
```

Item widgets and embedded partials often do not need direct `UIDefine` entries.

When adding or renaming a view, keep these aligned:

- prefab name
- prefab path
- Lua path
- `UIDefine` value
- call sites such as `UIManager:Open(...)`
- `Partial.Widget` values

## Old-Style Plane Caveat

Old-style `Plane` files use `_ViewBase:New(...)` and `InitComponents`. Existing old-style files should be handled in their local style. Do not migrate a file to new-style unless explicitly asked.
