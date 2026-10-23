"""Test di PathEntity e PathNode."""

from __future__ import annotations

import math

from lasercontrolsuite.core.entities import PolylineEntity
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.path import (
    PathEntity,
    PathNode,
    polyline_to_path,
)


# =====================================================================
# PathNode
# =====================================================================
def test_node_is_corner_when_no_handles() -> None:
    n = PathNode(point=(1.0, 2.0))
    assert n.is_corner()
    assert n.abs_handle_in() is None
    assert n.abs_handle_out() is None


def test_node_abs_handles() -> None:
    n = PathNode(point=(10.0, 20.0), handle_in=(-1.0, -2.0), handle_out=(1.0, 2.0))
    assert n.abs_handle_in() == (9.0, 18.0)
    assert n.abs_handle_out() == (11.0, 22.0)


# =====================================================================
# local_points / segmentazione
# =====================================================================
def test_empty_path_has_no_points() -> None:
    p = PathEntity(layer_id="L1")
    assert p.local_points() == []
    assert p.segment_count() == 0


def test_single_node_path() -> None:
    p = PathEntity(layer_id="L1", nodes=[PathNode((5.0, 5.0))])
    assert p.local_points() == [(5.0, 5.0)]
    assert p.segment_count() == 0


def test_two_corner_nodes_is_line() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((10.0, 0.0))],
    )
    pts = p.local_points()
    assert pts[0] == (0.0, 0.0)
    assert pts[-1] == (10.0, 0.0)
    assert len(pts) == 2  # solo endpoints, nessun campione intermedio


def test_two_curved_nodes_samples_curve() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0), handle_out=(1.0, 0.0)),
            PathNode((10.0, 0.0), handle_in=(-1.0, 0.0)),
        ],
    )
    pts = p.local_points()
    assert len(pts) > 2  # campionamento intermedio
    assert pts[0] == (0.0, 0.0)
    assert math.isclose(pts[-1][0], 10.0, abs_tol=1e-6)


def test_closed_path_segment_count() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((1.0, 0.0)), PathNode((0.5, 1.0))],
        closed=True,
    )
    assert p.segment_count() == 3
    assert p.is_closed_path()


def test_open_path_segment_count() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((1.0, 0.0)), PathNode((0.5, 1.0))],
        closed=False,
    )
    assert p.segment_count() == 2
    assert not p.is_closed_path()


def test_mixed_segments_line_and_curve() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0)),
            PathNode((5.0, 0.0), handle_in=(-1.0, 0.0)),  # curva in entrata
            PathNode((10.0, 0.0)),
        ],
    )
    pts = p.local_points()
    # primo segmento è linea: (0,0) → (5,0) direttamente
    # secondo è curva: (5,0) → (10,0) con molti campioni
    assert len(pts) > 3


# =====================================================================
# Snap points
# =====================================================================
def test_snap_points_include_nodes_and_handles() -> None:
    n = PathNode((0.0, 0.0), handle_out=(1.0, 0.0))
    p = PathEntity(layer_id="L1", nodes=[n, PathNode((10.0, 0.0))])
    sp = p.local_snap_points()
    assert (0.0, 0.0) in sp
    assert (1.0, 0.0) in sp  # handle assoluto
    assert (10.0, 0.0) in sp


# =====================================================================
# Transform
# =====================================================================
def test_world_points_respect_transform() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((1.0, 0.0))],
    )
    p.transform = Matrix2D.translation(100.0, 50.0)
    wp = p.world_points()
    assert wp[0] == (100.0, 50.0)
    assert wp[-1] == (101.0, 50.0)


# =====================================================================
# polyline_to_path
# =====================================================================
def test_polyline_to_path_preserves_geometry() -> None:
    poly = PolylineEntity.rect("L1", 0.0, 0.0, 10.0, 5.0)
    path = polyline_to_path(poly)
    assert len(path.nodes) == 4
    assert path.closed is True
    assert path.layer_id == "L1"
    # Tutti i nodi sono corner (nessun handle)
    for node in path.nodes:
        assert node.is_corner()


def test_polyline_to_path_preserves_transform() -> None:
    poly = PolylineEntity.line("L1", 0.0, 0.0, 1.0, 0.0)
    poly.transform = Matrix2D.translation(5.0, 5.0)
    path = polyline_to_path(poly)
    assert path.transform.almost_equals(poly.transform)


# =====================================================================
# Bounding box (ereditato da Entity)
# =====================================================================
def test_path_bounding_box_line() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[PathNode((0.0, 0.0)), PathNode((10.0, 5.0))],
    )
    x0, y0, x1, y1 = p.local_bounding_box()
    assert math.isclose(x0, 0.0, abs_tol=1e-9)
    assert math.isclose(y0, 0.0, abs_tol=1e-9)
    assert math.isclose(x1, 10.0, abs_tol=1e-9)
    assert math.isclose(y1, 5.0, abs_tol=1e-9)


def test_path_bounding_box_curved() -> None:
    p = PathEntity(
        layer_id="L1",
        nodes=[
            PathNode((0.0, 0.0), handle_out=(5.0, 10.0)),
            PathNode((10.0, 0.0), handle_in=(-5.0, 10.0)),
        ],
    )
    x0, y0, x1, y1 = p.local_bounding_box()
    # La curva "sale" sopra il livello dei nodi (y > 0)
    assert y1 > 0.5