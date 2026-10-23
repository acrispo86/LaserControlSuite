"""Test delle funzioni pure di path editing."""

from __future__ import annotations

import math

import pytest

from lasercontrolsuite.core.entities import (
    BezierEntity,
    CircleEntity,
    EllipseEntity,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
    TextEntity,
)
from lasercontrolsuite.core.path import PathEntity, PathNode
from lasercontrolsuite.core.path_edit import (
    HandleKind,
    add_node_at_segment,
    curve_line_segment_through_point,
    entity_to_path,
    find_nearest_handle,
    find_nearest_node,
    find_nearest_segment,
    is_smooth_node,
    move_handle,
    move_node,
    remove_node_at,
    set_node_corner,
    set_node_smooth,
    translate_curve_segment,
)


def _triangle_path() -> PathEntity:
    return PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0)),
            PathNode((10.0, 0.0)),
            PathNode((5.0, 8.0)),
        ],
        closed=False,
    )


def _curved_path() -> PathEntity:
    return PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0), handle_out=(2.0, 0.0)),
            PathNode((10.0, 0.0), handle_in=(-2.0, 0.0)),
        ],
        closed=False,
    )


# =====================================================================
# Hit test
# =====================================================================
def test_find_nearest_node_exact() -> None:
    p = _triangle_path()
    hit = find_nearest_node(p, (10.0, 0.0), tolerance=0.5)
    assert hit is not None
    assert hit.index == 1


def test_find_nearest_node_out_of_tolerance() -> None:
    p = _triangle_path()
    hit = find_nearest_node(p, (100.0, 100.0), tolerance=1.0)
    assert hit is None


def test_find_nearest_handle_none_when_corners() -> None:
    p = _triangle_path()
    assert find_nearest_handle(p, (0.0, 0.0), tolerance=2.0) is None


def test_find_nearest_handle_out() -> None:
    p = _curved_path()
    hit = find_nearest_handle(p, (2.0, 0.0), tolerance=1.0)
    assert hit is not None
    assert hit.node_index == 0
    assert hit.kind is HandleKind.OUT


def test_find_nearest_handle_in() -> None:
    p = _curved_path()
    hit = find_nearest_handle(p, (8.0, 0.0), tolerance=1.0)
    assert hit is not None
    assert hit.node_index == 1
    assert hit.kind is HandleKind.IN


def test_find_nearest_segment_line() -> None:
    p = _triangle_path()
    hit = find_nearest_segment(p, (5.0, 0.1), tolerance=0.5)
    assert hit is not None
    assert hit.segment_index == 0
    assert math.isclose(hit.t, 0.5, abs_tol=0.05)
    assert math.isclose(hit.point[0], 5.0, abs_tol=0.1)
    assert math.isclose(hit.point[1], 0.0, abs_tol=0.1)


def test_find_nearest_segment_curve() -> None:
    p = _curved_path()
    hit = find_nearest_segment(p, (5.0, 0.0), tolerance=1.0)
    assert hit is not None
    assert hit.segment_index == 0
    assert 0.4 <= hit.t <= 0.6


# =====================================================================
# add_node_at_segment
# =====================================================================
def test_add_node_on_line_splits_into_corner() -> None:
    p = _triangle_path()
    new_i = add_node_at_segment(p, 0, 0.5)
    assert new_i == 1
    assert len(p.nodes) == 4
    assert math.isclose(p.nodes[1].point[0], 5.0, abs_tol=1e-6)
    assert math.isclose(p.nodes[1].point[1], 0.0, abs_tol=1e-6)
    assert p.nodes[1].is_corner()


def test_add_node_on_curve_preserves_shape() -> None:
    p = _curved_path()
    before = p.local_points()
    add_node_at_segment(p, 0, 0.5)
    after = p.local_points()
    assert len(p.nodes) == 3
    assert math.isclose(before[0][0], after[0][0], abs_tol=1e-6)
    assert math.isclose(before[-1][0], after[-1][0], abs_tol=1e-6)


def test_add_node_index_out_of_range() -> None:
    p = _triangle_path()
    with pytest.raises(IndexError):
        add_node_at_segment(p, 10, 0.5)


# =====================================================================
# remove_node_at
# =====================================================================
def test_remove_node() -> None:
    p = _triangle_path()
    remove_node_at(p, 1)
    assert len(p.nodes) == 2


def test_remove_node_keeps_at_least_two() -> None:
    p = PathEntity(layer_id="L1", nodes=[PathNode((0, 0)), PathNode((1, 0))])
    remove_node_at(p, 0)
    assert len(p.nodes) == 2


# =====================================================================
# corner / smooth
# =====================================================================
def test_set_node_corner_removes_handles() -> None:
    p = _curved_path()
    set_node_corner(p, 0)
    assert p.nodes[0].is_corner()


def test_set_node_smooth_from_corner_creates_handles() -> None:
    p = _triangle_path()
    set_node_smooth(p, 1)
    assert p.nodes[1].handle_in is not None
    assert p.nodes[1].handle_out is not None
    assert is_smooth_node(p.nodes[1])


def test_is_smooth_node_detects_non_symmetric() -> None:
    n = PathNode(point=(0.0, 0.0), handle_in=(-1.0, 0.0), handle_out=(2.0, 0.0))
    assert not is_smooth_node(n)


# =====================================================================
# move
# =====================================================================
def test_move_node_shifts_handles_with_it() -> None:
    p = _curved_path()
    move_node(p, 0, 5.0, 5.0)
    assert math.isclose(p.nodes[0].point[0], 5.0, abs_tol=1e-9)
    assert math.isclose(p.nodes[0].point[1], 5.0, abs_tol=1e-9)
    h = p.nodes[0].abs_handle_out()
    assert h is not None
    assert math.isclose(h[0], 7.0, abs_tol=1e-9)
    assert math.isclose(h[1], 5.0, abs_tol=1e-9)


def test_move_handle_symmetric_updates_other() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0), handle_in=(-2.0, 0.0), handle_out=(2.0, 0.0)),
            PathNode((10.0, 0.0)),
        ],
    )
    move_handle(p, 0, HandleKind.OUT, (3.0, 3.0), symmetric=True)
    assert p.nodes[0].handle_out == (3.0, 3.0)
    assert p.nodes[0].handle_in == (-3.0, -3.0)


def test_move_handle_non_symmetric_keeps_other() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0), handle_in=(-2.0, 0.0), handle_out=(2.0, 0.0)),
            PathNode((10.0, 0.0)),
        ],
    )
    move_handle(p, 0, HandleKind.OUT, (3.0, 3.0), symmetric=False)
    assert p.nodes[0].handle_out == (3.0, 3.0)
    assert p.nodes[0].handle_in == (-2.0, 0.0)


# =====================================================================
# curve_line_segment_through_point
# =====================================================================
def test_curve_line_segment_through_point_bends_line() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((10.0, 0.0))],
    )
    ok = curve_line_segment_through_point(p, 0, (5.0, 3.0))
    assert ok is True
    assert p.nodes[0].handle_out is not None
    assert p.nodes[1].handle_in is not None

    pts = p.local_points()
    mid = pts[len(pts) // 2]
    assert math.isclose(mid[0], 5.0, abs_tol=0.05)
    assert math.isclose(mid[1], 3.0, abs_tol=0.05)


def test_curve_line_segment_no_op_when_projection_zero() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((10.0, 0.0))],
    )
    ok = curve_line_segment_through_point(p, 0, (7.0, 0.0))
    assert ok is False
    assert p.nodes[0].is_corner()
    assert p.nodes[1].is_corner()


def test_curve_line_segment_returns_false_on_curve() -> None:
    p = _curved_path()
    ok = curve_line_segment_through_point(p, 0, (5.0, 3.0))
    assert ok is False


def test_curve_line_segment_invalid_index() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((10.0, 0.0))],
    )
    ok = curve_line_segment_through_point(p, 5, (5.0, 3.0))
    assert ok is False


# =====================================================================
# translate_curve_segment
# =====================================================================
def test_translate_curve_segment_shifts_handles() -> None:
    p = _curved_path()
    ok = translate_curve_segment(p, 0, 1.0, 2.0)
    assert ok is True
    assert math.isclose(p.nodes[0].handle_out[0], 3.0, abs_tol=1e-9)
    assert math.isclose(p.nodes[0].handle_out[1], 2.0, abs_tol=1e-9)
    assert math.isclose(p.nodes[1].handle_in[0], -1.0, abs_tol=1e-9)
    assert math.isclose(p.nodes[1].handle_in[1], 2.0, abs_tol=1e-9)


def test_translate_curve_segment_no_op_on_line() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((10.0, 0.0))],
    )
    ok = translate_curve_segment(p, 0, 1.0, 2.0)
    assert ok is False


# =====================================================================
# entity_to_path
# =====================================================================
def test_entity_to_path_preserves_path() -> None:
    """Un PathEntity ritorna se stesso."""
    p = _triangle_path()
    assert entity_to_path(p) is p


def test_entity_to_path_from_polyline() -> None:
    poly = PolylineEntity.rect("L1", 0.0, 0.0, 10.0, 5.0)
    path = entity_to_path(poly)
    assert path is not None
    assert isinstance(path, PathEntity)
    assert len(path.nodes) == 4
    assert path.closed is True
    assert path.id == poly.id
    assert path.layer_id == poly.layer_id
    for node in path.nodes:
        assert node.is_corner()


def test_entity_to_path_from_circle() -> None:
    c = CircleEntity(layer_id="L1", cx=0.0, cy=0.0, r=5.0)
    path = entity_to_path(c)
    assert path is not None
    assert path.closed is True
    assert len(path.nodes) == c._ARC_SEGMENTS
    assert path.id == c.id


def test_entity_to_path_from_ellipse() -> None:
    e = EllipseEntity(layer_id="L1", cx=0.0, cy=0.0, rx=5.0, ry=3.0)
    path = entity_to_path(e)
    assert path is not None
    assert path.closed is True
    assert len(path.nodes) == e._ARC_SEGMENTS


def test_entity_to_path_from_polygon() -> None:
    p = PolygonEntity(layer_id="L1", radius=5.0, sides=6)
    path = entity_to_path(p)
    assert path is not None
    assert path.closed is True
    assert len(path.nodes) == 6


def test_entity_to_path_from_star() -> None:
    s = StarEntity(layer_id="L1", outer_radius=5.0, inner_radius=2.0, points=5)
    path = entity_to_path(s)
    assert path is not None
    assert path.closed is True
    assert len(path.nodes) == 10


def test_entity_to_path_from_bezier() -> None:
    b = BezierEntity(
        layer_id="L1",
        p0=(0.0, 0.0),
        p1=(1.0, 2.0),
        p2=(3.0, 2.0),
        p3=(4.0, 0.0),
    )
    path = entity_to_path(b)
    assert path is not None
    assert len(path.nodes) == 2
    assert path.closed is False
    n0 = path.nodes[0]
    n1 = path.nodes[1]
    assert n0.handle_out is not None
    assert n1.handle_in is not None


def test_entity_to_path_from_text_returns_none() -> None:
    t = TextEntity(layer_id="L1", text="Hello")
    assert entity_to_path(t) is None


def test_entity_to_path_preserves_transform() -> None:
    from lasercontrolsuite.core.matrix import Matrix2D

    poly = PolylineEntity.rect("L1", 0.0, 0.0, 1.0, 1.0)
    poly.transform = Matrix2D.translation(10.0, 20.0)
    path = entity_to_path(poly)
    assert path is not None
    assert path.transform.almost_equals(poly.transform)