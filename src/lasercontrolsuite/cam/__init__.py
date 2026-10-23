"""Motore CAM: generazione G-code dai documenti.

API principale:
    from lasercontrolsuite.cam import CutParams, generate_gcode
    params = CutParams(feed=1200, power_percent=60, passes=2)
    result = generate_gcode(document, params)
    print(result.gcode)

Il modulo è **puro Python**: nessuna dipendenza da Qt o da hardware.
"""

from __future__ import annotations

from lasercontrolsuite.cam.gcode import GCodeResult, generate_gcode
from lasercontrolsuite.cam.order import order_paths
from lasercontrolsuite.cam.params import CutParams, GlobalParams, LaserMode
from lasercontrolsuite.cam.preview import (
    PreviewPath,
    PreviewScene,
    build_preview,
)
from lasercontrolsuite.cam.stats import GCodeStats, estimate_stats

__all__ = [
    "CutParams",
    "GlobalParams"
    "LaserMode",
    "GCodeResult",
    "generate_gcode",
    "order_paths",
    "PreviewPath",
    "PreviewScene",
    "build_preview",
    "GCodeStats",
    "estimate_stats",
]