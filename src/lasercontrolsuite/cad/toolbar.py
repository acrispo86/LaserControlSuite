"""Toolbar verticale a icone per gli strumenti di disegno."""

from __future__ import annotations

from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QAction, QActionGroup, QKeySequence
from PySide6.QtWidgets import QToolBar

from lasercontrolsuite.cad.shortcuts import Shortcuts
from lasercontrolsuite.resources.icons import make_icon
from lasercontrolsuite.resources.theme import THEME


class DrawingToolBar(QToolBar):
    """Toolbar verticale con i tool di disegno."""

    toolChanged = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__("Disegno", parent)
        self.setOrientation(Qt.Orientation.Vertical)
        self.setMovable(False)
        self.setIconSize(QSize(THEME.icon_size_large, THEME.icon_size_large))
        self.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonIconOnly)

        self._group = QActionGroup(self)
        self._group.setExclusive(True)
        self._actions: dict[str, QAction] = {}

        self._add_tool("select", "Seleziona", Shortcuts.SELECT)
        self._add_tool("nodes", "Nodi", Shortcuts.NODE)
        self._add_tool("pen", "Penna", Shortcuts.PEN)
        self._add_tool("line", "Linea", Shortcuts.LINE)
        self._add_tool("polyline", "Polilinea", Shortcuts.POLYLINE)
        self._add_tool("bezier", "Bézier (4 click)", Shortcuts.BEZIER)
        self.addSeparator()
        self._add_tool("rect", "Rettangolo", Shortcuts.RECT)
        self._add_tool("ellipse", "Ellisse", Shortcuts.ELLIPSE)
        self._add_tool("polygon", "Poligono", Shortcuts.POLYGON)
        self._add_tool("star", "Stella", Shortcuts.STAR)
        self.addSeparator()
        self._add_tool("text", "Testo", Shortcuts.TEXT)

        self._actions["select"].setChecked(True)

    def _add_tool(self, name: str, label: str, shortcut: str) -> None:
        action = QAction(make_icon(name), label, self)
        action.setCheckable(True)
        action.setShortcut(QKeySequence(shortcut))
        action.setToolTip(f"{label}  ({shortcut})")
        action.setData(name)
        action.triggered.connect(lambda _checked=False, n=name: self._on_triggered(n))
        self._group.addAction(action)
        self.addAction(action)
        self._actions[name] = action

    def _on_triggered(self, name: str) -> None:
        self.toolChanged.emit(name)

    def set_current_tool(self, name: str) -> None:
        action = self._actions.get(name)
        if action is None:
            return
        if action.isChecked():
            return
        action.setChecked(True)
        self.toolChanged.emit(name)