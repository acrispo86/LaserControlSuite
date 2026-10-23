"""Scena CAD: sfondo, area di lavoro (stile LightBurn), entità.

Layout:
  * sfondo esterno: grigio medio
  * area di lavoro: rettangolo bianco
  * bordi: bordo inferiore rosso (X), bordo sinistro verde (Y),
    bordo superiore/destro grigio scuro
  * griglia solo dentro l'area

Step 9d: il `CadScene` ascolta `ThemeManager.themeChanged` e ricostruisce
le proprie penne + i colori della griglia.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QBrush, QColor, QPainter, QPen, QUndoStack
from PySide6.QtWidgets import QGraphicsScene

from lasercontrolsuite.cad.entity_item import EntityItem
from lasercontrolsuite.cad.grid import GridRenderer
from lasercontrolsuite.core.document import Document, DocumentEvent
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager


class CadScene(QGraphicsScene):
    """Scena QGraphicsScene specializzata per il CAD laser."""

    SNAP_MARKER_SIZE_PX = 10.0
    DEFAULT_WORKAREA = QRectF(-1000.0, -1000.0, 2000.0, 2000.0)

    def __init__(
        self,
        document: Document | None = None,
        undo_stack: QUndoStack | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)

        self._document = document if document is not None else Document()
        self._undo_stack = undo_stack if undo_stack is not None else QUndoStack(self)

        self._grid = GridRenderer(show_axes=False)

        self._px_per_unit: float = 1.0
        self._snap_point: QPointF | None = None
        self._items_by_entity_id: dict[str, EntityItem] = {}
        self._tool = None  # type: ignore[assignment]

        # Area di lavoro
        self._work_area: QRectF | None = None

        # Attributi riempiti da _apply_theme()
        self._outside_color = QColor()
        self._workarea_color = QColor()
        self._border_pen_neutral = QPen()
        self._border_pen_x = QPen()
        self._border_pen_y = QPen()
        self._snap_pen = QPen()
        self._snap_brush = QBrush()
        self._apply_theme()

        self.setSceneRect(self.DEFAULT_WORKAREA)
        self._document.subscribe(self._on_document_event)

        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

        for entity in self._document.entities.values():
            self._spawn_item(entity)

    # ------------------------------------------------------------------ API
    @property
    def document(self) -> Document:
        return self._document

    @property
    def undo_stack(self) -> QUndoStack:
        return self._undo_stack

    @property
    def grid(self) -> GridRenderer:
        return self._grid

    @property
    def px_per_unit(self) -> float:
        return self._px_per_unit

    def set_px_per_unit(self, value: float) -> None:
        v = max(float(value), 1e-9)
        if v == self._px_per_unit:
            return
        self._px_per_unit = v
        self.update()

    def set_snap_point(self, point: QPointF | None) -> None:
        if point is None and self._snap_point is None:
            return
        if (
            point is not None
            and self._snap_point is not None
            and point.x() == self._snap_point.x()
            and point.y() == self._snap_point.y()
        ):
            return
        self._snap_point = QPointF(point) if point is not None else None
        self.update()

    @property
    def snap_point(self) -> QPointF | None:
        return None if self._snap_point is None else QPointF(self._snap_point)

    def set_tool(self, tool) -> None:
        self._tool = tool
        self.update()

    def entity_item(self, entity_id: str) -> EntityItem | None:
        return self._items_by_entity_id.get(entity_id)

    def set_work_area(self, rect: QRectF | None) -> None:
        new_rect = QRectF(rect) if rect is not None else None
        if self._work_area == new_rect:
            return
        self._work_area = new_rect
        self.update()

    @property
    def work_area(self) -> QRectF | None:
        if self._work_area is None:
            return None
        return QRectF(self._work_area)

    # ------------------------------------------------------------------ tema
    def _apply_theme(self) -> None:
        """(Ri)costruisce penne/colori dal tema corrente."""
        self._outside_color = QColor(THEME.canvas_outside_bg)
        self._workarea_color = QColor(THEME.canvas_workarea_bg)

        w = float(THEME.canvas_axis_width)
        self._border_pen_neutral = QPen(QColor(THEME.canvas_workarea_border), w)
        self._border_pen_neutral.setCosmetic(True)
        self._border_pen_x = QPen(QColor(THEME.canvas_axis_x_color), w)
        self._border_pen_x.setCosmetic(True)
        self._border_pen_y = QPen(QColor(THEME.canvas_axis_y_color), w)
        self._border_pen_y.setCosmetic(True)

        marker_pen = QPen(QColor(THEME.snap_marker), 2)
        marker_pen.setCosmetic(True)
        self._snap_pen = marker_pen
        self._snap_brush = QBrush(QColor(0x00, 0xD4, 0xFF, 64))

        self._grid.set_colors(
            minor_color=THEME.grid_minor,
            major_color=THEME.grid_major,
            axis_x_color=THEME.grid_axis_x,
            axis_y_color=THEME.grid_axis_y,
        )

    def _on_theme_changed(self, _name: str) -> None:
        self._apply_theme()
        self.update()

    # ------------------------------------------------------------------ eventi
    def _spawn_item(self, entity) -> EntityItem:
        item = EntityItem(entity, self._document)
        self.addItem(item)
        self._items_by_entity_id[entity.id] = item
        self._apply_layer_to_item(item)
        return item

    def _apply_layer_to_item(self, item: EntityItem) -> None:
        layer = self._document.get_layer(item.entity.layer_id)
        item.sync_from_layer(layer)

    def _refresh_layers(self) -> None:
        for item in self._items_by_entity_id.values():
            self._apply_layer_to_item(item)

    def _on_document_event(self, event: DocumentEvent) -> None:
        if event.type == "entity_added" and event.entity_id is not None:
            entity = self._document.get_entity(event.entity_id)
            if entity is not None and entity.id not in self._items_by_entity_id:
                self._spawn_item(entity)
        elif event.type == "entity_removed" and event.entity_id is not None:
            item = self._items_by_entity_id.pop(event.entity_id, None)
            if item is not None:
                self.removeItem(item)
        elif event.type == "entity_changed" and event.entity_id is not None:
            item = self._items_by_entity_id.get(event.entity_id)
            if item is not None:
                item.sync_from_entity()
                self._apply_layer_to_item(item)
        elif event.type in ("layer_added", "layer_removed", "layer_changed"):
            self._refresh_layers()

    # ------------------------------------------------------------------ rendering
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, self._outside_color)

        if self._work_area is None:
            return

        painter.fillRect(self._work_area, self._workarea_color)

        painter.save()
        try:
            painter.setClipRect(self._work_area)
            self._grid.draw(painter, rect, self._px_per_unit)
        finally:
            painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        super().drawForeground(painter, rect)

        if self._work_area is not None:
            self._draw_work_area_borders(painter, self._work_area)

        if self._tool is not None:
            self._tool.paint_overlay(painter)

        if self._snap_point is None:
            return

        size_scene = self.SNAP_MARKER_SIZE_PX / self._px_per_unit
        half = size_scene / 2.0
        painter.save()
        try:
            painter.setPen(self._snap_pen)
            painter.setBrush(self._snap_brush)
            painter.drawRect(
                QRectF(
                    self._snap_point.x() - half,
                    self._snap_point.y() - half,
                    size_scene,
                    size_scene,
                )
            )
        finally:
            painter.restore()

    def _draw_work_area_borders(self, painter: QPainter, wa: QRectF) -> None:
        painter.setBrush(Qt.BrushStyle.NoBrush)

        painter.setPen(self._border_pen_x)
        painter.drawLine(wa.bottomLeft(), wa.bottomRight())

        painter.setPen(self._border_pen_y)
        painter.drawLine(wa.bottomLeft(), wa.topLeft())

        painter.setPen(self._border_pen_neutral)
        painter.drawLine(wa.topLeft(), wa.topRight())
        painter.drawLine(wa.topRight(), wa.bottomRight())