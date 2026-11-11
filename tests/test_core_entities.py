"""Test delle entità geometriche."""

from __future__ import annotations

import math
from dataclasses import fields

from lasercontrolsuite.core.entities import (
    BezierEntity,
    CircleEntity,
    EllipseEntity,
    PolylineEntity,
)
from lasercontrolsuite.core.matrix import Matrix2D


def test_polyline_line_factory() -> None:
    e = PolylineEntity.line("L1", 0.0, 0.0, 10.0, 5.0)
    assert e.points == [(0.0, 0.0), (10.0, 5.0)]
    assert e.closed is False
    assert e.layer_id == "L1"


def test_polyline_rect_factory() -> None:
    e = PolylineEntity.rect("L1", 1.0, 2.0, 4.0, 3.0)
    assert e.points == [(1.0, 2.0), (5.0, 2.0), (5.0, 5.0), (1.0, 5.0)]
    assert e.closed is True


def test_world_points_respect_transform() -> None:
    e = PolylineEntity.line("L1", 0.0, 0.0, 1.0, 0.0)
    e.transform = Matrix2D.translation(10.0, 20.0)
    assert e.world_points() == [(10.0, 20.0), (11.0, 20.0)]


def test_snap_points_include_midpoints() -> None:
    e = PolylineEntity.line("L1", 0.0, 0.0, 10.0, 0.0)
    sp = e.local_snap_points()
    # 2 vertici + 1 midpoint
    assert (0.0, 0.0) in sp
    assert (10.0, 0.0) in sp
    assert (5.0, 0.0) in sp


def test_snap_points_closed_polygon() -> None:
    e = PolylineEntity.rect("L1", 0.0, 0.0, 2.0, 2.0)
    sp = e.local_snap_points()
    # 4 vertici + 4 midpoints
    assert len(sp) == 8
    assert (1.0, 0.0) in sp   # midpoint lato inferiore
    assert (0.0, 1.0) in sp   # midpoint lato sinistro


def test_circle_bounding_box() -> None:
    c = CircleEntity(layer_id="L1", cx=5.0, cy=5.0, r=3.0)
    assert c.local_bounding_box() == (2.0, 2.0, 8.0, 8.0)


def test_circle_snap_points() -> None:
    c = CircleEntity(layer_id="L1", cx=0.0, cy=0.0, r=2.0)
    sp = c.local_snap_points()
    assert (0.0, 0.0) in sp
    assert (2.0, 0.0) in sp
    assert (-2.0, 0.0) in sp
    assert (0.0, 2.0) in sp
    assert (0.0, -2.0) in sp


def test_world_bounding_box_after_rotation() -> None:
    # un quadrato ruotato di 45° ha AABB più grande
    e = PolylineEntity.rect("L1", -1.0, -1.0, 2.0, 2.0)
    e.transform = Matrix2D.rotation_deg(45.0)
    x0, y0, x1, y1 = e.world_bounding_box()
    diag = math.sqrt(2.0)
    assert math.isclose(x1 - x0, 2 * diag, rel_tol=1e-9)


# =====================================================================
# Step 9i-c — bug #18: ClassVar[int] per le costanti di campionamento
# =====================================================================
def test_circle_arc_segments_is_classvar() -> None:
    """_ARC_SEGMENTS è ClassVar: non è campo della dataclass, vive sulla classe."""
    field_names = {f.name for f in fields(CircleEntity)}
    assert "_ARC_SEGMENTS" not in field_names
    assert "_ARC_SEGMENTS" in CircleEntity.__dict__
    assert isinstance(CircleEntity._ARC_SEGMENTS, int)

    # Stessa costante sia da classe che da istanza
    c = CircleEntity(layer_id="L1", cx=0.0, cy=0.0, r=1.0)
    assert c._ARC_SEGMENTS == CircleEntity._ARC_SEGMENTS

    # Non finisce in vars(istanza) come attributo proprio
    assert "_ARC_SEGMENTS" not in vars(c)


def test_ellipse_arc_segments_is_classvar() -> None:
    field_names = {f.name for f in fields(EllipseEntity)}
    assert "_ARC_SEGMENTS" not in field_names
    assert "_ARC_SEGMENTS" in EllipseEntity.__dict__
    assert isinstance(EllipseEntity._ARC_SEGMENTS, int)

    e = EllipseEntity(layer_id="L1", cx=0.0, cy=0.0, rx=1.0, ry=2.0)
    assert e._ARC_SEGMENTS == EllipseEntity._ARC_SEGMENTS
    assert "_ARC_SEGMENTS" not in vars(e)


def test_bezier_samples_is_classvar() -> None:
    field_names = {f.name for f in fields(BezierEntity)}
    assert "_SAMPLES" not in field_names
    assert "_SAMPLES" in BezierEntity.__dict__
    assert isinstance(BezierEntity._SAMPLES, int)

    b = BezierEntity(
        layer_id="L1",
        p0=(0.0, 0.0),
        p1=(1.0, 0.0),
        p2=(2.0, 0.0),
        p3=(3.0, 0.0),
    )
    assert b._SAMPLES == BezierEntity._SAMPLES
    assert "_SAMPLES" not in vars(b)