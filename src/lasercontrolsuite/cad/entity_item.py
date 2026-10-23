"""QGraphicsItem che visualizza una ``Entity`` e implementa ``SnapProvider``.

Nota sulla convenzione Y e sulle unità del testo:
  - Il sistema di coordinate della scena ha Y verso l'alto (Y-up), come nelle
    macchine CNC. Qt invece usa Y verso il basso (Y-down). Il view applica
    una scala ``(s, -s)`` per mappare Y-scena → Y-viewport. Questo funziona
    per tutte le entità geometriche che generiamo direttamente (linee,
    cerchi, poligoni, ...), perché le definiamo noi in Y-up.
  - Il testo è l'eccezione. ``QPainterPath.addText`` produce un path in
    convenzione Qt (Y-down) e con coordinate in "pixel logici" (dipende dal
    DPI logico dello schermo, default 96). La nostra scena è in mm.
    Applichiamo quindi a livello di item una conversione combinata:
      scale(mm/px) + flip Y.

Step 9d: le penne sono ricostruite a ogni `paint()` da `THEME` (proxy):
non serve cache. Sul `themeChanged` facciamo solo `update()`.
"""

from __future__ import annotations

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import (
    QColor,
    QFont,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QTransform,
)
from PySide6.QtWidgets import QGraphicsItem, QGraphicsScene

from lasercontrolsuite.cad.qt_utils import mm_per_px_at_qt_dpi, to_qtransform
from lasercontrolsuite.core.commands import TransformEntityCommand
from lasercontrolsuite.core.document import Document
from lasercontrolsuite.core.entities import (
    BezierEntity,
    CircleEntity,
    EllipseEntity,
    Entity,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
    TextEntity,
)
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import PathEntity
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager


HIT_PEN_WIDTH_LOCAL = 0.4  # mm
TEXT_MM_PER_PT = 25.4 / 72.0


class EntityItem(QGraphicsItem):
    """Rappresentazione Qt di una entità del documento."""

    def __init__(
        self,
        entity: Entity,
        document: Document,
        parent: QGraphicsItem | None = None,
    ) -> None:
        super().__init__(parent)
        self._entity = entity
        self._document = document
        self._pre_drag_transform: Matrix2D = entity.transform

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setZValue(1.0)

        self._sync_transform()

        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ API
    @property
    def entity(self) -> Entity:
        return self._entity

    def sync_from_entity(self) -> None:
        self.prepareGeometryChange()
        self._sync_transform()
        self.update()

    def _sync_transform(self) -> None:
        self.setTransform(to_qtransform(self._entity.transform))

    # ------------------------------------------------------------- tema
    def _on_theme_changed(self, _name: str) -> None:
        self.update()

    # ------------------------------------------------------------- SnapProvider
    def snap_points(self) -> list[QPointF]:
        return [
            self.mapToScene(QPointF(x, y))
            for (x, y) in self._entity.local_snap_points()
        ]

    # ------------------------------------------------------------- geometry
    def _build_local_path(self) -> QPainterPath:
        path = QPainterPath()
        e = self._entity

        if isinstance(e, TextEntity):
            self._build_text_path(path, e)
        elif isinstance(e, PathEntity):
            self._build_path_entity(path, e)
        elif isinstance(e, BezierEntity):
            path.moveTo(*e.p0)
            path.cubicTo(QPointF(*e.p1), QPointF(*e.p2), QPointF(*e.p3))
        elif isinstance(e, CircleEntity):
            path.addEllipse(QPointF(e.cx, e.cy), e.r, e.r)
        elif isinstance(e, EllipseEntity):
            path.addEllipse(QPointF(e.cx, e.cy), e.rx, e.ry)
        elif isinstance(e, (PolygonEntity, StarEntity, PolylineEntity)):
            pts = e.local_points()
            if not pts:
                return path
            path.moveTo(*pts[0])
            for x, y in pts[1:]:
                path.lineTo(x, y)
            if isinstance(e, PolylineEntity) and e.closed:
                path.closeSubpath()
            elif isinstance(e, (PolygonEntity, StarEntity)):
                path.closeSubpath()
        else:
            pts = e.local_points()
            if pts:
                path.moveTo(*pts[0])
                for x, y in pts[1:]:
                    path.lineTo(x, y)
        return path

    def _build_path_entity(self, path: QPainterPath, e: PathEntity) -> None:
        nodes = e.nodes
        if not nodes:
            return
        path.moveTo(*nodes[0].point)
        n = len(nodes)
        last = n if e.closed else n - 1
        for i in range(last):
            a = nodes[i]
            b = nodes[(i + 1) % n]
            if a.handle_out is None and b.handle_in is None:
                path.lineTo(*b.point)
            else:
                p0 = a.point
                p1 = a.abs_handle_out() or p0
                p2 = b.abs_handle_in() or b.point
                p3 = b.point
                path.cubicTo(QPointF(*p1), QPointF(*p2), QPointF(*p3))

    def _build_text_path(self, path: QPainterPath, e: TextEntity) -> None:
        if not e.text:
            return
        font = QFont(e.font_family)
        pt_size = e.font_size_mm / TEXT_MM_PER_PT
        font.setPointSizeF(max(1.0, pt_size))

        raw_path = QPainterPath()
        raw_path.addText(0.0, 0.0, font, e.text)

        s = mm_per_px_at_qt_dpi()
        conv = QTransform()
        conv.scale(s, -s)
        path.addPath(conv.map(raw_path))

    # ------------------------------------------------------------- QGraphicsItem
    def boundingRect(self) -> QRectF:  # noqa: N802
        r = self._build_local_path().boundingRect()
        m = HIT_PEN_WIDTH_LOCAL
        return r.adjusted(-m, -m, m, m)

    def shape(self) -> QPainterPath:
        path = self._build_local_path()
        if isinstance(self._entity, TextEntity):
            return path
        stroker = QPainterPathStroker()
        stroker.setWidth(HIT_PEN_WIDTH_LOCAL * 4)
        return stroker.createStroke(path)

    def paint(self, painter: QPainter, option, widget=None) -> None:  # noqa: N802
        base_color = self._layer_color()
        if self.isSelected():
            pen = QPen(QColor(THEME.entity_selected), 2)
        else:
            pen = QPen(QColor(base_color), 1)
        pen.setCosmetic(True)
        painter.setPen(pen)

        e = self._entity
        if isinstance(e, TextEntity):
            painter.setBrush(pen.color())
            painter.setPen(Qt.PenStyle.NoPen)
        else:
            painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawPath(self._build_local_path())

    def _layer_color(self) -> str:
        try:
            layer = self._document.get_layer(self._entity.layer_id)
        except Exception:
            layer = None
        if layer is not None and layer.color:
            return layer.color
        return THEME.entity_default

    # ------------------------------------------------------------- state layer
    def sync_from_layer(self, layer) -> None:
        if layer is None:
            return
        self.setVisible(bool(layer.visible))
        selectable = not bool(layer.locked)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, selectable)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, selectable)
        self.update()

    # ------------------------------------------------------------- interazione
    def mousePressEvent(self, event) -> None:  # noqa: N802
        self._pre_drag_transform = self._entity.transform
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # noqa: N802
        super().mouseReleaseEvent(event)
        if event.button() != Qt.MouseButton.LeftButton:
            return
        delta = self.pos()
        if delta.isNull():
            return

        self.setPos(0.0, 0.0)
        new_transform = (
            Matrix2D.translation(delta.x(), delta.y()) @ self._pre_drag_transform
        )

        scene = self.scene()
        if isinstance(scene, QGraphicsScene) and hasattr(scene, "undo_stack"):
            scene.undo_stack.push(
                TransformEntityCommand(
                    self._document, self._entity.id, new_transform
                )
            )
        else:
            self._document.update_entity_transform(self._entity.id, new_transform)