"""Mappa centralizzata delle scorciatoie da tastiera."""

from __future__ import annotations


class Shortcuts:
    """Scorciatoie applicative (formato stringa Qt)."""

    # Strumenti
    SELECT = "V"
    NODE = "N"
    PEN = "P"
    LINE = "L"
    POLYLINE = "Shift+L"
    BEZIER = "B"
    RECT = "R"
    ELLIPSE = "E"
    POLYGON = "G"
    STAR = "S"
    TEXT = "T"

    # Modifica
    UNDO = "Ctrl+Z"
    REDO = "Ctrl+Shift+Z"
    REDO_ALT = "Ctrl+Y"
    DELETE = "Del"

    # Vista
    ZOOM_IN = "Ctrl++"
    ZOOM_IN_ALT = "Ctrl+="
    ZOOM_OUT = "Ctrl+-"
    ZOOM_RESET = "Ctrl+0"
    ZOOM_FIT = "F"

    # File
    NEW = "Ctrl+N"
    OPEN = "Ctrl+O"
    SAVE = "Ctrl+S"
    QUIT = "Ctrl+Q"


ALL_SHORTCUTS: dict[str, str] = {
    name: value for name, value in vars(Shortcuts).items()
    if not name.startswith("_") and isinstance(value, str)
}