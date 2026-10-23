"""Righelli overlay per il canvas.

Due widget sottili (top + left) figli del viewport del ``QGraphicsView``.
Disegnano i tick in mm sincronizzati con la trasformazione del view.

Il view li aggiorna chiamando ``update()`` a ogni cambiamento di trasformazione
o di dimensione. Step 9d: ascoltano il cambio tema per ricostruire i colori.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QPointF, Qt
from PySide6.QtGui import QColor, QFont, QPainter, QPen
from PySide6.QtWidgets import QWidget

from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager


_TICK_LADDER = (
    0.1, 0.2, 0.5,
    1.0, 2.0, 5.0,
    10.0, 20.0, 50.0,
    100.0, 200.0, 500.0,
    1000.0,
)


class RulerOverlay(QWidget):
    """Righello orizzontale o verticale."""

    THICKNESS = 18

    def __init__(self, view, orientation: Qt.Orientation, parent=None) -> None:
        super().__init__(parent or view.viewport())
        self._view = view
        self._orientation = orientation

        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self.setAutoFillBackground(False)

        if orientation == Qt.Orientation.Horizontal:
            self.setFixedHeight(self.THICKNESS)
        else:
            self.setFixedWidth(self.THICKNESS)

        self._bg = QColor()
        self._fg = QColor()
        self._accent = QColor()
        self._border = QColor()
        self._font = QFont(THEME.font_family)
        self._font.setPointSize(7)
        self._apply_theme()

        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

    def _apply_theme(self) -> None:
        self._bg = QColor(THEME.bg_panel)
        self._fg = QColor(THEME.fg_secondary)
        self._accent = QColor(THEME.accent)
        self._border = QColor(THEME.border)

    def _on_theme_changed(self, _name: str) -> None:
        self._apply_theme()
        self.update()

    # ------------------------------------------------------------------ API
    def sync_geometry(self) -> None:
        vp = self._view.viewport()
        if self._orientation == Qt.Orientation.Horizontal:
            self.setGeometry(0, 0, vp.width(), self.THICKNESS)
        else:
            self.setGeometry(0, 0, self.THICKNESS, vp.height())

    # ------------------------------------------------------------- painting
    def paintEvent(self, event) -> None:  # noqa: N802
        painter = QPainter(self)
        try:
            painter.fillRect(self.rect(), self._bg)

            view = self._view
            t = view.transform()
            s = abs(t.m11())

            if s <= 0.0:
                return

            step = self._choose_step(s)
            if step <= 0.0:
                return

            if self._orientation == Qt.Orientation.Horizontal:
                self._paint_horizontal(painter, view, step)
            else:
                self._paint_vertical(painter, view, step)

            edge_pen = QPen(self._border, 1)
            painter.setPen(edge_pen)
            if self._orientation == Qt.Orientation.Horizontal:
                painter.drawLine(0, self.height() - 1, self.width(), self.height() - 1)
            else:
                painter.drawLine(self.width() - 1, 0, self.width() - 1, self.height())
        finally:
            painter.end()

    def _paint_horizontal(self, painter: QPainter, view, step: float) -> None:
        vp = view.viewport()
        p_left = view.mapToScene(0, 0)
        p_right = view.mapToScene(vp.width(), 0)
        x_min = min(p_left.x(), p_right.x())
        x_max = max(p_left.x(), p_right.x())

        i0 = math.floor(x_min / step) - 1
        i1 = math.ceil(x_max / step) + 1

        tick_pen = QPen(self._fg, 1)
        accent_pen = QPen(self._accent, 1)

        painter.setFont(self._font)

        for i in range(i0, i1 + 1):
            x = i * step
            vp_pt = view.mapFromScene(QPointF(x, 0.0))
            px = vp_pt.x()
            if px < -40 or px > vp.width() + 40:
                continue

            painter.setPen(accent_pen if abs(x) < 1e-9 else tick_pen)
            painter.drawLine(px, self.height() - 5, px, self.height() - 1)

            if i % 5 == 0:
                label = self._format_mm(x)
                painter.setPen(self._fg)
                painter.drawText(int(px) + 2, 10, label)

    def _paint_vertical(self, painter: QPainter, view, step: float) -> None:
        vp = view.viewport()
        p_top = view.mapToScene(0, 0)
        p_bot = view.mapToScene(0, vp.height())
        y_min = min(p_top.y(), p_bot.y())
        y_max = max(p_top.y(), p_bot.y())

        i0 = math.floor(y_min / step) - 1
        i1 = math.ceil(y_max / step) + 1

        tick_pen = QPen(self._fg, 1)
        accent_pen = QPen(self._accent, 1)

        painter.setFont(self._font)

        for i in range(i0, i1 + 1):
            y = i * step
            vp_pt = view.mapFromScene(QPointF(0.0, y))
            py = vp_pt.y()
            if py < -40 or py > vp.height() + 40:
                continue

            painter.setPen(accent_pen if abs(y) < 1e-9 else tick_pen)
            painter.drawLine(self.width() - 5, py, self.width() - 1, py)

            if i % 5 == 0:
                label = self._format_mm(y)
                painter.setPen(self._fg)
                painter.save()
                painter.translate(8, int(py) + 3)
                painter.rotate(-90)
                painter.drawText(0, 0, label)
                painter.restore()

    @staticmethod
    def _choose_step(px_per_mm: float) -> float:
        target_px = 60.0
        for v in _TICK_LADDER:
            if v * px_per_mm >= target_px:
                return v
        return _TICK_LADDER[-1]

    @staticmethod
    def _format_mm(value: float) -> str:
        if abs(value) < 1e-9:
            return "0"
        if abs(value) >= 100:
            return f"{value:.0f}"
        if abs(value) >= 10:
            return f"{value:.1f}"
        return f"{value:.2f}"