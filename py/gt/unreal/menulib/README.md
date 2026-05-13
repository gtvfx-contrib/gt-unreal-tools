# `gt.unreal.menulib` — Filesystem-Driven Unreal Menu Builder

Builds and manages Unreal Engine menus (main menu bar and right-click context menus) by walking a directory tree. No C++, no plugin required — pure Python using Unreal's `ToolMenus` API.

---

## Table of Contents

1. [Overview](#overview)
2. [Module Structure](#module-structure)
3. [Directory Tree Conventions](#directory-tree-conventions)
4. [Script File Format](#script-file-format)
5. [Sidecar Files](#sidecar-files)
6. [Main Menu Bar](#main-menu-bar)
   - [MenuLib](#menulib)
   - [MenuSession](#menusession)
   - [load_from_env](#load_from_env)
7. [Context Menus](#context-menus)
   - [ContextMenuLib](#contextmenulib)
   - [ContextMenuSession](#contextmenusession)
   - [load_context_from_root](#load_context_from_root)
   - [load_context_from_env](#load_context_from_env)
8. [Startup File Pattern](#startup-file-pattern)
9. [Multi-Package / Multi-Root Merging](#multi-package--multi-root-merging)
10. [Injection Slots](#injection-slots)
11. [Suppression](#suppression)
12. [Environment Variables Reference](#environment-variables-reference)
13. [Public API Reference](#public-api-reference)

---

## Overview

`menulib` maps a directory tree to an Unreal Engine menu hierarchy:

| Filesystem item | Menu result |
|---|---|
| Root folder | Top-level sub-menu on the Level Editor main menu bar |
| Sub-folder | Nested sub-menu (arbitrarily deep) |
| `*.py` file | Clickable action item |
| `<N>_sep.*` file | Separator line |
| `__menu__.json` sidecar | Display name / sort order override for a folder |
| `__inject__.json` sidecar | Injection slot — populate a sub-menu from another env var |

Unreal's `ToolMenus` system uses stable string `Name` paths (e.g. `LevelEditor.MainMenu.MyTools.Animation`) as identifiers, so no GUID management is needed.

When an action item is clicked, Unreal executes:

```python
import runpy; runpy.run_path(r'<absolute path to .py file>')
```

---

## Module Structure

```
menulib/
├── __init__.py        ← public package surface; aggregates all sub-modules
├── _shared.py         ← constants, registry, MenuNode, helpers, scanner
├── _main_menu.py      ← MenuLib, MenuSession, load_from_env
└── _context_menu.py   ← ContextMenuLib, ContextMenuSession, load_context_from_*
```

Import everything from the package root — never import from sub-modules directly:

```python
from gt.unreal.menulib import MenuLib, MenuSession, ContextMenuLib, ContextMenuSession
```

---

## Directory Tree Conventions

### Naming and sort order

A **numeric prefix** sets the sort order and is stripped from the display name:

```
00_MyMenu/          → display: "MyMenu",   order: 0.0
05_Animation/       → display: "Animation", order: 5.0
08.5_Utils/         → display: "Utils",    order: 8.5
10 Export/          → display: "Export",   order: 10.0   (space separator also works)
NoPrefix/           → display: "NoPrefix", order: ∞ (appended last)
```

### Separators

Any file whose name matches `<digits>_sep` (case-insensitive) is rendered as a separator:

```
00_sep.py           → separator at sort position 0
05_sep.txt          → separator at sort position 5
```

### Skipped entries

The following directory names are **silently ignored**:

| Pattern | Example |
|---|---|
| Contains `_resource` (case-insensitive) | `icons_resource`, `data_resource` |
| Starts with `.` | `.git`, `.venv` |
| Equals `__pycache__` | `__pycache__` |

### Example tree

```
MyTools/                        ← top-level menu: "MyTools"
├── __menu__.json               ← optional: override display name / order
├── 00_Rigging/                 ← sub-menu: "Rigging"
│   ├── 00_BuildRig.py          ← action: "Build Rig"
│   └── 01_sep.py               ← separator
│   └── 02_CleanupRig.py        ← action: "Cleanup Rig"
├── 01_Animation/               ← sub-menu: "Animation"
│   └── 00_BakeAnimation.py     ← action: "Bake Animation"
└── icons_resource/             ← skipped entirely
```

---

## Script File Format

Each `.py` file in the tree becomes one menu action. Header comments at the top of the file supply optional metadata:

```python
# label: My Tool Name       ← display name (falls back to filename if omitted)
# tooltip: What it does     ← hover text shown in the menu
# order: 1.5                ← float sort key (overrides filename prefix if set)
# section: My Group         ← Unreal section/group label (visible header above items)

import my_package.tool
my_package.tool.launch()
```

All four comment keys are **optional** and **case-insensitive**. Only the first occurrence of each key is used. Any non-header lines below are ignored during parsing but are executed in full when the action is invoked.

### Section grouping

Items sharing the same `# section:` value are grouped under a visible label in the menu. Items without a section are placed in an unlabelled default section.

```python
# section: Rigging Tools
```

---

## Sidecar Files

### `__menu__.json` — Folder metadata

Place alongside any folder to override its display name and/or sort order:

```json
{
    "display_name": "My Overridden Title",
    "order": 3.5
}
```

Both keys are optional. If absent the folder's filename (numeric prefix stripped) is used.

For `ContextMenuLib`, a `__menu__.json` at the root may also supply `"menu_name"` to override the Unreal context menu path derived from the folder basename:

```json
{
    "menu_name": "ContentBrowser.AssetContextMenu"
}
```

### `__inject__.json` — Injection slot

Marks a folder as an *injection slot*: its sub-menu content is populated from another environment variable at load time rather than from files on disk. See [Injection Slots](#injection-slots) below.

---

## Main Menu Bar

### MenuLib

The core class. Scans a root directory and registers a top-level sub-menu on `LevelEditor.MainMenu`.

```python
from gt.unreal.menulib import MenuLib

lib = MenuLib(r"C:/tools/MyTools")
lib.build()     # scan + register immediately
lib.remove()    # unregister
```

**Constructor parameters:**

| Parameter | Type | Description |
|---|---|---|
| `root_dir` | `str` | Path to the root folder. Folder name (prefix stripped) becomes the menu title. |
| `callback_id` | `str` \| `None` | Stable owner name for Unreal registration. Auto-derived from `root_dir` if omitted. |

**Key methods:**

| Method | Description |
|---|---|
| `build()` | Scan directory tree(s) and register the menu. Calls `remove()` first — safe to call repeatedly. |
| `remove()` | Unregister the menu and remove from the internal registry. |
| `add_root(root_dir)` | Merge a second directory tree into this menu. Must be called before `build()`. |

---

### MenuSession

Manages the load/remove lifecycle for all menus sourced from a single environment variable. Intended for per-package startup scripts.

```python
from gt.unreal.menulib import MenuSession

session = MenuSession("STUDIO_MENU_ROOTS")
session.load()      # builds all menus from the env var
session.remove()    # tears them all down
session.load()      # safe to call again — removes then rebuilds
```

**Constructor parameters:**

| Parameter | Type | Description |
|---|---|---|
| `env_var` | `str` | Name of the environment variable containing semicolon-separated root paths. |

**Key methods:**

| Method | Returns | Description |
|---|---|---|
| `load()` | `List[MenuLib]` | Remove then rebuild. Returns the list of built instances, or `[]` if suppressed. |
| `remove()` | `None` | Tear down all menus registered by this session. |

---

### load_from_env

Lower-level convenience function. Reads an env var, groups paths by basename, and returns the built `MenuLib` instances.

```python
from gt.unreal.menulib import load_from_env

libs = load_from_env("STUDIO_MENU_ROOTS")
```

Paths that share the same folder basename are automatically merged into one top-level menu (see [Multi-Package / Multi-Root Merging](#multi-package--multi-root-merging)).

---

## Context Menus

Context menus (right-click menus in the Content Browser, viewport, outliner, etc.) are managed separately. The root folder's **basename** is used as the Unreal `ToolMenu` name to attach to.

### ContextMenuLib

Scans a root directory and injects items into an existing Unreal context menu.

```python
from gt.unreal.menulib import ContextMenuLib

lib = ContextMenuLib(r"C:/tools/contexts/ContentBrowser.AssetContextMenu")
lib.build()
lib.remove()
```

The folder name `ContentBrowser.AssetContextMenu` is used directly as the Unreal menu path. A `__menu__.json` with a `"menu_name"` key can override this.

**Directory structure example:**

```
ContentBrowser.AssetContextMenu/
├── 00_Validate.py          ← action added directly to the context menu
├── 01_sep.py               ← separator
└── 02_Export/              ← sub-menu "Export"
    └── 00_FBX.py
```

---

### ContextMenuSession

Mirrors `MenuSession` for context menus.

```python
from gt.unreal.menulib import ContextMenuSession

session = ContextMenuSession("STUDIO_CONTEXT_ROOTS")
session.load()
session.remove()
```

The environment variable should point to one or more **contexts-root** directories (not directly to context menu folders). Each contexts-root is scanned for sub-folders; every qualifying sub-folder becomes one `ContextMenuLib` instance.

**Expected layout:**

```
contexts/                                   ← value in STUDIO_CONTEXT_ROOTS
├── ContentBrowser.AssetContextMenu/        → attaches to Content Browser asset menu
│   └── 00_Validate.py
└── LevelEditor.ActorContextMenu/           → attaches to viewport actor menu
    └── 00_QuickExport.py
```

---

### load_context_from_root

Scan a single contexts-root directory and build one `ContextMenuLib` per sub-folder.

```python
from gt.unreal.menulib import load_context_from_root

libs = load_context_from_root(r"C:/tools/contexts")
```

---

### load_context_from_env

Lower-level equivalent of `ContextMenuSession.load()`. Reads the env var, groups context menu folders by name across multiple roots, and returns the built instances.

```python
from gt.unreal.menulib import load_context_from_env

libs = load_context_from_env("STUDIO_CONTEXT_ROOTS")
```

---

## Startup File Pattern

Unreal executes Python startup scripts automatically at editor boot. Create an `init_unreal.py` alongside your package and point Unreal's Python path to its directory.

**`gt/unreal/startup/init_unreal.py`:**

```python
print("!---- Startup from Unreal Tools ----!")


def initialize():
    """Initialize the Unreal menu library."""
    from gt.unreal.menulib import MenuSession, ContextMenuSession

    session = MenuSession("STUDIO_MENU_ROOTS")
    session.load()

    session = ContextMenuSession("CONTEXT_MENU_ROOTS")
    session.load()


initialize()
```

Unreal discovers and runs any file named `init_unreal.py` that lives on the Python path automatically when the editor starts. Wrapping the body in `initialize()` keeps the module namespace clean.

### Wiring up the environment variables

Set the env vars **before** launching Unreal (e.g. in a studio launcher script):

```batch
REM Windows launcher batch file
set STUDIO_MENU_ROOTS=Z:\pipeline\menus\MyStudioTools
set CONTEXT_MENU_ROOTS=Z:\pipeline\menus\contexts
"C:\Program Files\Epic Games\UE_5.4\Engine\Binaries\Win64\UnrealEditor.exe" MyProject.uproject
```

Or via Python before calling `session.load()`:

```python
import os
os.environ["STUDIO_MENU_ROOTS"] = r"Z:\pipeline\menus\MyStudioTools"
os.environ["CONTEXT_MENU_ROOTS"] = r"Z:\pipeline\menus\contexts"
```

### Multi-package startup

When multiple packages each need to contribute menus, each package can own its own `MenuSession` pointing to its own env var. The sessions are independent and each can be loaded/removed without affecting the others:

```python
# package_a/init_unreal.py
from gt.unreal.menulib import MenuSession, ContextMenuSession

_menu_session = MenuSession("PACKAGE_A_MENU_ROOTS")
_context_session = ContextMenuSession("PACKAGE_A_CONTEXT_ROOTS")

_menu_session.load()
_context_session.load()
```

```python
# package_b/init_unreal.py
from gt.unreal.menulib import MenuSession

_menu_session = MenuSession("PACKAGE_B_MENU_ROOTS")
_menu_session.load()
```

---

## Multi-Package / Multi-Root Merging

Multiple directory trees that share the **same root folder basename** are automatically merged into a single top-level menu. This allows several packages to contribute to one shared menu without coordination.

```
# STUDIO_MENU_ROOTS = "Z:/RepoA/MyStudioTools;Z:/RepoB/MyStudioTools"

Z:/RepoA/MyStudioTools/
└── 00_Rigging/
    └── BuildRig.py

Z:/RepoB/MyStudioTools/
└── 00_Rigging/           ← same sub-menu name → merged recursively
    └── CleanupRig.py
└── 01_Animation/
    └── BakeAnim.py
```

Result: one `MyStudioTools` menu containing a `Rigging` sub-menu with both `BuildRig` and `CleanupRig` actions, plus an `Animation` sub-menu.

The same merging logic applies to `ContextMenuLib` when multiple roots contribute to the same context menu basename.

---

## Injection Slots

An injection slot lets a sub-menu in one tool's tree be populated dynamically from another package's env var at load time. This is the mechanism for building a unified aggregation menu (e.g. a shared "Studio Tools" top-level menu that ingests contributions from many independent env vars).

### Setup

1. Create a folder inside your menu tree with `__inject__.json`:

```
MyStudioTools/
└── 05_ClientTools/             ← sub-menu "Client Tools"
    └── __inject__.json
```

2. The `__inject__.json` specifies which env var to read:

```json
{
    "source_env": "CLIENT_TOOL_ROOTS",
    "display_name": "Client Tools"
}
```

3. At load time, `menulib` reads `CLIENT_TOOL_ROOTS`, scans all listed directories, and populates the `Client Tools` sub-menu with their contents.

4. To suppress the injection slot's own `MenuSession` (so it doesn't also appear as a top-level menu), add its env var name to `MENULIB_SUPPRESSED`:

```batch
set MENULIB_SUPPRESSED=CLIENT_TOOL_ROOTS
```

### Local items alongside an injection slot

Any `.py` files placed directly inside the injection slot folder are merged with the injected content:

```
05_ClientTools/
├── __inject__.json
└── 00_Fallback.py      ← always present, merged with injected items
```

---

## Suppression

Set the `MENULIB_SUPPRESSED` environment variable to a semicolon-separated list of env var names. Any `MenuSession` or `ContextMenuSession` whose `env_var` appears in this list will skip `load()` silently.

```batch
set MENULIB_SUPPRESSED=CLIENT_TOOL_ROOTS;VENDOR_CONTEXT_ROOTS
```

This is primarily used to prevent a package's menus from appearing as both a top-level menu *and* an injected sub-menu simultaneously.

---

## Environment Variables Reference

| Variable | Used by | Description |
|---|---|---|
| `STUDIO_MENU_ROOTS` *(example)* | `MenuSession` / `load_from_env` | Semicolon-separated paths to menu root directories. Multiple paths sharing the same basename are merged. |
| `STUDIO_CONTEXT_ROOTS` *(example)* | `ContextMenuSession` / `load_context_from_env` | Semicolon-separated paths to **contexts-root** directories. Each sub-folder of a contexts-root becomes one context menu. |
| `MENULIB_SUPPRESSED` | `MenuSession`, `ContextMenuSession` | Semicolon-separated env var names whose sessions should be skipped on `load()`. |

> The env var names `STUDIO_MENU_ROOTS` and `STUDIO_CONTEXT_ROOTS` are **examples** — use whatever names suit your studio. Pass the chosen names to `MenuSession(...)` / `ContextMenuSession(...)`.

---

## Public API Reference

All names below are importable directly from `gt.unreal.menulib`.

### Classes

| Class | Module | Description |
|---|---|---|
| `MenuLib` | `_main_menu` | Scans a directory tree and builds a top-level Level Editor menu. |
| `MenuSession` | `_main_menu` | Lifecycle manager for main menus sourced from one env var. |
| `ContextMenuLib` | `_context_menu` | Scans a directory tree and injects items into an existing context menu. |
| `ContextMenuSession` | `_context_menu` | Lifecycle manager for context menus sourced from one env var. |
| `MenuNode` | `_shared` | Dataclass representing one node in the scanned menu tree. |

### Functions

| Function | Module | Description |
|---|---|---|
| `load_from_env(env_var)` | `_main_menu` | Build one `MenuLib` per unique basename found in `env_var`. |
| `load_context_from_env(env_var)` | `_context_menu` | Build one `ContextMenuLib` per context menu discovered in `env_var`. |
| `load_context_from_root(root_dir)` | `_context_menu` | Build one `ContextMenuLib` per sub-folder of `root_dir`. |

### Data

| Name | Type | Description |
|---|---|---|
| `_registry` | `dict[str, MenuLib \| ContextMenuLib]` | Module-level map of `callback_id → lib instance`. Can be inspected to see what is currently registered. |
