"""Test per ``config.machine`` (puro Python)."""
import pytest

from lasercontrolsuite.config.machine import (
    DEFAULT_MACHINE_NAME,
    DEFAULT_WORK_AREA_MM,
    Machine,
    MachineOrigin,
)


def test_defaults():
    m = Machine(name=DEFAULT_MACHINE_NAME, width_mm=400, height_mm=400)
    assert m.origin is MachineOrigin.BOTTOM_LEFT
    assert m.width_mm == 400
    assert m.height_mm == 400


def test_work_area_bottom_left():
    m = Machine("x", 400, 300, MachineOrigin.BOTTOM_LEFT)
    assert m.work_area_bounds() == (0.0, 0.0, 400.0, 300.0)


def test_work_area_bottom_right():
    m = Machine("x", 400, 300, MachineOrigin.BOTTOM_RIGHT)
    assert m.work_area_bounds() == (-400.0, 0.0, 0.0, 300.0)


def test_work_area_center():
    m = Machine("x", 400, 300, MachineOrigin.CENTER)
    assert m.work_area_bounds() == (-200.0, -150.0, 200.0, 150.0)


def test_origin_point_is_zero():
    m = Machine("x", 100, 100, MachineOrigin.CENTER)
    assert m.origin_point() == (0.0, 0.0)


def test_negative_dimensions_rejected():
    with pytest.raises(ValueError):
        Machine("x", -1, 100)
    with pytest.raises(ValueError):
        Machine("x", 100, 0)


def test_origin_label_italian():
    assert "basso-sinistra" in MachineOrigin.BOTTOM_LEFT.label_it
    assert "basso-destra" in MachineOrigin.BOTTOM_RIGHT.label_it
    assert "Centro" in MachineOrigin.CENTER.label_it


def test_default_work_area_constant():
    assert DEFAULT_WORK_AREA_MM == 400.0