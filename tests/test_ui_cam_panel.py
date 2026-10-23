"""Test del pannello CAM multi-layer (Step 9c)."""
from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lasercontrolsuite.core.entities import PolylineEntity  # noqa: E402
from lasercontrolsuite.core.layer import Layer  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication
    return get_or_create_qapplication([])


@pytest.fixture()
def ctx(qapp: QApplication):
    from lasercontrolsuite.cad.view import CadGraphicsView
    from lasercontrolsuite.ui.panels.cam_panel import CamPanel

    v = CadGraphicsView()
    v.resize(800, 600)
    v.show()
    qapp.processEvents()
    panel = CamPanel(v)
    yield v, panel
    # disconnessione dal documento
    try:
        v.cad_scene.document.unsubscribe(panel._on_document_event)
    except Exception:
        pass
    panel.close()
    v.close()
    panel.deleteLater()
    v.deleteLater()
    qapp.processEvents()


def _add_rect(view, x, y, w=10.0, h=5.0, layer_id=None):
    doc = view.cad_scene.document
    e = PolylineEntity.rect(layer_id or doc.active_layer_id, x, y, w, h)
    if layer_id:
        e.layer_id = layer_id
    doc.add_entity(e)
    return e


def test_panel_table_reflects_default_layer(ctx) -> None:
    view, panel = ctx
    assert panel._table.rowCount() == 1
    name_item = panel._table.item(0, panel.COL_NAME)
    assert name_item is not None
    assert name_item.text() == "Layer 1"


def test_add_layer_increases_rows(ctx) -> None:
    view, panel = ctx
    doc = view.cad_scene.document
    panel._on_add_layer()
    assert len(doc.layers) == 2
    assert panel._table.rowCount() == 2


def test_remove_last_layer_is_prevented(ctx) -> None:
    view, panel = ctx
    doc = view.cad_scene.document
    panel._table.selectRow(0)
    panel._on_remove_layer()
    assert len(doc.layers) == 1  # non rimosso


def test_edit_power_updates_layer(ctx, qapp) -> None:
    view, panel = ctx
    doc = view.cad_scene.document
    layer = list(doc.layers.values())[0]
    panel._table.selectRow(0)
    item = panel._table.item(0, panel.COL_POWER)
    item.setText("77")
    qapp.processEvents()
    assert layer.power_percent == 77


def test_edit_speed_updates_layer(ctx, qapp) -> None:
    view, panel = ctx
    doc = view.cad_scene.document
    layer = list(doc.layers.values())[0]
    panel._table.selectRow(0)
    item = panel._table.item(0, panel.COL_SPEED)
    item.setText("1500")
    qapp.processEvents()
    assert layer.speed_mm_min == 1500.0


def test_generate_with_rect_uses_layer_params(ctx) -> None:
    view, panel = ctx
    doc = view.cad_scene.document
    layer = list(doc.layers.values())[0]
    layer.power_percent = 42
    layer.speed_mm_min = 700.0
    _add_rect(view, 0.0, 0.0)
    ok = panel._on_generate()
    assert ok is True
    # S = 42/100 * 1000 = 420
    assert "M4 S420" in panel.last_gcode
    assert "F700" in panel.last_gcode


def test_generate_multi_layer_report(ctx) -> None:
    view, panel = ctx
    doc = view.cad_scene.document
    l1 = list(doc.layers.values())[0]
    l2 = Layer.new("Layer 2", priority=1)
    doc.add_layer(l2)
    _add_rect(view, 0.0, 0.0, layer_id=l1.id)
    _add_rect(view, 20.0, 0.0, layer_id=l2.id)
    ok = panel._on_generate()
    assert ok is True
    text = panel._stats.text()
    assert "Layer: 2" in text
    assert "Layer 1" in text
    assert "Layer 2" in text


def test_generate_only_selected(ctx) -> None:
    view, panel = ctx
    a = _add_rect(view, 0.0, 0.0)
    _add_rect(view, 100.0, 0.0)
    scene = view.cad_scene
    scene.clearSelection()
    scene.entity_item(a.id).setSelected(True)
    panel._only_selected.setChecked(True)
    ok = panel._on_generate()
    assert ok is True
    assert "Percorsi: 1" in panel._stats.text()


def test_global_params_from_ui(ctx) -> None:
    _, panel = ctx
    panel._s_max.setValue(2000)
    panel._travel_feed.setValue(3000)
    g = panel.current_global_params()
    assert g.s_max == 2000
    assert g.travel_feed_mm_min == 3000.0