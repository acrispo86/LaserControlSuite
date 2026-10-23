"""Overlay di editing nodi: disegna nodi e handle del path in editing.

L'overlay è un ``QGraphicsItem`` **figlio** dell'``EntityItem`` del path in
editing, così eredita automaticamente la sua trasformazione. Disegna:
  - una linea sottile dal nodo ai propri handle
  - i handle come quadratini
  - i nodi come cerchi (pieni = selezionati, vuoti = non selezionati)

La dimensione visiva dei marker è costante in pixel: nel ``paint`` la scala
corrente viene letta da ``painter.transform().m11()``.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen
from PySide6.QtWidgets import QGraphicsItem

from lasercontrolsuite.core.path import PathEntity
from lasercontrolsuite.core.path_edit import is_smooth_node
from lasercontrolsuite.resources.theme import THEME


# Raggi in pixel (costanti sullo schermo).
NODE_RADIUS_PX: float = 4.5
HANDLE_HALF_PX: float = 3.0
HANDLE_LINE_WIDTH_PX: float = 1.0

# Colori
NODE_FILL = QColor(THEME.accent)
NODE_STROKE = QColor(THEME.accent)
NODE_SELECTED_FILL = QColor(0xFF, 0xFF, 0xFF)
HANDLE_FILL = QColor(0xFF, 0x8C, 0x00)
HANDLE_LINE = QColor(0xFF, 0x8C, 0x00, 120)


class NodeOverlayItem(QGraphicsItem):
    """Disegna nodi e handle del path in editing."""

    #: Margine in mm attorno al path per la bounding rect (generoso).
    MARGIN_LOCAL = 5.0

    def __init__(self, path_item, path_entity: PathEntity) -> None:
        super().__init__(parent=path_item)
        self._path = path_entity
        self._selected_nodes: set[int] = set()
        self.setZValue(1000.0)
        self.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, False)

    # ------------------------------------------------------------------ API
    @property
    def path(self) -> PathEntity:
        return self._path

    @property
    def selected_nodes(self) -> set[int]:
        return set(self._selected_nodes)

    def refresh(self) -> None:
        """Da chiamare quando i nodi cambiano dall'esterno (es. undo)."""
        self.prepareGeometryChange()
        self.update()

    def set_selected_nodes(self, indices: set[int]) -> None:
        if indices == self._selected_nodes:
            return
        self._selected_nodes = set(indices)
        self.update()

    def clear_selection(self) -> None:
        self.set_selected_nodes(set())

    # ------------------------------------------------------------- QGraphicsItem
    def boundingRect(self) -> QRectF:  # noqa: N802
        xs: list[float] = []
        ys: list[float] = []
        for node in self._path.nodes:
            xs.append(node.point[0])
            ys.append(node.point[1])
            if node.handle_in is not None:
                xs.append(node.point[0] + node.handle_in[0])
                ys.append(node.point[1] + node.handle_in[1])
            if node.handle_out is not None:
                xs.append(node.point[0] + node.handle_out[0])
                ys.append(node.point[1] + node.handle_out[1])
        if not xs:
            return QRectF()
        m = self.MARGIN_LOCAL
        return QRectF(
            min(xs) - m,
            min(ys) - m,
            max(xs) - min(xs) + 2 * m,
            max(ys) - min(ys) + 2 * m,
        )

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        scale = abs(painter.transform().m11())
        if scale <= 1e-9:
            return

        node_radius = NODE_RADIUS_PX / scale
        handle_half = HANDLE_HALF_PX / scale
        line_width = HANDLE_LINE_WIDTH_PX / scale

        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

            # Linee handle
            pen = QPen(HANDLE_LINE, line_width)
            pen.setCosmetic(True)
            painter.setPen(pen)
            for i, node in enumerate(self._path.nodes):
                center = QPointF(node.point[0], node.point[1])
                if node.handle_in is not None:
                    h = node.abs_handle_in()
                    assert h is not None
                    painter.drawLine(center, QPointF(h[0], h[1]))
                if node.handle_out is not None:
                    h = node.abs_handle_out()
                    assert h is not None
                    painter.drawLine(center, QPointF(h[0], h[1]))

            # Handle (quadratini)
            handle_brush = QBrush(HANDLE_FILL)
            for node in self._path.nodes:
                for h in (node.abs_handle_in(), node.abs_handle_out()):
                    if h is None:
                        continue
                    rect = QRectF(
                        h[0] - handle_half,
                        h[1] - handle_half,
                        2 * handle_half,
                        2 * handle_half,
                    )
                    painter.setBrush(handle_brush)
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawRect(rect)

            # Nodi (cerchi)
            for i, node in enumerate(self._path.nodes):
                center = QPointF(node.point[0], node.point[1])
                selected = i in self._selected_nodes
                fill = NODE_SELECTED_FILL if selected else NODE_FILL
                painter.setBrush(QBrush(fill))
                stroke = QPen(NODE_STROKE, max(1.0, node_radius * 0.4))
                stroke.setCosmetic(True)
                painter.setPen(stroke)
                if is_smooth_node(node):
                    painter.drawEllipse(center, node_radius, node_radius)
                else:
                    # Corner: quadratino (stessa dimensione del cerchio)
                    rect = QRectF(
                        center.x() - node_radius,
                        center.y() - node_radius,
                        2 * node_radius,
                        2 * node_radius,
                    )
                    painter.drawRect(rect)
        finally:
            painter.restore()