"""Test delle operazioni geometriche pure."""

from __future__ import annotations

import math

from lasercontrolsuite.core.entities import PolylineEntity
from lasercontrolsuite.core.matrix import Matrix2D
from lasercontrolsuite.core.operations import (
    AlignMode,
    DistributeMode,
    clone_entity,
    compute_align,
    compute_distribute,
    compute_polar_array,
    nudge_transforms,
    rotation_of,
)


def _rect(layer_id: str, x: float, y: float, w: float = 10.0, h: float = 10.0):
    return PolylineEntity.rect(layer_id, x, y, w, h)


# --------------------------------------------------------------- clone
def test_clone_entity_new_id() -> None:
    e = _rect("L1", 0.0, 0.0)
    c = clone_entity(e)
    assert c.id != e.id
    assert c.points == e.points


# --------------------------------------------------------------- rotation_of
def test_rotation_of_identity() -> None:
    assert abs(rotation_of(Matrix2D.identity())) < 1e-9


def test_rotation_of_90_deg() -> None:
    assert math.isclose(
        math.degrees(rotation_of(Matrix2D.rotation_deg(90.0))), 90.0, abs_tol=1e-9
    )


# --------------------------------------------------------------- align
def test_align_left() -> None:
    a = _rect("L1", 0.0, 0.0)
    b = _rect("L1", 100.0, 50.0)
    result = compute_align([a, b], AlignMode.LEFT)
    # b deve spostarsi a X=0
    assert b.id in result
    new_b = result[b.id]
    x0, _, _, _ = _apply(b, new_b)
    assert math.isclose(x0, 0.0, abs_tol=1e-9)


def test_align_right() -> None:
    a = _rect("L1", 0.0, 0.0)
    b = _rect("L1", 50.0, 0.0)
    result = compute_align([a, b], AlignMode.RIGHT)
    assert a.id in result
    _, _, new_a_x1, _ = _apply(a, result[a.id])
    _, _, b_x1, _ = b.world_bounding_box()
    assert math.isclose(new_a_x1, b_x1, abs_tol=1e-9)


def test_align_top_and_bottom() -> None:
    a = _rect("L1", 0.0, 0.0)
    b = _rect("L1", 50.0, 100.0)
    top_result = compute_align([a, b], AlignMode.TOP)
    new_a_y1 = _apply(a, top_result[a.id])[3]
    assert math.isclose(new_a_y1, 110.0, abs_tol=1e-9)

    bot_result = compute_align([a, b], AlignMode.BOTTOM)
    new_b_y0 = _apply(b, bot_result[b.id])[1]
    assert math.isclose(new_b_y0, 0.0, abs_tol=1e-9)


def test_align_center_h_uses_union_bbox() -> None:
    a = _rect("L1", 0.0, 0.0, 10.0, 10.0)
    b = _rect("L1", 100.0, 0.0, 10.0, 10.0)
    result = compute_align([a, b], AlignMode.CENTER_H)
    cx_a = (_apply(a, result[a.id])[0] + _apply(a, result[a.id])[2]) / 2.0
    cx_b = (_apply(b, result[b.id])[0] + _apply(b, result[b.id])[2]) / 2.0
    assert math.isclose(cx_a, cx_b, abs_tol=1e-9)
    assert math.isclose(cx_a, 55.0, abs_tol=1e-9)


def test_align_no_op_with_one_entity() -> None:
    a = _rect("L1", 0.0, 0.0)
    assert compute_align([a], AlignMode.LEFT) == {}


# --------------------------------------------------------------- distribute
def test_distribute_horizontal_centers() -> None:
    a = _rect("L1", 0.0, 0.0, 10.0, 10.0)
    b = _rect("L1", 30.0, 0.0, 10.0, 10.0)
    c = _rect("L1", 100.0, 0.0, 10.0, 10.0)
    result = compute_distribute([a, b, c], DistributeMode.HORIZONTAL)
    # a e c restano fermi, b va a metà
    centers = []
    for e in (a, b, c):
        t = result.get(e.id, e.transform)
        bb = _apply(e, t)
        centers.append((bb[0] + bb[2]) / 2.0)
    # a=5, c=105, b=55
    assert math.isclose(centers[0], 5.0, abs_tol=1e-9)
    assert math.isclose(centers[1], 55.0, abs_tol=1e-9)
    assert math.isclose(centers[2], 105.0, abs_tol=1e-9)


def test_distribute_returns_empty_with_two() -> None:
    a = _rect("L1", 0.0, 0.0)
    b = _rect("L1", 10.0, 0.0)
    assert compute_distribute([a, b], DistributeMode.HORIZONTAL) == {}


# --------------------------------------------------------------- nudge
def test_nudge_transforms() -> None:
    a = _rect("L1", 0.0, 0.0)
    result = nudge_transforms([a], 5.0, -3.0)
    new_t = result[a.id]
    x0, y0, _, _ = _apply(a, new_t)
    assert math.isclose(x0, 5.0, abs_tol=1e-9)
    assert math.isclose(y0, -3.0, abs_tol=1e-9)


def test_nudge_zero_returns_empty() -> None:
    a = _rect("L1", 0.0, 0.0)
    assert nudge_transforms([a], 0.0, 0.0) == {}


# --------------------------------------------------------------- polar array
def test_polar_array_basic() -> None:
    a = _rect("L1", 10.0, 0.0, 10.0, 10.0)  # centro (15, 5)
    result = compute_polar_array(
        [a],
        center=(0.0, 0.0),
        count=4,
        total_angle_deg=360.0,
        start_angle_deg=0.0,
        include_original=True,
    )
    assert len(result) == 3  # 4 totali, 1 originale
    # controlla il centro del primo clone: dovrebbe essere ruotato di 90°
    # originale centro (15,5) -> ruotato di 90° attorno a (0,0) -> (-5,15)
    bb = result[0].world_bounding_box()
    cx = (bb[0] + bb[2]) / 2.0
    cy = (bb[1] + bb[3]) / 2.0
    assert math.isclose(cx, -5.0, abs_tol=1e-6)
    assert math.isclose(cy, 15.0, abs_tol=1e-6)


def test_polar_array_partial_angle() -> None:
    a = _rect("L1", 10.0, 0.0, 10.0, 10.0) # centro (15,5)
    result = compute_polar_array(
        [a],
        center=(0.0, 0.0),
        count=3,
        total_angle_deg=90.0,
        start_angle_deg=0.0,
        include_original=True,
    )
    assert len(result) == 2
    # passo = 90 / (3-1) = 45°
    # primo clone ruotato di 45°
    bb = result[0].world_bounding_box()
    cx = (bb[0] + bb[2]) / 2.0
    cy = (bb[1] + bb[3]) / 2.0
    # (15,5) ruotato di 45°: x = 15*cos45 - 5*sin45 = (15-5)*0.707 = 7.07; y = 15*sin45 + 5*cos45 = (15+5)*0.707 = 14.14
    rad = math.radians(45)
    expected_x = 15*math.cos(rad) - 5*math.sin(rad)
    expected_y = 15*math.sin(rad) + 5*math.cos(rad)
    assert math.isclose(cx, expected_x, abs_tol=1e-6)
    assert math.isclose(cy, expected_y, abs_tol=1e-6)


def test_polar_array_without_rotation() -> None:
    a = _rect("L1", 10.0, 0.0, 10.0, 10.0) # centro (15,5)
    result = compute_polar_array(
        [a],
        center=(0.0, 0.0),
        count=4,
        total_angle_deg=360.0,
        rotate_copies=False,
    )
    assert len(result) == 3
    # Il clone non è ruotato, ma traslato. Il centro del clone dovrebbe essere ruotato di 90°.
    # originale centro (15,5). Ruotato di 90° -> (-5,15).
    # La traslazione applicata è ( -5 - 15, 15 - 5 ) = (-20, 10).
    # La bbox del clone sarà quella originale spostata di (-20, 10).
    # bbox originale: (10,0) a (20,10). Centro (15,5). Dopo traslazione: (-10,10) a (0,20). Centro (-5,15).
    bb = result[0].world_bounding_box()
    cx = (bb[0] + bb[2]) / 2.0
    cy = (bb[1] + bb[3]) / 2.0
    assert math.isclose(cx, -5.0, abs_tol=1e-6)
    assert math.isclose(cy, 15.0, abs_tol=1e-6)


# --------------------------------------------------------------- helpers
def _apply(entity, transform: Matrix2D) -> tuple[float, float, float, float]:
    """Simula l'applicazione della nuova transform e restituisce il bbox."""
    saved = entity.transform
    try:
        entity.transform = transform
        return entity.world_bounding_box()
    finally:
        entity.transform = saved