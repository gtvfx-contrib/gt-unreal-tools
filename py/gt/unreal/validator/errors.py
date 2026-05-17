"""Custom exception types for the validator package.

Defines specialised exceptions for Unreal Engine API integration so that
callers can catch predictable, well-named failures rather than relying on
broad ``Exception`` catches.

"""

__all__ = ["UnrealAPIError"]


class UnrealAPIError(RuntimeError):
    """Raised when the Unreal Python API produces an unexpected error.

    Wraps exceptions that originate from Unreal Engine's C++/Python bridge
    (e.g. ``EditorAssetLibrary`` calls) into a single, predictable type.

    Examples:
        >>> from validator.env import loadUnrealAsset
        >>> from validator.errors import UnrealAPIError
        >>> try:
        ...     asset = loadUnrealAsset("/Game/Meshes/SM_Rock")
        ... except UnrealAPIError as exc:
        ...     print(f"Skipping asset: {exc}")
    
    """
