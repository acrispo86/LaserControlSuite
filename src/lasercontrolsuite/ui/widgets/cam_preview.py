"""Anteprima grafica dei percorsi CAM (stile LightBurn).

Step 9d: la vista ascolta ``ThemeManager.themeChanged`` e ricostruisce
colori cachati (sfondo, area di lavoro, griglia, penne dei percorsi,
stylesheet del tooltip). I colori letti al volo dal proxy ``THEME`` sono
già aggiornati automaticamente.
"""

from __future__ import annotations

import math

from PySide6.QtCore import QLineF, QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QBrush,
    QColor,
    QFont,
    QLinearGradient,
    QMouseEvent,
    QPainter,
    QPainterPath,
    QPainterPathStroker,
    QPen,
    QResizeEvent,
    QShowEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsPathItem,
    QGraphicsScene,
    QGraphicsView,
    QLabel,
    QWidget,
)

from lasercontrolsuite.cad.grid import GridRenderer
from lasercontrolsuite.cad.rulers import RulerOverlay
from lasercontrolsuite.cam.preview import PreviewPath, PreviewScene
from lasercontrolsuite.config import Machine
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager


class _PreviewPathItem(QGraphicsPathItem):
    """QGraphicsPathItem con hit area larga e supporto hover/selezione."""

    HIT_TOLERANCE_MM: float = 2.5

    def __init__(self, path_data: PreviewPath, color: QColor, base_width: float) -> None:
        super().__init__()
        self._path_data = path_data
        self._base_color = QColor(color)
        self._base_width = float(base_width)

        self.setPath(_build_qpath(path_data))
        self._apply_pen(hover=False)

        self.setAcceptHoverEvents(True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setZValue(20.0)

    @property
    def path_data(self) -> PreviewPath:
        return self._path_data

    def set_base_color(self, color: QColor) -> None:
        """Aggiorna il colore base (usato al cambio tema)."""
        self._base_color = QColor(color)
        self._apply_pen(hover=False)

    def info_text(self) -> str:
        pd = self._path_data
        length = _polyline_length(pd.points, pd.closed)
        return (
            f"Percorso #{pd.order_index + 1}\n"
            f"Lunghezza: {length:.2f} mm\n"
            f"Punti: {len(pd.points)}\n"
            f"Chiuso: {'sì' if pd.closed else 'no'}"
        )

    def shape(self) -> QPainterPath:
        stroker = QPainterPathStroker()
        stroker.setWidth(self.HIT_TOLERANCE_MM)
        stroker.setCapStyle(Qt.PenCapStyle.RoundCap)
        stroker.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        return stroker.createStroke(self.path())

    def _apply_pen(self, hover: bool) -> None:
        selected = self.isSelected()
        if hover or selected:
            color = QColor(THEME.cam_hover_boost)
            width = self._base_width * 2.4
        else:
            color = QColor(self._base_color)
            width = self._base_width
        pen = QPen(color, width)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        pen.setJoinStyle(Qt.PenJoinStyle.RoundJoin)
        pen.setCosmetic(True)
        self.setPen(pen)

    def hoverEnterEvent(self, event) -> None:  # noqa: N802
        self._apply_pen(hover=True)
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event) -> None:  # noqa: N802
        self._apply_pen(hover=False)
        super().hoverLeaveEvent(event)

    def itemChange(self, change, value):  # noqa: N802
        if change == QGraphicsItem.GraphicsItemChange.ItemSelectedHasChanged:
            self._apply_pen(hover=False)
        return super().itemChange(change, value)


class _LegendWidget(QWidget):
    """Barra verticale con gradiente blu→rosso e numeri 1..N."""

    WIDTH: int = 78
    HEIGHT: int = 180
    BAR_W: int = 14
    BAR_H: int = 140

    def __init__(self, parent: QWidget) -> None:
        super().__init__(parent)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
        self._count: int = 0

    def set_count(self, n: int) -> None:
        if n == self._count:
            return
        self._count = n
        self.update()

    def paintEvent(self, event) -> None:  # noqa: N802
        if self._count < 2:
            return
        p = QPainter(self)
        try:
            p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            p.setPen(QPen(QColor(THEME.cam_legend_border), 1))
            p.setBrush(QBrush(QColor(THEME.cam_legend_bg)))
            p.drawRoundedRect(self.rect().adjusted(0, 0, -1, -1), 4, 4)

            x = 8
            y = 34
            grad = QLinearGradient(x, y, x, y + self.BAR_H)
            grad.setColorAt(0.0, QColor(THEME.cam_path_first))
            grad.setColorAt(1.0, QColor(THEME.cam_path_last))
            p.setBrush(QBrush(grad))
            p.setPen(Qt.PenStyle.NoPen)
            p.drawRect(x, y, self.BAR_W, self.BAR_H)

            font = QFont(THEME.font_family)
            font.setPointSize(8)
            p.setFont(font)
            p.setPen(QColor(THEME.fg_secondary))
            p.drawText(0, 12, self.width(), 20, Qt.AlignmentFlag.AlignCenter, "Ordine")
            p.setPen(QColor(THEME.fg_primary))
            p.drawText(x + self.BAR_W + 6, y + 10, "1")
            p.drawText(x + self.BAR_W + 6, y + self.BAR_H, str(self._count))
        finally:
            p.end()


class CamPreviewView(QGraphicsView):
    """Vista di sola lettura per l'anteprima CAM."""

    PX_PER_MM: float = 96.0 / 25.4
    MIN_ZOOM: float = 0.005
    MAX_ZOOM: float = 400.0
    WHEEL_BASE: float = 1.0015
    FIT_MARGIN: float = 0.10

    hoveredPathChanged = Signal(object)

    def __init__(
        self,
        preview_scene: PreviewScene,
        machine: Machine,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._preview = preview_scene
        self._machine = machine

        self._scene = QGraphicsScene(self)
        self._scene.setSceneRect(-1e5, -1e5, 2e5, 2e5)
        self.setScene(self._scene)

        self._grid = GridRenderer(show_axes=False)
        self._outside_color = QColor()
        self._workarea_color = QColor()
        self._origin_color = QColor()

        self._pan_active = False
        self._pan_anchor = QPoint()
        self._rulers: list[RulerOverlay] = []
        self._path_items: list[_PreviewPathItem] = []
        self._work_rect = self._compute_work_rect()
        self._fitted = False

        self._tooltip = QLabel(self.viewport())
        self._tooltip.hide()

        self._legend = _LegendWidget(self.viewport())

        self._configure_view()
        self._apply_base_transform()
        self._apply_theme()
        self._populate()
        self._create_rulers()
        self._position_overlays()

        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ API
    @property
    def preview_scene(self) -> PreviewScene:
        return self._preview

    @property
    def machine(self) -> Machine:
        return self._machine

    @property
    def work_rect(self) -> QRectF:
        return QRectF(self._work_rect)

    def has_selection(self) -> bool:
        return bool(self._scene.selectedItems())

    def clear_selection(self) -> None:
        self._scene.clearSelection()
        self._tooltip.hide()

    def fit_to_content(self, margin: float | None = None) -> None:
        if margin is None:
            margin = self.FIT_MARGIN

        rect = QRectF(self._work_rect)
        items_rect = self._scene.itemsBoundingRect()
        if not items_rect.isEmpty():
            rect = rect.united(items_rect)
        if rect.isEmpty():
            return

        m = max(rect.width(), rect.height()) * margin
        rect = rect.adjusted(-m, -m, m, m)
        vw = max(self.viewport().width(), 1)
        vh = max(self.viewport().height(), 1)

        scale_px = min(vw / rect.width(), vh / rect.height())
        scale_px = max(self.MIN_ZOOM * self.PX_PER_MM,
                       min(self.MAX_ZOOM * self.PX_PER_MM, scale_px))

        cx, cy = rect.center().x(), rect.center().y()
        t = QTransform()
        t.scale(scale_px, -scale_px)
        t.translate(-cx, -cy)
        t = QTransform().translate(vw / 2.0, vh / 2.0) * t
        self.setTransform(t)
        self._fitted = True

    # --------------------------------------------------------------- tema
    def _apply_theme(self) -> None:
        """(Ri)costruisce colori e stylesheet dal tema corrente."""
        self._outside_color = QColor(THEME.canvas_outside_bg)
        self._workarea_color = QColor(THEME.canvas_workarea_bg)
        self._origin_color = QColor(THEME.origin_marker)

        self._grid.set_colors(
            minor_color=THEME.grid_minor,
            major_color=THEME.grid_major,
            axis_x_color=THEME.grid_axis_x,
            axis_y_color=THEME.grid_axis_y,
        )

        self._tooltip.setStyleSheet(
            f"background-color: {THEME.cam_tooltip_bg};"
            f"color: {THEME.fg_primary};"
            f"border: 1px solid {THEME.cam_legend_border};"
            f"border-radius: 3px;"
            f"padding: 4px 6px;"
            f"font-family: {THEME.font_mono};"
            f"font-size: 9pt;"
        )

    def _on_theme_changed(self, _name: str) -> None:
        self._apply_theme()
        # Ricolora i percorsi in base al gradiente attuale
        n = len(self._path_items)
        for i, item in enumerate(self._path_items):
            item.set_base_color(_gradient_color(i, n))
        # La legenda ridisegna col gradiente attuale
        self._legend.update()
        self.viewport().update()

    # --------------------------------------------------------------- internals
    def _configure_view(self) -> None:
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QGraphicsView.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _apply_base_transform(self) -> None:
        t = QTransform()
        t.scale(self.PX_PER_MM, -self.PX_PER_MM)
        self.setTransform(t)

    def _compute_work_rect(self) -> QRectF:
        x0, y0, x1, y1 = self._machine.work_area_bounds()
        return QRectF(x0, y0, x1 - x0, y1 - y0)

    def _populate(self) -> None:
        travel_pen = QPen(QColor(THEME.cam_travel), 0.7)
        travel_pen.setCosmetic(True)
        travel_pen.setStyle(Qt.PenStyle.DashLine)
        for (a, b) in self._preview.travel_segments:
            ln = QGraphicsLineItem(QLineF(a[0], a[1], b[0], b[1]))
            ln.setPen(travel_pen)
            ln.setZValue(10.0)
            self._scene.addItem(ln)

        n = len(self._preview.cut_paths)
        for path in self._preview.cut_paths:
            color = _gradient_color(path.order_index, n)
            item = _PreviewPathItem(path, color, base_width=1.4)
            self._scene.addItem(item)
            self._path_items.append(item)

        if self._preview.cut_paths:
            x0, y0 = self._preview.cut_paths[0].points[0]
            r = max(self._machine.width_mm, self._machine.height_mm) * 0.005
            marker_pen = QPen(QColor(THEME.cam_start_marker), 0.4)
            marker_pen.setCosmetic(True)
            marker = self._scene.addEllipse(
                x0 - r, y0 - r, 2 * r, 2 * r,
                marker_pen,
                QBrush(QColor(THEME.cam_start_marker)),
            )
            marker.setZValue(30.0)

        self._legend.set_count(n)

    def _create_rulers(self) -> None:
        top = RulerOverlay(self, Qt.Orientation.Horizontal)
        left = RulerOverlay(self, Qt.Orientation.Vertical)
        self._rulers = [top, left]
        self._sync_rulers()

    def _sync_rulers(self) -> None:
        for r in self._rulers:
            r.sync_geometry()
            r.raise_()
            r.update()
        self._position_overlays()

    def _position_overlays(self) -> None:
        if self._legend is None:
            return
        vw = self.viewport().width()
        self._legend.move(max(0, vw - self._legend.width() - 12), 30)
        self._legend.raise_()

    def setTransform(self, transform: QTransform) -> None:  # noqa: N802
        super().setTransform(transform)
        for r in self._rulers:
            r.update()

    def _zoom_at(self, view_pos: QPointF, factor: float) -> None:
        if factor <= 0.0:
            return
        current = abs(self.transform().m11()) / self.PX_PER_MM
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, current * factor))
        factor = target / current
        if abs(factor - 1.0) < 1e-9:
            return
        scene_pos = self.mapToScene(view_pos.toPoint())
        t = self.transform()
        t.translate(scene_pos.x(), scene_pos.y())
        t.scale(factor, factor)
        t.translate(-scene_pos.x(), -scene_pos.y())
        self.setTransform(t)

    def _pan_by_pixels(self, dx: float, dy: float) -> None:
        t = self.transform() * QTransform().translate(dx, dy)
        self.setTransform(t)

    # ------------------------------------------------------------------ events
    def showEvent(self, event: QShowEvent) -> None:  # noqa: N802
        super().showEvent(event)
        self._sync_rulers()
        QTimer.singleShot(0, self._fit_once)

    def _fit_once(self) -> None:
        if self._fitted:
            return
        self.fit_to_content()
        self.setFocus()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_rulers()
        if not self._fitted:
            QTimer.singleShot(0, self._fit_once)

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        self._zoom_at(event.position(), self.WHEEL_BASE ** delta)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = True
            self._pan_anchor = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        if event.button() == Qt.MouseButton.LeftButton:
            item = self.itemAt(event.position().toPoint())
            if not isinstance(item, _PreviewPathItem):
                self._scene.clearSelection()
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._pan_active:
            current = event.position().toPoint()
            delta = current - self._pan_anchor
            self._pan_anchor = current
            self._pan_by_pixels(delta.x(), delta.y())
            event.accept()
            return

        item = self.itemAt(event.position().toPoint())
        if isinstance(item, _PreviewPathItem):
            self._tooltip.setText(item.info_text())
            self._tooltip.adjustSize()
            self._tooltip.move(12, 12)
            self._tooltip.raise_()
            self._tooltip.show()
            self.hoveredPathChanged.emit(item.path_data)
        else:
            self._tooltip.hide()
            self.hoveredPathChanged.emit(None)

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_active:
            self._pan_active = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event) -> None:  # noqa: N802
        if event.key() == Qt.Key.Key_Escape:
            self.clear_selection()
            event.accept()
            return
        if event.key() == Qt.Key.Key_F:
            self.fit_to_content()
            event.accept()
            return
        super().keyPressEvent(event)

    # ------------------------------------------------------------- rendering
    def drawBackground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        painter.fillRect(rect, self._outside_color)
        painter.fillRect(self._work_rect, self._workarea_color)
        painter.save()
        try:
            painter.setClipRect(self._work_rect)
            self._grid.draw(painter, rect, abs(self.transform().m11()) or 1.0)
        finally:
            painter.restore()

    def drawForeground(self, painter: QPainter, rect: QRectF) -> None:  # noqa: N802
        super().drawForeground(painter, rect)

        w = float(THEME.canvas_axis_width)
        pen_x = QPen(QColor(THEME.canvas_axis_x_color), w)
        pen_x.setCosmetic(True)
        pen_y = QPen(QColor(THEME.canvas_axis_y_color), w)
        pen_y.setCosmetic(True)
        pen_n = QPen(QColor(THEME.canvas_workarea_border), w)
        pen_n.setCosmetic(True)
        wr = self._work_rect

        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.setPen(pen_x)
        painter.drawLine(wr.bottomLeft(), wr.bottomRight())
        painter.setPen(pen_y)
        painter.drawLine(wr.bottomLeft(), wr.topLeft())
        painter.setPen(pen_n)
        painter.drawLine(wr.topLeft(), wr.topRight())
        painter.drawLine(wr.topRight(), wr.bottomRight())

        self._draw_dimension_label(painter)

    def _draw_dimension_label(self, painter: QPainter) -> None:
        painter.save()
        painter.resetTransform()
        font = QFont(THEME.font_family)
        font.setPointSize(8)
        painter.setFont(font)
        painter.setPen(QColor(THEME.fg_secondary))
        m = self._machine
        label = f"{m.name} — {m.width_mm:g} × {m.height_mm:g} mm"
        painter.drawText(12, self.viewport().height() - 12, label)
        painter.restore()


def _build_qpath(path: PreviewPath) -> QPainterPath:
    qp = QPainterPath()
    if not path.points:
        return qp
    x0, y0 = path.points[0]
    qp.moveTo(x0, y0)
    for (x, y) in path.points[1:]:
        qp.lineTo(x, y)
    if path.closed and len(path.points) > 1:
        qp.closeSubpath()
    return qp


def _polyline_length(points: list[tuple[float, float]], closed: bool) -> float:
    if len(points) < 2:
        return 0.0
    total = 0.0
    for i in range(len(points) - 1):
        x1, y1 = points[i]
        x2, y2 = points[i + 1]
        total += math.hypot(x2 - x1, y2 - y1)
    if closed:
        x1, y1 = points[-1]
        x2, y2 = points[0]
        total += math.hypot(x2 - x1, y2 - y1)
    return total


def _gradient_color(order_index: int, total: int) -> QColor:
    if total <= 1:
        return QColor(THEME.cam_path_first)
    t = max(0.0, min(1.0, order_index / (total - 1)))
    hue = int(round(220 * (1.0 - t)))
    return QColor.fromHsv(hue, 220, 200)