"""Test dei tool: Ellipse, Polygon, Star, Bezier, Text, Polyline."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPointF, Qt  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lasercontrolsuite.core.entities import (  # noqa: E402
    BezierEntity,
    EllipseEntity,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
)


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


def _first_entity(view):
    return next(iter(view.cad_scene.document.entities.values()))


def _bbox_center(entity):
    x0, y0, x1, y1 = entity.world_bounding_box()
    return ((x0 + x1) / 2.0, (y0 + y1) / 2.0)


# =====================================================================
# Ellipse
# =====================================================================
def test_ellipse_tool_creates_ellipse(view) -> None:
    from lasercontrolsuite.cad.tools import EllipseTool

    tool = EllipseTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(40.0, 20.0))

    e = _first_entity(view)
    assert isinstance(e, EllipseEntity)
    assert math.isclose(e.rx, 20.0, abs_tol=1e-6)
    assert math.isclose(e.ry, 10.0, abs_tol=1e-6)
    cx, cy = _bbox_center(e)
    assert math.isclose(cx, 20.0, abs_tol=1e-6)
    assert math.isclose(cy, 10.0, abs_tol=1e-6)


def test_ellipse_tool_shift_makes_circle(view) -> None:
    from lasercontrolsuite.cad.tools import EllipseTool

    tool = EllipseTool(view)
    view.set_tool(tool)

    tool.mouse_press(_FakeMouseEvent(), QPointF(0.0, 0.0))
    tool.mouse_press(
        _FakeMouseEvent(modifiers=Qt.KeyboardModifier.ShiftModifier),
        QPointF(40.0, 10.0),
    )
    e = _first_entity(view)
    assert isinstance(e, EllipseEntity)
    assert math.isclose(e.rx, e.ry, abs_tol=1e-9)


# =====================================================================
# Polygon — centro nella posizione del primo click
# =====================================================================
def test_polygon_tool_creates_polygon(view) -> None:
    from lasercontrolsuite.cad.tools import PolygonTool

    tool = PolygonTool(view, sides=6)
    view.set_tool(tool)

    tool.mouse_press(_FakeMouseEvent(), QPointF(0.0, 0.0))
    tool.mouse_press(_FakeMouseEvent(), QPointF(0.0, 30.0))

    e = _first_entity(view)
    assert isinstance(e, PolygonEntity)
    assert e.sides == 6
    assert math.isclose(e.radius, 30.0, abs_tol=1e-9)
    cx, cy = _bbox_center(e)
    assert math.isclose(cx, 0.0, abs_tol=1e-6)
    assert math.isclose(cy, 0.0, abs_tol=1e-6)


def test_polygon_tool_center_is_where_user_clicked(view) -> None:
    """Regressione: il centro del poligono deve stare dove si è cliccato.

    Bug precedente: la rotation veniva applicata sulla geometria centrata su
    (cx, cy), spostando il poligono fuori posto.
    """
    from lasercontrolsuite.cad.tools import PolygonTool

    tool = PolygonTool(view, sides=6)
    view.set_tool(tool)

    tool.mouse_press(_FakeMouseEvent(), QPointF(100.0, 50.0))
    tool.mouse_press(_FakeMouseEvent(), QPointF(100.0, 80.0))  # raggio 30, in alto

    e = _first_entity(view)
    cx, cy = _bbox_center(e)
    assert math.isclose(cx, 100.0, abs_tol=1e-6), f"cx={cx}"
    assert math.isclose(cy, 50.0, abs_tol=1e-6), f"cy={cy}"


def test_polygon_tool_rotated_center_still_at_click(view) -> None:
    """Anche con angolo di rotazione non nullo, il centro è dove si clicca."""
    from lasercontrolsuite.cad.tools import PolygonTool

    tool = PolygonTool(view, sides=6)
    view.set_tool(tool)

    # Secondo click a 45° rispetto al centro → rotazione non banale
    tool.mouse_press(_FakeMouseEvent(), QPointF(-40.0, 60.0))
    tool.mouse_press(_FakeMouseEvent(), QPointF(-40.0 + 30.0, 60.0 + 30.0))

    e = _first_entity(view)
    cx, cy = _bbox_center(e)
    assert math.isclose(cx, -40.0, abs_tol=1e-6), f"cx={cx}"
    assert math.isclose(cy, 60.0, abs_tol=1e-6), f"cy={cy}"


# =====================================================================
# Star — centro nella posizione del primo click
# =====================================================================
def test_star_tool_creates_star(view) -> None:
    from lasercontrolsuite.cad.tools import StarTool

    tool = StarTool(view, points=5, inner_ratio=0.4)
    view.set_tool(tool)

    tool.mouse_press(_FakeMouseEvent(), QPointF(0.0, 0.0))
    tool.mouse_press(_FakeMouseEvent(), QPointF(0.0, 50.0))

    e = _first_entity(view)
    assert isinstance(e, StarEntity)
    assert e.points == 5
    assert math.isclose(e.outer_radius, 50.0, abs_tol=1e-9)
    assert math.isclose(e.inner_radius, 20.0, abs_tol=1e-9)


def test_star_tool_center_is_where_user_clicked(view) -> None:
    """Regressione analoga a quella del poligono."""
    from lasercontrolsuite.cad.tools import StarTool

    tool = StarTool(view, points=5, inner_ratio=0.4)
    view.set_tool(tool)

    tool.mouse_press(_FakeMouseEvent(), QPointF(80.0, -30.0))
    tool.mouse_press(_FakeMouseEvent(), QPointF(80.0, 20.0))  # 50 in alto

    e = _first_entity(view)
    # Per una stella il bbox non è simmetrico, quindi tolleranza più larga
    cx, cy = _bbox_center(e)
    assert abs(cx - 80.0) < 1.0, f"cx={cx}"
    assert abs(cy - (-30.0)) < 5.0, f"cy={cy}"


# =====================================================================
# Bezier / Polyline
# =====================================================================
def test_bezier_tool_creates_after_4_clicks(view) -> None:
    from lasercontrolsuite.cad.tools import BezierTool

    tool = BezierTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 20.0))
    tool.mouse_press(ev, QPointF(30.0, 20.0))
    tool.mouse_press(ev, QPointF(40.0, 0.0))

    e = _first_entity(view)
    assert isinstance(e, BezierEntity)
    assert e.p0 == (0.0, 0.0)
    assert e.p3 == (40.0, 0.0)


def test_polyline_tool_multiple_clicks_and_enter_finishes(view) -> None:
    from lasercontrolsuite.cad.tools import PolylineTool

    tool = PolylineTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 10.0))

    tool.key_press(_FakeKeyEvent(Qt.Key.Key_Return))

    e = _first_entity(view)
    assert isinstance(e, PolylineEntity)
    assert len(e.points) == 3
    assert e.closed is False


def test_polyline_tool_closes_on_first_point(view) -> None:
    from lasercontrolsuite.cad.tools import PolylineTool

    tool = PolylineTool(view)
    view.set_tool(tool)
    ev = _FakeMouseEvent()

    tool.mouse_press(ev, QPointF(0.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 0.0))
    tool.mouse_press(ev, QPointF(10.0, 10.0))
    tool.mouse_press(ev, QPointF(0.0, 0.0))

    e = _first_entity(view)
    assert isinstance(e, PolylineEntity)
    assert e.closed is True