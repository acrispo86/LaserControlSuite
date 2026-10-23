"""Test del Pen tool."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QEvent, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QMouseEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lasercontrolsuite.core.entities import PolylineEntity  # noqa: E402
from lasercontrolsuite.core.path import PathEntity  # noqa: E402


class _FakeMouseEvent:
    def __init__(self, button=Qt.MouseButton.LeftButton) -> None:
        self._button = button

    def button(self):
        return self._button

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


def _first_entity(view):
    return next(iter(view.cad_scene.document.entities.values()))


def test_pen_tool_creates_path_after_two_corner_clicks(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(50.0, 0.0))
    tool.mouse_release(ev, QPointF(50.0, 0.0))
    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Return))

    e = _first_entity(view)
    assert isinstance(e, PathEntity)
    assert len(e.nodes) == 2
    assert e.closed is False


def test_pen_tool_click_drag_creates_smooth_node(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_move(ev, QPointF(20.0, 10.0))
    tool.mouse_release(ev, QPointF(20.0, 10.0))

    tool.mouse_press(ev, QPointF(100.0, 0.0))
    tool.mouse_release(ev, QPointF(100.0, 0.0))

    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Return))

    e = _first_entity(view)
    assert isinstance(e, PathEntity)
    assert len(e.nodes) == 2
    assert e.nodes[0].handle_out is not None
    assert e.nodes[0].handle_in is not None


def test_pen_tool_click_first_node_closes_path(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(50.0, 0.0))
    tool.mouse_release(ev, QPointF(50.0, 0.0))
    tool.mouse_press(ev, QPointF(25.0, 30.0))
    tool.mouse_release(ev, QPointF(25.0, 30.0))
    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))

    e = _first_entity(view)
    assert isinstance(e, PathEntity)
    assert e.closed is True
    assert len(e.nodes) == 3


def test_pen_tool_escape_resets(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(10.0, 10.0))
    tool.mouse_release(ev, QPointF(10.0, 10.0))
    assert len(tool._nodes) == 1

    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Escape))
    assert len(tool._nodes) == 0
    assert len(view.cad_scene.document.entities) == 0


def test_pen_tool_enter_with_single_node_does_nothing(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(10.0, 10.0))
    tool.mouse_release(ev, QPointF(10.0, 10.0))
    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Return))
    assert len(view.cad_scene.document.entities) == 0


def test_pen_tool_undo_removes_path(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(50.0, 0.0))
    tool.mouse_release(ev, QPointF(50.0, 0.0))
    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Return))

    assert len(view.cad_scene.document.entities) == 1
    view.cad_scene.undo_stack.undo()
    assert len(view.cad_scene.document.entities) == 0
    view.cad_scene.undo_stack.redo()
    assert len(view.cad_scene.document.entities) == 1


def test_pen_tool_smooth_handles_are_symmetric(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_move(ev, QPointF(10.0, 5.0))
    tool.mouse_release(ev, QPointF(10.0, 5.0))
    tool.mouse_press(ev, QPointF(50.0, 0.0))
    tool.mouse_release(ev, QPointF(50.0, 0.0))
    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Return))

    e = _first_entity(view)
    n0 = e.nodes[0]
    assert n0.handle_out is not None
    assert n0.handle_in is not None
    assert math.isclose(n0.handle_in[0], -n0.handle_out[0], abs_tol=1e-9)
    assert math.isclose(n0.handle_in[1], -n0.handle_out[1], abs_tol=1e-9)


# =====================================================================
# Doppio click
# =====================================================================
def test_pen_tool_double_click_commits_open_path(view) -> None:
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(50.0, 0.0))
    tool.mouse_release(ev, QPointF(50.0, 0.0))
    tool.mouse_press(ev, QPointF(50.0, 50.0))
    tool.mouse_release(ev, QPointF(50.0, 50.0))

    handled = tool.mouse_double_click(ev, QPointF(50.0, 50.0))
    assert handled is True

    e = _first_entity(view)
    assert isinstance(e, PathEntity)
    assert e.closed is False
    assert len(e.nodes) == 3


def test_polyline_tool_double_click_finishes(view) -> None:
    from lasercontrolsuite.cad.tools import PolylineTool

    tool = PolylineTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 10.0))

    handled = tool.mouse_double_click(ev, QPointF(10.0, 10.0))
    assert handled is True

    e = _first_entity(view)
    assert isinstance(e, PolylineEntity)
    assert len(e.points) == 3
    assert e.closed is False


def test_view_forwards_double_click_to_tool(view) -> None:
    """Il view inoltra ``mouseDoubleClickEvent`` al tool attivo."""
    from lasercontrolsuite.cad.tools import PenTool

    tool = PenTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_release(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(50.0, 0.0))
    tool.mouse_release(ev, QPointF(50.0, 0.0))

    # Firma moderna: (type, localPos, globalPos, button, buttons, modifiers)
    pos = QPointF(100.0, 100.0)
    qt_ev = QMouseEvent(
        QEvent.Type.MouseButtonDblClick,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    view.mouseDoubleClickEvent(qt_ev)
    assert len(view.cad_scene.document.entities) == 1