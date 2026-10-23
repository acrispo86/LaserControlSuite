"""Test del pannello proprietà."""

from __future__ import annotations

import math
import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from lasercontrolsuite.core.entities import PolylineEntity  # noqa: E402


@pytest.fixture(scope="session")
def qapp() -> QApplication:
    from lasercontrolsuite.app import get_or_create_qapplication

    return get_or_create_qapplication([])


@pytest.fixture()
def ctx(qapp: QApplication):
    from lasercontrolsuite.cad.view import CadGraphicsView
    from lasercontrolsuite.ui.panels.property_panel import PropertyPanel

    v = CadGraphicsView()
    v.resize(800, 600)
    v.show()
    qapp.processEvents()
    panel = PropertyPanel(v)
    yield v, panel
    panel.detach()
    panel.close()
    v.close()


def _add_rect(view, x, y, w=10.0, h=5.0):
    doc = view.cad_scene.document
    e = PolylineEntity.rect(doc.active_layer_id, x, y, w, h)
    doc.add_entity(e)
    return e


def _select(view, e):
    scene = view.cad_scene
    scene.clearSelection()
    item = scene.entity_item(e.id)
    if item is not None:
        item.setSelected(True)


# =====================================================================
# Funzionamento base
# =====================================================================
def test_panel_disabled_with_no_selection(ctx) -> None:
    view, panel = ctx
    assert not panel._x.isEnabled()
    assert panel._type_label.text() == "—"


def test_panel_shows_entity_bbox(ctx) -> None:
    view, panel = ctx
    e = _add_rect(view, 5.0, 7.0, 4.0, 3.0)
    _select(view, e)
    assert math.isclose(panel._x.value(), 5.0, abs_tol=1e-9)
    assert math.isclose(panel._y.value(), 7.0, abs_tol=1e-9)
    assert math.isclose(panel._w.value(), 4.0, abs_tol=1e-9)
    assert math.isclose(panel._h.value(), 3.0, abs_tol=1e-9)
    assert panel._x.isEnabled()


def test_panel_edit_x_moves_entity(ctx) -> None:
    view, panel = ctx
    e = _add_rect(view, 0.0, 0.0)
    _select(view, e)
    panel._x.setValue(25.0)
    panel._x.editingFinished.emit()
    x0, _, _, _ = e.world_bounding_box()
    assert math.isclose(x0, 25.0, abs_tol=1e-9)


def test_panel_edit_w_scales_entity(ctx) -> None:
    view, panel = ctx
    e = _add_rect(view, 0.0, 0.0, 10.0, 5.0)
    _select(view, e)
    panel._w.setValue(20.0)
    panel._w.editingFinished.emit()
    x0, _, x1, _ = e.world_bounding_box()
    assert math.isclose(x1 - x0, 20.0, abs_tol=1e-6)


def test_panel_rotation_90(ctx) -> None:
    view, panel = ctx
    e = _add_rect(view, 0.0, 0.0, 10.0, 2.0)
    _select(view, e)
    panel._r.setValue(90.0)
    panel._r.editingFinished.emit()
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x1 - x0, 2.0, abs_tol=1e-6)
    assert math.isclose(y1 - y0, 10.0, abs_tol=1e-6)


def test_panel_disabled_with_multiple_selection(ctx) -> None:
    view, panel = ctx
    a = _add_rect(view, 0.0, 0.0)
    b = _add_rect(view, 50.0, 0.0)
    scene = view.cad_scene
    scene.clearSelection()
    for e in (a, b):
        scene.entity_item(e.id).setSelected(True)
    assert not panel._x.isEnabled()
    assert "2" in panel._type_label.text()


# =====================================================================
# Robustezza (regressioni)
# =====================================================================
def test_detach_is_idempotent(ctx) -> None:
    _, panel = ctx
    panel.detach()
    panel.detach()  # non deve sollevare
    assert panel._detached


def test_callbacks_after_detach_are_safe(ctx) -> None:
    """Dopo detach, le callback non fanno nulla e non sollevano eccezioni."""
    view, panel = ctx
    e = _add_rect(view, 0.0, 0.0)
    _select(view, e)
    panel.detach()
    panel._refresh()
    from lasercontrolsuite.core.document import DocumentEvent
    panel._on_document_event(DocumentEvent("entity_changed", entity_id=e.id))
    assert panel._selected_entities() == []


def test_selected_entities_safe_when_scene_deleted(qapp: QApplication) -> None:
    """Il pannello regge una scena "morta" senza crash.

    Scenari coperti:
      - ``selectedItems()`` solleva ``RuntimeError`` (C++ distrutto).
      - la scena non ha l'attributo ``selectionChanged`` (mock parziale).
      - ``detach()`` non assume nulla sulla forma della scena.
    """
    from lasercontrolsuite.cad.view import CadGraphicsView
    from lasercontrolsuite.ui.panels.property_panel import PropertyPanel

    v = CadGraphicsView()
    v.resize(400, 300)
    panel = PropertyPanel(v)

    class _Dead:
        """Scena finta: nessun segnale, ma metodo che solleva come il C++ morto."""

        def selectedItems(self):
            raise RuntimeError("Internal C++ object (CadScene) already deleted.")

    panel._scene = _Dead()  # type: ignore[assignment]
    assert panel._selected_entities() == []
    panel._refresh()  # non deve sollevare

    # detach() deve essere difensivo: niente selectionChanged, niente segnale
    panel.detach()
    assert panel._detached

    panel.close()
    v.close()