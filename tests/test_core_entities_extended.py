"""Test delle entità: ellisse, poligono, stella, bézier, testo."""

from __future__ import annotations

import math

from lasercontrolsuite.core.entities import (
    BezierEntity,
    CircleEntity,
    EllipseEntity,
    PolygonEntity,
    PolylineEntity,
    StarEntity,
    TextEntity,
)
from lasercontrolsuite.core.matrix import Matrix2D


# =====================================================================
# Ellipse
# =====================================================================
def test_ellipse_bounding_box() -> None:
    e = EllipseEntity(layer_id="L1", cx=5.0, cy=5.0, rx=3.0, ry=2.0)
    assert e.local_bounding_box() == (2.0, 3.0, 8.0, 7.0)


def test_ellipse_snap_points() -> None:
    e = EllipseEntity(layer_id="L1", cx=0.0, cy=0.0, rx=4.0, ry=2.0)
    sp = e.local_snap_points()
    assert (0.0, 0.0) in sp
    assert (4.0, 0.0) in sp
    assert (-4.0, 0.0) in sp
    assert (0.0, 2.0) in sp
    assert (0.0, -2.0) in sp


# =====================================================================
# Polygon — geometria locale centrata su (0, 0)
# =====================================================================
def test_polygon_sides_minimum() -> None:
    p = PolygonEntity(layer_id="L1", sides=2)
    assert p.sides == 3


def test_polygon_local_points_hexagon() -> None:
    """Il primo vertice è in alto (ore 12), centro locale (0, 0)."""
    p = PolygonEntity(layer_id="L1", radius=1.0, sides=6)
    pts = p.local_points()
    assert len(pts) == 6
    assert math.isclose(pts[0][0], 0.0, abs_tol=1e-9)
    assert math.isclose(pts[0][1], 1.0, abs_tol=1e-9)


def test_polygon_square_is_diamond() -> None:
    """4 lati, vertice in alto → rombo; bbox locale [-r, r]²."""
    p = PolygonEntity(layer_id="L1", radius=1.0, sides=4)
    x0, y0, x1, y1 = p.local_bounding_box()
    assert math.isclose(x0, -1.0, abs_tol=1e-9)
    assert math.isclose(y0, -1.0, abs_tol=1e-9)
    assert math.isclose(x1, 1.0, abs_tol=1e-9)
    assert math.isclose(y1, 1.0, abs_tol=1e-9)


def test_polygon_hexagon_bounding_box() -> None:
    """Esagono vertice in alto: bbox locale largo √3/2·2 in X, 2 in Y."""
    p = PolygonEntity(layer_id="L1", radius=1.0, sides=6)
    x0, y0, x1, y1 = p.local_bounding_box()
    assert math.isclose(x1, math.sqrt(3) / 2.0, abs_tol=1e-9)
    assert math.isclose(y1, 1.0, abs_tol=1e-9)
    assert math.isclose(x0, -math.sqrt(3) / 2.0, abs_tol=1e-9)


def test_polygon_rotation_applied_via_transform() -> None:
    """Ruotando di 45° il rombo, otteniamo un quadrato a lati H/V."""
    p = PolygonEntity(layer_id="L1", radius=1.0, sides=4)
    p.transform = Matrix2D.rotation_deg(45.0)
    x0, y0, x1, y1 = p.world_bounding_box()
    expected = math.sqrt(2) / 2.0
    assert math.isclose(x1, expected, abs_tol=1e-9)
    assert math.isclose(y1, expected, abs_tol=1e-9)
    assert math.isclose(x0, -expected, abs_tol=1e-9)
    assert math.isclose(y0, -expected, abs_tol=1e-9)


def test_polygon_translation_via_transform_moves_center() -> None:
    """Traslazione via transform sposta il centro nel punto desiderato.

    Regressione per il bug del poligono creato fuori posto: la geometria
    locale è centrata su (0, 0), quindi `translation(cx, cy) @ rotation(a)`
    deve posizionare il centro esattamente a (cx, cy).
    """
    p = PolygonEntity(layer_id="L1", radius=10.0, sides=6)
    p.transform = (
        Matrix2D.translation(100.0, 50.0) @ Matrix2D.rotation_deg(30.0)
    )
    x0, y0, x1, y1 = p.world_bounding_box()
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    # Per un esagono regolare, il bbox è simmetrico rispetto al centro
    assert math.isclose(cx, 100.0, abs_tol=1e-9)
    assert math.isclose(cy, 50.0, abs_tol=1e-9)


def test_polygon_snap_points_count() -> None:
    p = PolygonEntity(layer_id="L1", radius=1.0, sides=5)
    sp = p.local_snap_points()
    # 1 centro + 5 vertici + 5 midpoint
    assert len(sp) == 11


def test_polygon_snap_points_center_at_origin() -> None:
    """Il punto di snap "centro" del poligono è in (0, 0) locale."""
    p = PolygonEntity(layer_id="L1", radius=1.0, sides=6)
    assert p.local_snap_points()[0] == (0.0, 0.0)


# =====================================================================
# Star — geometria locale centrata su (0, 0)
# =====================================================================
def test_star_points_minimum() -> None:
    s = StarEntity(layer_id="L1", points=2)
    assert s.points == 3


def test_star_local_points_count() -> None:
    s = StarEntity(layer_id="L1", outer_radius=2.0, inner_radius=1.0, points=5)
    pts = s.local_points()
    assert len(pts) == 10


def test_star_inner_radius_clamped() -> None:
    s = StarEntity(layer_id="L1", outer_radius=2.0, inner_radius=0.0, points=5)
    assert 0.0 < s.inner_radius < s.outer_radius


def test_star_first_point_is_up() -> None:
    s = StarEntity(layer_id="L1", outer_radius=1.0, inner_radius=0.4, points=5)
    pts = s.local_points()
    assert math.isclose(pts[0][0], 0.0, abs_tol=1e-9)
    assert math.isclose(pts[0][1], 1.0, abs_tol=1e-9)


def test_star_alternates_outer_inner() -> None:
    s = StarEntity(layer_id="L1", outer_radius=2.0, inner_radius=1.0, points=5)
    pts = s.local_points()
    for i, (x, y) in enumerate(pts):
        r = math.hypot(x, y)
        expected = 2.0 if i % 2 == 0 else 1.0
        assert math.isclose(r, expected, abs_tol=1e-9)


def test_star_translation_via_transform_moves_center() -> None:
    s = StarEntity(layer_id="L1", outer_radius=10.0, inner_radius=4.0, points=5)
    s.transform = Matrix2D.translation(30.0, 70.0)
    x0, y0, x1, y1 = s.world_bounding_box()
    cx = (x0 + x1) / 2.0
    cy = (y0 + y1) / 2.0
    # Per una stella a 5 punte il bbox non è perfettamente simmetrico,
    # ma il centro deve essere molto vicino al punto (30, 70).
    assert math.isclose(cx, 30.0, abs_tol=1.0)
    assert math.isclose(cy, 70.0, abs_tol=2.0)


# =====================================================================
# Bezier
# =====================================================================
def test_bezier_linear_case() -> None:
    e = BezierEntity(
        layer_id="L1", p0=(0.0, 0.0), p1=(0.0, 0.0), p2=(1.0, 0.0), p3=(1.0, 0.0)
    )
    pts = e.local_points()
    for x, y in pts:
        assert math.isclose(y, 0.0, abs_tol=1e-9)
        assert 0.0 <= x <= 1.0 + 1e-9


def test_bezier_snap_points_are_control_points() -> None:
    e = BezierEntity(
        layer_id="L1", p0=(0.0, 0.0), p1=(1.0, 2.0), p2=(3.0, 2.0), p3=(4.0, 0.0)
    )
    sp = e.local_snap_points()
    assert (0.0, 0.0) in sp
    assert (1.0, 2.0) in sp
    assert (3.0, 2.0) in sp
    assert (4.0, 0.0) in sp


def test_bezier_world_transform() -> None:
    e = BezierEntity(
        layer_id="L1", p0=(0.0, 0.0), p1=(1.0, 0.0), p2=(1.0, 0.0), p3=(2.0, 0.0)
    )
    e.transform = Matrix2D.translation(10.0, 5.0)
    wp = e.world_snap_points()
    assert (10.0, 5.0) in wp
    assert (12.0, 5.0) in wp


def test_bezier_endpoints_are_p0_and_p3() -> None:
    e = BezierEntity(
        layer_id="L1", p0=(1.0, 1.0), p1=(2.0, 3.0), p2=(4.0, 3.0), p3=(5.0, 1.0)
    )
    pts = e.local_points()
    assert math.isclose(pts[0][0], 1.0, abs_tol=1e-9)
    assert math.isclose(pts[-1][0], 5.0, abs_tol=1e-9)


# =====================================================================
# Text
# =====================================================================
def test_text_bounding_box_positive() -> None:
    t = TextEntity(layer_id="L1", text="Hello", font_size_mm=10.0)
    x0, y0, x1, y1 = t.local_bounding_box()
    assert x1 > x0
    assert y1 > y0


def test_text_snap_points_center() -> None:
    t = TextEntity(layer_id="L1", text="Hi", font_size_mm=10.0)
    sp = t.local_snap_points()
    assert len(sp) == 6


def test_text_empty_still_has_bbox() -> None:
    t = TextEntity(layer_id="L1", text="", font_size_mm=10.0)
    x0, y0, x1, y1 = t.local_bounding_box()
    assert x1 > x0
    assert y1 > y0


# =====================================================================
# world_bounding_box — regressioni e proprietà generali
# =====================================================================
def test_world_bbox_equals_local_bbox_when_identity() -> None:
    entities = [
        PolylineEntity.rect("L1", -1.0, -2.0, 3.0, 4.0),
        CircleEntity(layer_id="L1", cx=1.0, cy=1.0, r=2.0),
        EllipseEntity(layer_id="L1", cx=0.0, cy=0.0, rx=3.0, ry=1.0),
        PolygonEntity(layer_id="L1", radius=2.0, sides=6),
        StarEntity(layer_id="L1", outer_radius=2.0, inner_radius=1.0, points=5),
        BezierEntity(
            layer_id="L1",
            p0=(0.0, 0.0),
            p1=(1.0, 2.0),
            p2=(2.0, -1.0),
            p3=(3.0, 0.0),
        ),
        TextEntity(layer_id="L1", text="Test", font_size_mm=5.0),
    ]
    for e in entities:
        lb = e.local_bounding_box()
        wb = e.world_bounding_box()
        assert math.isclose(lb[0], wb[0], abs_tol=1e-9), type(e).__name__
        assert math.isclose(lb[1], wb[1], abs_tol=1e-9), type(e).__name__
        assert math.isclose(lb[2], wb[2], abs_tol=1e-9), type(e).__name__
        assert math.isclose(lb[3], wb[3], abs_tol=1e-9), type(e).__name__


def test_world_bbox_translation_only() -> None:
    e = PolylineEntity.rect("L1", 0.0, 0.0, 10.0, 5.0)
    e.transform = Matrix2D.translation(100.0, -50.0)
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, 100.0, abs_tol=1e-9)
    assert math.isclose(y0, -50.0, abs_tol=1e-9)
    assert math.isclose(x1, 110.0, abs_tol=1e-9)
    assert math.isclose(y1, -45.0, abs_tol=1e-9)


def test_world_bbox_rotation_90_square() -> None:
    e = PolylineEntity.rect("L1", -1.0, -2.0, 2.0, 4.0)
    e.transform = Matrix2D.rotation_deg(90.0)
    x0, y0, x1, y1 = e.world_bounding_box()
    assert math.isclose(x0, -2.0, abs_tol=1e-9)
    assert math.isclose(y0, -1.0, abs_tol=1e-9)
    assert math.isclose(x1, 2.0, abs_tol=1e-9)
    assert math.isclose(y1, 1.0, abs_tol=1e-9)


def test_world_bbox_of_circle_under_rotation() -> None:
    e = CircleEntity(layer_id="L1", cx=0.0, cy=0.0, r=5.0)
    e.transform = Matrix2D.rotation_deg(37.0)
    x0, y0, x1, y1 = e.world_bounding_box()
    assert x0 >= -5.0 - 1e-9
    assert x1 <= 5.0 + 1e-9
    assert y0 >= -5.0 - 1e-9
    assert y1 <= 5.0 + 1e-9
    assert x1 >= 4.9
    assert y1 >= 4.9


def test_world_bbox_strictly_smaller_than_corner_transform() -> None:
    p = PolygonEntity(layer_id="L1", radius=1.0, sides=4)
    p.transform = Matrix2D.rotation_deg(45.0)

    sx0, sy0, sx1, sy1 = p.world_bounding_box()
    strict_width = sx1 - sx0

    lx0, ly0, lx1, ly1 = p.local_bounding_box()
    corners = p.transform.transform_points(
        [(lx0, ly0), (lx1, ly0), (lx1, ly1), (lx0, ly1)]
    )
    xs = [c[0] for c in corners]
    over_width = max(xs) - min(xs)

    assert strict_width < over_width - 1e-6
    assert math.isclose(strict_width, math.sqrt(2.0), abs_tol=1e-9)
    assert math.isclose(over_width, 2.0 * math.sqrt(2.0), abs_tol=1e-9)