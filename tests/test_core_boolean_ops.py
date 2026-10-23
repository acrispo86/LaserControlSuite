"""Test delle operazioni booleane su path (Step 9f)."""
from __future__ import annotations

import pytest

from lasercontrolsuite.core.boolean_ops import BooleanMode, boolean_operation
from lasercontrolsuite.core.entities import CircleEntity, PolylineEntity
from lasercontrolsuite.core.path import PathEntity, PathNode


def _rect(x, y, w, h):
    return PolylineEntity.rect("L1", x, y, w, h)


def test_union_two_overlapping_rects():
    a = _rect(0, 0, 10, 10)
    b = _rect(5, 0, 10, 10)
    paths, warnings = boolean_operation([a, b], BooleanMode.UNION)
    assert len(paths) == 1  # un solo poligono risultante
    assert not warnings
    path = paths[0]
    xs = [n.point[0] for n in path.nodes]
    ys = [n.point[1] for n in path.nodes]
    assert min(xs) == pytest.approx(0.0)
    assert max(xs) == pytest.approx(15.0)
    assert min(ys) == pytest.approx(0.0)
    assert max(ys) == pytest.approx(10.0)


def test_difference_rect_minus_rect():
    a = _rect(0, 0, 10, 10)
    b = _rect(2, 2, 5, 5)
    paths, warnings = boolean_operation([a, b], BooleanMode.DIFFERENCE)
    assert len(paths) == 2  # anello esterno + foro
    assert not warnings
    outer = paths[0]
    inner = paths[1]
    xs_outer = [n.point[0] for n in outer.nodes]
    ys_outer = [n.point[1] for n in outer.nodes]
    assert min(xs_outer) == pytest.approx(0.0)
    assert max(xs_outer) == pytest.approx(10.0)
    xs_inner = [n.point[0] for n in inner.nodes]
    ys_inner = [n.point[1] for n in inner.nodes]
    assert min(xs_inner) == pytest.approx(2.0)
    assert max(xs_inner) == pytest.approx(7.0)


def test_intersection_two_rects():
    a = _rect(0, 0, 10, 10)
    b = _rect(5, 0, 10, 10)
    paths, warnings = boolean_operation([a, b], BooleanMode.INTERSECTION)
    assert len(paths) == 1
    assert not warnings
    path = paths[0]
    xs = [n.point[0] for n in path.nodes]
    ys = [n.point[1] for n in path.nodes]
    assert min(xs) == pytest.approx(5.0)
    assert max(xs) == pytest.approx(10.0)
    assert min(ys) == pytest.approx(0.0)
    assert max(ys) == pytest.approx(10.0)


def test_intersection_empty():
    a = _rect(0, 0, 10, 10)
    b = _rect(20, 0, 10, 10)
    paths, warnings = boolean_operation([a, b], BooleanMode.INTERSECTION)
    assert paths == []
    assert "Il risultato dell'operazione è vuoto." in warnings


def test_difference_with_open_path_warning():
    a = _rect(0, 0, 10, 10)
    b = PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0)),
            PathNode((5.0, 0.0)),
            PathNode((5.0, 5.0)),
        ],
        closed=False,
    )
    paths, warnings = boolean_operation([a, b], BooleanMode.UNION)
    assert len(paths) == 1
    assert any("Path aperto chiuso automaticamente" in w for w in warnings)


def test_non_convertible_entity_warning():
    from lasercontrolsuite.core.entities import TextEntity

    a = _rect(0, 0, 10, 10)
    t = TextEntity(layer_id="L1", text="Hello")
    paths, warnings = boolean_operation([a, t], BooleanMode.UNION)
    assert paths == []
    assert any("Entità non convertibile" in w for w in warnings)


def test_less_than_two_entities():
    a = _rect(0, 0, 10, 10)
    paths, warnings = boolean_operation([a], BooleanMode.UNION)
    assert paths == []
    assert any("almeno due entità" in w for w in warnings)