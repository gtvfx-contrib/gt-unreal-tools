"""Unreal context menu (right-click menu) builder.

Provides :class:`ContextMenuLib`, :class:`ContextMenuSession`,
:func:`load_context_from_root`, and :func:`load_context_from_env` for
attaching items to existing Unreal context menus (Content Browser, viewport,
outliner, etc.).

"""

from __future__ import annotations

__all__ = [
    "ContextMenuLib",
    "ContextMenuSession",
    "load_context_from_env",
    "load_context_from_root",
]

import os
from typing import List, Optional

from ._shared import (
    MenuNode,
    _registry,
    _read_folder_config,
    _scan_directory,
    _merge_children,
    _populate_menu,
    _is_resource_dir,
    _SUPPRESSED_ENV,
    _safe_name,
)

import unreal


# ---------------------------------------------------------------------------
# ContextMenuLib
# ---------------------------------------------------------------------------

class ContextMenuLib:
    """Adds items to an existing Unreal context menu from a directory tree.

    The root folder's **basename** is used as the Unreal ``ToolMenu`` name to
    attach to.  For example, a folder named
    ``ContentBrowser.AssetContextMenu`` attaches to the Content Browser
    asset right-click menu.  Items in the folder become action entries;
    sub-folders become nested sub-menus — the same directory conventions as
    :class:`MenuLib` apply throughout.

    The ``__menu__.json`` sidecar may supply an optional ``"menu_name"`` key
    to override the Unreal menu name derived from the folder basename.

    Directory structure example::

        ContentBrowser.AssetContextMenu/   ← folder basename = Unreal menu path
        ├── 00_Validate.py                 ← action added directly to the menu
        ├── 01_sep.py                      ← separator
        └── 02_Export/                     ← sub-menu "Export"
            └── 00_FBX.py

    Usage::

        lib = ContextMenuLib(r"C:/tools/ContentBrowser.AssetContextMenu")
        lib.build()    # scan + attach to the existing context menu
        lib.remove()   # unregister all added entries

    """

    def __init__(
        self,
        root_dir: str,
        callback_id: Optional[str] = None,
    ) -> None:
        self.root_dir = os.path.normpath(root_dir)
        config = _read_folder_config(self.root_dir)
        self._target_menu_name: str = (
            config.get("menu_name") or os.path.basename(self.root_dir)
        )
        if callback_id is None:
            callback_id = (
                f"contextmenulib_{_safe_name(os.path.basename(self.root_dir))}"
            )
        self.callback_id = callback_id
        self._extra_roots: List[str] = []

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_root(self, root_dir: str) -> None:
        """Register an additional directory to merge into this context menu.

        Must be called *before* :meth:`build`.
        """
        self._extra_roots.append(os.path.normpath(root_dir))

    def build(self) -> None:
        """Scan directory tree(s) and attach items to the Unreal context menu.

        Idempotent: calls :meth:`remove` first so repeated calls rebuild
        cleanly.  Any extra roots registered via :meth:`add_root` are merged
        into the primary tree before items are attached.
        """
        if not os.path.isdir(self.root_dir):
            raise ValueError(
                f"ContextMenuLib: root_dir does not exist: {self.root_dir!r}"
            )

        children = _scan_directory(self.root_dir)
        for extra in self._extra_roots:
            if not os.path.isdir(extra):
                print(f"ContextMenuLib: extra root not found, skipping: {extra!r}")
                continue
            _merge_children(children, _scan_directory(extra))

        root_node = MenuNode(
            display_name=self._target_menu_name,
            path=self.root_dir,
            is_submenu=True,
            children=children,
        )

        self.remove()
        _registry[self.callback_id] = self

        try:
            self._attach_to_context_menu(root_node)
            self._refresh()
        except Exception as exc:
            print(
                f"ContextMenuLib: failed to build {self._target_menu_name!r}: {exc}"
            )

    def remove(self) -> None:
        """Unregister all entries added by this instance.

        Uses ``ToolMenus.unregister_owner_by_name`` to remove every entry
        across all menus that was registered under this instance's
        *callback_id*.  Errors are silently swallowed so :meth:`build` can
        safely call this on its first run.
        """
        try:
            menus = unreal.ToolMenus.get()
            menus.unregister_owner_by_name(unreal.Name(self.callback_id))
            menus.refresh_all_widgets()
        except Exception:
            pass
        _registry.pop(self.callback_id, None)

    # ------------------------------------------------------------------
    # Internal: Unreal menu construction
    # ------------------------------------------------------------------

    def _attach_to_context_menu(self, root_node: MenuNode) -> None:
        """Find the target context menu and populate it from *root_node*'s children."""
        menus = unreal.ToolMenus.get()
        context_menu = menus.find_menu(unreal.Name(self._target_menu_name))
        if not context_menu:
            raise RuntimeError(
                f"ContextMenuLib: context menu not found: {self._target_menu_name!r}"
            )
        _populate_menu(self.callback_id, context_menu, root_node)

    def _refresh(self) -> None:
        """Refresh all Unreal menu widgets to make changes visible."""
        try:
            unreal.ToolMenus.get().refresh_all_widgets()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# ContextMenuSession
# ---------------------------------------------------------------------------

class ContextMenuSession:
    """Manages the load/remove lifecycle for context menus sourced from one env var.

    Mirrors :class:`MenuSession` but produces :class:`ContextMenuLib` instances
    that attach to existing Unreal context menus rather than the main menu bar::

        from gt.unreal.menulib import ContextMenuSession

        _session = ContextMenuSession("STUDIO_CONTEXT_ROOTS")
        _session.load()

    If ``MENULIB_SUPPRESSED`` contains this session's *env_var* name, ``load()``
    is a no-op.
    """

    def __init__(self, env_var: str) -> None:
        self.env_var = env_var
        self._instances: List[ContextMenuLib] = []

    def load(self) -> List[ContextMenuLib]:
        """Remove existing entries then rebuild from *env_var*.

        Returns the list of :class:`ContextMenuLib` instances built, or an
        empty list if this session is suppressed.
        """
        suppressed = {
            v.strip()
            for v in os.environ.get(_SUPPRESSED_ENV, "").split(";")
            if v.strip()
        }
        if self.env_var in suppressed:
            print(
                f"ContextMenuSession({self.env_var!r}): suppressed by"
                f" {_SUPPRESSED_ENV!r}, skipping."
            )
            return []

        self.remove()
        self._instances = load_context_from_env(self.env_var)
        return self._instances

    def remove(self) -> None:
        """Unregister all context menu entries registered by this session."""
        for lib in self._instances:
            try:
                lib.remove()
            except Exception as exc:
                print(
                    f"ContextMenuSession({self.env_var!r}): failed to remove"
                    f" {lib.root_dir!r}: {exc}"
                )
        self._instances = []


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def load_context_from_root(root_dir: str) -> List[ContextMenuLib]:
    """Scan *root_dir* for sub-folders and build one :class:`ContextMenuLib` each.

    Each sub-folder's basename is used as the Unreal context menu path to
    attach to (e.g. ``ContentBrowser.AssetContextMenu``).  Sub-folders whose
    name contains ``_resource``, starts with ``.``, or equals ``__pycache__``
    are ignored.

    Example layout::

        contexts/                                  ← pass this path
        └── ContentBrowser.AssetContextMenu/       ← becomes one ContextMenuLib
            └── run_validation.py

    Returns the list of built :class:`ContextMenuLib` instances.
    """
    root_dir = os.path.normpath(root_dir)
    if not os.path.isdir(root_dir):
        print(f"load_context_from_root: directory not found: {root_dir!r}")
        return []

    instances: List[ContextMenuLib] = []
    try:
        entries = sorted(os.scandir(root_dir), key=lambda e: e.name.lower())
    except OSError as exc:
        print(f"load_context_from_root: cannot scan {root_dir!r}: {exc}")
        return []

    for entry in entries:
        if not entry.is_dir():
            continue
        if (
            _is_resource_dir(entry.name)
            or entry.name.startswith(".")
            or entry.name == "__pycache__"
        ):
            continue
        try:
            lib = ContextMenuLib(entry.path)
            lib.build()
            instances.append(lib)
        except Exception as exc:
            print(f"ContextMenuLib: failed to build menu from {entry.path!r}: {exc}")

    return instances


def load_context_from_env(env_var: str) -> List[ContextMenuLib]:
    """Instantiate one :class:`ContextMenuLib` per context menu discovered in *env_var*.

    The environment variable should contain one or more **contexts-root** directory
    paths separated by semicolons.  Each contexts-root is scanned for sub-folders;
    every sub-folder whose basename names a context menu (e.g.
    ``ContentBrowser.AssetContextMenu``) becomes a :class:`ContextMenuLib` instance.

    Sub-folders with the same basename across multiple roots are automatically
    merged via :meth:`ContextMenuLib.add_root`, so contributions from several
    packages can coexist in one context menu.

    Example layout::

        # CONTEXT_MENU_ROOTS = "Z:/RepoA/contexts;Z:/RepoB/contexts"
        #
        # Z:/RepoA/contexts/
        # └── ContentBrowser.AssetContextMenu/
        #     └── validate.py
        #
        # Z:/RepoB/contexts/
        # └── ContentBrowser.AssetContextMenu/   ← same name → merged
        #     └── export.py

    Returns the list of built :class:`ContextMenuLib` instances.
    """
    raw = os.environ.get(env_var, "")

    # groups: context-menu-name → list of folder paths (one per contributing root)
    groups: dict = {}
    for root in raw.split(";"):
        root = root.strip()
        if not root or not os.path.isdir(root):
            continue
        try:
            entries = os.scandir(root)
        except OSError:
            continue
        for entry in entries:
            if not entry.is_dir():
                continue
            if (
                _is_resource_dir(entry.name)
                or entry.name.startswith(".")
                or entry.name == "__pycache__"
            ):
                continue
            groups.setdefault(entry.name, []).append(entry.path)

    instances: List[ContextMenuLib] = []
    for paths in groups.values():
        try:
            lib = ContextMenuLib(paths[0])
            for extra in paths[1:]:
                lib.add_root(extra)
            lib.build()
            instances.append(lib)
        except Exception as exc:
            print(f"ContextMenuLib: failed to build menu from {paths[0]!r}: {exc}")

    return instances
