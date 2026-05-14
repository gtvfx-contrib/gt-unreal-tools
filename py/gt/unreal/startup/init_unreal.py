"""Startup script for Unreal Engine integration."""



def initialize():
    """Initialize the Unreal menu library."""
    from gt.unreal.menulib import MenuSession, ContextMenuSession
    
    session = MenuSession("STUDIO_MENU_ROOTS")
    session.load()

    session = ContextMenuSession("CONTEXT_MENU_ROOTS")
    session.load()


try:
    initialize()
except Exception as e:
    print(f"Error during initialization: {e}")
