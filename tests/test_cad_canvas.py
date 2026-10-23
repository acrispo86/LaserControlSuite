"""Test dello Step 2: canvas CAD (zoom, pan, griglia, snapping)."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtCore import QPoint, QPointF, Qt  # noqa: E402
from PySide6.QtGui import QImage, QPainter, QWheelEvent  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402


# ---------------------------------------------------------------- Fixtures
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


# --------------------------------------------------------------------- Grid
def test_grid_step_ladder_at_zoom_1() -> None:
    from lasercontrolsuite.cad.grid import GridRenderer

    g = GridRenderer(min_px=4.0)
    px_per_unit = 96.0 / 25.4  # ≈ 3.78 px/mm
    minor, major = g.choose_steps(px_per_unit)
    # 1mm * 3.78 < 4 → minor = 2mm (dal ladder 1-2-5)
    assert minor in (1.0, 2.0)
    assert math.isclose(major, minor * 10, rel_tol=1e-9)


def test_grid_step_adapts_to_zoom() -> None:
    from lasercontrolsuite.cad.grid import GridRenderer

    g = GridRenderer(min_px=4.0)
    minor_low, _ = g.choose_steps(0.01)
    assert minor_low >= 500.0

    minor_high, _ = g.choose_steps(1000.0)
    assert minor_high <= 0.01


# ----------------------------------------------------------------- Zoom
def test_view_initial_zoom_is_1(view) -> None:
    assert math.isclose(view.current_zoom(), 1.0, rel_tol=1e-9)


def test_view_y_axis_is_flipped(view) -> None:
    t = view.transform()
    assert t.m11() > 0
    assert t.m22() < 0


def test_zoom_at_preserves_point_under_cursor(view) -> None:
    viewport_pt = QPointF(300.0, 200.0)
    scene_before = view.mapToScene(viewport_pt.toPoint())
    view._zoom_at(viewport_pt, 2.0)
    scene_after = view.mapToScene(viewport_pt.toPoint())
    assert math.isclose(scene_before.x(), scene_after.x(), abs_tol=1e-6)
    assert math.isclose(scene_before.y(), scene_after.y(), abs_tol=1e-6)
    assert math.isclose(view.current_zoom(), 2.0, rel_tol=1e-6)


def test_zoom_is_clamped(view) -> None:
    view.set_zoom(1e6)
    assert view.current_zoom() <= view.MAX_ZOOM + 1e-9
    view.set_zoom(1e-9)
    assert view.current_zoom() >= view.MIN_ZOOM - 1e-9


def test_reset_zoom_is_100_percent(view) -> None:
    view.set_zoom(3.0)
    view.reset_zoom()
    assert math.isclose(view.current_zoom(), 1.0, rel_tol=1e-9)


def test_wheel_zooms_in_on_positive_delta(view) -> None:
    z0 = view.current_zoom()
    event = QWheelEvent(
        QPointF(400.0, 300.0),
        QPointF(400.0, 300.0),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    view.wheelEvent(event)
    assert view.current_zoom() > z0


# --------------------------------------------------------------------- Pan
def test_pan_shifts_scene_by_pixel_delta(view) -> None:
    center = QPointF(view.viewport().rect().center())
    scene_before = view.mapToScene(center.toPoint())

    dx_px, dy_px = 50.0, -30.0
    view._pan_by_pixels(dx_px, dy_px)
    scene_after = view.mapToScene(center.toPoint())

    s = abs(view.transform().m11())
    assert math.isclose(
        scene_after.x() - scene_before.x(), -dx_px / s, rel_tol=1e-6
    )
    assert math.isclose(
        scene_after.y() - scene_before.y(), dy_px / s, rel_tol=1e-6
    )


# ----------------------------------------------------------------- Snapping
class _FakeTransform:
    def __init__(self, m11: float) -> None:
        self._m11 = m11

    def m11(self) -> float:
        return self._m11


class _FakeScene:
    def __init__(self, items: list | None = None) -> None:
        self._items = items or []

    def items(self) -> list:
        return list(self._items)


class _FakeView:
    def __init__(self, m11: float = 10.0, items: list | None = None) -> None:
        self._t = _FakeTransform(m11)
        self.cad_scene = _FakeScene(items)

    def transform(self) -> _FakeTransform:
        return self._t


def test_snap_to_grid() -> None:
    from lasercontrolsuite.cad.snap import SnapEngine

    engine = SnapEngine(grid_step=1.0, enabled=True, pixel_tolerance=5.0)
    snapped = engine.snap(QPointF(3.4, -2.7), _FakeView())
    assert math.isclose(snapped.x(), 3.0, abs_tol=1e-9)
    assert math.isclose(snapped.y(), -3.0, abs_tol=1e-9)


def test_snap_disabled_returns_same_object() -> None:
    from lasercontrolsuite.cad.snap import SnapEngine

    engine = SnapEngine(enabled=False)
    p = QPointF(1.234, 5.678)
    assert engine.snap(p, _FakeView()) is p


def test_snap_to_item_endpoint_priority() -> None:
    from PySide6.QtWidgets import QGraphicsRectItem

    from lasercontrolsuite.cad.snap import SnapEngine

    class SnappyRect(QGraphicsRectItem):
        def snap_points(self):
            return [QPointF(0.0, 0.0), QPointF(10.0, 10.0)]

    item = SnappyRect(0, 0, 10, 10)
    engine = SnapEngine(grid_step=1.0, enabled=True, pixel_tolerance=20.0)
    snapped = engine.snap(QPointF(0.3, 0.3), _FakeView(items=[item]))
    assert snapped.x() == 0.0
    assert snapped.y() == 0.0


def test_snap_marker_roundtrip(view) -> None:
    p = QPointF(12.0, -4.0)
    view.cad_scene.set_snap_point(p)
    assert view.cad_scene.snap_point is not None
    view.cad_scene.set_snap_point(None)
    assert view.cad_scene.snap_point is None


# ------------------------------------------------------------- Smoke render
def test_view_renders_without_crash(view) -> None:
    img = QImage(400, 300, QImage.Format.Format_ARGB32)
    img.fill(0)
    p = QPainter(img)
    try:
        view.render(p)
    finally:
        p.end()
    assert not img.isNull()

def test_cad_scene_work_area(qapp):
    from PySide6.QtCore import QRectF
    from lasercontrolsuite.cad.scene import CadScene
    s = CadScene()
    assert s.work_area is None
    r = QRectF(0, 0, 400, 400)
    s.set_work_area(r)
    assert s.work_area == r
    s.set_work_area(None)
    assert s.work_area is None