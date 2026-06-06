"""Shared infrastructure for the Unreal Level Editor menu library.

Constants, the module-level registry, the :class:`MenuNode` data model,
all pure-Python helper functions, the directory scanner, and the Unreal
menu-population helper live here.  Both :mod:`._main_menu` and
:mod:`._context_menu` import from this module.

"""

from __future__ import annotations

__all__ = [
    "MenuNode",
    "list_menus",
    "_registry",
]

import unreal

import json
import os
import re
from dataclasses import dataclass, field
from typing import Optional

# ---------------------------------------------------------------------------
# Module-level registry — maps callback_id → MenuLib / ContextMenuLib instance
# ---------------------------------------------------------------------------

_registry: dict[str, object] = {}

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

# Unreal Engine version prefix (e.g. "5.5.4") used for UE version-specific logic where needed
UE_VERSION = unreal.SystemLibrary.get_engine_version()[:5]


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
    children: list["MenuNode"] = field(default_factory=list)
    order: float = float("inf")
    tooltip: str = ""
    section: str = ""


# ---------------------------------------------------------------------------
# General helpers
# ---------------------------------------------------------------------------

def list_menus(search_limit: int = 2000, output: bool = False) -> list[str]:
    """Return a list of all registered menu names."""
    registered_names = set()

    if UE_VERSION >= "5":
        prefix = "RegisteredMenu_"
    else:
        prefix = "ToolMenu_"
    
    # Iterate through potential transient object indices to find registered menus
    for i in range(search_limit):
        obj_path = f"/Engine/Transient.ToolMenus_0:{prefix}{i}"
        menu_obj = unreal.find_object(None, obj_path)
        
        if menu_obj:
            name = str(menu_obj.menu_name)
            if name != "None":
                registered_names.add(name)

    if output:
        unreal.log("Registered menus:")
        for name in sorted(registered_names):
            unreal.log(f" - {name}")
                
    return sorted(list(registered_names))


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
            return float(m.group(1))
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

def _scan_directory_local_only(dir_path: str) -> list[MenuNode]:
    """Scan *dir_path* for local ``.py`` action files only (no subdirectory recursion).

    Used by :func:`_scan_inject_slot` to collect items that live alongside an
    ``__inject__.json`` sidecar so they can be merged with injected content.
    """
    nodes: list[MenuNode] = []

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


def _scan_inject_slot(folder_path: str, config: dict) -> list[MenuNode]:
    """Resolve an injection slot and return its flattened child nodes.

    Reads ``source_env`` from *config*, scans all valid paths listed in that
    env var (grouped and merged by basename, same as :func:`load_from_env`),
    then merges the result with any local ``.py`` files in *folder_path*.
    Returns an empty list if the env var is unset or resolves to no valid
    directories.
    """
    source_env = config.get("source_env", "")
    raw = os.environ.get(source_env, "") if source_env else ""

    injected: list[MenuNode] = []
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


def _scan_directory(dir_path: str) -> list[MenuNode]:
    """Recursively scan *dir_path* and return an ordered list of :class:`MenuNode`.

    * Directories → submenu nodes (recursive scan)
    * Directories with ``__inject__.json`` → injection slots
    * ``<N>_sep.*`` files → separator nodes
    * ``*.py`` files → action nodes

    Directories whose name contains ``_resource``, starts with ``.``, or equals
    ``__pycache__`` are skipped entirely.
    """
    nodes: list[MenuNode] = []

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
                section = inject_config.get("section", "")
                tooltip = inject_config.get("tooltip", "")
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
                    section=section,
                    tooltip=tooltip,
                ))
            else:
                # ── normal submenu ─────────────────────────────────────────
                config = _read_folder_config(entry.path)
                display = config.get("display_name") or _strip_prefix(name)
                section = config.get("section", "")
                tooltip = config.get("tooltip", "")
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
                    section=section,
                    tooltip=tooltip,
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


def _merge_children(primary: list[MenuNode], secondary: list[MenuNode]) -> None:
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

    Sub-menu nodes are pre-registered via ``ToolMenus.register_menu`` before
    the ``add_sub_menu`` entry is added to the parent.  Pre-registration
    ensures the sub-menu is a **persistent** ``ToolMenu`` in the registry so
    that items added to it survive dynamic menu rebuilds (e.g.
    ``ContentBrowser.AssetContextMenu`` is rebuilt each time it opens; items
    added to an ephemeral handle returned by ``add_sub_menu`` on a dynamic
    menu are discarded on the next rebuild).

    Leaf action items with no explicit ``# section:`` metadata are placed in
    the implicit ``""`` (NAME_None) section, which is always present on every
    registered ``ToolMenu`` and is rendered unconditionally.  Items with an
    explicit ``# section:`` use the named section (created via
    ``add_section`` if needed).  The same ``section`` / ``tooltip`` metadata
    is honoured for sub-menu folder nodes via ``__menu__.json``.

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
    # Section used when placing sub-menu entries in the parent.  add_sub_menu
    # uses FindOrAddSection internally so this section is always valid.
    _SUB_SECTION = "default"
    _parent_path = str(getattr(parent_menu, "menu_name", "?"))
    added_sections: set = set()

    def _ensure_section(sec_name: str, sec_label: str) -> None:
        """Create *sec_name* on *parent_menu* if not already created.

        Skipped for the empty string (NAME_None), which is always implicitly
        present on every ``ToolMenu``.  For named sections, ``add_section`` is
        wrapped in its own try-except so that a failure does not abort the
        entire child item.
        """
        if not sec_name or sec_name in added_sections:
            return
        try:
            parent_menu.add_section(
                unreal.Name(sec_name),
                unreal.Text(sec_label) if sec_label else unreal.Text(""),
            )
        except Exception as exc:
            print(
                f"MenuLib: add_section({sec_name!r}) on {_parent_path!r}"
                f" raised {type(exc).__name__}: {exc}"
            )
        added_sections.add(sec_name)

    for child in node.children:
        try:
            if child.is_separator:
                entry = unreal.ToolMenuEntry(type=unreal.MultiBlockType.SEPARATOR)
                parent_menu.add_menu_entry(unreal.Name(""), entry)

            elif child.is_submenu:
                sub_name = _safe_name(child.display_name)
                sub_section_label = child.section
                sub_section = (
                    "".join(sub_section_label.split()) if sub_section_label else _SUB_SECTION
                )
                _ensure_section(sub_section, sub_section_label)

                parent_path = str(parent_menu.menu_name)
                sub_path = f"{parent_path}.{sub_name}"

                # TODO: Implement DEBUG logging and replace these prints with log statements
                # print(
                #     f"MenuLib: add_sub_menu {child.display_name!r}"
                #     f" on {_parent_path!r} section={sub_section!r}"
                # )

                # Pre-register the sub-menu as a persistent ToolMenu so its
                # items survive dynamic menu rebuilds (e.g. the base
                # ContentBrowser.AssetContextMenu is rebuilt each time it
                # opens; items added to an unregistered ephemeral handle
                # are discarded).  register_menu is idempotent: if the menu
                # is already registered it returns the existing instance.
                tool_menus = unreal.ToolMenus.get()
                sub = tool_menus.find_menu(unreal.Name(sub_path))
                if not sub:
                    try:
                        # Signature varies by UE version — try progressively
                        # simpler calls until one succeeds.
                        try:
                            sub = tool_menus.register_menu(
                                unreal.Name(sub_path),
                                unreal.Name(""),
                            )
                        except TypeError:
                            sub = tool_menus.register_menu(unreal.Name(sub_path))
                        # print(f"MenuLib: registered sub-menu {sub_path!r}")
                    except Exception as reg_exc:
                        print(
                            f"MenuLib: register_menu({sub_path!r}) raised"
                            f" {type(reg_exc).__name__}: {reg_exc}"
                        )

                # Add the flyout entry in the parent that points to our
                # (now-registered) sub-menu.
                add_sub_result = parent_menu.add_sub_menu(
                    unreal.Name(owner_name),
                    unreal.Name(sub_section),
                    sub_name,
                    unreal.Text(child.display_name),
                    unreal.Text(child.tooltip) if child.tooltip else unreal.Text(""),
                )

                # Fall back to the add_sub_menu return value or a fresh
                # find_menu call if register_menu was not available.
                if not sub:
                    sub = add_sub_result
                    if not sub:
                        try:
                            sub = tool_menus.find_menu(unreal.Name(sub_path))
                        except Exception:
                            pass

                if sub:
                    # print(
                    #     f"MenuLib: OK sub-menu {child.display_name!r}"
                    #     f" -> {str(getattr(sub, 'menu_name', '?'))!r}"
                    # )
                    _populate_menu(owner_name, sub, child)
                else:
                    print(
                        f"MenuLib: could not obtain sub-menu handle for"
                        f" {child.display_name!r} — items inside will be skipped"
                    )

            else:
                # Use the explicit section declared by the item file, or fall
                # back to NAME_None ("") which is always implicitly present on
                # every registered ToolMenu and is rendered unconditionally.
                # Using a named "default" section on dynamically-created
                # sub-menus of context menus can cause items to be silently
                # excluded from rendering by Unreal.
                section_label = child.section
                section_name = "".join(section_label.split()) if section_label else ""
                _ensure_section(section_name, section_label)

                entry = unreal.ToolMenuEntry(
                    name=_safe_name(child.display_name),
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
                # print(
                #     f"MenuLib: adding entry {child.display_name!r}"
                #     f" to {_parent_path!r}"
                #     + (f" section={section_name!r}" if section_name else "")
                # )
                try:
                    parent_menu.add_menu_entry(unreal.Name(section_name), entry)
                    # print(f"MenuLib: OK added {child.display_name!r}")
                except Exception as entry_exc:
                    print(
                        f"MenuLib: failed to add item {child.display_name!r}"
                        f" to {_parent_path!r}: {entry_exc}"
                    )

        except Exception as exc:
            print(f"MenuLib: failed to add item {child.display_name!r}: {exc}")
