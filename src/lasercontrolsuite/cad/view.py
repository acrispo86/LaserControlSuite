"""Vista CAD: zoom, pan, tracking cursore, snapping, tool, righelli,
barra di navigazione overlay.

Convenzione Qt (row-vector):
  - ``A * B`` significa "applica B, poi A"
  - pan: ``T' = T * Tr(dx_px, dy_px)``
  - zoom ancorato al cursore: ``T' = T * Tr(sx, sy) * S(f) * Tr(-sx, -sy)``

Fit iniziale: ritentato finché il viewport ha dimensioni valide.
"""

from __future__ import annotations

from PySide6.QtCore import QPoint, QPointF, QRectF, Qt, QTimer, Signal
from PySide6.QtGui import (
    QKeyEvent,
    QMouseEvent,
    QPainter,
    QResizeEvent,
    QShowEvent,
    QTransform,
    QWheelEvent,
)
from PySide6.QtWidgets import (
    QFrame,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QWidget,
)

from lasercontrolsuite.cad.editor import CanvasEditor
from lasercontrolsuite.cad.rulers import RulerOverlay
from lasercontrolsuite.cad.scene import CadScene
from lasercontrolsuite.cad.snap import SnapEngine
from lasercontrolsuite.cad.tools import Tool
from lasercontrolsuite.resources.theme import THEME
from lasercontrolsuite.resources.theme_manager import ThemeManager


class _NavBar(QWidget):
    """Barra di navigazione overlay: zoom out, %, zoom in, 1:1, fit."""

    def __init__(self, view: "CadGraphicsView") -> None:
        super().__init__(view.viewport())
        self._view = view

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 2, 4, 2)
        layout.setSpacing(2)

        self._btn_out = QPushButton("−", self)
        self._btn_out.setFixedWidth(28)
        self._btn_out.setToolTip("Riduci zoom")
        self._btn_out.clicked.connect(view.zoom_out)

        self._zoom_label = QLabel("100%", self)
        self._zoom_label.setFixedWidth(52)
        self._zoom_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self._btn_in = QPushButton("+", self)
        self._btn_in.setFixedWidth(28)
        self._btn_in.setToolTip("Aumenta zoom")
        self._btn_in.clicked.connect(view.zoom_in)

        self._btn_100 = QPushButton("1:1", self)
        self._btn_100.setFixedWidth(36)
        self._btn_100.setToolTip("Zoom 100% (Ctrl+0)")
        self._btn_100.clicked.connect(view.reset_zoom)

        self._btn_fit = QPushButton("Fit", self)
        self._btn_fit.setFixedWidth(42)
        self._btn_fit.setToolTip("Adatta all'area di lavoro (Ctrl+Shift+F)")
        self._btn_fit.clicked.connect(view.fit_to_work_area)

        layout.addWidget(self._btn_out)
        layout.addWidget(self._zoom_label)
        layout.addWidget(self._btn_in)
        layout.addWidget(self._btn_100)
        layout.addWidget(self._btn_fit)

        self._apply_theme()
        self.adjustSize()

    def _apply_theme(self) -> None:
        self.setStyleSheet(
            f"""
            QPushButton {{
                background-color: {THEME.bg_panel};
                color: {THEME.fg_primary};
                border: 1px solid {THEME.border};
                border-radius: 3px;
                padding: 2px 4px;
                min-width: 0;
                font-size: 10pt;
            }}
            QPushButton:hover {{
                background-color: {THEME.bg_input};
                border-color: {THEME.accent};
            }}
            QLabel {{
                background-color: transparent;
                color: {THEME.fg_primary};
                font-family: {THEME.font_mono};
                font-size: 9pt;
            }}
            """
        )

    def set_zoom_text(self, zoom: float) -> None:
        self._zoom_label.setText(f"{int(round(zoom * 100))}%")


class CadGraphicsView(QGraphicsView):
    """QGraphicsView con zoom, pan, tool e righelli."""

    PX_PER_MM: float = 96.0 / 25.4

    MIN_ZOOM: float = 0.01
    MAX_ZOOM: float = 200.0

    WHEEL_BASE: float = 1.0015

    NUDGE_STEP_MM: float = 1.0
    NUDGE_STEP_FINE_MM: float = 0.1

    WORK_AREA_FIT_MARGIN: float = 0.05
    MIN_VIEWPORT_PX: int = 100

    zoomChanged = Signal(float)
    cursorMoved = Signal(QPointF)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)

        self._scene = CadScene(parent=None)
        self.setScene(self._scene)

        self._snap = SnapEngine(grid_step=1.0, enabled=True, pixel_tolerance=10.0)
        self._tool: Tool | None = None
        self._pan_active: bool = False
        self._pan_anchor: QPoint = QPoint()
        self._initial_view_done: bool = False
        self._editor: CanvasEditor | None = None

        self._ruler_top: RulerOverlay | None = None
        self._ruler_left: RulerOverlay | None = None
        self._navbar: _NavBar | None = None

        self._configure_view()
        self._apply_base_transform()
        self._create_editor()
        self._create_rulers()
        self._create_navbar()
        self.zoomChanged.connect(self._on_zoom_for_navbar)

        ThemeManager.instance().themeChanged.connect(self._on_theme_changed)

    # ------------------------------------------------------------------ API
    @property
    def cad_scene(self) -> CadScene:
        return self._scene

    @property
    def snap_engine(self) -> SnapEngine:
        return self._snap

    @property
    def current_tool(self) -> Tool | None:
        return self._tool

    @property
    def editor(self) -> CanvasEditor:
        assert self._editor is not None
        return self._editor

    def set_tool(self, tool: Tool | None) -> None:
        if self._tool is not None:
            self._tool.deactivate()
        self._tool = tool
        self._scene.set_tool(tool)
        if tool is not None:
            tool.activate()

    def set_work_area(self, rect: QRectF | None) -> None:
        self._scene.set_work_area(rect)
        if rect is not None and not self._initial_view_done:
            self._schedule_initial_fit()

    # ------------------------------------------------------------------ tema
    def _on_theme_changed(self, _name: str) -> None:
        if self._navbar is not None:
            self._navbar._apply_theme()
            self._navbar.adjustSize()
            self._position_navbar()
        self.viewport().update()

    # ------------------------------------------------------------------ zoom/pan
    def current_zoom(self) -> float:
        return abs(self.transform().m11()) / self.PX_PER_MM

    def set_zoom(self, zoom: float) -> None:
        target = max(self.MIN_ZOOM, min(self.MAX_ZOOM, float(zoom)))
        factor = target / self.current_zoom()
        if abs(factor - 1.0) < 1e-9:
            return
        center = QPointF(self.viewport().rect().center())
        self._zoom_at(center, factor)

    def zoom_in(self) -> None:
        self.set_zoom(self.current_zoom() * 1.25)

    def zoom_out(self) -> None:
        self.set_zoom(self.current_zoom() / 1.25)

    def reset_zoom(self) -> None:
        vw = max(self.viewport().width(), 1)
        vh = max(self.viewport().height(), 1)
        s = self.PX_PER_MM
        t = QTransform()
        t.translate(vw / 2.0, vh / 2.0)
        t.scale(s, -s)
        self.setTransform(t)

    def fit_scene_in_view(self, margin: float = 0.05) -> None:
        rect = self._scene.itemsBoundingRect()
        if rect.isEmpty():
            rect = self._scene.sceneRect()
        if rect.isEmpty():
            return
        self._fit_rect(rect, margin)

    def fit_to_work_area(self, margin: float | None = None) -> None:
        if margin is None:
            margin = self.WORK_AREA_FIT_MARGIN

        wa = self._scene.work_area
        if wa is None or wa.isEmpty():
            return
        self._fit_rect(wa, margin)

    def _fit_rect(self, rect: QRectF, margin: float) -> None:
        vw = self.viewport().width()
        vh = self.viewport().height()
        if vw <= 0 or vh <= 0:
            return

        m = max(rect.width(), rect.height()) * margin
        r = rect.adjusted(-m, -m, m, m)

        scale_px = min(vw / r.width(), vh / r.height())
        min_px = self.MIN_ZOOM * self.PX_PER_MM
        max_px = self.MAX_ZOOM * self.PX_PER_MM
        scale_px = max(min_px, min(max_px, scale_px))

        cx, cy = rect.center().x(), rect.center().y()

        t = QTransform()
        t.translate(vw / 2.0, vh / 2.0)
        t.scale(scale_px, -scale_px)
        t.translate(-cx, -cy)
        self.setTransform(t)

    # -------------------------------------------------------------- internals
    def _configure_view(self) -> None:
        self.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        self.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
        self.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.SmartViewportUpdate)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setResizeAnchor(QGraphicsView.ViewportAnchor.NoAnchor)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.setFrameShape(QFrame.Shape.NoFrame)
        self.setMouseTracking(True)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

    def _apply_base_transform(self) -> None:
        t = QTransform()
        t.scale(self.PX_PER_MM, -self.PX_PER_MM)
        self.setTransform(t)

    def _create_editor(self) -> None:
        self._editor = CanvasEditor(self)

    def _create_rulers(self) -> None:
        self._ruler_top = RulerOverlay(self, Qt.Orientation.Horizontal)
        self._ruler_left = RulerOverlay(self, Qt.Orientation.Vertical)
        self._sync_rulers()

    def _create_navbar(self) -> None:
        self._navbar = _NavBar(self)
        self._position_navbar()

    def _position_navbar(self) -> None:
        if self._navbar is None:
            return
        vw = self.viewport().width()
        vh = self.viewport().height()
        w = self._navbar.width()
        h = self._navbar.height()
        self._navbar.move(vw - w - 12, vh - h - 12)
        self._navbar.raise_()

    def _sync_rulers(self) -> None:
        if self._ruler_top is None or self._ruler_left is None:
            return
        self._ruler_top.sync_geometry()
        self._ruler_left.sync_geometry()
        self._ruler_top.raise_()
        self._ruler_left.raise_()
        self._ruler_top.update()
        self._ruler_left.update()
        self._position_navbar()

    def _schedule_initial_fit(self) -> None:
        if self._initial_view_done:
            return
        QTimer.singleShot(0, self._try_initial_fit)

    def _try_initial_fit(self) -> None:
        if self._initial_view_done:
            return
        vw = self.viewport().width()
        vh = self.viewport().height()
        if vw < self.MIN_VIEWPORT_PX or vh < self.MIN_VIEWPORT_PX:
            QTimer.singleShot(50, self._try_initial_fit)
            return
        if self._scene.work_area is None:
            QTimer.singleShot(50, self._try_initial_fit)
            return
        self._initial_view_done = True
        self.fit_to_work_area()

    def setTransform(self, transform: QTransform) -> None:  # noqa: N802
        super().setTransform(transform)
        self._on_transform_changed()

    def _on_transform_changed(self) -> None:
        self._scene.set_px_per_unit(abs(self.transform().m11()))
        self.zoomChanged.emit(self.current_zoom())
        if self._ruler_top is not None:
            self._ruler_top.update()
        if self._ruler_left is not None:
            self._ruler_left.update()

    def _on_zoom_for_navbar(self, zoom: float) -> None:
        if self._navbar is not None:
            self._navbar.set_zoom_text(zoom)

    def _zoom_at(self, view_pos: QPointF, factor: float) -> None:
        if factor <= 0.0:
            return
        current = self.current_zoom()
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
        self._schedule_initial_fit()

    def resizeEvent(self, event: QResizeEvent) -> None:  # noqa: N802
        super().resizeEvent(event)
        self._sync_rulers()
        if not self._initial_view_done:
            self._schedule_initial_fit()

    def wheelEvent(self, event: QWheelEvent) -> None:  # noqa: N802
        delta = event.angleDelta().y()
        if delta == 0:
            event.ignore()
            return
        factor = self.WHEEL_BASE ** delta
        self._zoom_at(event.position(), factor)
        event.accept()

    def mousePressEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton:
            self._pan_active = True
            self._pan_anchor = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return

        if self._tool is not None and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._tool.mouse_press(event, scene_pos):
                event.accept()
                return

        super().mousePressEvent(event)

    def mouseDoubleClickEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._tool is not None and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._tool.mouse_double_click(event, scene_pos):
                event.accept()
                return
        super().mouseDoubleClickEvent(event)

    def mouseMoveEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if self._pan_active:
            current = event.position().toPoint()
            delta = current - self._pan_anchor
            self._pan_anchor = current
            self._pan_by_pixels(delta.x(), delta.y())
            event.accept()
            return

        scene_pos = self.mapToScene(event.position().toPoint())
        self.cursorMoved.emit(scene_pos)

        if self._snap.enabled:
            snapped = self._snap.snap(scene_pos, self)
            self._scene.set_snap_point(snapped)
        else:
            self._scene.set_snap_point(None)

        if self._tool is not None:
            if self._tool.mouse_move(event, scene_pos):
                event.accept()
                return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event: QMouseEvent) -> None:  # noqa: N802
        if event.button() == Qt.MouseButton.MiddleButton and self._pan_active:
            self._pan_active = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        if self._tool is not None and event.button() == Qt.MouseButton.LeftButton:
            scene_pos = self.mapToScene(event.position().toPoint())
            if self._tool.mouse_release(event, scene_pos):
                event.accept()
                return

        super().mouseReleaseEvent(event)

    def keyPressEvent(self, event: QKeyEvent) -> None:  # noqa: N802
        if self._tool is not None and self._tool.key_press(event):
            event.accept()
            return

        modifiers = event.modifiers()
        key = event.key()
        no_mod = modifiers == Qt.KeyboardModifier.NoModifier
        shift = bool(modifiers & Qt.KeyboardModifier.ShiftModifier)

        step = self.NUDGE_STEP_FINE_MM if shift else self.NUDGE_STEP_MM
        if key in (
            Qt.Key.Key_Left,
            Qt.Key.Key_Right,
            Qt.Key.Key_Up,
            Qt.Key.Key_Down,
        ) and (no_mod or shift):
            dx = dy = 0.0
            if key == Qt.Key.Key_Left:
                dx = -step
            elif key == Qt.Key.Key_Right:
                dx = step
            elif key == Qt.Key.Key_Up:
                dy = step
            elif key == Qt.Key.Key_Down:
                dy = -step
            if self._editor is not None and self._editor.nudge(dx, dy):
                event.accept()
                return

        if no_mod:
            if key in (Qt.Key.Key_Plus, Qt.Key.Key_Equal):
                self.zoom_in()
                event.accept()
                return
            if key == Qt.Key.Key_Minus:
                self.zoom_out()
                event.accept()
                return
            if key == Qt.Key.Key_0:
                self.reset_zoom()
                event.accept()
                return
            if key == Qt.Key.Key_F:
                self.fit_to_work_area()
                event.accept()
                return

        super().keyPressEvent(event)