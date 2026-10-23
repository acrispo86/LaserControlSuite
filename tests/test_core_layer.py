"""Test del Layer con priority e normalizzazione."""
from __future__ import annotations

from lasercontrolsuite.core.layer import Layer, SUGGESTED_COLORS


def test_new_defaults():
    l = Layer.new("L1")
    assert l.name == "L1"
    assert l.priority == 0
    assert l.power_percent == 50
    assert l.speed_mm_min == 600.0
    assert l.passes == 1
    assert l.air_assist is False


def test_new_with_priority():
    l = Layer.new("L2", color="#FF0000", priority=3)
    assert l.priority == 3
    assert l.color == "#FF0000"


def test_normalized_clamps():
    l = Layer(name="L", power_percent=200, speed_mm_min=-5.0,
              passes=0, priority=-3)
    n = l.normalized()
    assert n.power_percent == 100
    assert n.speed_mm_min == 1.0
    assert n.passes == 1
    assert n.priority == -3  # priority non viene clampata


def test_suggested_colors_nonempty():
    assert len(SUGGESTED_COLORS) >= 4