"""Conversioni tra oggetti del core (puro Python) e Qt.

Contiene anche utility relative al "mondo Qt" che non hanno senso nel core:
il DPI logico usato da ``QPainterPath.addText`` e simili.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF
from PySide6.QtGui import QGuiApplication, QTransform

from lasercontrolsuite.core.matrix import Matrix2D


#: Millimetri per pollice (definizione).
MM_PER_INCH: float = 25.4


def qt_path_dpi() -> float:
    """DPI logico usato da Qt per convertire point→pixel nei path (``addText``).

    Corrisponde a ``qt_defaultDpi()`` del runtime Qt: il DPI logico dello
    schermo primario, oppure 96 se non c'è uno schermo (ambienti offscreen,
    sessioni headless). Viene usato per convertire i path di testo da "pixel"
    a mm quando la scena è in millimetri.

    Returns:
        DPI > 0. Valore di fallback: 96.
    """
    app = QGuiApplication.instance()
    if app is None:
        return 96.0
    screen = app.primaryScreen()
    if screen is None:
        return 96.0
    dpi = float(screen.logicalDotsPerInch())
    return dpi if dpi > 0.0 else 96.0


def mm_per_px_at_qt_dpi() -> float:
    """Fattore di conversione pixel→mm al DPI corrente di Qt."""
    return MM_PER_INCH / qt_path_dpi()


def to_qtransform(m: Matrix2D) -> QTransform:
    """Converte ``Matrix2D`` in ``QTransform``."""
    return QTransform(m.a, m.b, m.c, m.d, m.e, m.f)


def from_qtransform(t: QTransform) -> Matrix2D:
    """Converte ``QTransform`` in ``Matrix2D``."""
    return Matrix2D(t.m11(), t.m12(), t.m21(), t.m22(), t.dx(), t.dy())


def to_qpointf(p: tuple[float, float]) -> QPointF:
    return QPointF(p[0], p[1])


def from_qpointf(p: QPointF) -> tuple[float, float]:
    return (p.x(), p.y())