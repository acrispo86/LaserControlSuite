"""Test dei tool di disegno."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lasercontrolsuite.core.entities import PolylineEntity  # noqa: E402


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
    v.resize(600, 400)
    v.show()
    qapp.processEvents()
    yield v
    v.close()


def test_line_tool_creates_entity_on_second_click(view) -> None:
    from lasercontrolsuite.cad.tools import LineTool

    tool = LineTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(10.0, 20.0))
    tool.mouse_press(ev, QPointF(50.0, 60.0))

    doc = view.cad_scene.document
    entities = list(doc.entities.values())
    assert len(entities) == 1
    e = entities[0]
    assert isinstance(e, PolylineEntity)
    assert len(e.points) == 2
    assert e.closed is False


def test_rect_tool_creates_normalized_rect(view) -> None:
    from lasercontrolsuite.cad.tools import RectTool

    tool = RectTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    # angoli invertiti: dal basso-destra all'alto-sinistra
    tool.mouse_press(ev, QPointF(20.0, 20.0))
    tool.mouse_press(ev, QPointF(5.0, 5.0))

    doc = view.cad_scene.document
    entities = list(doc.entities.values())
    assert len(entities) == 1
    e = entities[0]
    assert isinstance(e, PolylineEntity)
    assert e.closed is True
    xs = sorted(p[0] for p in e.points)
    ys = sorted(p[1] for p in e.points)
    assert math.isclose(xs[0], 5.0, abs_tol=1e-9)
    assert math.isclose(ys[0], 5.0, abs_tol=1e-9)
    assert math.isclose(xs[-1], 20.0, abs_tol=1e-9)
    assert math.isclose(ys[-1], 20.0, abs_tol=1e-9)


def test_line_tool_escape_resets_state(view) -> None:
    from lasercontrolsuite.cad.tools import LineTool

    tool = LineTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()
    key_ev = _FakeKeyEvent(Qt.Key.Key_Escape)

    tool.mouse_press(ev, QPointF(10.0, 10.0))
    assert tool._start is not None
    handled = tool.key_press(key_ev)
    assert handled is True
    assert tool._start is None


def test_undo_removes_created_entity(view) -> None:
    from lasercontrolsuite.cad.tools import LineTool

    tool = LineTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()
    tool.mouse_press(ev, QPointF(1.0, 1.0))
    tool.mouse_press(ev, QPointF(2.0, 2.0))

    doc = view.cad_scene.document
    assert len(doc.entities) == 1

    view.cad_scene.undo_stack.undo()
    assert len(doc.entities) == 0

    view.cad_scene.undo_stack.redo()
    assert len(doc.entities) == 1