"""Test dei parametri CAM."""

from __future__ import annotations

from lasercontrolsuite.cam.params import CutParams, LaserMode


def test_s_value_default() -> None:
    p = CutParams(power_percent=50, s_max=1000)
    assert p.s_value() == 500


def test_s_value_max() -> None:
    p = CutParams(power_percent=100, s_max=1000)
    assert p.s_value() == 1000


def test_s_value_clamped() -> None:
    assert CutParams(power_percent=150, s_max=1000).s_value() == 1000
    assert CutParams(power_percent=-50, s_max=1000).s_value() == 0


def test_s_value_small_s_max() -> None:
    p = CutParams(power_percent=50, s_max=255)
    # 0.5 * 255 = 127.5 → 128
    assert p.s_value() in (127, 128)


def test_normalized_clamps_values() -> None:
    p = CutParams(feed_mm_min=-10, power_percent=200, passes=0, s_max=-5)
    n = p.normalized()
    assert n.feed_mm_min >= 1.0
    assert n.power_percent == 100.0
    assert n.passes == 1
    assert n.s_max >= 1


def test_laser_mode_default_is_m4() -> None:
    assert CutParams().laser_mode is LaserMode.M4


def test_normalized_accepts_string_laser_mode() -> None:
    p = CutParams(laser_mode="M3")  # type: ignore[arg-type]
    n = p.normalized()
    assert n.laser_mode is LaserMode.M3

# =====================================================================
# Step 9c — GlobalParams + from_layer
# =====================================================================
from lasercontrolsuite.cam.params import GlobalParams
from lasercontrolsuite.core.layer import Layer


def test_global_params_defaults():
    g = GlobalParams()
    assert g.s_max == 1000
    assert g.laser_mode == LaserMode.M4
    assert g.travel_home is True


def test_global_params_normalized():
    g = GlobalParams(s_max=0, travel_feed_mm_min=-5.0)
    n = g.normalized()
    assert n.s_max == 1
    assert n.travel_feed_mm_min == 0.0


def test_cutparams_from_layer():
    layer = Layer(name="Cut", speed_mm_min=1200.0, power_percent=75,
                  passes=3, air_assist=True)
    g = GlobalParams(s_max=2000, laser_mode=LaserMode.M3, travel_home=False)
    cut = CutParams.from_layer(layer, g)
    assert cut.feed_mm_min == 1200.0
    assert cut.power_percent == 75.0
    assert cut.passes == 3
    assert cut.air_assist is True
    assert cut.s_max == 2000
    assert cut.laser_mode == LaserMode.M3
    assert cut.travel_home is False
    assert cut.layer_id == layer.id
    assert cut.layer_name == "Cut"