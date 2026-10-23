"""Test dell'appiattimento entità → polilinee mondo."""

from __future__ import annotations

import math

from lasercontrolsuite.cam.flatten import (
    FlatPath,
    flatten_document,
    flatten_entity,
)
from lasercontrolsuite.core.document import Document
from lasercontrolsuite.core.entities import (
    CircleEntity,
    EllipseEntity,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
)
from lasercontrolsuite.core.layer import Layer
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import PathEntity, PathNode


# =====================================================================
# flatten_entity — tipi
# =====================================================================
def test_flatten_polyline() -> None:
    e = PolylineEntity.rect("L1", 0.0, 0.0, 10.0, 5.0)
    paths = flatten_entity(e)
    assert len(paths) == 1
    assert paths[0].closed is True
    assert paths[0].entity_id == e.id


def test_flatten_polyline_applies_transform() -> None:
    e = PolylineEntity.rect("L1", 0.0, 0.0, 10.0, 5.0)
    e.transform = Matrix2D.translation(100.0, 200.0)
    paths = flatten_entity(e)
    xs = [p[0] for p in paths[0].points]
    ys = [p[1] for p in paths[0].points]
    assert min(xs) == 100.0
    assert max(xs) == 110.0
    assert min(ys) == 200.0
    assert max(ys) == 205.0


def test_flatten_circle() -> None:
    e = CircleEntity(layer_id="L1", cx=0.0, cy=0.0, r=10.0)
    paths = flatten_entity(e)
    assert len(paths) == 1
    assert paths[0].closed is True
    assert len(paths[0].points) >= 32


def test_flatten_ellipse() -> None:
    e = EllipseEntity(layer_id="L1", cx=0.0, cy=0.0, rx=10.0, ry=5.0)
    paths = flatten_entity(e)
    assert paths[0].closed is True


def test_flatten_polygon() -> None:
    e = PolygonEntity(layer_id="L1", radius=10.0, sides=6)
    paths = flatten_entity(e)
    assert paths[0].closed is True
    assert len(paths[0].points) == 6


def test_flatten_star() -> None:
    e = StarEntity(layer_id="L1", outer_radius=10.0, inner_radius=4.0, points=5)
    paths = flatten_entity(e)
    assert paths[0].closed is True
    assert len(paths[0].points) == 10


def test_flatten_path_entity() -> None:
    e = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((10.0, 0.0)), PathNode((10.0, 10.0))],
    )
    paths = flatten_entity(e)
    assert len(paths) == 1
    assert paths[0].closed is False


# =====================================================================
# flatten_entity — visibilità
# =====================================================================
def test_flatten_invisible_entity_returns_empty() -> None:
    """Default: entità invisibili saltate."""
    e = PolylineEntity.rect("L1", 0.0, 0.0, 1.0, 1.0)
    e.visible = False
    assert flatten_entity(e) == []


def test_flatten_entity_include_hidden_flag() -> None:
    """Con ``include_hidden=True`` anche le entità invisibili vengono appiattite."""
    e = PolylineEntity.rect("L1", 0.0, 0.0, 1.0, 1.0)
    e.visible = False
    paths = flatten_entity(e, include_hidden=True)
    assert len(paths) == 1
    assert paths[0].entity_id == e.id


# =====================================================================
# flatten_document — visibilità
# =====================================================================
def test_flatten_document_skips_hidden() -> None:
    doc = Document()
    a = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 10.0, 5.0)
    b = PolylineEntity.rect(doc.active_layer_id, 20.0, 20.0, 5.0, 5.0)
    b.visible = False
    doc.add_entity(a)
    doc.add_entity(b)
    paths = flatten_document(doc)
    assert len(paths) == 1
    assert paths[0].entity_id == a.id


def test_flatten_document_include_hidden() -> None:
    """Con ``include_hidden=True`` anche le entità nascoste vengono appiattite.

    Regressione: prima c'era un doppio filtro sulla visibilità (in
    ``flatten_document`` *e* in ``flatten_entity``), quindi ``include_hidden``
    non aveva effetto. Ora il flag viene passato anche a ``flatten_entity``.
    """
    doc = Document()
    a = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 1.0, 1.0)
    a.visible = False
    doc.add_entity(a)
    assert flatten_document(doc) == []
    paths = flatten_document(doc, include_hidden=True)
    assert len(paths) == 1
    assert paths[0].entity_id == a.id


def test_flatten_document_mixed_visibility() -> None:
    """Con ``include_hidden=True`` visibili + nascoste vanno tutte appiattite."""
    doc = Document()
    a = PolylineEntity.rect(doc.active_layer_id, 0.0, 0.0, 1.0, 1.0)
    b = PolylineEntity.rect(doc.active_layer_id, 10.0, 0.0, 1.0, 1.0)
    b.visible = False
    doc.add_entity(a)
    doc.add_entity(b)

    assert len(flatten_document(doc)) == 1
    assert len(flatten_document(doc, include_hidden=True)) == 2


# =====================================================================
# Step 9c — layer_id propagato nei FlatPath
# =====================================================================
def test_flatten_entity_propagates_layer_id():
    layer = Layer.new("L1")
    e = PolylineEntity.rect(layer.id, 0.0, 0.0, 10.0, 5.0)
    e.layer_id = layer.id
    paths = flatten_entity(e)
    assert len(paths) == 1
    assert paths[0].layer_id == layer.id


def test_flatten_document_paths_carry_layer_id():
    doc = Document()
    layer_a = Layer.new("A")
    layer_b = Layer.new("B")
    doc.add_layer(layer_a)
    doc.add_layer(layer_b)

    e_a = PolylineEntity.rect(layer_a.id, 0.0, 0.0, 1.0, 1.0)
    e_b = PolylineEntity.rect(layer_b.id, 10.0, 0.0, 1.0, 1.0)
    e_a.layer_id = layer_a.id
    e_b.layer_id = layer_b.id
    doc.add_entity(e_a)
    doc.add_entity(e_b)

    paths = flatten_document(doc)
    layers = sorted({p.layer_id for p in paths})
    assert layers == sorted([layer_a.id, layer_b.id])