"""Icone SVG inline."""

from __future__ import annotations

from PySide6.QtCore import QByteArray, Qt
from PySide6.QtGui import QIcon, QPainter, QPixmap
from PySide6.QtSvg import QSvgRenderer

from lasercontrolsuite.resources.theme import THEME


_SVG_TEMPLATE = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
    'fill="none" stroke="{color}" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round">{body}</svg>'
)


_BODIES: dict[str, str] = {
    "select": (
        '<path d="M5 3 L5 19 L10 14 L14 22 L16 21 L12 13 L19 13 Z" '
        'fill="{color}" stroke="none"/>'
    ),
    "line": '<line x1="4" y1="20" x2="20" y2="4"/>'
            '<circle cx="4" cy="20" r="1.6" fill="{color}" stroke="none"/>'
            '<circle cx="20" cy="4" r="1.6" fill="{color}" stroke="none"/>',
    "polyline": '<polyline points="4,18 9,10 14,14 20,6"/>'
                '<circle cx="4" cy="18" r="1.4" fill="{color}" stroke="none"/>'
                '<circle cx="20" cy="6" r="1.4" fill="{color}" stroke="none"/>',
    "bezier": '<path d="M3 20 C 8 20, 8 4, 12 4 S 18 20, 21 20"/>'
              '<circle cx="3" cy="20" r="1.4" fill="{color}" stroke="none"/>'
              '<circle cx="21" cy="20" r="1.4" fill="{color}" stroke="none"/>',
    "pen": '<path d="M3 21 L5 15 L17 3 L21 7 L9 19 Z"/>'
           '<line x1="5" y1="15" x2="9" y2="19"/>'
           '<line x1="14" y1="6" x2="18" y2="10"/>',
    "nodes": '<path d="M4 12 C 8 4, 12 20, 20 12"/>'
             '<rect x="2.2" y="10.2" width="3.6" height="3.6" '
             'fill="{color}" stroke="none"/>'
             '<rect x="18.2" y="10.2" width="3.6" height="3.6" '
             'fill="{color}" stroke="none"/>'
             '<rect x="10.2" y="10.2" width="3.6" height="3.6" '
             'fill="{color}" stroke="{color}"/>',
    "rect": '<rect x="4" y="6" width="16" height="12" rx="0.5"/>',
    "ellipse": '<ellipse cx="12" cy="12" rx="9" ry="6"/>',
    "polygon": '<path d="M12 3 L20 8 L20 16 L12 21 L4 16 L4 8 Z"/>',
    "star": '<path d="M12 3 L14.4 9.6 L21.5 9.6 L15.8 13.8 L18.1 20.4 '
            'L12 16.2 L5.9 20.4 L8.2 13.8 L2.5 9.6 L9.6 9.6 Z"/>',
    "text": '<path d="M5 6 L5 4 L19 4 L19 6"/>'
            '<line x1="12" y1="4" x2="12" y2="20"/>'
            '<line x1="9" y1="20" x2="15" y2="20"/>',
    "undo": '<path d="M9 7 L4 12 L9 17"/>'
            '<path d="M4 12 H14 A6 6 0 0 1 20 18"/>',
    "redo": '<path d="M15 7 L20 12 L15 17"/>'
            '<path d="M20 12 H10 A6 6 0 0 0 4 18"/>',
    "zoom_in": '<circle cx="11" cy="11" r="6"/>'
               '<line x1="16" y1="16" x2="21" y2="21"/>'
               '<line x1="8" y1="11" x2="14" y2="11"/>'
               '<line x1="11" y1="8" x2="11" y2="14"/>',
    "zoom_out": '<circle cx="11" cy="11" r="6"/>'
                '<line x1="16" y1="16" x2="21" y2="21"/>'
                '<line x1="8" y1="11" x2="14" y2="11"/>',
    "fit": '<rect x="3" y="3" width="18" height="18" rx="1"/>'
           '<path d="M8 8 L8 12 M8 8 L12 8 M16 8 L16 12 M16 8 L12 8 '
           'M8 16 L8 12 M8 16 L12 16 M16 16 L16 12 M16 16 L12 16"/>',
}


def _render_svg_to_pixmap(svg_text: str, size: int) -> QPixmap:
    renderer = QSvgRenderer(QByteArray(svg_text.encode("utf-8")))
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    try:
        renderer.render(painter)
    finally:
        painter.end()
    return pixmap


def make_icon(name: str, color: str | None = None) -> QIcon:
    """Costruisce un ``QIcon`` da una delle icone inline."""
    body_template = _BODIES.get(name)
    if body_template is None:
        raise KeyError(
            f"Icona sconosciuta: {name!r}. "
            f"Disponibili: {', '.join(sorted(_BODIES))}"
        )
    stroke = color or THEME.fg_primary
    body = body_template.replace("{color}", stroke)
    svg = _SVG_TEMPLATE.format(color=stroke, body=body)
    icon = QIcon()
    for size in (16, 22, 24, 32, 48, 64):
        icon.addPixmap(_render_svg_to_pixmap(svg, size))
    return icon


def available_icons() -> list[str]:
    """Elenco delle icone disponibili (utile per test e debug)."""
    return sorted(_BODIES.keys())