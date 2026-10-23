"""Test per ``CamPreviewView``: costruzione, item generati, fit, hover."""
import pytest

from PySide6.QtCore import QPoint

from lasercontrolsuite.cam.preview import PreviewPath, PreviewScene
from lasercontrolsuite.config import Machine, MachineOrigin
from lasercontrolsuite.ui.widgets.cam_preview import (
    CamPreviewView,
    _PreviewPathItem,
)


def _scene_two_paths():
    return PreviewScene(
        cut_paths=[
            PreviewPath(order_index=0, points=[(0, 0), (50, 0), (50, 50), (0, 50)],
                        closed=True, entity_id="e1"),
            PreviewPath(order_index=1, points=[(100, 100), (150, 150)],
                        closed=False, entity_id="e2"),
        ],
        travel_segments=[((0.0, 0.0), (0.0, 0.0)), ((0.0, 50.0), (100.0, 100.0))],
    )


def _machine():
    return Machine("Test", 400.0, 400.0, MachineOrigin.BOTTOM_LEFT)


def test_view_builds_with_items(qapp):
    v = CamPreviewView(_scene_two_paths(), _machine())
    items = [it for it in v.scene().items() if isinstance(it, _PreviewPathItem)]
    assert len(items) == 2


def test_work_rect_matches_machine(qapp):
    v = CamPreviewView(_scene_two_paths(), _machine())
    r = v.work_rect
    assert r.left() == 0.0
    assert r.top() == 0.0
    assert r.right() == 400.0
    assert r.bottom() == 400.0


def test_colors_change_with_order(qapp):
    v = CamPreviewView(_scene_two_paths(), _machine())
    items = [it for it in v.scene().items() if isinstance(it, _PreviewPathItem)]
    items.sort(key=lambda it: it.path_data.order_index)
    c0 = items[0].pen().color()
    c1 = items[1].pen().color()
    assert c0 != c1


def test_empty_scene_does_not_crash(qapp):
    s = PreviewScene(cut_paths=[], travel_segments=[])
    v = CamPreviewView(s, _machine())
    assert v.work_rect.width() == 400.0


def test_item_info_text_contains_length(qapp):
    v = CamPreviewView(_scene_two_paths(), _machine())
    items = [it for it in v.scene().items() if isinstance(it, _PreviewPathItem)]
    items.sort(key=lambda it: it.path_data.order_index)
    info = items[0].info_text()
    assert "Percorso #1" in info
    # Perimeter of a 50x50 square = 200 mm
    assert "200.00 mm" in info


def test_fit_runs_without_error(qapp):
    v = CamPreviewView(_scene_two_paths(), _machine())
    v.resize(600, 400)
    v.fit_to_content()
    # Non assertion: just shouldn't raise
    assert v.transform().m11() != 0.0


def test_escape_clears_selection(qapp):
    v = CamPreviewView(_scene_two_paths(), _machine())
    items = [it for it in v.scene().items() if isinstance(it, _PreviewPathItem)]
    items[0].setSelected(True)
    v.keyPressEvent(_mk_key_event())
    assert not items[0].isSelected()


def _mk_key_event():
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    return QKeyEvent(QKeyEvent.Type.KeyPress, Qt.Key.Key_Escape, Qt.KeyboardModifier.NoModifier)