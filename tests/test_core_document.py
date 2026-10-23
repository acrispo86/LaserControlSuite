"""Test del documento."""

from __future__ import annotations

import pytest

from lasercontrolsuite.core.document import Document, DocumentEvent
from lasercontrolsuite.core.entities import PolylineEntity
from lasercontrolsuite.core.layer import Layer


def test_default_layer_exists() -> None:
    doc = Document()
    assert len(doc.layers) == 1
    assert doc.active_layer_id in doc.layers


def test_add_entity_emits_event() -> None:
    doc = Document()
    events: list[DocumentEvent] = []
    doc.subscribe(events.append)

    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)

    assert len(events) == 1
    assert events[0].type == "entity_added"
    assert events[0].entity_id == e.id


def test_remove_entity_emits_event() -> None:
    doc = Document()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)

    events: list[DocumentEvent] = []
    doc.subscribe(events.append)
    doc.remove_entity(e.id)

    assert events[0].type == "entity_removed"
    assert doc.get_entity(e.id) is None


def test_add_duplicate_id_raises() -> None:
    doc = Document()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)
    with pytest.raises(ValueError):
        doc.add_entity(e)


def test_update_transform_emits_event() -> None:
    from lasercontrolsuite.core.matrix import Matrix2D

    doc = Document()
    e = PolylineEntity.line(doc.active_layer_id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)

    events: list[DocumentEvent] = []
    doc.subscribe(events.append)
    doc.update_entity_transform(e.id, Matrix2D.translation(5.0, 0.0))

    assert events[0].type == "entity_changed"
    assert e.transform.almost_equals(Matrix2D.translation(5.0, 0.0))


def test_remove_layer_removes_its_entities() -> None:
    doc = Document()
    layer = Layer.new("Layer 2")
    doc.add_layer(layer)

    e = PolylineEntity.line(layer.id, 0.0, 0.0, 1.0, 0.0)
    doc.add_entity(e)

    doc.remove_layer(layer.id)

    assert doc.get_layer(layer.id) is None
    assert doc.get_entity(e.id) is None