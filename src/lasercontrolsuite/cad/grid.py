"""Rendering della griglia millimetrata adattiva del canvas CAD.

La griglia ha due livelli visivi:
  - linee *minor* (più dense, colore tenue)
  - linee *major* (ogni ``major_factor`` linee minor, colore più marcato)

Il passo delle linee minor è scelto automaticamente in scala 1-2-5-10 in modo
che la loro distanza in pixel non scenda sotto ``min_px``.

I colori sono configurabili dal costruttore: la tela CAD usa toni scuri su
sfondo chiaro (stile LightBurn); altri contesti possono sovrascriverli.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen


class GridRenderer:
    """Disegna una griglia millimetrata adattiva."""

    LADDER: tuple[float, ...] = (
        1e-3, 2e-3, 5e-3,
        1e-2, 2e-2, 5e-2,
        1e-1, 2e-1, 5e-1,
        1.0, 2.0, 5.0,
        10.0, 20.0, 50.0,
        100.0, 200.0, 500.0,
        1000.0, 2000.0, 5000.0,
    )

    #: Colori di default (tela scura). Sovrascrivibili dal costruttore.
    DEFAULT_MINOR_COLOR = QColor(0x2A, 0x2A, 0x2A)
    DEFAULT_MAJOR_COLOR = QColor(0x40, 0x40, 0x40)
    DEFAULT_AXIS_X_COLOR = QColor(0xC0, 0x39, 0x2B)
    DEFAULT_AXIS_Y_COLOR = QColor(0x27, 0xAE, 0x60)

    def __init__(
        self,
        min_px: float = 4.0,
        major_factor: int = 10,
        show_minor: bool = True,
        show_major: bool = True,
        show_axes: bool = True,
        minor_color: QColor | str | None = None,
        major_color: QColor | str | None = None,
        axis_x_color: QColor | str | None = None,
        axis_y_color: QColor | str | None = None,
    ) -> None:
        self.min_px = min_px
        self.major_factor = max(2, int(major_factor))
        self.show_minor = show_minor
        self.show_major = show_major
        self.show_axes = show_axes

        minor = QColor(minor_color) if minor_color is not None else QColor(self.DEFAULT_MINOR_COLOR)
        major = QColor(major_color) if major_color is not None else QColor(self.DEFAULT_MAJOR_COLOR)
        ax = QColor(axis_x_color) if axis_x_color is not None else QColor(self.DEFAULT_AXIS_X_COLOR)
        ay = QColor(axis_y_color) if axis_y_color is not None else QColor(self.DEFAULT_AXIS_Y_COLOR)

        self._minor_pen = QPen(minor, 0)
        self._major_pen = QPen(major, 0)
        self._axis_x_pen = QPen(ax, 1.2)
        self._axis_x_pen.setCosmetic(True)
        self._axis_y_pen = QPen(ay, 1.2)
        self._axis_y_pen.setCosmetic(True)

    # ------------------------------------------------------------------ API
    def set_colors(
        self,
        minor_color: QColor | str | None = None,
        major_color: QColor | str | None = None,
        axis_x_color: QColor | str | None = None,
        axis_y_color: QColor | str | None = None,
    ) -> None:
        """Aggiorna i colori al volo (utile al cambio tema)."""
        if minor_color is not None:
            self._minor_pen = QPen(QColor(minor_color), 0)
        if major_color is not None:
            self._major_pen = QPen(QColor(major_color), 0)
        if axis_x_color is not None:
            p = QPen(QColor(axis_x_color), 1.2)
            p.setCosmetic(True)
            self._axis_x_pen = p
        if axis_y_color is not None:
            p = QPen(QColor(axis_y_color), 1.2)
            p.setCosmetic(True)
            self._axis_y_pen = p

    def draw(self, painter: QPainter, rect: QRectF, px_per_unit: float) -> None:
        if px_per_unit <= 0.0 or rect.isEmpty():
            return

        minor_step, major_step = self.choose_steps(px_per_unit)

        painter.save()
        try:
            if self.show_minor:
                self._draw_lines(painter, rect, minor_step, major_step)
            if self.show_major:
                self._draw_lines(painter, rect, major_step, major_step)
            if self.show_axes:
                self._draw_axes(painter, rect)
        finally:
            painter.restore()

    def choose_steps(self, px_per_unit: float) -> tuple[float, float]:
        minor = self.LADDER[-1]
        for value in self.LADDER:
            if value * px_per_unit >= self.min_px:
                minor = value
                break
        major = minor * self.major_factor
        return minor, major

    # -------------------------------------------------------------- helpers
    def _draw_lines(
        self,
        painter: QPainter,
        rect: QRectF,
        step: float,
        major_step: float,
    ) -> None:
        if step <= 0.0:
            return

        # Se lo step coincide col major, usa la penna major (colore più marcato).
        pen = self._major_pen if math.isclose(step, major_step, rel_tol=1e-9) else self._minor_pen
        painter.setPen(pen)

        i0 = math.floor(rect.left() / step)
        i1 = math.ceil(rect.right() / step)
        top, bottom = rect.top(), rect.bottom()
        v_lines = [QLineF(i * step, top, i * step, bottom) for i in range(i0, i1 + 1)]
        if v_lines:
            painter.drawLines(v_lines)

        j0 = math.floor(rect.top() / step)
        j1 = math.ceil(rect.bottom() / step)
        left, right = rect.left(), rect.right()
        h_lines = [QLineF(left, j * step, right, j * step) for j in range(j0, j1 + 1)]
        if h_lines:
            painter.drawLines(h_lines)

    def _draw_axes(self, painter: QPainter, rect: QRectF) -> None:
        if rect.top() <= 0.0 <= rect.bottom():
            painter.setPen(self._axis_x_pen)
            painter.drawLine(QLineF(rect.left(), 0.0, rect.right(), 0.0))
        if rect.left() <= 0.0 <= rect.right():
            painter.setPen(self._axis_y_pen)
            painter.drawLine(QLineF(0.0, rect.top(), 0.0, rect.bottom()))