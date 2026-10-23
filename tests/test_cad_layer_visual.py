"""Verifica che il colore/visible/locked del layer siano applicati agli item."""
from __future__ import annotations

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import pytest
from PySide6.QtWidgets import QApplication

from lasercontrolsuite.core.entities import PolylineEntity
from lasercontrolsuite.core.layer import Layer


@pytest.fixture(scope="session")
def qapp():
    from lasercontrolsuite.app import get_or_create_qapplication
    return get_or_create_qapplication([])


def test_item_color_follows_layer(qapp):
    from lasercontrolsuite.cad.view import CadGraphicsView
    v = CadGraphicsView()
    doc = v.cad_scene.document
    layer = list(doc.layers.values())[0]
    layer.color = "#FF0000"
    e = PolylineEntity.rect(layer.id, 0.0, 0.0, 1.0, 1.0)
    doc.add_entity(e)
    item = v.cad_scene.entity_item(e.id)
    assert item._layer_color() == "#FF0000"
    v.close()


def test_item_hidden_when_layer_hidden(qapp):
    from lasercontrolsuite.cad.view import CadGraphicsView
    v = CadGraphicsView()
    doc = v.cad_scene.document
    layer = list(doc.layers.values())[0]
    e = PolylineEntity.rect(layer.id, 0.0, 0.0, 1.0, 1.0)
    doc.add_entity(e)
    item = v.cad_scene.entity_item(e.id)
    assert item.isVisible()
    layer.visible = False
    # emette evento layer_changed per forzare refresh
    from lasercontrolsuite.core.document import DocumentEvent
    doc._emit(DocumentEvent("layer_changed", layer_id=layer.id))
    assert not item.isVisible()
    v.close()


def test_item_not_selectable_when_layer_locked(qapp):
    from PySide6.QtWidgets import QGraphicsItem
    from lasercontrolsuite.cad.view import CadGraphicsView
    v = CadGraphicsView()
    doc = v.cad_scene.document
    layer = list(doc.layers.values())[0]
    e = PolylineEntity.rect(layer.id, 0.0, 0.0, 1.0, 1.0)
    doc.add_entity(e)
    item = v.cad_scene.entity_item(e.id)
    assert item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable
    layer.locked = True
    from lasercontrolsuite.core.document import DocumentEvent
    doc._emit(DocumentEvent("layer_changed", layer_id=layer.id))
    assert not (item.flags() & QGraphicsItem.GraphicsItemFlag.ItemIsSelectable)
    v.close()