"""Dati per l'anteprima dei percorsi CAM.

L'anteprima è indipendente dalla UI: produce una struttura dati che la view
può disegnare (con QPainter o QGraphicsPathItem).
"""

from __future__ import annotations

from dataclasses import dataclass

from lasercontrolsuite.cam.flatten import FlatPath


@dataclass
class PreviewPath:
    """Percorso di anteprima."""

    order_index: int           # posizione nell'ordine di lavorazione (0-based)
    points: list[tuple[float, float]]
    closed: bool
    entity_id: str


@dataclass
class PreviewScene:
    """Anteprima completa di un lavoro CAM."""

    cut_paths: list[PreviewPath]
    travel_segments: list[tuple[tuple[float, float], tuple[float, float]]]

    def bounds(self) -> tuple[float, float, float, float]:
        xs: list[float] = []
        ys: list[float] = []
        for p in self.cut_paths:
            for x, y in p.points:
                xs.append(x)
                ys.append(y)
        for (a, b) in self.travel_segments:
            xs.extend([a[0], b[0]])
            ys.extend([a[1], b[1]])
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))


def build_preview(
    paths: list[FlatPath],
    start: tuple[float, float] = (0.0, 0.0),
    include_travel: bool = True,
) -> PreviewScene:
    """Costruisce l'anteprima dai percorsi (già ordinati)."""
    cut = [
        PreviewPath(
            order_index=i,
            points=list(p.points),
            closed=p.closed,
            entity_id=p.entity_id,
        )
        for i, p in enumerate(paths)
    ]

    travels: list[tuple[tuple[float, float], tuple[float, float]]] = []
    if include_travel:
        cur = start
        for p in paths:
            head = p.points[0]
            if head != cur:
                travels.append((cur, head))
            cur = p.points[0] if p.closed else p.points[-1]

    return PreviewScene(cut_paths=cut, travel_segments=travels)