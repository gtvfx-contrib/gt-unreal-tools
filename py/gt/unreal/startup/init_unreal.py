

print("!---- Startup from Unreal Tools ----!")


def initialize():
    """Initialize the Unreal menu library."""
    from gt.unreal.menulib import MenuSession, ContextMenuSession
    
    session = MenuSession("STUDIO_MENU_ROOTS")
    session.load()

    session = ContextMenuSession("CONTEXT_MENU_ROOTS")
    session.load()



initialize()
