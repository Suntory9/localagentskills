# UnityMCP Execution

How to drive UnityMCP for prefab generation and modification in this project.

## Hard Preconditions

Before any prefab-generation work:

1. Confirm UnityMCP tools are available in the current environment.
2. Confirm the Unity Editor is reachable and ready for tools.
3. If UnityMCP is unavailable or not connected, stop. Tell the user the skill requires UnityMCP installed and connected. Do not silently fall back to manual editor instructions unless the user explicitly asks for a non-UnityMCP fallback.

## Build Mode Decision

Pick one before touching Unity:

- **Mode A — Mockup → New Prefab.** No reference prefab. Build from schema only. Use this for novel UI with no same-feature analog. In this project, this should be rare — most openable views have a same-feature neighbor.
- **Mode B — Mockup + Reference Prefab → Content Replacement.** Instantiate the reference, preserve `Root` / mask / body shell, replace only the intended `Content` subtree. **Default mode for this project's openable views.**

If the mode is unclear, infer from the files the user provided. If risk is material, ask one concise clarification.

## Standard Tool Sequence

Prefer this pattern over ad-hoc editor scripts:

1. `manage_asset` or `manage_prefabs` to locate prefab assets and reference prefabs.
2. `manage_prefabs.get_hierarchy` to inspect reference structure before modifying.
3. `manage_gameobject` to instantiate prefabs or create empty nodes.
4. `manage_components.set_property` to apply `RectTransform`, text, image, layout values.
5. `batch_execute` for repetitive creation or property updates.
6. `manage_prefabs.create_from_gameobject` with `unlink_if_instance=true` when saving a modified prefab instance as a new prefab.
7. `read_console` plus optional screenshots to verify results.

## Mode A — New Prefab

1. Create a temporary scene object hierarchy from the schema JSON.
2. Add/configure `RectTransform`, `Image`, `Button`, layout groups, text components through UnityMCP.
3. Apply project conventions during creation, not after — root component stack for openable views, font references, slicing, anchors.
4. Save as a new prefab in the target folder (`Assets/Prefabs/Plane/<Feature>/<Name>.prefab`).
5. Set the prefab importer's `assetBundleName` to `plane/<Feature>/<Name>` for new openable views.
6. Delete temporary scene instances after the prefab is saved.

## Mode B — Reference + Content Replacement

1. Instantiate the reference prefab into the scene as a temporary working copy.
2. **Preserve the outer structure** unless the user explicitly asks to replace it: root, mask (`BG`-style), body (`Content`-style), animator, common navigation (`DownLeft` etc.), font policy.
3. Attempt true deletion of existing `Content` children first when the task is full-replacement.
4. Generate new nodes directly under `Content` after the old children are removed.
5. **Fallback when deletion is unsafe** (Unity forbids deleting linked prefab-instance children): disable the old children instead, note the fallback explicitly, and place new structure under a fresh child such as `Content/NewRoot`. Do not silently leave the fallback hidden — surface it in the final report.
6. Reuse nested prefabs (item cells, common buttons, return controls) — instantiate, do not visually recreate.
7. Save the modified instance as a new prefab in the same directory as the reference unless the user requests otherwise. Use `unlink_if_instance=true`.
8. Remove the temporary scene instance after saving.

## Execution Guidelines

- Prefer `batch_execute` for repeated property writes; serial `set_property` calls are wasteful and harder to roll back.
- Disable layout drivers on the target container before applying manual `RectTransform` values — otherwise the layout group will overwrite your writes.
- Use full path targeting when sibling node names repeat. `Content/Items/0/Icon` not `Icon`.
- Verify real component and property names from MCP resources when a property write is uncertain. Guessing leads to silent no-op writes.
- For Mode B full content replacement, attempt true deletion first; only fall back to hiding when Unity blocks it.

## Reuse Rules

When a reusable prefab or node is specified:

- Instantiate or duplicate the existing prefab rather than rebuilding the subtree.
- Keep inherited visuals, animators, button transitions where possible.
- Modify only the minimum text, active state, layout, and positioning required.
- If a reused node contains multiple identically named children, address them by full path.

For card/cell-like nodes:

- Instantiate the prefab for each repeated slot.
- Set slot-specific content (numbers, labels, active flags).
- Hide unrelated badges/decorators when the mockup does not show them.

## Component Strategy

- If the reference prefab contains the desired button or text style, duplicate and retarget — do not build a fresh stack from scratch.
- If the target flow already uses `TextMeshProUGUI`, reuse TMP-bearing nodes from the reference. If it uses legacy `Text`, stay with legacy `Text` and the project font.
- If pure UnityMCP creation requires guessing unstable component setup, prefer duplicating an existing project node over switching to scripts.

## Validation After Build

1. `read_console` for errors/warnings caused by the build.
2. Inspect the resulting prefab asset path.
3. Capture a scene or game view screenshot when visual verification matters.
4. If the result is structurally correct but visually off, iterate with UnityMCP — do not switch to a manual workflow.

Cross-reference `references/validation-checklist.md` for the full per-prefab and per-View checks before reporting done.

## What To Report Back

After build, surface:

- Created/modified prefab path.
- Reference prefab used, or explicit "no suitable reference existed".
- AssetBundle name set for new view-type prefabs, or why it is intentionally empty.
- Any nodes left disabled instead of deleted due to prefab-instance limitations.
- Any visual mismatches or unresolved asset bindings still open.
- Anything still requiring Unity Editor, device, or integration verification you could not do via MCP.
