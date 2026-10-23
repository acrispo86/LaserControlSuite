"""Statistiche per singolo layer.

Separate da ``cam.stats`` perché il calcolo per-layer ha bisogno dei
parametri del layer (feed, passate) e non solo del percorso.
"""

from __future__ import annotations

from dataclasses import dataclass

from lasercontrolsuite.cam.flatten import FlatPath
from lasercontrolsuite.cam.params import CutParams


@dataclass
class LayerCutStats:
    """Statistiche di lavorazione per un singolo layer."""

    layer_id: str = ""
    layer_name: str = ""
    n_paths: int = 0
    n_passes: int = 1
    cut_length_mm: float = 0.0
    estimated_cut_seconds: float = 0.0
    feed_mm_min: float = 0.0
    power_percent: float = 0.0
    s_value: int = 0
    air_assist: bool = False

    def estimated_cut_time_str(self) -> str:
        s = max(0.0, self.estimated_cut_seconds)
        mm, ss = divmod(int(round(s)), 60)
        hh, mm = divmod(mm, 60)
        if hh:
            return f"{hh}h {mm:02d}m {ss:02d}s"
        if mm:
            return f"{mm}m {ss:02d}s"
        return f"{ss}s"


def compute_layer_stats(
    paths: list[FlatPath],
    params: CutParams,
) -> LayerCutStats:
    """Calcola le statistiche di un layer dai suoi percorsi."""
    total_len = 0.0
    for p in paths:
        pts = p.points
        n = len(pts)
        if n < 2:
            continue
        for i in range(n - 1):
            x1, y1 = pts[i]
            x2, y2 = pts[i + 1]
            total_len += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
        if p.closed:
            x1, y1 = pts[-1]
            x2, y2 = pts[0]
            total_len += ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5

    total_len *= max(1, params.passes)
    feed = max(1.0, float(params.feed_mm_min))
    seconds = total_len / feed * 60.0

    return LayerCutStats(
        layer_id=params.layer_id,
        layer_name=params.layer_name,
        n_paths=len(paths),
        n_passes=max(1, params.passes),
        cut_length_mm=total_len,
        estimated_cut_seconds=seconds,
        feed_mm_min=float(params.feed_mm_min),
        power_percent=float(params.power_percent),
        s_value=params.s_value(),
        air_assist=bool(params.air_assist),
    )