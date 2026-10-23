"""Strumenti di interazione (tool) per il canvas CAD."""

from __future__ import annotations

import copy
import math
from abc import ABC, abstractmethod

from PySide6.QtCore import QPointF, QRectF, Qt
from PySide6.QtGui import QColor, QPainter, QPainterPath, QPen
from PySide6.QtWidgets import QGraphicsView, QInputDialog

from lasercontrolsuite.core.commands import (
    AddEntityCommand,
    EditPathCommand,
    ReplaceEntityCommand,
)
from lasercontrolsuite.core.entities import (
    BezierEntity,
    EllipseEntity,
    PolylineEntity,
    PolygonEntity,
    StarEntity,
    TextEntity,
)
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import PathEntity, PathNode
from lasercontrolsuite.core.path_edit import (
    HandleKind,
    add_node_at_segment,
    curve_line_segment_through_point,
    entity_to_path,
    find_nearest_handle,
    find_nearest_node,
    find_nearest_segment,
    is_smooth_node,
    move_handle,
    move_node,
    remove_node_at,
    set_node_corner,
    set_node_smooth,
    translate_curve_segment,
)
from lasercontrolsuite.resources.theme import THEME


PREVIEW_COLOR = QColor(THEME.entity_preview)
PEN_HANDLE_PIXELS = 12.0

NODE_PICK_PX = 8.0
HANDLE_PICK_PX = 7.0
SEGMENT_PICK_PX = 6.0
SEGMENT_DRAG_MIN_PX = 2.0


def _snap(view, pos: QPointF) -> QPointF:
    return view.snap_engine.snap(pos, view)


def _constrain_axis(start: QPointF, current: QPointF) -> QPointF:
    dx = current.x() - start.x()
    dy = current.y() - start.y()
    ang = math.atan2(dy, dx)
    step = math.pi / 4.0
    snapped_ang = round(ang / step) * step
    length = math.hypot(dx, dy)
    return QPointF(
        start.x() + length * math.cos(snapped_ang),
        start.y() + length * math.sin(snapped_ang),
    )


class Tool(ABC):
    name: str = "tool"

    def __init__(self, view) -> None:
        self._view = view

    @property
    def view(self):
        return self._view

    @property
    def scene(self):
        return self._view.cad_scene

    @property
    def document(self):
        return self.scene.document

    @property
    def undo_stack(self):
        return self.scene.undo_stack

    def activate(self) -> None: ...
    def deactivate(self) -> None: ...

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        return False

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        return False

    def mouse_release(self, event, scene_pos: QPointF) -> bool:
        return False

    def mouse_double_click(self, event, scene_pos: QPointF) -> bool:
        return False

    def key_press(self, event) -> bool:
        return False

    def paint_overlay(self, painter: QPainter) -> None: ...

    def _start_preview(self) -> QPen:
        pen = QPen(PREVIEW_COLOR, 1, Qt.PenStyle.DashLine)
        pen.setCosmetic(True)
        return pen


# =====================================================================
# Select
# =====================================================================
class SelectTool(Tool):
    name = "select"

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._view.setDragMode(QGraphicsView.DragMode.RubberBandDrag)

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)


# =====================================================================
# Linea
# =====================================================================
class LineTool(Tool):
    name = "line"

    def __init__(self, view) -> None:
        super().__init__(view)
        self._start: QPointF | None = None
        self._current: QPointF | None = None

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._start = None
        self._current = None
        self.scene.update()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        if self._start is None:
            self._start = QPointF(snapped)
        else:
            entity = PolylineEntity.line(
                layer_id=self.document.active_layer_id,
                x1=self._start.x(),
                y1=self._start.y(),
                x2=snapped.x(),
                y2=snapped.y(),
            )
            self.undo_stack.push(AddEntityCommand(self.document, entity))
            self._reset()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self._start is None:
            return False
        snapped = _snap(self.view, scene_pos)
        if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
            snapped = _constrain_axis(self._start, snapped)
        self._current = snapped
        self.scene.update()
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._start is not None:
            self._reset()
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if self._start is None or self._current is None:
            return
        painter.setPen(self._start_preview())
        painter.drawLine(self._start, self._current)


# =====================================================================
# Polilinea
# =====================================================================
class PolylineTool(Tool):
    name = "polyline"

    def __init__(self, view) -> None:
        super().__init__(view)
        self._points: list[QPointF] = []
        self._hover: QPointF | None = None

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._points = []
        self._hover = None
        self.scene.update()

    def _finish(self, close: bool = False) -> None:
        if len(self._points) < 2:
            self._reset()
            return
        pts = [(p.x(), p.y()) for p in self._points]
        entity = PolylineEntity(
            layer_id=self.document.active_layer_id,
            points=pts,
            closed=close,
        )
        self.undo_stack.push(AddEntityCommand(self.document, entity))
        self._reset()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        if self._points and snapped == self._points[0]:
            self._finish(close=True)
            return True
        self._points.append(QPointF(snapped))
        self.scene.update()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if not self._points:
            return False
        self._hover = _snap(self.view, scene_pos)
        self.scene.update()
        return True

    def mouse_double_click(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self._points:
            return False
        self._finish(close=False)
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._points:
            self._reset()
            return True
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._points:
            self._finish(close=False)
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if not self._points:
            return
        painter.setPen(self._start_preview())
        for i in range(len(self._points) - 1):
            painter.drawLine(self._points[i], self._points[i + 1])
        if self._hover is not None:
            painter.drawLine(self._points[-1], self._hover)


# =====================================================================
# Bézier (legacy)
# =====================================================================
class BezierTool(Tool):
    name = "bezier"

    def __init__(self, view) -> None:
        super().__init__(view)
        self._points: list[QPointF] = []
        self._hover: QPointF | None = None

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._points = []
        self._hover = None
        self.scene.update()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        self._points.append(QPointF(snapped))
        if len(self._points) == 4:
            e = BezierEntity(
                layer_id=self.document.active_layer_id,
                p0=(self._points[0].x(), self._points[0].y()),
                p1=(self._points[1].x(), self._points[1].y()),
                p2=(self._points[2].x(), self._points[2].y()),
                p3=(self._points[3].x(), self._points[3].y()),
            )
            self.undo_stack.push(AddEntityCommand(self.document, e))
            self._reset()
        else:
            self.scene.update()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if not self._points:
            return False
        self._hover = _snap(self.view, scene_pos)
        self.scene.update()
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._points:
            self._reset()
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if not self._points:
            return
        painter.setPen(self._start_preview())
        pts = list(self._points) + ([self._hover] if self._hover is not None else [])
        for i in range(len(pts) - 1):
            painter.drawLine(pts[i], pts[i + 1])
        if len(self._points) >= 2:
            p0 = self._points[0]
            p1 = self._points[1] if len(self._points) > 1 else p0
            p2 = self._points[2] if len(self._points) > 2 else p1
            p3 = self._points[3] if len(self._points) > 3 else (
                self._hover if self._hover is not None else p2
            )
            path = QPainterPath()
            path.moveTo(p0)
            path.cubicTo(p1, p2, p3)
            painter.drawPath(path)


# =====================================================================
# Pen tool
# =====================================================================
class PenTool(Tool):
    name = "pen"

    def __init__(self, view) -> None:
        super().__init__(view)
        self._nodes: list[PathNode] = []
        self._hover: QPointF | None = None
        self._dragging: bool = False
        self._drag_start: QPointF | None = None
        self._drag_current: QPointF | None = None

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._nodes = []
        self._hover = None
        self._dragging = False
        self._drag_start = None
        self._drag_current = None
        self.scene.update()

    def _commit(self, closed: bool) -> None:
        if len(self._nodes) < 2:
            self._reset()
            return
        path = PathEntity(
            layer_id=self.document.active_layer_id,
            nodes=list(self._nodes),
            closed=closed,
        )
        self.undo_stack.push(AddEntityCommand(self.document, path))
        self._reset()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        if self._nodes:
            first = self._nodes[0].point
            dist = math.hypot(snapped.x() - first[0], snapped.y() - first[1])
            pixel_tol = 8.0 / max(abs(self.view.transform().m11()), 1e-9)
            if dist < pixel_tol:
                self._commit(closed=True)
                return True

        self._dragging = True
        self._drag_start = QPointF(snapped)
        self._drag_current = QPointF(snapped)
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        snapped = _snap(self.view, scene_pos)
        if self._dragging and self._drag_start is not None:
            self._drag_current = snapped
            self.scene.update()
            return True
        if self._nodes:
            self._hover = snapped
            self.scene.update()
            return True
        return False

    def mouse_release(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self._dragging or self._drag_start is None:
            return False
        start = self._drag_start
        end = self._drag_current or start
        drag_dx = end.x() - start.x()
        drag_dy = end.y() - start.y()
        threshold_scene = PEN_HANDLE_PIXELS / max(
            abs(self.view.transform().m11()), 1e-9
        )
        if math.hypot(drag_dx, drag_dy) >= threshold_scene:
            node = PathNode(
                point=(start.x(), start.y()),
                handle_out=(drag_dx, drag_dy),
                handle_in=(-drag_dx, -drag_dy),
            )
        else:
            node = PathNode(point=(start.x(), start.y()))
        self._nodes.append(node)
        self._dragging = False
        self._drag_start = None
        self._drag_current = None
        self._hover = QPointF(start)
        self.scene.update()
        return True

    def mouse_double_click(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        if not self._nodes:
            return False
        self._commit(closed=False)
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._nodes:
            self._reset()
            return True
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self._nodes:
            self._commit(closed=False)
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if not self._nodes and self._drag_start is None:
            return
        painter.setPen(self._start_preview())
        if self._nodes:
            path = QPainterPath()
            path.moveTo(*self._nodes[0].point)
            for i in range(1, len(self._nodes)):
                a = self._nodes[i - 1]
                b = self._nodes[i]
                if a.handle_out is None and b.handle_in is None:
                    path.lineTo(*b.point)
                else:
                    p0 = a.point
                    p1 = a.abs_handle_out() or p0
                    p2 = b.abs_handle_in() or b.point
                    p3 = b.point
                    path.cubicTo(QPointF(*p1), QPointF(*p2), QPointF(*p3))
            if self._hover is not None and not self._dragging:
                last = self._nodes[-1]
                preview = QPainterPath(path)
                if last.handle_out is None:
                    preview.lineTo(self._hover)
                else:
                    p1 = last.abs_handle_out() or last.point
                    preview.cubicTo(
                        QPointF(*p1), QPointF(self._hover), QPointF(self._hover)
                    )
                painter.drawPath(preview)
            else:
                painter.drawPath(path)

        if self._dragging and self._drag_start is not None and self._drag_current is not None:
            painter.setPen(self._start_preview())
            painter.drawLine(self._drag_start, self._drag_current)
            dx = self._drag_current.x() - self._drag_start.x()
            dy = self._drag_current.y() - self._drag_start.y()
            other = QPointF(self._drag_start.x() - dx, self._drag_start.y() - dy)
            painter.drawLine(self._drag_start, other)

        painter.setPen(QPen(PREVIEW_COLOR, 1))
        painter.setBrush(PREVIEW_COLOR)
        for node in self._nodes:
            p = QPointF(*node.point)
            painter.drawEllipse(p, 2.0, 2.0)
        if self._drag_start is not None:
            painter.drawEllipse(self._drag_start, 2.0, 2.0)


# =====================================================================
# Node edit tool
# =====================================================================
class NodeEditTool(Tool):
    """Editor di nodi, handle e segmenti per un ``PathEntity``.

    Se l'entità selezionata non è un ``PathEntity`` ma è convertibile
    (rettangolo, cerchio, ellisse, poligono, stella, bézier, polilinea),
    viene **automaticamente convertita** a ``PathEntity`` preservando id,
    layer e transform. La conversione è annullabile con Ctrl+Z.
    """

    name = "nodes"

    def __init__(self, view) -> None:
        super().__init__(view)
        self._path_id: str | None = None
        self._overlay = None  # type: ignore[assignment]
        self._selected: set[int] = set()
        self._drag_mode: str | None = None
        self._drag_node_index: int = -1
        self._drag_segment_index: int = -1
        self._drag_start_local: tuple[float, float] = (0.0, 0.0)
        self._segment_drag_moved: bool = False
        self._drag_original_nodes: list[PathNode] | None = None
        self._drag_original_closed: bool = False
        self._converting: bool = False  # guard per evitare ricorsione

    # --------------------------------------------------------------- lifecycle
    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.scene.selectionChanged.connect(self._on_scene_selection_changed)
        self._on_scene_selection_changed()

    def deactivate(self) -> None:
        try:
            self.scene.selectionChanged.disconnect(self._on_scene_selection_changed)
        except (RuntimeError, TypeError):
            pass
        self._detach_overlay()
        self._view.setCursor(Qt.CursorShape.ArrowCursor)

    # --------------------------------------------------------------- overlay
    def _on_scene_selection_changed(self) -> None:
        if self._converting:
            return

        entities = self._selected_entities()
        if len(entities) != 1:
            self._detach_overlay()
            return

        entity = entities[0]

        # Se non è un Path, prova a convertirlo
        if not isinstance(entity, PathEntity):
            converted = entity_to_path(entity)
            if converted is None:
                # Non convertibile (es. testo): niente overlay
                self._detach_overlay()
                return

            # Conversione automatica con undo. Preserva id.
            self._converting = True
            try:
                self.undo_stack.push(
                    ReplaceEntityCommand(
                        self.document, entity, converted,
                        label="Converti in path",
                    )
                )
                # Riseleziona l'entità convertita (stesso id)
                self._reselect(converted.id)
            finally:
                self._converting = False
            # La selezione è cambiata di nuovo: selezionerà il path nuovo
            # al prossimo giro (selectionChanged → _on_scene_selection_changed).
            # Per sicurezza, procediamo direttamente.
            if isinstance(converted, PathEntity):
                self._attach(converted)
            return

        # È già un Path
        if entity.id != self._path_id:
            self._attach(entity)

    def _selected_entities(self) -> list:
        from lasercontrolsuite.cad.entity_item import EntityItem

        return [
            item.entity
            for item in self.scene.selectedItems()
            if isinstance(item, EntityItem)
        ]

    def _reselect(self, entity_id: str) -> None:
        """Riseleziona l'item con l'id dato (dopo una conversione)."""
        scene = self.scene
        scene.clearSelection()
        item = scene.entity_item(entity_id)
        if item is not None:
            item.setSelected(True)

    def _attach(self, path: PathEntity) -> None:
        from lasercontrolsuite.cad.node_overlay import NodeOverlayItem

        self._detach_overlay()
        item = self.scene.entity_item(path.id)
        if item is None:
            return
        self._path_id = path.id
        self._selected = set()
        self._overlay = NodeOverlayItem(item, path)
        self._overlay.refresh()
        self.scene.update()

    def _detach_overlay(self) -> None:
        if self._overlay is not None:
            try:
                self._overlay.setParentItem(None)
                if self._overlay.scene() is not None:
                    self._overlay.scene().removeItem(self._overlay)
            except (RuntimeError, AttributeError):
                pass
            self._overlay = None
        self._path_id = None
        self._selected = set()
        self.scene.update()

    def _path(self) -> PathEntity | None:
        if self._path_id is None:
            return None
        entity = self.document.get_entity(self._path_id)
        if isinstance(entity, PathEntity):
            return entity
        return None

    # --------------------------------------------------------------- helpers
    def _px_to_scene(self, px: float) -> float:
        scale = abs(self.view.transform().m11())
        if scale <= 0.0:
            return px
        return px / scale

    def _scene_to_local(self, path: PathEntity, scene_pos: QPointF) -> tuple[float, float]:
        inv = path.transform.inverted()
        return inv.transform_point(scene_pos.x(), scene_pos.y())

    def _refresh_overlay(self) -> None:
        if self._overlay is not None:
            self._overlay.refresh()
            self._overlay.set_selected_nodes(self._selected)

    def _notify_entity_changed(self, path: PathEntity) -> None:
        from lasercontrolsuite.core.document import DocumentEvent
        self.document._emit(DocumentEvent("entity_changed", entity_id=path.id))

    # --------------------------------------------------------------- snapshot/undo
    def _snapshot(self, path: PathEntity) -> tuple[list[PathNode], bool]:
        return copy.deepcopy(path.nodes), path.closed

    def _push_edit(
        self, path: PathEntity, old_nodes: list[PathNode], old_closed: bool, label: str
    ) -> None:
        cmd = EditPathCommand(
            self.document, path.id,
            old_nodes, path.nodes,
            old_closed, path.closed,
            label=label,
        )
        self.undo_stack.push(cmd)
        self._refresh_overlay()

    # --------------------------------------------------------------- mouse
    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        path = self._path()
        if path is None:
            return False

        local = self._scene_to_local(path, scene_pos)

        hit_handle = find_nearest_handle(path, local, self._px_to_scene(HANDLE_PICK_PX))
        if hit_handle is not None:
            if hit_handle.node_index not in self._selected:
                if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                    self._selected.add(hit_handle.node_index)
                else:
                    self._selected = {hit_handle.node_index}
            self._begin_drag(path, node_index=hit_handle.node_index,
                             mode='handle_in' if hit_handle.kind is HandleKind.IN else 'handle_out')
            return True

        hit_node = find_nearest_node(path, local, self._px_to_scene(NODE_PICK_PX))
        if hit_node is not None:
            if event.modifiers() & Qt.KeyboardModifier.ShiftModifier:
                self._selected.symmetric_difference_update({hit_node.index})
            else:
                if hit_node.index not in self._selected:
                    self._selected = {hit_node.index}
            self._begin_drag(path, node_index=hit_node.index, mode='node')
            self._refresh_overlay()
            return True

        hit_seg = find_nearest_segment(path, local, self._px_to_scene(SEGMENT_PICK_PX * 2))
        if hit_seg is not None:
            self._drag_mode = 'segment'
            self._drag_segment_index = hit_seg.segment_index
            self._drag_start_local = local
            self._segment_drag_moved = False
            self._drag_original_nodes, self._drag_original_closed = self._snapshot(path)
            return True

        self._selected = set()
        self._refresh_overlay()
        return True

    def _begin_drag(self, path: PathEntity, node_index: int, mode: str) -> None:
        self._drag_mode = mode
        self._drag_node_index = node_index
        self._drag_original_nodes, self._drag_original_closed = self._snapshot(path)
        self._refresh_overlay()

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self._drag_mode is None:
            return False
        path = self._path()
        if path is None:
            return False

        local = self._scene_to_local(path, scene_pos)

        if self._drag_mode == 'node':
            node = path.nodes[self._drag_node_index]
            dx = local[0] - node.point[0]
            dy = local[1] - node.point[1]
            if abs(dx) < 1e-12 and abs(dy) < 1e-12:
                return True
            move_node(path, self._drag_node_index, dx, dy)
        elif self._drag_mode in ('handle_in', 'handle_out'):
            kind = HandleKind.IN if self._drag_mode == 'handle_in' else HandleKind.OUT
            node = path.nodes[self._drag_node_index]
            symmetric = is_smooth_node(node)
            move_handle(path, self._drag_node_index, kind, local, symmetric=symmetric)
        elif self._drag_mode == 'segment':
            self._apply_segment_drag(path, local)
        else:
            return False

        self._notify_entity_changed(path)
        self._refresh_overlay()
        return True

    def _apply_segment_drag(self, path: PathEntity, local: tuple[float, float]) -> None:
        if self._drag_original_nodes is None:
            return

        for i, node in enumerate(self._drag_original_nodes):
            if i < len(path.nodes):
                path.nodes[i] = copy.deepcopy(node)
            else:
                path.nodes.append(copy.deepcopy(node))

        scale = abs(self.view.transform().m11())
        min_scene = (SEGMENT_DRAG_MIN_PX / scale) if scale > 0 else 0.1
        dx_total = local[0] - self._drag_start_local[0]
        dy_total = local[1] - self._drag_start_local[1]
        if math.hypot(dx_total, dy_total) < min_scene:
            return

        self._segment_drag_moved = True

        n = len(path.nodes)
        a = path.nodes[self._drag_segment_index]
        b = path.nodes[(self._drag_segment_index + 1) % n]
        is_line = a.handle_out is None and b.handle_in is None

        if is_line:
            curve_line_segment_through_point(path, self._drag_segment_index, local)
        else:
            translate_curve_segment(path, self._drag_segment_index, dx_total, dy_total)

    def mouse_release(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton or self._drag_mode is None:
            return False
        path = self._path()
        if path is None:
            self._end_drag()
            return False

        if self._drag_mode == 'segment' and not self._segment_drag_moved:
            self._selected = set()
            self._end_drag()
            self._refresh_overlay()
            return True

        if self._drag_original_nodes is None:
            self._end_drag()
            return False

        old_nodes = self._drag_original_nodes
        old_closed = self._drag_original_closed
        new_nodes = copy.deepcopy(path.nodes)
        new_closed = path.closed

        if old_nodes == new_nodes and old_closed == new_closed:
            self._end_drag()
            self._refresh_overlay()
            return True

        cmd = EditPathCommand(
            self.document, path.id,
            old_nodes, new_nodes,
            old_closed, new_closed,
            label=self._drag_label(),
        )
        self.undo_stack.push(cmd)
        self._end_drag()
        self._refresh_overlay()
        return True

    def _end_drag(self) -> None:
        self._drag_mode = None
        self._drag_node_index = -1
        self._drag_segment_index = -1
        self._segment_drag_moved = False
        self._drag_original_nodes = None
        self._drag_original_closed = False
        self._drag_start_local = (0.0, 0.0)

    def _drag_label(self) -> str:
        if self._drag_mode == 'node':
            return "Sposta nodo"
        if self._drag_mode == 'segment':
            return "Modifica segmento"
        return "Modifica handle"

    # --------------------------------------------------------------- double click
    def mouse_double_click(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        path = self._path()
        if path is None:
            return False

        local = self._scene_to_local(path, scene_pos)
        if find_nearest_node(path, local, self._px_to_scene(NODE_PICK_PX)) is not None:
            return False
        hit = find_nearest_segment(path, local, self._px_to_scene(SEGMENT_PICK_PX * 3))
        if hit is None:
            return False

        old_nodes, old_closed = self._snapshot(path)
        new_index = add_node_at_segment(path, hit.segment_index, hit.t)
        self._selected = {new_index}
        self._push_edit(path, old_nodes, old_closed, "Aggiungi nodo")
        return True

    # --------------------------------------------------------------- key
    def key_press(self, event) -> bool:
        path = self._path()
        if path is None:
            return False

        key = event.key()

        if key == Qt.Key.Key_Escape:
            self._selected = set()
            self._refresh_overlay()
            return True

        if key in (Qt.Key.Key_Delete, Qt.Key.Key_Backspace):
            if not self._selected:
                return False
            old_nodes, old_closed = self._snapshot(path)
            for idx in sorted(self._selected, reverse=True):
                if 0 <= idx < len(path.nodes):
                    remove_node_at(path, idx)
            self._selected = set()
            self._push_edit(path, old_nodes, old_closed, "Rimuovi nodi")
            return True

        if key == Qt.Key.Key_C:
            if not self._selected:
                return False
            old_nodes, old_closed = self._snapshot(path)
            for idx in sorted(self._selected):
                if 0 <= idx < len(path.nodes):
                    set_node_corner(path, idx)
            self._push_edit(path, old_nodes, old_closed, "Converti in corner")
            return True

        if key == Qt.Key.Key_S:
            if not self._selected:
                return False
            old_nodes, old_closed = self._snapshot(path)
            for idx in sorted(self._selected):
                if 0 <= idx < len(path.nodes):
                    set_node_smooth(path, idx)
            self._push_edit(path, old_nodes, old_closed, "Converti in smooth")
            return True

        return False

    def paint_overlay(self, painter: QPainter) -> None:
        return


# =====================================================================
# Rettangolo
# =====================================================================
class RectTool(Tool):
    name = "rect"

    def __init__(self, view) -> None:
        super().__init__(view)
        self._start: QPointF | None = None
        self._current: QPointF | None = None

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._start = None
        self._current = None
        self.scene.update()

    def _rect_from(self, start: QPointF, end: QPointF, from_center: bool, square: bool) -> QRectF:
        dx = end.x() - start.x()
        dy = end.y() - start.y()
        if square:
            side = max(abs(dx), abs(dy))
            dx = math.copysign(side, dx) if dx != 0 else side
            dy = math.copysign(side, dy) if dy != 0 else side
        if from_center:
            return QRectF(
                start.x() - abs(dx), start.y() - abs(dy), 2 * abs(dx), 2 * abs(dy)
            )
        return QRectF(start, QPointF(start.x() + dx, start.y() + dy)).normalized()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        if self._start is None:
            self._start = QPointF(snapped)
            return True
        from_center = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier) if hasattr(event, "modifiers") else False
        square = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier) if hasattr(event, "modifiers") else False
        r = self._rect_from(self._start, snapped, from_center, square)
        if r.width() < 1e-9 or r.height() < 1e-9:
            self._reset()
            return True
        entity = PolylineEntity.rect(
            layer_id=self.document.active_layer_id,
            x=r.left(), y=r.top(), w=r.width(), h=r.height(),
        )
        self.undo_stack.push(AddEntityCommand(self.document, entity))
        self._reset()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self._start is None:
            return False
        self._current = _snap(self.view, scene_pos)
        self.scene.update()
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._start is not None:
            self._reset()
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if self._start is None or self._current is None:
            return
        painter.setPen(self._start_preview())
        painter.drawRect(QRectF(self._start, self._current).normalized())


# =====================================================================
# Ellisse
# =====================================================================
class EllipseTool(Tool):
    name = "ellipse"

    def __init__(self, view) -> None:
        super().__init__(view)
        self._start: QPointF | None = None
        self._current: QPointF | None = None

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._start = None
        self._current = None
        self.scene.update()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        if self._start is None:
            self._start = QPointF(snapped)
            return True

        shift = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier) if hasattr(event, "modifiers") else False
        alt = bool(event.modifiers() & Qt.KeyboardModifier.AltModifier) if hasattr(event, "modifiers") else False

        dx = snapped.x() - self._start.x()
        dy = snapped.y() - self._start.y()
        if shift:
            side = max(abs(dx), abs(dy))
            dx = math.copysign(side, dx) if dx != 0 else side
            dy = math.copysign(side, dy) if dy != 0 else side
        if alt:
            cx, cy = self._start.x(), self._start.y()
            rx, ry = abs(dx), abs(dy)
        else:
            cx = self._start.x() + dx / 2.0
            cy = self._start.y() + dy / 2.0
            rx, ry = abs(dx) / 2.0, abs(dy) / 2.0
        if rx < 1e-9 or ry < 1e-9:
            self._reset()
            return True
        e = EllipseEntity(
            layer_id=self.document.active_layer_id,
            cx=cx, cy=cy, rx=rx, ry=ry,
        )
        self.undo_stack.push(AddEntityCommand(self.document, e))
        self._reset()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self._start is None:
            return False
        self._current = _snap(self.view, scene_pos)
        self.scene.update()
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._start is not None:
            self._reset()
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if self._start is None or self._current is None:
            return
        painter.setPen(self._start_preview())
        painter.drawEllipse(QRectF(self._start, self._current).normalized())


# =====================================================================
# Poligono
# =====================================================================
class PolygonTool(Tool):
    name = "polygon"

    def __init__(self, view, sides: int = 6) -> None:
        super().__init__(view)
        self._center: QPointF | None = None
        self._current: QPointF | None = None
        self.sides = max(3, sides)

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._center = None
        self._current = None
        self.scene.update()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        if self._center is None:
            self._center = QPointF(snapped)
            return True
        dx = snapped.x() - self._center.x()
        dy = snapped.y() - self._center.y()
        radius = math.hypot(dx, dy)
        if radius < 1e-9:
            self._reset()
            return True
        angle = math.atan2(dy, dx) - math.pi / 2.0
        e = PolygonEntity(
            layer_id=self.document.active_layer_id,
            radius=radius,
            sides=self.sides,
        )
        e.transform = (
            Matrix2D.translation(self._center.x(), self._center.y())
            @ Matrix2D.rotation(angle)
        )
        self.undo_stack.push(AddEntityCommand(self.document, e))
        self._reset()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self._center is None:
            return False
        self._current = _snap(self.view, scene_pos)
        self.scene.update()
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._center is not None:
            self._reset()
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if self._center is None or self._current is None:
            return
        painter.setPen(self._start_preview())
        dx = self._current.x() - self._center.x()
        dy = self._current.y() - self._center.y()
        radius = math.hypot(dx, dy)
        start = math.atan2(dy, dx)
        n = self.sides
        pts = [
            QPointF(
                self._center.x() + radius * math.cos(start + 2 * math.pi * i / n),
                self._center.y() + radius * math.sin(start + 2 * math.pi * i / n),
            )
            for i in range(n)
        ]
        for i in range(n):
            painter.drawLine(pts[i], pts[(i + 1) % n])


# =====================================================================
# Stella
# =====================================================================
class StarTool(Tool):
    name = "star"

    def __init__(self, view, points: int = 5, inner_ratio: float = 0.4) -> None:
        super().__init__(view)
        self._center: QPointF | None = None
        self._current: QPointF | None = None
        self.points = max(3, points)
        self.inner_ratio = max(0.05, min(0.95, inner_ratio))

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.CrossCursor)
        self._reset()

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)
        self._reset()

    def _reset(self) -> None:
        self._center = None
        self._current = None
        self.scene.update()

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        if self._center is None:
            self._center = QPointF(snapped)
            return True
        dx = snapped.x() - self._center.x()
        dy = snapped.y() - self._center.y()
        radius = math.hypot(dx, dy)
        if radius < 1e-9:
            self._reset()
            return True
        angle = math.atan2(dy, dx) - math.pi / 2.0
        e = StarEntity(
            layer_id=self.document.active_layer_id,
            outer_radius=radius,
            inner_radius=radius * self.inner_ratio,
            points=self.points,
        )
        e.transform = (
            Matrix2D.translation(self._center.x(), self._center.y())
            @ Matrix2D.rotation(angle)
        )
        self.undo_stack.push(AddEntityCommand(self.document, e))
        self._reset()
        return True

    def mouse_move(self, event, scene_pos: QPointF) -> bool:
        if self._center is None:
            return False
        self._current = _snap(self.view, scene_pos)
        self.scene.update()
        return True

    def key_press(self, event) -> bool:
        if event.key() == Qt.Key.Key_Escape and self._center is not None:
            self._reset()
            return True
        return False

    def paint_overlay(self, painter: QPainter) -> None:
        if self._center is None or self._current is None:
            return
        painter.setPen(self._start_preview())
        dx = self._current.x() - self._center.x()
        dy = self._current.y() - self._center.y()
        r_out = math.hypot(dx, dy)
        r_in = r_out * self.inner_ratio
        start = math.atan2(dy, dx)
        n = self.points
        pts: list[QPointF] = []
        for i in range(2 * n):
            angle = start + math.pi * i / n
            r = r_out if i % 2 == 0 else r_in
            pts.append(
                QPointF(
                    self._center.x() + r * math.cos(angle),
                    self._center.y() + r * math.sin(angle),
                )
            )
        for i in range(len(pts)):
            painter.drawLine(pts[i], pts[(i + 1) % len(pts)])


# =====================================================================
# Testo
# =====================================================================
class TextTool(Tool):
    name = "text"

    def activate(self) -> None:
        self._view.setCursor(Qt.CursorShape.IBeamCursor)

    def deactivate(self) -> None:
        self._view.setCursor(Qt.CursorShape.ArrowCursor)

    def mouse_press(self, event, scene_pos: QPointF) -> bool:
        if event.button() != Qt.MouseButton.LeftButton:
            return False
        snapped = _snap(self.view, scene_pos)
        text, ok = QInputDialog.getText(self._view, "Testo", "Contenuto:")
        if not ok or not text.strip():
            return True
        e = TextEntity(
            layer_id=self.document.active_layer_id,
            text=text,
        )
        e.transform = Matrix2D.translation(snapped.x(), snapped.y())
        self.undo_stack.push(AddEntityCommand(self.document, e))
        return True