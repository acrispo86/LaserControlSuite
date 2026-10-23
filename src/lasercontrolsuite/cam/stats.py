"""Statistiche del lavoro CAM: lunghezze, tempi stimati."""

from __future__ import annotations

import math
from dataclasses import dataclass

from lasercontrolsuite.cam.flatten import FlatPath
from lasercontrolsuite.cam.params import CutParams


@dataclass
class GCodeStats:
    """Statistiche stimate sul lavoro."""

    n_paths: int = 0
    cut_length_mm: float = 0.0
    travel_length_mm: float = 0.0
    n_gcode_lines: int = 0
    n_passes: int = 1
    estimated_cut_seconds: float = 0.0
    estimated_travel_seconds: float = 0.0

    @property
    def estimated_total_seconds(self) -> float:
        return self.estimated_cut_seconds + self.estimated_travel_seconds

    def estimated_cut_time_str(self) -> str:
        return _fmt_time(self.estimated_cut_seconds)

    def estimated_total_time_str(self) -> str:
        return _fmt_time(self.estimated_total_seconds)


def _fmt_time(sec: float) -> str:
    if sec < 60:
        return f"{sec:.1f} s"
    m = int(sec // 60)
    s = int(sec % 60)
    if m < 60:
        return f"{m} min {s} s"
    h = m // 60
    m = m % 60
    return f"{h} h {m} min"


def estimate_stats(
    paths: list[FlatPath],
    params: CutParams,
    gcode_line_count: int = 0,
) -> GCodeStats:
    """Stima lunghezze e tempi dai percorsi ordinati e dai parametri."""
    n = len(paths)
    cut_len = 0.0
    travel_len = 0.0

    if n == 0:
        return GCodeStats(n_paths=0, n_passes=params.passes)

    def _seg_len(a, b) -> float:
        return math.hypot(b[0] - a[0], b[1] - a[1])

    cur = (0.0, 0.0)
    for p in paths:
        # Travel dal punto corrente all'inizio del percorso
        head = p.points[0]
        travel_len += _seg_len(cur, head)
        # Lunghezza taglio
        for i in range(len(p.points) - 1):
            cut_len += _seg_len(p.points[i], p.points[i + 1])
        if p.closed and len(p.points) >= 2:
            cut_len += _seg_len(p.points[-1], p.points[0])
        cur = head if p.closed else p.points[-1]

    feed = max(1.0, params.feed_mm_min)
    travel_feed = params.travel_feed_mm_min or 3000.0

    cut_time = (cut_len * params.passes) / feed * 60.0
    travel_time = (travel_len * params.passes) / travel_feed * 60.0

    return GCodeStats(
        n_paths=n,
        cut_length_mm=cut_len,
        travel_length_mm=travel_len,
        n_gcode_lines=gcode_line_count,
        n_passes=params.passes,
        estimated_cut_seconds=cut_time,
        estimated_travel_seconds=travel_time,
    )