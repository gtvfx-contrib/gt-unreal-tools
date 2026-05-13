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

from __future__ import annotations

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

import unreal

import json
import os
import re
from dataclasses import dataclass, field
from typing import List, Optional

# ---------------------------------------------------------------------------
# Module-level registry — maps callback_id → MenuLib instance
# ---------------------------------------------------------------------------

_registry: dict[str, "MenuLib"] = {}

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_MAIN_MENU = "LevelEditor.MainMenu"
_MENU_JSON = "__menu__.json"
_INJECT_JSON = "__inject__.json"
_SUPPRESSED_ENV = "MENULIB_SUPPRESSED"

# Separator filename pattern: digits + underscore + "sep"
_SEP_RE = re.compile(r"^\d+(\.\d+)?_sep\b", re.IGNORECASE)

# Numeric prefix pattern stripped from display names: "00_", "08.5_", "08 "
_PREFIX_RE = re.compile(r"^\d+(\.\d+)?[_ ]")

# Header comment patterns parsed from .py menu item files
_LABEL_RE = re.compile(r"^#\s*label\s*:\s*(.+)", re.IGNORECASE)
_TOOLTIP_RE = re.compile(r"^#\s*tooltip\s*:\s*(.+)", re.IGNORECASE)
_ITEM_ORDER_RE = re.compile(r"^#\s*order\s*:\s*([0-9]*\.?[0-9]+)", re.IGNORECASE)
_SECTION_RE = re.compile(r"^#\s*section\s*:\s*(.+)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class MenuNode:
    """Represents one node in the menu tree."""

    display_name: str
    path: str
    is_separator: bool = False
    is_submenu: bool = False
    children: List["MenuNode"] = field(default_factory=list)
    order: float = float("inf")
    tooltip: str = ""
    section: str = ""


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def _strip_prefix(name: str) -> str:
    """Remove a leading numeric prefix (e.g. ``00_``) from *name*."""
    return _PREFIX_RE.sub("", name).strip()


def _is_separator(filename: str) -> bool:
    return bool(_SEP_RE.match(filename))


def _extract_order(name: str) -> float:
    """Return the sort key from a file or folder name.

    Supports integer prefixes (``01_``) and decimal prefixes (``01.5_``).
    Names without a numeric prefix sort to ``float("inf")``.

    """
    m = _PREFIX_RE.match(name)
    if m:
        try:
            return float(re.match(r"(\d+(?:\.\d+)?)", name).group(1))
        except (AttributeError, ValueError):
            pass
    return float("inf")


def _is_resource_dir(name: str) -> bool:
    return "_resource" in name.lower()


def _safe_name(label: str) -> unreal.Name:
    """Return a ``Name``-safe identifier from *label* (alphanumeric + underscores only)."""
    return unreal.Name(re.sub(r"[^A-Za-z0-9_]", "_", label))


# ---------------------------------------------------------------------------
# Folder config helpers  (read __menu__.json)
# ---------------------------------------------------------------------------

def _read_folder_config(folder_path: str) -> dict:
    """Return the parsed ``__menu__.json`` for *folder_path*, or ``{}`` if absent."""
    sidecar = os.path.join(folder_path, _MENU_JSON)
    if os.path.isfile(sidecar):
        try:
            with open(sidecar, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            pass
    return {}


# ---------------------------------------------------------------------------
# Inject config helpers  (read __inject__.json)
# ---------------------------------------------------------------------------

def _read_inject_config(folder_path: str) -> Optional[dict]:
    """Return the parsed ``__inject__.json`` for *folder_path*, or ``None`` if absent."""
    sidecar = os.path.join(folder_path, _INJECT_JSON)
    if os.path.isfile(sidecar):
        try:
            with open(sidecar, "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, json.JSONDecodeError):
            return {}
    return None


# ---------------------------------------------------------------------------
# Python item file parser
# ---------------------------------------------------------------------------

def _parse_py_item(path: str) -> dict:
    """Parse the header comments of a ``.py`` menu item file.

    Returns a dict with keys:

    * ``label``   — display name string, or ``""`` if absent
    * ``tooltip`` — tooltip string, or ``""`` if absent
    * ``order``   — float sort key, or ``None`` if absent
    * ``section`` — Unreal section label string, or ``""`` if absent

    Example header::

        # label: My Tool
        # tooltip: Opens the tool
        # order: 1.0
        # section: My Group

    """
    result: dict = {"label": "", "tooltip": "", "order": None, "section": ""}

    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            lines = fh.readlines()
    except OSError:
        return result

    for line in lines:
        if not result["label"]:
            m = _LABEL_RE.match(line)
            if m:
                result["label"] = m.group(1).strip()

        if not result["tooltip"]:
            m = _TOOLTIP_RE.match(line)
            if m:
                result["tooltip"] = m.group(1).strip()

        if result["order"] is None:
            m = _ITEM_ORDER_RE.match(line)
            if m:
                try:
                    result["order"] = float(m.group(1))
                except ValueError:
                    pass

        if not result["section"]:
            m = _SECTION_RE.match(line)
            if m:
                result["section"] = m.group(1).strip()

    return result


# ---------------------------------------------------------------------------
# Directory scanner
# ---------------------------------------------------------------------------

def _scan_directory_local_only(dir_path: str) -> List[MenuNode]:
    """Scan *dir_path* for local ``.py`` action files only (no subdirectory recursion).

    Used by :func:`_scan_inject_slot` to collect items that live alongside an
    ``__inject__.json`` sidecar so they can be merged with injected content.
    """
    nodes: List[MenuNode] = []

    try:
        entries = sorted(os.scandir(dir_path), key=lambda e: e.name.lower())
    except OSError:
        return nodes

    for entry in entries:
        name = entry.name
        if not entry.is_file():
            continue
        if name.lower() in (_MENU_JSON.lower(), _INJECT_JSON.lower()):
            continue
        if not name.lower().endswith(".py"):
            continue

        if _is_separator(name):
            nodes.append(MenuNode(
                display_name="",
                path=entry.path,
                is_separator=True,
                order=_extract_order(name),
            ))
        else:
            meta = _parse_py_item(entry.path)
            display = meta["label"] or _strip_prefix(os.path.splitext(name)[0])
            order = meta["order"] if meta["order"] is not None else _extract_order(name)
            nodes.append(MenuNode(
                display_name=display,
                path=entry.path,
                order=order,
                tooltip=meta["tooltip"],
                section=meta["section"],
            ))

    return nodes


def _scan_inject_slot(folder_path: str, config: dict) -> List[MenuNode]:
    """Resolve an injection slot and return its flattened child nodes.

    Reads ``source_env`` from *config*, scans all valid paths listed in that
    env var (grouped and merged by basename, same as :func:`load_from_env`),
    then merges the result with any local ``.py`` files in *folder_path*.
    Returns an empty list if the env var is unset or resolves to no valid
    directories.
    """
    source_env = config.get("source_env", "")
    raw = os.environ.get(source_env, "") if source_env else ""

    injected: List[MenuNode] = []
    groups: dict = {}
    for path in raw.split(";"):
        path = path.strip()
        if path and os.path.isdir(path):
            name = os.path.basename(os.path.normpath(path))
            groups.setdefault(name, []).append(path)

    for paths in groups.values():
        primary_nodes = _scan_directory(paths[0])
        for extra in paths[1:]:
            extra_nodes = _scan_directory(extra)
            _merge_children(primary_nodes, extra_nodes)
        injected.extend(primary_nodes)

    local = _scan_directory_local_only(folder_path)

    combined = injected + local
    combined.sort(key=lambda n: n.order)
    return combined


def _scan_directory(dir_path: str) -> List[MenuNode]:
    """Recursively scan *dir_path* and return an ordered list of :class:`MenuNode`.

    * Directories → submenu nodes (recursive scan)
    * Directories with ``__inject__.json`` → injection slots
    * ``<N>_sep.*`` files → separator nodes
    * ``*.py`` files → action nodes

    Directories whose name contains ``_resource``, starts with ``.``, or equals
    ``__pycache__`` are skipped entirely.
    """
    nodes: List[MenuNode] = []

    try:
        entries = sorted(os.scandir(dir_path), key=lambda e: e.name.lower())
    except OSError:
        return nodes

    for entry in entries:
        name = entry.name

        if entry.is_dir():
            if _is_resource_dir(name) or name.startswith(".") or name == "__pycache__":
                continue

            inject_config = _read_inject_config(entry.path)
            if inject_config is not None:
                # ── injection slot ─────────────────────────────────────────
                display = inject_config.get("display_name") or _strip_prefix(name)
                order = _extract_order(name)
                children = _scan_inject_slot(entry.path, inject_config)
                if not children:
                    continue  # silently omit empty injection slots
                nodes.append(MenuNode(
                    display_name=display,
                    path=entry.path,
                    is_submenu=True,
                    children=children,
                    order=order,
                ))
            else:
                # ── normal submenu ─────────────────────────────────────────
                config = _read_folder_config(entry.path)
                display = config.get("display_name") or _strip_prefix(name)
                children = _scan_directory(entry.path)
                try:
                    order = (
                        float(config["order"]) if "order" in config
                        else _extract_order(name)
                    )
                except (TypeError, ValueError):
                    order = _extract_order(name)
                nodes.append(MenuNode(
                    display_name=display,
                    path=entry.path,
                    is_submenu=True,
                    children=children,
                    order=order,
                ))

        elif entry.is_file() and name.lower().endswith(".py"):
            if _is_separator(name):
                nodes.append(MenuNode(
                    display_name="",
                    path=entry.path,
                    is_separator=True,
                    order=_extract_order(name),
                ))
            else:
                meta = _parse_py_item(entry.path)
                display = meta["label"] or _strip_prefix(os.path.splitext(name)[0])
                order = meta["order"] if meta["order"] is not None else _extract_order(name)
                nodes.append(MenuNode(
                    display_name=display,
                    path=entry.path,
                    order=order,
                    tooltip=meta["tooltip"],
                    section=meta["section"],
                ))

    return nodes


def _merge_children(primary: List[MenuNode], secondary: List[MenuNode]) -> None:
    """Merge *secondary* nodes into *primary* in-place, then sort by order.

    Sub-menus whose ``display_name`` matches an existing primary sub-menu are
    merged recursively.  All other nodes (actions, separators, and new
    sub-menus) are appended.  The combined list is stable-sorted by
    :attr:`MenuNode.order` so explicit ``"order"`` values take effect across
    package boundaries.
    """
    for sec in secondary:
        if sec.is_submenu:
            match = next(
                (n for n in primary if n.is_submenu and n.display_name == sec.display_name),
                None,
            )
            if match:
                _merge_children(match.children, sec.children)
            else:
                primary.append(sec)
        else:
            primary.append(sec)

    primary.sort(key=lambda n: n.order)


# ---------------------------------------------------------------------------
# Menu population helper
# ---------------------------------------------------------------------------

def _populate_menu(owner_name: str, parent_menu, node: MenuNode) -> None:
    """Recursively populate *parent_menu* from *node*'s children.

    Sections are created on first use with ``add_section``.  Items and
    sub-menus that carry no explicit ``section`` metadata are placed into a
    section named ``"default"`` (with an empty label so no visible section
    header appears).  Using a non-empty section name is required for freshly
    created sub-menus (returned by ``add_sub_menu``) because those menus start
    with zero pre-built sections; passing ``NAME_None`` (the empty string) as
    the section name is a silent no-op in Unreal's ``AddSection`` and the
    resulting ``NAME_None`` section is skipped by the menu renderer for regular
    entries.

    Parameters
    ----------
    owner_name:
        The Unreal owner ``Name`` string used when registering sub-menus and
        entries.  Passing a consistent owner across all items in a menu tree
        enables bulk removal via ``ToolMenus.unregister_owner_by_name``.
    parent_menu:
        An ``unreal.ToolMenu`` object to populate.
    node:
        The :class:`MenuNode` whose children are added to *parent_menu*.
    """
    _DEFAULT_SECTION = "default"
    added_sections: set = set()

    def _ensure_section(sec_name: str, sec_label: str) -> None:
        if sec_name not in added_sections:
            parent_menu.add_section(
                unreal.Name(sec_name),
                unreal.Text(sec_label) if sec_label else unreal.Text(""),
            )
            added_sections.add(sec_name)

    for child in node.children:
        try:
            if child.is_separator:
                _ensure_section(_DEFAULT_SECTION, "")
                entry = unreal.ToolMenuEntry(type=unreal.MultiBlockType.SEPARATOR)
                parent_menu.add_menu_entry(unreal.Name(_DEFAULT_SECTION), entry)

            elif child.is_submenu:
                _ensure_section(_DEFAULT_SECTION, "")
                sub = parent_menu.add_sub_menu(
                    unreal.Name(owner_name),
                    unreal.Name(_DEFAULT_SECTION),
                    _safe_name(child.display_name),
                    unreal.Text(child.display_name),
                )
                _populate_menu(owner_name, sub, child)

            else:
                section_label = child.section
                section_name = (
                    "".join(section_label.split()) if section_label else _DEFAULT_SECTION
                )
                _ensure_section(section_name, section_label)

                entry = unreal.ToolMenuEntry(
                    name=unreal.Name(_safe_name(child.display_name)),
                    type=unreal.MultiBlockType.MENU_ENTRY,
                    owner=unreal.ToolMenuOwner(unreal.Name(owner_name)),
                )
                entry.set_label(unreal.Text(child.display_name))
                if child.tooltip:
                    entry.set_tool_tip(unreal.Text(child.tooltip))
                entry.set_string_command(
                    unreal.ToolMenuStringCommandType.PYTHON,
                    unreal.Name(""),
                    string=f"import runpy; runpy.run_path({repr(child.path)})",
                )
                parent_menu.add_menu_entry(unreal.Name(section_name), entry)

        except Exception as exc:
            print(f"MenuLib: failed to add item {child.display_name!r}: {exc}")


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
        if _is_resource_dir(entry.name) or entry.name.startswith(".") or entry.name == "__pycache__":
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
            if _is_resource_dir(entry.name) or entry.name.startswith(".") or entry.name == "__pycache__":
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
