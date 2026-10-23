"""Test del NodeEditTool."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lasercontrolsuite.core.entities import (  # noqa: E402
    CircleEntity,
    EllipseEntity,
    PolylineEntity,
    TextEntity,
)
from lasercontrolsuite.core.path import PathEntity, PathNode  # noqa: E402


class _FakeMouseEvent:
    def __init__(
        self,
        button=Qt.MouseButton.LeftButton,
        modifiers=Qt.KeyboardModifier.NoModifier,
    ) -> None:
        self._button = button
        self._modifiers = modifiers

    def button(self):
        return self._button

    def modifiers(self):
        return self._modifiers

    def accept(self) -> None: ...
    def ignore(self) -> None: ...


class _FakeKeyEvent:
    def __init__(self, key) -> None:
        self._key = key

    def key(self):
        return self._key


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication

    return get_or_create_qapplication([])


@pytest.fixture()
def view(qapp: QApplication):
    from lasercontrolsuite.cad.view import CadGraphicsView

    v = CadGraphicsView()
    v.resize(800, 600)
    v.show()
    qapp.processEvents()
    yield v
    v.close()


def _make_path(view, nodes, closed=False):
    doc = view.cad_scene.document
    p = PathEntity(layer_id=doc.active_layer_id, nodes=nodes, closed=closed)
    doc.add_entity(p)
    return p


def _select(view, entity):
    scene = view.cad_scene
    scene.clearSelection()
    item = scene.entity_item(entity.id)
    if item is not None:
        item.setSelected(True)


def _activate_node_tool(view):
    from lasercontrolsuite.cad.tools import NodeEditTool

    tool = NodeEditTool(view)
    view.set_tool(tool)
    return tool


# =====================================================================
# Conversione automatica su attach
# =====================================================================
def test_node_tool_converts_polyline_to_path(view) -> None:
    """Attivando N su un rettangolo (PolylineEntity) → diventa PathEntity.

    Regressione: l'utente si aspettava di poter modificare i lati del
    rettangolo, ma il node editor funziona solo su PathEntity.
    """
    doc = view.cad_scene.document
    poly = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 10.0, 5.0)
    doc.add_entity(poly)

    tool = _activate_node_tool(view)
    _select(view, poly)
    QApplication.processEvents()

    # L'entità è stata convertita (stesso id, tipo diverso)
    entity = doc.get_entity(poly.id)
    assert isinstance(entity, PathEntity)
    assert len(entity.nodes) == 4
    assert entity.closed is True
    # L'overlay è agganciato
    assert tool._overlay is not None


def test_node_tool_conversion_undoable(view) -> None:
    """Ctrl+Z dopo la conversione ripristina la PolylineEntity originale."""
    doc = view.cad_scene.document
    poly = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 10.0, 5.0)
    doc.add_entity(poly)

    tool = _activate_node_tool(view)
    _select(view, poly)
    QApplication.processEvents()
    assert isinstance(doc.get_entity(poly.id), PathEntity)

    view.cad_scene.undo_stack.undo()
    entity = doc.get_entity(poly.id)
    assert isinstance(entity, PolylineEntity)
    assert entity is poly


def test_node_tool_converts_circle(view) -> None:
    doc = view.cad_scene.document
    c = CircleEntity(layer_id=doc.active_layer_id, cx=0.0, cy=0.0, r=5.0)
    doc.add_entity(c)
    tool = _activate_node_tool(view)
    _select(view, c)
    QApplication.processEvents()
    assert isinstance(doc.get_entity(c.id), PathEntity)


def test_node_tool_converts_ellipse(view) -> None:
    doc = view.cad_scene.document
    e = EllipseEntity(layer_id=doc.active_layer_id, cx=0.0, cy=0.0, rx=5.0, ry=3.0)
    doc.add_entity(e)
    tool = _activate_node_tool(view)
    _select(view, e)
    QApplication.processEvents()
    assert isinstance(doc.get_entity(e.id), PathEntity)


def test_node_tool_does_not_convert_text(view) -> None:
    """TextEntity non è convertibile: niente overlay, nessuna conversione."""
    doc = view.cad_scene.document
    t = TextEntity(layer_id=doc.active_layer_id, text="Hello")
    doc.add_entity(t)
    tool = _activate_node_tool(view)
    _select(view, t)
    QApplication.processEvents()
    # Nessuna conversione
    assert isinstance(doc.get_entity(t.id), TextEntity)
    # Nessun overlay
    assert tool._overlay is None


def test_node_tool_converts_only_once(view) -> None:
    """Se è già un PathEntity, attivare N non crea un'altra conversione."""
    doc = view.cad_scene.document
    poly = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 10.0, 5.0)
    doc.add_entity(poly)

    tool = _activate_node_tool(view)
    _select(view, poly)
    QApplication.processEvents()

    stack_before = view.cad_scene.undo_stack.count()
    view.cad_scene.clearSelection()
    QApplication.processEvents()
    _select(view, doc.get_entity(poly.id))
    QApplication.processEvents()
    # Nessun nuovo comando pushato (era già PathEntity)
    assert view.cad_scene.undo_stack.count() == stack_before


# =====================================================================
# Overlay: attach / detach
# =====================================================================
def test_overlay_created_when_path_selected(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0)), PathNode((10, 10))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()
    assert tool._overlay is not None
    assert tool._path_id == p.id


def test_overlay_removed_when_selection_empty(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()
    assert tool._overlay is not None
    view.cad_scene.clearSelection()
    QApplication.processEvents()
    assert tool._overlay is None


def test_overlay_only_for_single_path(view) -> None:
    a = _make_path(view, [PathNode((0, 0)), PathNode((10, 0))])
    b = _make_path(view, [PathNode((20, 0)), PathNode((30, 0))])
    tool = _activate_node_tool(view)
    scene = view.cad_scene
    scene.clearSelection()
    scene.entity_item(a.id).setSelected(True)
    scene.entity_item(b.id).setSelected(True)
    QApplication.processEvents()
    assert tool._overlay is None


# =====================================================================
# Selezione nodi
# =====================================================================
def test_click_node_selects_it(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0)), PathNode((10, 10))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(10.02, 0.02))
    assert 1 in tool._selected


def test_shift_click_adds_to_selection(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0)), PathNode((10, 10))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    assert tool._selected == {0}
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    ev_shift = _FakeMouseEvent(modifiers=Qt.KeyboardModifier.ShiftModifier)
    tool.mouse_press(ev_shift, QPointF(10.0, 0.0))
    assert tool._selected == {0, 1}


def test_click_empty_deselects(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    assert tool._selected == {0}
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(500.0, 500.0))
    assert tool._selected == set()


# =====================================================================
# Drag nodo
# =====================================================================
def test_drag_node_moves_it(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0)), PathNode((10, 10))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_move(ev, QPointF(5.0, 5.0))
    tool.mouse_release(ev, QPointF(5.0, 5.0))

    assert math.isclose(p.nodes[0].point[0], 5.0, abs_tol=0.2)
    assert math.isclose(p.nodes[0].point[1], 5.0, abs_tol=0.2)


def test_drag_node_undo(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_move(ev, QPointF(5.0, 5.0))
    tool.mouse_release(ev, QPointF(5.0, 5.0))

    assert math.isclose(p.nodes[0].point[0], 5.0, abs_tol=0.2)

    view.cad_scene.undo_stack.undo()
    assert math.isclose(p.nodes[0].point[0], 0.0, abs_tol=0.05)


# =====================================================================
# Drag handle
# =====================================================================
def test_drag_handle_updates_symmetric(view) -> None:
    p = PathEntity(
        layer_id=view.cad_scene.document.active_layer_id,
        nodes=[
            PathNode((0, 0), handle_in=(-2, 0), handle_out=(2, 0)),
            PathNode((10, 0)),
        ],
    )
    view.cad_scene.document.add_entity(p)
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(2.0, 0.0))
    assert tool._drag_mode == "handle_out"
    tool.mouse_move(ev, QPointF(3.0, 3.0))
    tool.mouse_release(ev, QPointF(3.0, 3.0))

    h_in = p.nodes[0].handle_in
    h_out = p.nodes[0].handle_out
    assert h_out is not None and h_in is not None
    assert math.isclose(h_in[0], -h_out[0], abs_tol=0.01)


# =====================================================================
# Drag segmento → curva
# =====================================================================
def test_drag_on_line_segment_curves_it(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((20, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(10.0, 0.0))
    assert tool._drag_mode == "segment"
    tool.mouse_move(ev, QPointF(10.0, 5.0))
    tool.mouse_release(ev, QPointF(10.0, 5.0))

    assert p.nodes[0].handle_out is not None
    assert p.nodes[1].handle_in is not None
    pts = p.local_points()
    mid = pts[len(pts) // 2]
    assert math.isclose(mid[0], 10.0, abs_tol=0.5)
    assert math.isclose(mid[1], 5.0, abs_tol=0.5)


def test_drag_on_curve_segment_translates_it(view) -> None:
    p = PathEntity(
        layer_id=view.cad_scene.document.active_layer_id,
        nodes=[
            PathNode((0, 0), handle_out=(5, 5)),
            PathNode((20, 0), handle_in=(-5, 5)),
        ],
    )
    view.cad_scene.document.add_entity(p)
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    old_out = p.nodes[0].handle_out
    old_in = p.nodes[1].handle_in
    assert old_out is not None and old_in is not None

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(10.0, 3.75))
    assert tool._drag_mode == "segment"
    tool.mouse_move(ev, QPointF(12.0, 4.75))
    tool.mouse_release(ev, QPointF(12.0, 4.75))

    new_out = p.nodes[0].handle_out
    assert new_out is not None
    assert math.isclose(new_out[0] - old_out[0], 2.0, abs_tol=0.3)


def test_click_on_segment_without_drag_deselects_nodes(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    assert tool._selected == {0}

    tool.mouse_press(ev, QPointF(5.0, 0.0))
    tool.mouse_release(ev, QPointF(5.0, 0.0))
    assert tool._selected == set()
    assert p.nodes[0].is_corner()


def test_segment_drag_undo(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((20, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(10.0, 0.0))
    tool.mouse_move(ev, QPointF(10.0, 5.0))
    tool.mouse_release(ev, QPointF(10.0, 5.0))

    assert p.nodes[0].handle_out is not None

    view.cad_scene.undo_stack.undo()
    assert p.nodes[0].is_corner()
    assert p.nodes[1].is_corner()


# =====================================================================
# Add nodo con doppio click
# =====================================================================
def test_double_click_on_segment_adds_node(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0)), PathNode((10, 10))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_double_click(ev, QPointF(5.0, 0.0))
    assert len(p.nodes) == 4


def test_double_click_not_on_segment_does_nothing(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_double_click(ev, QPointF(100.0, 100.0))
    assert len(p.nodes) == 2


# =====================================================================
# Del / Corner / Smooth
# =====================================================================
def test_delete_key_removes_selected_nodes(view) -> None:
    p = _make_path(view, [
        PathNode((0, 0)), PathNode((5, 0)),
        PathNode((10, 0)), PathNode((10, 10)),
    ])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(5.0, 0.0))
    tool.mouse_release(ev, QPointF(5.0, 0.0))
    assert tool._selected == {1}

    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Delete))
    assert len(p.nodes) == 3
    assert all(
        not (math.isclose(n.point[0], 5.0, abs_tol=1e-9)
             and math.isclose(n.point[1], 0.0, abs_tol=1e-9))
        for n in p.nodes
    )


def test_corner_key_removes_handles(view) -> None:
    p = PathEntity(
        layer_id=view.cad_scene.document.active_layer_id,
        nodes=[
            PathNode((0, 0), handle_in=(-1, 0), handle_out=(1, 0)),
            PathNode((10, 0)),
        ],
    )
    view.cad_scene.document.add_entity(p)
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    tool.key_press(_FakeKeyEvent(Qt.Key.Key_C))
    assert p.nodes[0].is_corner()


def test_smooth_key_creates_handles(view) -> None:
    p = _make_path(view, [
        PathNode((0, 0)), PathNode((5, 0)), PathNode((10, 5)),
    ])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(5.0, 0.0))
    tool.mouse_release(ev, QPointF(5.0, 0.0))
    tool.key_press(_FakeKeyEvent(Qt.Key.Key_S))
    assert p.nodes[1].handle_in is not None
    assert p.nodes[1].handle_out is not None


# =====================================================================
# Esc
# =====================================================================
def test_escape_deselects(view) -> None:
    p = _make_path(view, [PathNode((0, 0)), PathNode((10, 0))])
    tool = _activate_node_tool(view)
    _select(view, p)
    QApplication.processEvents()

    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    assert tool._selected == {0}
    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Escape))
    assert tool._selected == set()