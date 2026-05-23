"""Startup script for Unreal Engine integration."""

import sys

import unreal
from gt.pycore import Startup


# Unreal Engine version prefix (e.g. "5.5.4") used for UE version-specific logic where needed
UE_VERSION = unreal.SystemLibrary.get_engine_version()[:5]

# Prevent __pycache__ directories and .pyc files from being generated from Unreal runtime.
sys.dont_write_bytecode = True


def _listMenus(search_limit: int = 2000, output: bool = False) -> list[str]:
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


def _printDict(pydict):
    """Sort the dictionary keys and print {key} = {value} for each.

    Args:
        pydict (dict)

    Returns:
        None

    """
    [print(f"{key} = {pydict.get(key)}") for key in sorted(pydict.keys())]


def _dump(obj, values=False):
    """Prints out a sorted list of the dir of the supplied object.

    Args:
        obj (Object): Any Python object compatible with dir
        values (bool, optional): If true will print <attr> = <attr value>

    """
    attrs = sorted(dir(obj))

    if not values:
        for attr in attrs:
            print(attr)
    else:
        for attr in attrs:
            print(f"{attr} = {getattr(obj, attr)}\n")


# ---------------------------------------------------------------------------
# Initialization steps
# ---------------------------------------------------------------------------

_startup = Startup(
    on_error=lambda name, exc: unreal.log_error(
        f"Startup: step '{name}' failed: {exc}"
    )
)


@_startup
def _initialize_LevelEditor_Menus():
    """Initialize the Unreal menu library."""
    from gt.unreal.menulib import MenuSession

    session = MenuSession("STUDIO_MENU_ROOTS")
    session.load()


@_startup
def _initialize_context_menus():
    """Initialize the Unreal context menu library."""
    from gt.unreal.menulib import ContextMenuSession

    session = ContextMenuSession("CONTEXT_MENU_ROOTS")
    session.load()


# Run all steps and remove every init name (and _startup itself) from globals.
_startup.run(globals())
