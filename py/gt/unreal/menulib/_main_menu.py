"""Level Editor main menu bar builder.

Provides :class:`MenuLib`, :class:`MenuSession`, and :func:`load_from_env`
for building and managing top-level sub-menus on the Unreal Level Editor
main menu bar.

"""

from __future__ import annotations

__all__ = [
    "MenuLib",
    "MenuSession",
    "load_from_env",
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
    _strip_prefix,
    _safe_name,
    _MAIN_MENU,
    _SUPPRESSED_ENV,
)

import unreal


# ---------------------------------------------------------------------------
# MenuLib
# ---------------------------------------------------------------------------

class MenuLib:
    """Builds and registers an Unreal Level Editor menu from a directory tree.

    Parameters
    ----------
    root_dir:
        Path to the root folder.  The folder name (numeric prefix stripped)
        becomes the top-level menu title.  An optional ``__menu__.json`` in the
        root folder may override the title via the ``"display_name"`` key.

    callback_id:
        Unique string identifier used to track this instance in the module
        registry and as the owner name when registering Unreal menus, which
        enables clean unregistration.  Defaults to a sanitised version of the
        root folder name prefixed with ``"menulib_"``.

    Usage::

        lib = MenuLib(r"C:/tools/MyTools")
        lib.build()    # scan directories + build Unreal menu immediately
        lib.remove()   # tear down

    """

    def __init__(
        self,
        root_dir: str,
        callback_id: Optional[str] = None,
    ) -> None:
        self.root_dir = os.path.normpath(root_dir)

        if callback_id is None:
            callback_id = f"menulib_{_safe_name(os.path.basename(self.root_dir))}"
        self.callback_id = callback_id

        self._extra_roots: List[str] = []
        self._root_node: Optional[MenuNode] = None
        self._registered_menu_name: Optional[str] = None

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def add_root(self, root_dir: str) -> None:
        """Register an additional directory to merge into this menu.

        Must be called *before* :meth:`build`.  The folder name should match
        :attr:`root_dir`'s basename so they represent the same logical menu
        (not enforced).
        """
        self._extra_roots.append(os.path.normpath(root_dir))

    def build(self) -> None:
        """Scan the directory tree(s) and build the Unreal menu immediately.

        Idempotent: calls :meth:`remove` first so repeated calls rebuild
        cleanly.  Any extra roots registered via :meth:`add_root` are merged
        into the primary tree before the menu is constructed.
        """
        if not os.path.isdir(self.root_dir):
            raise ValueError(f"MenuLib: root_dir does not exist: {self.root_dir!r}")

        config = _read_folder_config(self.root_dir)
        display_name = (
            config.get("display_name")
            or _strip_prefix(os.path.basename(self.root_dir))
        )
        children = _scan_directory(self.root_dir)

        for extra in self._extra_roots:
            if not os.path.isdir(extra):
                print(f"MenuLib: extra root not found, skipping: {extra!r}")
                continue
            extra_children = _scan_directory(extra)
            _merge_children(children, extra_children)

        self._root_node = MenuNode(
            display_name=display_name,
            path=self.root_dir,
            is_submenu=True,
            children=children,
        )

        self.remove()
        _registry[self.callback_id] = self

        try:
            self._build_menu(self._root_node)
            self._refresh()
        except Exception as exc:
            print(f"MenuLib: failed to build menu {self.callback_id!r}: {exc}")

    def remove(self) -> None:
        """Tear down the Unreal menu registered by this instance.

        Attempts ``ToolMenus.unregister_owner_by_name`` first (preferred in UE5)
        then falls back to ``ToolMenus.remove_menu``.  Errors are silently
        swallowed so that :meth:`build` can safely call this on its first run.
        """
        if self._registered_menu_name:
            try:
                menus = unreal.ToolMenus.get()
                try:
                    menus.unregister_owner_by_name(unreal.Name(self.callback_id))
                except (AttributeError, Exception):
                    menus.remove_menu(unreal.Name(self._registered_menu_name))
                menus.refresh_all_widgets()
            except Exception:
                pass
            self._registered_menu_name = None
        _registry.pop(self.callback_id, None)

    # ------------------------------------------------------------------
    # Internal: Unreal menu construction
    # ------------------------------------------------------------------

    def _get_main_menu(self):
        """Return the ``LevelEditor.MainMenu`` :class:`unreal.ToolMenu` object.

        Raises :class:`RuntimeError` if the menu cannot be found.
        """
        menus = unreal.ToolMenus.get()
        main_menu = menus.find_menu(unreal.Name(_MAIN_MENU))
        if not main_menu:
            raise RuntimeError("MenuLib: failed to find LevelEditor.MainMenu")
        return main_menu

    def _build_menu(self, root_node: MenuNode) -> None:
        """Create the top-level sub-menu entry on the main menu bar."""
        main_menu = self._get_main_menu()
        sub_menu = main_menu.add_sub_menu(
            unreal.Name(self.callback_id),
            unreal.Name(""),
            _safe_name(root_node.display_name),
            unreal.Text(root_node.display_name),
        )
        self._registered_menu_name = str(sub_menu.menu_name)
        self._build_submenu(sub_menu, root_node)

    def _build_submenu(self, parent_menu, node: MenuNode) -> None:
        """Recursively populate *parent_menu* from *node*'s children."""
        _populate_menu(self.callback_id, parent_menu, node)

    def _refresh(self) -> None:
        """Refresh all Unreal menu widgets to make changes visible."""
        try:
            unreal.ToolMenus.get().refresh_all_widgets()
        except Exception:
            pass


# ---------------------------------------------------------------------------
# MenuSession
# ---------------------------------------------------------------------------

class MenuSession:
    """Manages the load/remove lifecycle for menus sourced from one env var.

    Simplifies per-package startup scripts::

        from gt.unreal.menulib import MenuSession

        _session = MenuSession("STUDIO_MENU_ROOTS")
        _session.load()

    The session can be reloaded or torn down at any time::

        _session.load()    # idempotent — removes then rebuilds
        _session.remove()  # tear down without rebuilding

    If ``MENULIB_SUPPRESSED`` contains this session's *env_var* name, ``load()``
    is a no-op — the menu is suppressed (e.g. because it has been injected into
    another menu via ``__inject__.json``).
    """

    def __init__(self, env_var: str) -> None:
        self.env_var = env_var
        self._instances: List[MenuLib] = []

    def load(self) -> List[MenuLib]:
        """Remove existing menus then rebuild from *env_var*.

        Returns the list of :class:`MenuLib` instances built, or an empty list
        if this session is suppressed.
        """
        suppressed = {
            v.strip()
            for v in os.environ.get(_SUPPRESSED_ENV, "").split(";")
            if v.strip()
        }
        if self.env_var in suppressed:
            print(
                f"MenuSession({self.env_var!r}): suppressed by"
                f" {_SUPPRESSED_ENV!r}, skipping."
            )
            return []

        self.remove()
        self._instances = load_from_env(self.env_var)
        return self._instances

    def remove(self) -> None:
        """Tear down all menus registered by this session."""
        for lib in self._instances:
            try:
                lib.remove()
            except Exception as exc:
                print(
                    f"MenuSession({self.env_var!r}): failed to remove"
                    f" {lib.root_dir!r}: {exc}"
                )
        self._instances = []


# ---------------------------------------------------------------------------
# Module-level convenience
# ---------------------------------------------------------------------------

def load_from_env(env_var: str) -> List[MenuLib]:
    """Instantiate one :class:`MenuLib` per unique menu name found in *env_var*.

    The environment variable should contain one or more directory paths separated
    by semicolons.  Paths sharing the same folder basename are automatically merged
    into a single top-level menu via :meth:`MenuLib.add_root`.

    Returns the list of built :class:`MenuLib` instances.

    Example::

        # STUDIO_MENU_ROOTS = "Z:/RepoA/MyTools;Z:/RepoB/MyTools"
        # Both share the basename "MyTools" → merged into one menu.
        libs = load_from_env("STUDIO_MENU_ROOTS")

    """
    raw = os.environ.get(env_var, "")

    groups: dict = {}
    for path in raw.split(";"):
        path = path.strip()
        if not path:
            continue
        name = os.path.basename(os.path.normpath(path))
        groups.setdefault(name, []).append(path)

    instances: List[MenuLib] = []
    for paths in groups.values():
        try:
            lib = MenuLib(paths[0])
            for extra in paths[1:]:
                lib.add_root(extra)
            lib.build()
            instances.append(lib)
        except Exception as exc:
            print(f"MenuLib: failed to build menu from {paths[0]!r}: {exc}")

    return instances
