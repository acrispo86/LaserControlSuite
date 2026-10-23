"""Test della matrice affine 2D."""

from __future__ import annotations

import math

import pytest

from lasercontrolsuite.core.matrix import Matrix2D


def test_identity_transforms_point_unchanged() -> None:
    m = Matrix2D.identity()
    assert m.transform_point(3.0, -7.0) == (3.0, -7.0)
    assert m.is_identity()


def test_translation() -> None:
    m = Matrix2D.translation(5.0, -2.0)
    assert m.transform_point(1.0, 1.0) == (6.0, -1.0)


def test_scaling() -> None:
    m = Matrix2D.scaling(2.0, 3.0)
    assert m.transform_point(4.0, 5.0) == (8.0, 15.0)


def test_rotation_90_deg() -> None:
    m = Matrix2D.rotation_deg(90.0)
    x, y = m.transform_point(1.0, 0.0)
    assert math.isclose(x, 0.0, abs_tol=1e-12)
    assert math.isclose(y, 1.0, abs_tol=1e-12)


def test_composition_applies_B_then_A() -> None:
    a = Matrix2D.translation(10.0, 0.0)
    b = Matrix2D.scaling(2.0, 2.0)
    combined = a @ b
    # (a @ b)(p) == a(b(p)) -> (2*3) + 10 = 16
    assert combined.transform_point(3.0, 0.0) == (16.0, 0.0)


def test_inverse_roundtrip() -> None:
    m = Matrix2D.translation(7.0, -3.0) @ Matrix2D.rotation_deg(37.0) @ Matrix2D.scaling(2.0)
    inv = m.inverted()
    x, y = m.transform_point(3.5, -1.25)
    x2, y2 = inv.transform_point(x, y)
    assert math.isclose(x2, 3.5, abs_tol=1e-9)
    assert math.isclose(y2, -1.25, abs_tol=1e-9)


def test_inverse_of_singular_raises() -> None:
    m = Matrix2D.scaling(0.0, 1.0)
    with pytest.raises(ValueError):
        m.inverted()


def test_determinant() -> None:
    m = Matrix2D.scaling(3.0, 4.0)
    assert math.isclose(m.determinant(), 12.0)


def test_transform_points_batch() -> None:
    m = Matrix2D.translation(1.0, 2.0)
    out = m.transform_points([(0.0, 0.0), (1.0, 1.0)])
    assert out == [(1.0, 2.0), (2.0, 3.0)]


def test_almost_equals() -> None:
    a = Matrix2D.translation(1.0, 2.0)
    b = Matrix2D.translation(1.0 + 1e-12, 2.0 - 1e-12)
    assert a.almost_equals(b)