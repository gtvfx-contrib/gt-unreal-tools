"""Filesystem-based Unreal Level Editor main menu bar builder.

Builds an Unreal Level Editor menu hierarchy by walking a directory tree:

  - Root folder       → top-level sub-menu on the main menu bar
  - Sub-folders       → nested sub-menus (arbitrarily deep)
  - ``*.py`` files    → clickable menu action items
  - ``<N>_sep.*``     → separator lines

Unlike the 3ds Max equivalent, Unreal's ``ToolMenus`` system uses stable string
``Name`` paths (e.g. ``LevelEditor.MainMenu.MyTools.Animation``) as identifiers
rather than UUIDs, so no GUID management is required.

**Script file format** (``*.py``)::

    # label: My Tool Name      ← display name (optional; falls back to filename)
    # tooltip: What it does    ← hover text (optional)
    # order: 0.0               ← float sort key (optional)
    # section: My Group        ← Unreal section/group label (optional)

    import my_package.tool
    my_package.tool.launch()

When a menu item is clicked Unreal executes::

    import runpy; runpy.run_path(r'<absolute path to .py file>')

**Sidecar files:**

  ``__menu__.json``   — Folder metadata: optional ``display_name`` and ``order``
                        override keys (no guid needed).
  ``__inject__.json`` — Injection slot: ``source_env`` (required) and optional
                        ``display_name``.

**Naming rules** (identical to the 3ds Max equivalent):

  - ``00_Name`` / ``08.5_Name`` — numeric prefix sets sort order; stripped from
    the display name
  - ``<N>_sep.*`` — rendered as a separator
  - ``_resource`` in a directory name — directory skipped entirely
  - ``.`` prefix or ``__pycache__`` — directory skipped
  - ``__inject__.json`` present — folder treated as an injection slot

**Usage**::

    from gt.unreal.menulib import MenuLib, MenuSession, load_from_env

    # Single root
    lib = MenuLib(r"C:/tools/MyTools")
    lib.build()

    # Multiple roots merged into one top-level menu
    lib = MenuLib(r"C:/RepoA/MyTools")
    lib.add_root(r"C:/RepoB/MyTools")
    lib.build()

    # Multiple roots from an environment variable (semicolon-separated paths)
    libs = load_from_env("STUDIO_MENU_ROOTS")

    # Per-package startup pattern
    session = MenuSession("STUDIO_MENU_ROOTS")
    session.load()     # idempotent — removes then rebuilds
    session.remove()   # tear down without rebuilding

**Context menus** (right-click menus in the Content Browser, viewport, etc.)::

    from gt.unreal.menulib import ContextMenuLib, ContextMenuSession

    # The env var points to a *contexts root* directory whose sub-folders are
    # each named after the Unreal context menu they should attach to:
    #
    #   contexts/
    #   └── ContentBrowser.AssetContextMenu/
    #       └── run_validation.py
    #
    session = ContextMenuSession("CONTEXT_MENU_ROOTS")
    session.load()

    # Or scan a single contexts-root directory directly (no env var):
    libs = load_context_from_root(r"C:/tools/contexts")

    # Or manage one context menu folder directly:
    lib = ContextMenuLib(r"C:/tools/contexts/ContentBrowser.AssetContextMenu")
    lib.build()

"""

__all__ = [
    "MenuLib",
    "MenuNode",
    "MenuSession",
    "load_from_env",
    "ContextMenuLib",
    "ContextMenuSession",
    "load_context_from_env",
    "load_context_from_root",
    "_registry",
]

from ._shared import *
from ._main_menu import *
from ._context_menu import *
